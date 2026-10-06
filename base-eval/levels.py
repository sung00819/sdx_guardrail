"""base-eval: 질문 답으로 급성 수준·만성 표지를 정한다 (전문가 자료 슬라이드 7·8).

점수 질문은 Jev 점수가 k - 0.5 이상이면 k 단계 이상 (common/rules.py at_least), 예/아니오는 '예' 확률 ≥ 0.7.
시점은 0(해당 없음) 확률을 뺀 나머지로 다시 낸 평균 점수로 구간을 정한다 (common/rules.py recent).

  급성 고   C-SSRS 사고 ④ 실행 의도 이상(1개월) · 자살 의도 '예' · 자살 행동(준비·중단·저지·시도) 최근 3개월·진행 중
            · 자살 의도가 있는 자해 최근 3개월 · 독립적 안전 유지 불가 표명
  급성 중   사고 ③ 방법 생각(의도 없음) · 계획 '예'(의도 없음) · 자살 행동 3~12개월 전 또는 시점 불명
            · 자해 행동 12개월 이내(시점 불명 포함)
  급성 저   사고 ①② (죽고 싶은 소망, 비특이적 능동적 사고) · 간접 경고신호 · 자해 충동만(행동 없음)
            · 부인 진술 (부인으로 낮추지 않는다)
  상향      급성 중 + 수단 접근 → 고, 급성 저 + 급성 위험 맥락 → 중 (한 단계까지만)
  만성 표지 자살 행동 12개월보다 전 · 자해 12개월보다 전 · 반복·심한 자해 · 만성적 자살 사고 · 정신과 병력
  자해 보완 자해 질문(j3)이 자해를 못 봤는데 v4i 자해 점수 ≥ 2.5 → 급성 중, ≥ 1.5 → 급성 저
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from rules import CONF, YES_PROB, at_least, pick_level, recent, upgrade  # noqa: E402


def time_bin(a, q):
    """시점 질문 → within_3m(진행·3개월) / 3_12m_or_unknown(3~12개월·불명) / over_12m(12개월 전)."""
    if recent(a, q, 3, unknown=2):
        return "within_3m"
    if recent(a, q, 2, unknown=2):
        return "3_12m_or_unknown"
    return "over_12m"


def judge_level(a):
    """a = 한 발화의 Jev 답 (flatten 된 dict). 반환: (급성 수준, 만성 표지 목록, 근거 목록)"""
    j1 = j2 = j3 = a  # 원래 판정기 세 개(j1·j2·j3)의 질문. 한 번에 물어 한 dict 에 있다
    hits = defaultdict(list)  # 수준 → 근거
    chronic = []
    yes = lambda q: (j1.get(q) or 0) >= YES_PROB  # noqa: E731

    # 자살 사고 (C-SSRS ①~⑤, 최근 1개월)
    if at_least(j1, "si_ideation_stage", 4) or yes("cssrs_intent"):
        hits["high"].append("suicidal_ideation_active_intent")
    elif at_least(j1, "si_ideation_stage", 3):
        hits["moderate"].append("suicidal_ideation_method")
    elif at_least(j1, "si_ideation_stage", 1):
        hits["low"].append("suicidal_ideation_passive")
    if yes("cssrs_plan") and not yes("cssrs_intent"):
        hits["moderate"].append("suicidal_ideation_plan")
    if yes("cannot_stay_safe"):
        hits["high"].append("unable_to_stay_safe")
    if yes("warning_signs"):
        hits["low"].append("indirect_warning")
    if yes("denial"):
        hits["low"].append("denies_risk")  # 부인으로 낮추지 않는다: 다른 기준이 더 높으면 그 수준이 남는다

    # 자살 행동 (j2)
    if at_least(j2, "sb_level", 1):
        t = time_bin(j2, "sb_time")
        if t == "within_3m":
            hits["high"].append("suicidal_behavior_within_3m")
        elif t == "over_12m":
            chronic.append("suicidal_behavior_over_12m")
        else:  # 3~12개월, 시점 불명, 또는 시점 확률이 없음
            hits["moderate"].append("suicidal_behavior_3_12m_or_unknown")

    # 자해 (j3)
    if at_least(j3, "sh_level", 2):  # 행동
        t = time_bin(j3, "sh_time")
        suicidal = j3.get("sh_suicidal_intent") == "suicidal" and (j3.get("sh_suicidal_intent_conf") or 0) >= CONF
        if t == "over_12m":
            chronic.append("self_harm_over_12m")
        elif suicidal and t == "within_3m":
            hits["high"].append("self_harm_suicidal_within_3m")
        else:
            hits["moderate"].append("self_harm_within_12m_or_unknown")
        if at_least(j3, "sh_level", 3):
            chronic.append("self_harm_severe")
    elif at_least(j3, "sh_level", 1):
        hits["low"].append("self_harm_urge")
    else:  # j3 가 자해를 못 봤을 때 j1(v4i) 자해 점수로 보완. 확인되지 않은 쪽으로 낮추지 않는다
        if at_least(j1, "self_harm", 3):
            hits["moderate"].append("self_harm_behavior_fallback")
        elif at_least(j1, "self_harm", 2):
            hits["low"].append("self_harm_urge_fallback")

    if yes("si_chronic"):
        chronic.append("suicidal_ideation_chronic")
    if yes("psych_history"):
        chronic.append("psychiatric_history")

    level, reasons = upgrade(*pick_level(hits), a)  # 가장 높은 기준 + 한 단계까지만 상향
    return level, chronic, reasons
