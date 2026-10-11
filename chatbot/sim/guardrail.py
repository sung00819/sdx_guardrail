"""시뮬레이션용 expert11 가드레일: 사용자 발화 → Jev 답 → 출력 코드 + 당장 위험 점수.

판정기를 오픈소스로 바꾸면 judge() 만 바꾸면 된다 (출력 코드가 챗봇 인터페이스).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
from combine import codes  # noqa: E402
from jev_client import call_jev, flatten, make_session  # noqa: E402
from risk_score import acute_risk  # noqa: E402
from rules import load_design  # noqa: E402

DESIGN = "expert11"
_questions = load_design(DESIGN, "questions")
_levels = load_design(DESIGN, "levels")


class Guardrail:
    def __init__(self, workers=8, context_chars=6000):
        self.session = make_session(workers)
        self.context_chars = context_chars
        self.cost = 0.0

    def judge(self, context, current):
        """context: 앞 대화 ("User: ...\\nAssistant: ..."), current: "User: ..." 한 줄"""
        raw = call_jev(self.session, {"context": context[-self.context_chars:], "current": current},
                       _questions.JUDGES["all"])
        self.cost += (raw.get("usage") or {}).get("cost") or 0
        a = flatten(raw.get("answers", {}))
        risk, comp = acute_risk(a)
        return {**codes(a, _levels), "risk": round(risk, 4), "risk_components": {k: round(v, 4) for k, v in comp.items()}}


def chatbot_block(out):
    """챗봇에 주는 [guardrail] 블록 (RESPONSE_GUIDE.md 1절). upgraded_by·risk 는 주지 않는다."""
    lines = ["[guardrail]", f"level: {out['level']}", f"response: {out['response']}"]
    for k in ("reasons", "context", "chronic"):
        lines.append(f"{k}: {', '.join(out[k]) if out[k] else 'none'}")
    return "\n".join(lines)
