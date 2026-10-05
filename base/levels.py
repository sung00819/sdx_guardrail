"""base: v4i 답으로 급성 수준·만성 표지를 정한다 ('점수 ≥ 1.5 무조건 발동' 대신 단계로 나눔).

v4i 에는 3·12개월 시점이 없고 current / past_only 만 있으므로 '확실한 과거'(past_only, 신뢰도 ≥ 0.9)는 만성 표지로,
나머지(현재·불확실)는 현재로 본다 (원칙 5: 확인되지 않은 정보로 낮추지 않음).

  급성 고   C-SSRS 의도 '예' · 계획 '예' + 의도 · 준비 '예' · 시도 '예'
  급성 중   C-SSRS 방법 '예'(의도 없음) · 계획 '예'(의도 없음) · 자해 행동 P(≥3) ≥ 0.5
  급성 저   자살 점수 P(≥2) ≥ 0.5 (소극적·적극적 자살 사고) · 자해 충동 P(≥2) ≥ 0.5
            (자살 점수 1 = 부정적 감정은 전문가 기준상 경고신호가 아니라서 신호 없음)
  만성 표지 위 항목이 '확실한 과거' · 심한 자해(sh_severe '예')
  상향      v4i 에는 수단 접근·급성 맥락 질문이 없어 하지 않는다
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from rules import CONF, P_ON, p_ge, pick_level, yes  # noqa: E402


def sure_past(a, axis):
    return a.get(f"{axis}_timeframe") == "past_only" and (a.get(f"{axis}_timeframe_conf") or 0) >= CONF


def judge_level(a):
    """a = 한 발화의 Jev 답 (flatten 된 dict). 반환: (급성 수준, 만성 표지 목록, 근거 목록)"""
    hits = defaultdict(list)
    chronic = []
    si_past, sh_past = sure_past(a, "si"), sure_past(a, "sh")

    def add(level, reason, past):
        if past:
            chronic.append(f"과거: {reason}")
        else:
            hits[level].append(reason)

    if yes(a, "cssrs_intent"):
        add("급성 고", "자살 의도", si_past)
    if yes(a, "cssrs_preparation"):
        add("급성 고", "준비 행동", si_past)
    if yes(a, "cssrs_attempt"):
        add("급성 고", "자살 시도", si_past)
    if yes(a, "cssrs_plan"):
        add("급성 고" if yes(a, "cssrs_intent") else "급성 중", "자살 계획", si_past)
    if yes(a, "cssrs_method") and not yes(a, "cssrs_intent"):
        add("급성 중", "방법 생각", si_past)
    if p_ge(a.get("suicide_risk_probs"), 2) >= P_ON:
        add("급성 저", "자살 사고", si_past)

    shp = a.get("self_harm_probs")
    if p_ge(shp, 3) >= P_ON:
        add("급성 중", "자해 행동", sh_past)
    elif p_ge(shp, 2) >= P_ON:
        add("급성 저", "자해 충동", sh_past)
    if yes(a, "sh_severe"):
        chronic.append("심한·반복 자해")

    level, reasons = pick_level(hits)
    return level, chronic, reasons
