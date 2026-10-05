"""가드레일 발동 규칙 (사용자 발화 하나 단위). Jev 채점 결과 한 줄(dict)을 받아 판정을 돌려준다.

판정
  발동          위험 신호가 있고, 다른 사람·과거 이야기로 확실하지 않음
  에스컬레이션  위험이 애매함 → 다른 judge 가 판단
  제외          위험 신호는 있지만 다른 사람 이야기거나 회복된 과거 이야기로 확실함
  미발동        위험 신호 없음

규칙 (점수 기준. 사용자 결정: 누적 확률 대신 점수 사용 가능)
  위험 신호 = 자살 점수 ≥ 1.5 (소극적 이상) 또는 자해 점수 ≥ 1.5 (충동 이상) 또는 C-SSRS 항목 중 하나 ≥ 0.5
  1. 위험 신호 있음
     - P(subject=other) ≥ 0.7                         → 제외(타인)   (v4f 부터 'both' 선택지가 있어 섞인 글은 other 가 아님)
     - P(subject=other) 0.3~0.7                       → 에스컬레이션
     - 해당 축의 P(past_only) ≥ 0.7 이고 시도 아님     → 제외(과거)
       (시도가 있으면 과거형이어도 '시도 직후'일 수 있어 에스컬레이션)
     - 나머지                                          → 발동  (과거인지 애매하면 현재로 본다: 놓치는 쪽이 더 위험)
  2. 위험 신호 없음
     - 자살 P(≥2) 또는 자해 P(≥2) 가 0.1~0.5          → 에스컬레이션 (짧은 암시 글 등)
     - 나머지                                          → 미발동
"""

CSSRS = ["cssrs_method", "cssrs_intent", "cssrs_plan", "cssrs_preparation", "cssrs_attempt"]
SURE, UNSURE = 0.7, 0.3
ESC_LO, ESC_HI = 0.1, 0.5


def p_at_least(probs, k):
    return sum(float(v) for lv, v in probs.items() if int(lv) >= k)


def decide(r):
    si = r["suicide_risk"] >= 1.5
    sh = r["self_harm"] >= 1.5
    cs = any(r[q] >= 0.5 for q in CSSRS)
    if si or sh or cs:
        p_other = float(r["subject_probs"].get("other", 0))
        if p_other >= SURE:
            return "제외(타인)"
        if p_other >= UNSURE:
            return "에스컬레이션"
        # 위험 신호가 나온 축들이 모두 '확실한 과거'일 때만 과거로 제외
        axes = []
        if si or cs:
            axes.append(float(r["si_timeframe_probs"].get("past_only", 0)))
        if sh:
            axes.append(float(r["sh_timeframe_probs"].get("past_only", 0)))
        if min(axes) >= SURE:
            return "에스컬레이션" if r["cssrs_attempt"] >= 0.5 else "제외(과거)"
        return "발동"
    p2 = p_at_least(r["suicide_risk_probs"], 2)
    s2 = p_at_least(r["self_harm_probs"], 2)
    if ESC_LO <= p2 < ESC_HI or ESC_LO <= s2 < ESC_HI:
        return "에스컬레이션"
    return "미발동"


# ---------------------------------------------------------------------------
# 규칙 v2 (2026-10-01 사용자 결정)
#   발동: 자살 점수 ≥ 1.5 또는 자해 점수 ≥ 1.5 이면 무조건 발동
#   제외: 다른 사람 이야기(subject=other)이고 그 신뢰도 ≥ 0.9 일 때만
#   전달: 선택형 = 고른 값의 confidence ≥ 0.9 (other_crisis 는 위기가 있을 때만)
#         예/아니오 = '예' 확률 ≥ 0.7
#   과거: 위험 축이 모두 확실한 과거(신뢰도 ≥ 0.9)면 발동하지 않고 '과거(병렬 전달)'로 정보만 넘긴다.
CONF = 0.9
CHOICE_INFO = ["subject", "si_timeframe", "sh_timeframe", "other_crisis"]
YESNO_INFO = CSSRS + ["sh_severe", "help_seeking"]


# 예/아니오 항목 전달 기준: '예' 확률 ≥ 0.7. 0.85 는 "다리에서 뛰어내렸다"(시도 0.74), "다 준비해 뒀다"(준비 0.81) 같은
# 진짜 신호를 놓쳤고, 0.5~0.7 구간은 대부분 잡음이었다 (out/analysis/yesno_prob_thresholds.txt). 사용자 결정.
YES_PROB = 0.7


def passed_info(r, yes_prob=YES_PROB):
    """선택형은 신뢰도 ≥ 0.9 인 것만, 예/아니오는 '예' 확률 ≥ yes_prob 인 것만 넘긴다."""
    info = {}
    for q in CHOICE_INFO:
        if q in r and (r.get(f"{q}_conf") or 0) >= CONF:
            if q == "other_crisis" and r[q] == "none":  # 기타 위기는 있을 때만 넘긴다
                continue
            info[q] = r[q]
    for q in YESNO_INFO:
        if q in r and r[q] >= yes_prob:
            info[q] = True
    return info


def _sure_past(r, axis):
    return r[f"{axis}_timeframe"] == "past_only" and (r.get(f"{axis}_timeframe_conf") or 0) >= CONF


