"""expert11: 질문 답으로 급성 수준·만성 표지를 정한다 (전문가 자료 슬라이드 7·8).

점수 질문은 누적 확률 P(≥k) ≥ P_ON(0.5) 이면 그 단계 이상, 예/아니오는 '예' 확률 ≥ 0.7.
시점은 0(해당 없음)을 뺀 나머지에서 최근 쪽부터 누적 확률 ≥ P_ON 인 구간으로 본다.
  시점 단계: 1 12개월보다 전 / 2 3~12개월 (행동·자해는 시점 불명 포함) / 3 1~3개월 / 4 1개월 안 (사고는 시점 불명 포함) / 5 지금

  급성 고   자살 의도(약간 이상) + 사고 1개월 안 · 자살 행동(멈춤·저지 포함) 3개월 안 · 준비 행동 3개월 안
            · 자살 의도 있는 자해 3개월 안 · 안전 유지 불가 표명
  급성 중   방법을 생각하는 사고(의도 없음) 1개월 안 · 계획 있음(의도 없음) 1개월 안
            · 자살 행동·준비 행동 3~12개월 전 또는 시점 불명 · 자해 행동 12개월 안(시점 불명 포함)
  급성 저   죽고 싶은 소망·비특이적 능동적 사고 1개월 안 · 간접 경고신호 · 자해 충동만
  상향      급성 중 + 수단 접근 → 고, 급성 저 + 급성 위험 맥락 → 중 (한 단계까지만)
  만성 표지 자살 행동·준비 행동 12개월보다 전 · 자해 12개월보다 전 또는 반복·심함
            · 1개월보다 전의 자살 사고·의도·계획 (시간 창이 지나면 삭제하지 않고 옮김) · 정신과 병력·위험요인
  제외      신호가 있는데 다른 사람 이야기 (v4i subject=other, 신뢰도 ≥ 0.9)
  대응      슬라이드 8 (common/rules.py RESPONSE)
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from rules import CONF, P_ON, YES_PROB, p_ge, pick_level, upgrade  # noqa: E402


def recent_at_least(probs, k):
    """시점 확률에서 0(해당 없음)을 빼고, 단계 k 이상(그만큼 최근)일 확률 ≥ P_ON 인지"""
    rest = 1 - float((probs or {}).get("0", 0))
    return rest > 0 and p_ge(probs, k) / rest >= P_ON


def judge_level(a):
    """a = 모든 판정기 답을 합친 dict. 반환: (급성 수준, 만성 표지 목록, 근거 목록)"""
    hits = defaultdict(list)
    chronic = []
    on = lambda q, k: p_ge(a.get(f"{q}_probs"), k) >= P_ON  # noqa: E731
    yes = lambda q: (a.get(q) or 0) >= YES_PROB  # noqa: E731
    t = lambda q, k: recent_at_least(a.get(f"{q}_probs"), k)  # noqa: E731

    # 2·3·5 사고·의도·계획: 1개월 창
    thought = on("suicide_ideation", 1) or on("suicide_intent", 1) or on("suicide_plan", 1)
    if thought and t("t_ideation", 4):
        if on("suicide_intent", 1):
            hits["급성 고"].append("자살 의도")
        elif on("suicide_plan", 2):  # 시기·장소까지 구체화
            hits["급성 중"].append("계획 있음(의도 없음)")
        elif on("suicide_ideation", 3) or on("suicide_plan", 1):  # 방법만 = C-SSRS ③
            hits["급성 중"].append("사고: 방법 생각")
        if on("suicide_ideation", 1) and not on("suicide_ideation", 3):
            hits["급성 저"].append("사고: 죽고 싶은 소망·비특이적")
    elif thought:
        chronic.append("1개월보다 전의 자살 사고")

    # 1·4 자살 행동·준비 행동: 3개월(고) / 12개월(중) 창
    for q, tq, name in (("suicide_behavior", "t_behavior", "자살 행동"), ("preparation", "t_preparation", "준비 행동")):
        if on(q, 1):
            if t(tq, 3):
                hits["급성 고"].append(f"{name} 3개월 안")
            elif t(tq, 2):
                hits["급성 중"].append(f"{name} 3~12개월·불명")
            else:
                chronic.append(f"{name} 12개월보다 전")

    # 6 자해: 12개월 창. 자살 의도가 확인되면 자살 행동으로 본다
    if on("sh_level", 2):
        suicidal = a.get("sh_intent") == "suicidal" and (a.get("sh_intent_conf") or 0) >= CONF
        if suicidal and t("t_self_harm", 3):
            hits["급성 고"].append("자살 의도 자해 3개월 안")
        elif t("t_self_harm", 2):
            hits["급성 중"].append("자해 12개월 안·불명")
        else:
            chronic.append("자해 12개월보다 전")
        if on("sh_level", 3):
            chronic.append("반복·심한 자해")
    elif on("sh_level", 1):
        hits["급성 저"].append("자해 충동")

    # 7~11 맥락
    if yes("cannot_stay_safe"):
        hits["급성 고"].append("안전 유지 불가")
    if yes("warning_signs"):
        hits["급성 저"].append("간접 경고신호")
    if yes("psych_history"):
        chronic.append("정신과 병력·위험요인")

    level, reasons = upgrade(*pick_level(hits), a)  # 가장 높은 기준 + 한 단계까지만 상향
    return level, chronic, reasons
