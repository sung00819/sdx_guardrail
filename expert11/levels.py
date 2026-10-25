"""expert11: 질문 답으로 급성 수준·만성 표지를 정한다 (전문가 자료 슬라이드 7·8, 2차 검토 의견 R2).

예/아니오는 '예' 확률 ≥ 0.7. 순서가 있는 선택형(실행 의도·자해 의도·빈도 등)은 위험 쪽 선택지 확률의 합 ≥ 0.5 (rules.has).
시점은 0(해당 없음) 확률을 뺀 나머지로 다시 낸 평균 점수로 구간을 정한다 (common/rules.py recent).
  시점 단계: 1 12개월보다 전 / 2 3~12개월 / 3 1~3개월 / 4 1개월 안 (시점 불명 포함, t11f) / 5 지금

  (실행 의도·구체성·준비는 자살 사고나 자살 행동이 함께 있을 때만 인정)
  급성 고   실행 의도(임박 또는 의도 표명) + 사고 1개월 안 · 자살 행동(실제·저지·중단) 3개월 안 · 준비 행동 3개월 안
            · 자살 의도 또는 혼합 의도가 있는 자해 3개월 안 · 안전 유지 불가 표명
  급성 중   구체적 계획(의도 없음) 1개월 안 · 방법 고려(의도 없음) 1개월 안
            · 자살 행동·준비 행동 3~12개월 전 · 자해 행동 12개월 안
  급성 저   비특이적 사고 1개월 안 · 간접 경고신호 · 우울 · 자해 충동만
  상향      없음 (t11f). t11e 는 급성 중 + 수단 접근 → 고, 급성 저 + 급성 위험 맥락 → 중 이었다. 수단 접근·급성 맥락은
            context·findings 에 기록만 하고, upgraded_by 는 항상 null 이다.
  만성 표지 자살 행동·준비 행동 12개월보다 전 · 자해 12개월보다 전 · 반복·장기간·치료가 필요했던 자해
            · 1개월보다 전의 자살 사고 (시간 창이 지나면 삭제하지 않고 옮김)
            · 정신과·물질 사용 병력 · 물질 사용 장애 · 가까운 사람의 자살
  자해 심각도가 낮다는 것으로 위험을 낮추지 않는다 (검토 의견 14). 보호요인은 기록만 하고 수준에 쓰지 않는다.
  대응      슬라이드 8 (common/rules.py RESPONSE)

reasons·chronic 코드 이름은 t11e 와 같다 (챗봇 시뮬레이터·라벨 데이터가 쓴다). t11f 에서 시점 불명이 4 가 되어
`*_3_12m_or_unknown` 은 이제 3~12개월만 뜻한다. 새로 생긴 코드: depressed_mood, substance_use_disorder, suicide_exposure.
측정 항목별 사실(준비 유형, 자해 의도·빈도 등)은 findings() 로 따로 낸다.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from rules import YES_PROB, has, pick_level, recent, top  # noqa: E402

UNKNOWN_TIME = 4  # 시점 불명은 1개월 안 (문서 4번 원문)


def _yes(a, q):
    return (a.get(q) or 0) >= YES_PROB


def judge_level(a):
    """a = 모든 판정기 답을 합친 dict. 반환: (급성 수준, 만성 표지 목록, 근거 목록)"""
    hits = defaultdict(list)
    chronic = []
    yes = lambda q: _yes(a, q)  # noqa: E731
    t = lambda q, k: recent(a, q, k, unknown=UNKNOWN_TIME)  # noqa: E731

    # 실행 의도·구체성·준비는 자살 사고나 자살 행동이 함께 잡혔을 때만 인정한다 (2026-10-07).
    # 앞 대화 없는 한 문장("I will do it tonight", "폭발물을 사고 싶어")에서 무엇을 하겠다는 건지 모르는 채로
    # 자살 의도·준비가 되는 것을 막는다.
    suicidal = yes("suicidal_ideation") or yes("suicide_behavior")

    # 5 사고·구체성·실행 의도: 1개월 창
    if yes("suicidal_ideation"):
        if t("t_ideation", 4):
            if has(a, "suicidal_intent", "imminent", "intent"):  # 검토 의견 21: 계획 유무와 상관없이 실행 의도는 급성 고
                hits["high"].append("suicidal_ideation_active_intent")
            elif yes("ideation_plan"):
                hits["moderate"].append("suicidal_ideation_plan")
            elif yes("ideation_method"):
                hits["moderate"].append("suicidal_ideation_method")
            else:
                hits["low"].append("suicidal_ideation_passive")
        else:
            chronic.append("suicidal_ideation_over_1m")

    # 1·2 자살 행동·준비 행동: 3개월(고) / 12개월(중) 창
    for q, tq, name in (("suicide_behavior", "t_behavior", "suicidal_behavior"), ("preparation", "t_preparation", "preparation")):
        if yes(q) and (suicidal or q == "suicide_behavior"):
            if t(tq, 3):
                hits["high"].append(f"{name}_within_3m")
            elif t(tq, 2):
                hits["moderate"].append(f"{name}_3_12m_or_unknown")
            else:
                chronic.append(f"{name}_over_12m")

    # 3 자해: 12개월 창. 자살 의도나 혼합 의도가 있으면 자살 행동으로 본다 (검토 의견 12: 혼합은 더 높은 쪽으로)
    if yes("self_harm"):
        if has(a, "sh_intent", "suicidal", "ambivalent_or_mixed") and t("t_self_harm", 3):
            hits["high"].append("self_harm_suicidal_within_3m")
        elif t("t_self_harm", 2):
            hits["moderate"].append("self_harm_within_12m_or_unknown")
        else:
            chronic.append("self_harm_over_12m")
        if (has(a, "sh_frequency", "repeated") or has(a, "sh_duration", "sustained")
                or has(a, "sh_severity", "medical_care", "life_threatening")):
            chronic.append("self_harm_severe")
    elif yes("sh_urge"):
        hits["low"].append("self_harm_urge")

    # 6~10 맥락
    if yes("cannot_stay_safe"):
        hits["high"].append("unable_to_stay_safe")
    if yes("warning_signs"):
        hits["low"].append("indirect_warning")
    if yes("depressed_mood"):
        hits["low"].append("depressed_mood")
    for q, code in (("psych_history", "psychiatric_history"), ("substance_use_disorder", "substance_use_disorder"),
                    ("suicide_exposure", "suicide_exposure")):
        if yes(q):
            chronic.append(code)

    level, reasons = pick_level(hits)  # 가장 높은 기준. t11f 는 맥락 요인으로 올리지 않는다 (측정 항목 표에 상향이 없음)
    return level, chronic, reasons


# 측정 항목별 사실: 시점·수준과 상관없이 Jev 가 본 것. (질문, 상위 예/아니오 질문, 코드 접두어, 뺄 선택지)
_FACT_CHOICES = (
    ("attempt_type", "suicide_behavior", "attempt", ("no_attempt",)),
    ("suicidal_intent", "suicidal_ideation", "intent", ("no_intent", "ambivalent_or_unclear")),
    ("ideation_duration", "suicidal_ideation", "ideation", ("no_ideation", "unclear", "brief_or_isolated")),
    ("sh_intent", "self_harm", "self_harm", ("no_self_harm",)),
    ("sh_severity", "self_harm", "self_harm", ("no_self_harm", "unclear")),
    ("sh_frequency", "self_harm", "self_harm", ("no_self_harm", "unclear", "once")),
    ("sh_duration", "self_harm", "self_harm", ("no_self_harm", "unclear", "single_or_short")),
)
# 예/아니오로 나눈 하위 질문: (질문, 상위 질문, 코드). 상위 질문이 '예'일 때만 센다
_FACT_SUB = (
    ("prep_obtain_means", "preparation", "preparation_obtain_means"),
    ("prep_suicide_note", "preparation", "preparation_suicide_note"),
    ("prep_affairs", "preparation", "preparation_put_affairs_in_order"),
    ("ideation_plan", "suicidal_ideation", "ideation_specific_plan"),
    ("ideation_method", "suicidal_ideation", "ideation_method"),
)
_FACT_YES = ("suicide_behavior", "preparation", "self_harm", "sh_urge", "suicidal_ideation", "cannot_stay_safe",
             "means_access", "warning_signs", "depressed_mood", "protective_factors", "acute_context",
             "psych_history", "substance_use_disorder", "suicide_exposure")


def findings(a):
    """측정 항목 표의 사실 코드 목록. 한 발화에 여러 칸이 함께 있으면 모두 낸다 (예: 약을 모으고 유서도 씀 →
    preparation_obtain_means, preparation_suicide_note). 예: self_harm_non_suicidal(자살 의도 없는 자해),
    self_harm_repeated(반복적 자해), ideation_specific_plan(구체적 계획), ideation_method(방법 고려), depressed_mood(우울)"""
    out = [q for q in _FACT_YES if _yes(a, q)]
    out += [code for q, parent, code in _FACT_SUB if _yes(a, parent) and _yes(a, q)]
    if "ideation_specific_plan" in out and "ideation_method" not in out:  # 구체적 계획은 방법 고려를 포함한다
        out.append("ideation_method")
    for q, parent, prefix, skip in _FACT_CHOICES:
        value = top(a, q)
        if _yes(a, parent) and value and value not in skip:
            out.append("intent_stated" if value == "intent" else f"{prefix}_{value}")
    return out
