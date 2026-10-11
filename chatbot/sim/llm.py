"""OpenAI 호환 채팅 클라이언트 (서버 vLLM, OpenRouter 모두)."""

import itertools
import json
import os
import re
import threading
import time

import requests


class Chat:
    """base_url 은 주소 하나 또는 여러 개(같은 모델 복제본). 여러 개면 pin() 으로 에피소드마다 하나에 고정한다."""

    def __init__(self, base_url, model, temperature=0.7, max_tokens=800, api_key=None, disable_thinking=False):
        urls = base_url if isinstance(base_url, list) else [base_url]
        self.urls = [u.rstrip("/") + "/chat/completions" for u in urls]
        self.url = self.urls[0]
        self._cycle, self._lock = itertools.cycle(self.urls), threading.Lock()
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.disable_thinking = disable_thinking
        self.session = requests.Session()
        key = api_key or os.environ.get("SIM_API_KEY")
        if key:
            self.session.headers["Authorization"] = f"Bearer {key}"

    def pin(self):
        """복제본 중 하나에 고정한 사본 (같은 세션·설정). 한 에피소드가 같은 서버를 쓰면 prefix 캐시가 산다"""
        with self._lock:
            url = next(self._cycle)
        clone = object.__new__(Chat)
        clone.__dict__.update(self.__dict__)
        clone.url = url
        return clone

    def __call__(self, messages, json_mode=False, retries=4):
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": self.max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.disable_thinking:  # Qwen3 하이브리드 모델: 생각 블록 없이 답만
            body["chat_template_kwargs"] = {"enable_thinking": False}
        down_since = None  # 연결 거부·끊김(SSH 터널 재연결 중)은 시도 횟수와 따로, 최대 10분까지 기다린다
        attempt = 0
        while attempt < retries:
            try:
                r = self.session.post(self.url, json=body, timeout=300)
                down_since = None
                if r.status_code == 200:
                    text = r.json()["choices"][0]["message"]["content"] or ""
                    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
                    return json.loads(text) if json_mode else text
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            except requests.exceptions.ConnectionError:
                down_since = down_since or time.time()
                if time.time() - down_since > 600:
                    raise
                time.sleep(10)
                continue
            except (requests.exceptions.RequestException, json.JSONDecodeError):
                if attempt == retries - 1:
                    raise
            time.sleep(min(2 ** attempt, 20))
            attempt += 1
        raise RuntimeError("retries exhausted")