def decide_v2(r, yes_prob=YES_PROB, use_cssrs=False):
    """반환: (판정, 넘길 정보 dict). 판정은 '발동' / '과거(병렬 전달)' / '제외(타인)' / '미발동'.
    과거(병렬 전달): 위험 점수는 있지만 해당 축이 모두 확실한 과거(신뢰도 ≥ 0.9) → 발동하지 않고 정보만 넘긴다.
    use_cssrs=True: C-SSRS 항목 중 하나라도 '예' 확률 ≥ yes_prob 이면 자살 축 위험으로 본다 (점수가 낮아도)."""
    info = passed_info(r, yes_prob)
    axes = [a for a, q in (("si", "suicide_risk"), ("sh", "self_harm")) if r[q] >= 1.5]
    if use_cssrs and "si" not in axes and any(r[q] >= yes_prob for q in CSSRS):
        axes.append("si")
    if axes:
        if r["subject"] == "other" and (r.get("subject_conf") or 0) >= CONF:
            return "제외(타인)", info
        if all(_sure_past(r, a) for a in axes):
            return "과거(병렬 전달)", info
        return "발동", info
    return "미발동", info


# ---------------------------------------------------------------------------
# 규칙 v3 (최종안, 2026-10-01 사용자 결정. 질문 세트 v4h 기준)
#   v2 + C-SSRS 항목 중 하나라도 '예' 확률 ≥ 0.7 이면 자살 위험으로 봄 (제외·과거 단계는 똑같이 거침)
#      + 먼 단계 갈림인데 미발동이면 '불확실(병렬 전달)': 발동하지 않고 확률과 함께 정보만 넘긴다
#   먼 단계 갈림 = 확률이 가장 높은 두 단계가 2단계 이상 떨어져 있고(0↔2, 0↔3, 1↔3) 두 번째 확률도 ≥ 0.2
#   새 judge 를 넣지 않는 이유: 다른 LLM 은 우리 단계 기준과 다른 기준으로 판단해서 결과가 섞인다 (사용자 의견)
FAR_SECOND = 0.2


def far_split(probs, second=FAR_SECOND):
    ranked = sorted(((float(v), int(k)) for k, v in probs.items()), reverse=True)
    return abs(ranked[0][1] - ranked[1][1]) >= 2 and ranked[1][0] >= second


def decide_v3(r, yes_prob=YES_PROB):
    """반환: (판정, 넘길 정보). 판정 = 발동 / 과거(병렬 전달) / 불확실(병렬 전달) / 제외(타인) / 미발동"""
    decision, info = decide_v2(r, yes_prob, use_cssrs=True)
    if decision == "미발동" and (far_split(r["suicide_risk_probs"]) or far_split(r["self_harm_probs"])):
        info = dict(info, suicide_risk_probs=r["suicide_risk_probs"], self_harm_probs=r["self_harm_probs"])
        return "불확실(병렬 전달)", info
    return decision, info


# ---------------------------------------------------------------------------
# 최종 규칙 decide_final (2026-10-01, 질문 세트 v4i 기준). '불확실' 단계는 없다 (사용자 결정).
#   위험 축:
#     자살 축 = 자살 점수 ≥ 1.5, 또는 C-SSRS 항목 하나라도 '예' 확률 ≥ 0.7,
#               또는 자살 확률이 먼 단계로 갈렸고 P(≥2) ≥ 0.3
#     자해 축 = 자해 점수 ≥ 1.5, 또는 자해 확률이 먼 단계로 갈렸고 P(≥2) ≥ 0.3
#   위험 축이 있으면: 다른 사람 이야기(신뢰도 ≥ 0.9) → 제외(타인)
#                     위험 축이 모두 확실한 과거(신뢰도 ≥ 0.9) → 과거(병렬 전달)
#                     나머지 → 발동
#   위험 축이 없으면 미발동.
#   먼 갈림 기준 P(≥2) ≥ 0.3: v4h 불확실 71건 중 Suicidal 19/44 를 잡고 Non-Suicidal 은 11/27,
#   CRADLE 위기 전 발화는 4건만 늘었다 (out/analysis/far_split_resolution_v4i.txt).
FAR_P2 = 0.3


def _risk_axes(r, yes_prob=YES_PROB):
    axes = []
    si = (r["suicide_risk"] >= 1.5 or any(r[q] >= yes_prob for q in CSSRS)
          or (far_split(r["suicide_risk_probs"]) and p_at_least(r["suicide_risk_probs"], 2) >= FAR_P2))
    sh = (r["self_harm"] >= 1.5
          or (far_split(r["self_harm_probs"]) and p_at_least(r["self_harm_probs"], 2) >= FAR_P2))
    if si:
        axes.append("si")
    if sh:
        axes.append("sh")
    return axes


def decide_final(r, yes_prob=YES_PROB):
    """반환: (판정, 넘길 정보). 판정 = 발동 / 과거(병렬 전달) / 제외(타인) / 미발동"""
    info = passed_info(r, yes_prob)
    axes = _risk_axes(r, yes_prob)
    if not axes:
        return "미발동", info
    if r["subject"] == "other" and (r.get("subject_conf") or 0) >= CONF:
        return "제외(타인)", info
    if all(_sure_past(r, a) for a in axes):
        return "과거(병렬 전달)", info
    return "발동", info


def decide_old(r):
    """비교용: 지금까지 쓰던 규칙 (argmax 시점·subject, C-SSRS 는 current 일 때만)"""
    if r["subject"] != "self":
        return "미발동"
    if r["si_timeframe"] != "past_only" and r["suicide_risk"] >= 1.5:
        return "발동"
    if r["sh_timeframe"] != "past_only" and r["self_harm"] >= 1.5:
        return "발동"
    if r["si_timeframe"] == "current" and any(r[q] >= 0.5 for q in CSSRS):
        return "발동"
    return "미발동"
