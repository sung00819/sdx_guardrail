"""OpenAI 호환 채팅 클라이언트 (서버 vLLM). base_url 이 여러 개면 에피소드마다 하나에 고정한다."""

import itertools
import json
import re
import threading
import time

import requests


class Chat:
    def __init__(self, base_url, model, temperature=0.7, max_tokens=800, disable_thinking=False, merge_system=False):
        urls = base_url if isinstance(base_url, list) else [base_url]
        self.urls = [u.rstrip("/") + "/chat/completions" for u in urls]
        self._cycle, self._lock = itertools.cycle(self.urls), threading.Lock()
        self.url = self.urls[0]
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.disable_thinking = disable_thinking
        self.merge_system = merge_system  # Gemma 처럼 대화 중간 system 을 못 받는 템플릿
        self.session = requests.Session()
        self.session.mount("http://", requests.adapters.HTTPAdapter(pool_maxsize=256))

    def pin(self):
        with self._lock:
            url = next(self._cycle)
        clone = object.__new__(Chat)
        clone.__dict__.update(self.__dict__)
        clone.url = url
        return clone

    @staticmethod
    def _merge(messages):
        """맨 앞이 아닌 system 메시지는 바로 앞 user 메시지 끝에 붙인다 (상태 지시·[guardrail] 블록이 마지막 system 으로 온다)"""
        out = []
        for i, m in enumerate(messages):
            if m["role"] == "system" and i > 0:
                j = max((k for k, x in enumerate(out) if x["role"] == "user"), default=None)
                if j is not None:
                    out[j] = {**out[j], "content": out[j]["content"] + "\n\n" + m["content"]}
                    continue
            out.append(m)
        return out

    def __call__(self, messages, json_mode=False, retries=4):
        if self.merge_system:
            messages = self._merge(messages)
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": self.max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.disable_thinking:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        last, down_since, attempt = None, None, 0
        while attempt < retries:
            try:
                r = self.session.post(self.url, json=body, timeout=300)
                down_since = None
                if r.status_code == 200:
                    text = r.json()["choices"][0]["message"]["content"] or ""
                    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
                    return json.loads(text) if json_mode else text
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.exceptions.ConnectionError as e:
                # 터널 재연결 중: 시도 횟수와 따로 최대 10분 기다린다 (2026-10-08 it003: 끊김 동안 64개 전부 실패)
                down_since = down_since or time.time()
                if time.time() - down_since > 600:
                    raise RuntimeError(f"connection down 10min: {e!r}")
                if len(self.urls) > 1:  # 서버가 여러 대면 다음 서버로 (한 대를 내려도 에피소드가 안 죽게)
                    self.url = self.urls[(self.urls.index(self.url) + 1) % len(self.urls)] if self.url in self.urls else self.urls[0]
                time.sleep(10)
                continue
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                last = repr(e)
            time.sleep(min(2 ** attempt, 20))
            attempt += 1
        raise RuntimeError(f"retries exhausted: {last}")
