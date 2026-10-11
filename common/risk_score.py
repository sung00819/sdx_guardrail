"""expert11 Jev 답 → 당장의 위험 점수 (0~1). 회복 챗봇 RL 보상의 '위험 감소' 항에 쓴다.

수단·병력·과거 이력처럼 대화로 바뀌지 않는 것은 빼고, 지금 상태만 본다 (사용자 결정 2026-10-06).
시점이 '지금'(t_*=5)이면 1, '1개월 안'(4)이면 0.5, 그보다 전이면 0 으로 곱한다.
base-eval 은 '지난 1개월' 기준이라 대화 뒤에 점수가 내려갈 수 없어서 expert11 을 쓴다.

  risk = Σ WEIGHTS[k] · component[k]        (component 는 모두 0~1)
"""

# [결정 필요] 가중치는 전문가 확인 전 초안
WEIGHTS = {
    "ideation": 0.25,          # 자살 사고 단계 (0~3) × 현재성
    "intent": 0.25,            # 실행 의도 (0 없음 / 1 약간·양가 / 2 확실) × 현재성
    "plan": 0.10,              # 계획 구체성 (0~3) × 현재성
    "cannot_stay_safe": 0.20,  # 혼자 안전 유지 불가 표명
    "warning_signs": 0.10,     # 간접 경고신호 (절망, 갇힌 느낌, 짐이 됨, 철수)
    "self_harm": 0.10,         # 자해 단계 (1 충동 · 2 행동 · 3 반복·심함) × 현재성
}
NOW, RECENT = 5, 4  # 시점 단계: 5 지금 · 4 1개월 안
RECENT_WEIGHT = 0.5


def expected(probs, top):
    """단계별 확률 → 기댓값 / 최고 단계 (0~1)"""
    probs = probs or {}
    return sum(int(k) * float(v) for k, v in probs.items()) / top


def currentness(time_probs):
    """시점 확률 → 그 신호가 '지금'인 정도. 0(해당 없음)을 뺀 나머지에서 지금 1 · 1개월 안 0.5"""
    time_probs = time_probs or {}
    rest = 1 - float(time_probs.get("0", 0))
    if rest <= 0:
        return 0.0
    return (float(time_probs.get(str(NOW), 0)) + RECENT_WEIGHT * float(time_probs.get(str(RECENT), 0))) / rest


def components(a):
    """a = 발화 하나의 expert11 Jev 답 (flatten 된 dict)"""
    cur_si = currentness(a.get("t_ideation_probs"))
    cur_sh = currentness(a.get("t_self_harm_probs"))
    return {
        "ideation": expected(a.get("suicide_ideation_probs"), 3) * cur_si,
        "intent": expected(a.get("suicide_intent_probs"), 2) * cur_si,
        "plan": expected(a.get("suicide_plan_probs"), 3) * cur_si,
        "cannot_stay_safe": float(a.get("cannot_stay_safe") or 0),
        "warning_signs": float(a.get("warning_signs") or 0),
        "self_harm": expected(a.get("sh_level_probs"), 3) * cur_sh,
    }


def acute_risk(a):
    comp = components(a)
    return sum(WEIGHTS[k] * v for k, v in comp.items()), comp
