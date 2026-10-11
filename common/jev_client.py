"""Jev(TypeSafe, OpenRouter Decisions API) 호출 공통 코드. 같은 API 를 쓰는 오픈소스 판정기(Kev, CLM)도 여기서 부른다.

API: https://openrouter.ai/docs/api/api-reference/alphadecisions
키: 환경변수 OPENROUTER_API_KEY, 또는 저장소 맨 위의 .env (OPENROUTER_API_KEY=...). .env 는 git 에 올리지 않는다.
Kev·CLM 은 54번 서버에 띄운다 (키 없음). 주소는 환경변수 KEV_URL / CLM_URL 로 바꿀 수 있고, 쉼표로 여러 개 주면 나눠 보낸다.
"""

import os
import random
import time

import requests

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"  # 재현성을 위해 버전 고정

# 판정기 이름 → (주소, model). Kev·CLM 은 TypeSafe /v1/systemone 과 같은 형식
JUDGE_MODELS = {
    "jev": (ENDPOINT, MODEL),
    # Kev = 2026-10-11 확정 판정기: Kev-4B 에 개발용 Jev 답을 학습한 어댑터 (54 ~/yumin_sim/judges/kev/runs/sdx_t11e_4b_v2,
    # 맥 사본 out/judges/models/sdx_t11e_4b_v2, 학습 데이터 kev_train_data.py --select --preset v2). 54 kev_serve.sh 로 띄운다.
    "kev": (os.environ.get("KEV_URL", "http://127.0.0.1:18631/v1/systemone"), "kev-latest"),
    "clm": (os.environ.get("CLM_URL", "http://127.0.0.1:18633/v1/systemone"), "clm-latest"),  # CLM-8B
}


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


def make_session(workers, judge="jev"):
    s = requests.Session()
    s.endpoint, s.model = JUDGE_MODELS[judge]
    if judge == "jev":
        key = api_key()
        if not key:
            raise SystemExit("OPENROUTER_API_KEY 를 환경변수나 .env 파일에 설정하세요.")
        s.headers["Authorization"] = f"Bearer {key}"
    # 기본 연결 풀(10개)보다 동시 요청이 많으면 연결이 버려지므로 workers 만큼 늘린다
    for scheme in ("https://", "http://"):
        s.mount(scheme, requests.adapters.HTTPAdapter(pool_maxsize=workers))
    return s


def call_jev(session, state, questions, retries=5):
    body = {"model": getattr(session, "model", MODEL), "state": state, "questions": questions}
    endpoints = getattr(session, "endpoint", ENDPOINT).split(",")  # 복제본이 여럿이면 무작위로 나눠 보낸다
    for attempt in range(retries):
        try:
            r = session.post(random.choice(endpoints), json=body, timeout=60)
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
