"""세 설계가 함께 쓰는 기준값과 도우미.

- 점수 질문: Jev 점수가 k - 0.5 이상이면 k 단계 이상으로 본다 (THRESHOLD_MODE = "score"). 누적 확률 방식도 남겨 둠.
- 예/아니오 질문: '예' 확률 ≥ YES_PROB.
- 선택형 질문: 고른 값의 신뢰도 ≥ CONF.
- 대응 수준: 전문가 검수 자료 슬라이드 8 (급성 수준 × 만성 위험 표지).
"""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGNS = ("base", "base-eval", "expert11")

P_ON = 0.5
YES_PROB = 0.7
CONF = 0.9

# 출력은 영어 코드로 낸다 (챗봇 등 다른 코드가 받는 값). 사람이 읽는 표·문서에는 LABEL_KO 의 한국어 이름을 쓴다.
LEVELS = ["none", "low", "moderate", "high"]
RESPONSES = ["urgent", "assess", "support", "normal", "other"]
EXCLUDED = "other"
LABEL_KO = {
    "none": "신호 없음", "low": "급성 저", "moderate": "급성 중", "high": "급성 고",
    "urgent": "즉시 대응", "assess": "확인과 연계", "support": "지지와 추적",
    "normal": "통상 대응", "other": "제외(타인)",
}
RESPONSE = {  # (급성 수준, 만성 표지 있음) → 대응 수준
    ("high", False): "urgent", ("high", True): "urgent",
    ("moderate", False): "assess", ("moderate", True): "assess",
    ("low", False): "support", ("low", True): "assess",
    ("none", False): "normal", ("none", True): "support",
}


def p_ge(probs, k):
    """점수 질문의 단계별 확률 → k 단계 이상일 확률"""
    return sum(float(v) for lv, v in (probs or {}).items() if int(lv) >= k)


def yes(a, q):
    return (a.get(q) or 0) >= YES_PROB


# 점수 질문의 단계 판정 방식
#   "score"   : Jev 점수(단계별 확률의 가중평균)가 k - 0.5 이상이면 k 단계 이상 (반올림 기준). 2026-10-06 사용자 결정
#   "cumprob" : 누적 확률 P(≥k) ≥ P_ON 이면 k 단계 이상 (이전 방식. CRADLE test 대응 수준 96.7~98.4% 같고,
#               점수 방식이 애매한 발화를 조금 더 높게 본다: 현재 위기 놓침은 줄고 위기 이전 발화 대응은 늘어남)
THRESHOLD_MODE = "score"


def at_least(a, q, k):
    """점수 질문 q 의 답이 k 단계 이상인지"""
    if THRESHOLD_MODE == "score":
        return (a.get(q) or 0) >= k - 0.5
    return p_ge(a.get(f"{q}_probs"), k) >= P_ON


def recent(a, q, k, unknown):
    """시점 질문 q 가 k 단계 이상(그만큼 최근)인지. 경험이 있을 때만 부른다.
    unknown = 시점 불명일 때 볼 단계 (행동·자해 2 = 3~12개월, 사고 4 = 1개월 안: 사용자 결정).
    점수 방식: 0(해당 없음) 확률을 뺀 나머지로 다시 낸 평균 점수 (0 이 섞여 과거 쪽으로 끌리지 않게).
      다만 시점 질문이 '해당 없음' 쪽이면(나머지 < 0.5) 남은 작은 확률로 시점을 정하지 않고 시점 불명으로 본다.
      (예: "Have a good night" 에서 준비 행동 점수 1.07 인데 시점은 98% '해당 없음' → 남은 2% 로 '지금'이 되어 즉시 대응이 됐음)"""
    probs = a.get(f"{q}_probs") or {}
    rest = 1 - float(probs.get("0", 0))
    if THRESHOLD_MODE == "score":
        if rest < 0.5:
            return unknown >= k
        return sum(int(lv) * float(v) for lv, v in probs.items()) / rest >= k - 0.5
    if rest <= 0:
        return False
    return p_ge(probs, k) / rest >= P_ON


def pick_level(hits):
    """가장 높은 기준으로 판정한다 (합산하지 않음). hits = {수준: [근거]}"""
    level = next((lv for lv in reversed(LEVELS) if hits.get(lv)), "none")
    reasons = [r for lv in reversed(LEVELS) for r in hits.get(lv, [])]
    return level, reasons


def upgrade(level, reasons, a):
    """맥락 요인으로 한 단계까지만 상향: 수단 접근(중→고), 급성 위험 맥락(저→중)"""
    if level == "moderate" and yes(a, "means_access"):
        return "high", reasons + ["escalated_means_access"]
    if level == "low" and yes(a, "acute_context"):
        return "moderate", reasons + ["escalated_acute_context"]
    return level, reasons


def respond(level, chronic, a):
    """신호가 있는데 다른 사람 이야기(v4i subject=other, 신뢰도 ≥ CONF)면 제외. 아니면 슬라이드 8 대응 수준"""
    if a.get("subject") == "other" and (a.get("subject_conf") or 0) >= CONF and (level != "none" or chronic):
        return EXCLUDED
    return RESPONSE[(level, bool(chronic))]


def load_design(name, module):
    """설계 폴더(base, base-eval, expert11)의 파일을 모듈로 불러온다. 폴더 이름에 '-'가 있어 import 문을 쓸 수 없다."""
    if name not in DESIGNS:
        raise SystemExit(f"없는 설계: {name}. 가능한 것: {DESIGNS}")
    path = os.path.join(ROOT, name, f"{module}.py")
    spec = importlib.util.spec_from_file_location(f"{name.replace('-', '_')}_{module}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
