"""세 설계가 함께 쓰는 기준값과 도우미.

- 점수 질문: 누적 확률 P(≥k) ≥ P_ON 이면 그 단계 이상으로 본다.
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

LEVELS = ["신호 없음", "급성 저", "급성 중", "급성 고"]
RESPONSES = ["즉시 대응", "확인과 연계", "지지와 추적", "통상 대응", "제외(타인)"]
RESPONSE = {  # (급성 수준, 만성 표지 있음) → 대응 수준
    ("급성 고", False): "즉시 대응", ("급성 고", True): "즉시 대응",
    ("급성 중", False): "확인과 연계", ("급성 중", True): "확인과 연계",
    ("급성 저", False): "지지와 추적", ("급성 저", True): "확인과 연계",
    ("신호 없음", False): "통상 대응", ("신호 없음", True): "지지와 추적",
}


def p_ge(probs, k):
    """점수 질문의 단계별 확률 → k 단계 이상일 확률"""
    return sum(float(v) for lv, v in (probs or {}).items() if int(lv) >= k)


def yes(a, q):
    return (a.get(q) or 0) >= YES_PROB


def pick_level(hits):
    """가장 높은 기준으로 판정한다 (합산하지 않음). hits = {수준: [근거]}"""
    level = next((lv for lv in reversed(LEVELS) if hits.get(lv)), "신호 없음")
    reasons = [r for lv in reversed(LEVELS) for r in hits.get(lv, [])]
    return level, reasons


def upgrade(level, reasons, a):
    """맥락 요인으로 한 단계까지만 상향: 수단 접근(중→고), 급성 위험 맥락(저→중)"""
    if level == "급성 중" and yes(a, "means_access"):
        return "급성 고", reasons + ["상향: 수단 접근"]
    if level == "급성 저" and yes(a, "acute_context"):
        return "급성 중", reasons + ["상향: 급성 위험 맥락"]
    return level, reasons


def respond(level, chronic, a):
    """신호가 있는데 다른 사람 이야기(v4i subject=other, 신뢰도 ≥ CONF)면 제외. 아니면 슬라이드 8 대응 수준"""
    if a.get("subject") == "other" and (a.get("subject_conf") or 0) >= CONF and (level != "신호 없음" or chronic):
        return "제외(타인)"
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
