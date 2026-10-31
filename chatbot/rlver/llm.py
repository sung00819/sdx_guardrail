"""OpenAI 호환 채팅 클라이언트 (서버 vLLM, OpenRouter).

../sim/llm.py 와 달리 <think> 블록을 지우지 않는다: think-then-say 챗봇은 생각 블록이 학습 샘플이고 형식 보상의 대상이다.
"""

import itertools
import os
import threading
import time

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def read_dotenv(path):
    """KEY=VALUE 줄 읽기 (../../common/jev_client.py 와 같은 규칙, 파이썬 3.8 에서도 돌게 따로 둔다)"""
    env = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                if k.startswith("export "):
                    k = k[len("export "):].strip()
                env[k] = v.strip().strip("'\"")
    return env


def api_key(name):
    if not name:
        return None
    env = {**read_dotenv(os.path.join(ROOT, "..", ".env")), **read_dotenv(os.path.join(ROOT, ".env"))}
    return os.environ.get(name) or env.get(name)


class Chat:
    """cfg: base_url(하나 또는 복제본 목록), model, temperature, max_tokens, api_key_env, disable_thinking"""

    def __init__(self, cfg):
        urls = cfg["base_url"] if isinstance(cfg["base_url"], list) else [cfg["base_url"]]
        self.urls = [u.rstrip("/") + "/chat/completions" for u in urls]
        self._cycle, self._lock = itertools.cycle(self.urls), threading.Lock()
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.7)
        self.max_tokens = cfg.get("max_tokens", 1024)
        self.disable_thinking = cfg.get("disable_thinking", False)
        self.native_think = cfg.get("native_think", False)  # 자체 생각 블록을 think 칸으로 쓴다 (bank 답 형식이 바뀐다)
        self.session = requests.Session()
        key = api_key(cfg.get("api_key_env"))
        if key:
            self.session.headers["Authorization"] = f"Bearer {key}"

    def __call__(self, messages, retries=5, prefill=None, stop=None, max_tokens=None, temperature=None):
        """prefill: 답의 앞부분을 미리 채우고 이어 쓰게 한다 (vLLM continue_final_message). 돌려주는 글에 prefill 을 붙인다.
        stop·max_tokens: 이 호출만 바꾼다 (bank_jev_plan 의 계획 단계)"""
        if prefill:
            messages = messages + [{"role": "assistant", "content": prefill}]
        body = {"model": self.model, "messages": messages, "temperature": self.temperature if temperature is None else temperature,
                "max_tokens": max_tokens or self.max_tokens}
        if stop:
            body["stop"] = stop
        if prefill:
            body.update(continue_final_message=True, add_generation_prompt=False)
        if self.disable_thinking:  # Qwen3 하이브리드: 모델 자체의 생각 모드는 끈다 (think-then-say 는 프롬프트로)
            body["chat_template_kwargs"] = {"enable_thinking": False}
        with self._lock:
            url = next(self._cycle)
        for attempt in range(retries):
            try:
                r = self.session.post(url, json=body, timeout=300)
                if r.status_code == 200:
                    return (prefill or "") + (r.json()["choices"][0]["message"]["content"] or "")
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            except requests.exceptions.RequestException:
                if attempt == retries - 1:
                    raise
            time.sleep(min(2 ** attempt, 20))
        raise RuntimeError("retries exhausted")
