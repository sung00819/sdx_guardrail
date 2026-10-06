"""Jev(TypeSafe, OpenRouter Decisions API) 호출 공통 코드.

API: https://openrouter.ai/docs/api/api-reference/alphadecisions
키: 환경변수 OPENROUTER_API_KEY, 또는 저장소 맨 위의 .env (OPENROUTER_API_KEY=...). .env 는 git 에 올리지 않는다.
"""

import os
import time

import requests

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"  # 재현성을 위해 버전 고정


def read_dotenv(path):
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip().removeprefix("export ").strip()] = v.strip().strip("'\"")
    return env


def api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "..", ".env"), os.path.join(here, "..", "..", ".env")):  # 저장소 맨 위, 그 위
        key = read_dotenv(path).get("OPENROUTER_API_KEY")
        if key:
            return key
    return None


def make_session(workers):
    key = api_key()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY 를 환경변수나 .env 파일에 설정하세요.")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {key}"
    # 기본 연결 풀(10개)보다 동시 요청이 많으면 연결이 버려지므로 workers 만큼 늘린다
    s.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=workers))
    return s


def call_jev(session, state, questions, retries=5):
    body = {"model": MODEL, "state": state, "questions": questions}
    for attempt in range(retries):
        try:
            r = session.post(ENDPOINT, json=body, timeout=60)
        except requests.exceptions.RequestException:  # 연결 끊김·타임아웃도 재시도
            time.sleep(min(2 ** attempt, 30))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) or 520 <= r.status_code <= 529:  # 52x: 중간 프록시 오류
            time.sleep(min(2 ** attempt, 30))
            continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    raise RuntimeError("retries exhausted")


def flatten(answers):
    """answers → {q: 값, q_conf: 신뢰도, q_probs: 확률}. score 는 가중평균 점수, choice 는 고른 값, noul 은 '예' 확률."""
    flat = {}
    for name, a in answers.items():
        kind = a.get("type")
        flat[name] = a.get({"score": "score", "choice": "choice", "noul": "noul"}.get(kind, "score"))
        flat[f"{name}_conf"] = a.get("confidence")
        if "probabilities" in a:
            flat[f"{name}_probs"] = a["probabilities"]
    return flat
