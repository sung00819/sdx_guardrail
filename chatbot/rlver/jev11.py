"""Jev 11축 판정 (2026-10-30, 질문 정본: 1030)jev.md). 15축의 위험 축 11개를 7개로 합친 안.

jev.py (13·15축) 는 건드리지 않고 따로 둔다. 판정 단위·state 는 jev.py 와 같다 (jev.window_state).
need 는 15축과 문구가 같으므로 여기서는 묻지 않는다.

    python chatbot/rlver/jev11.py --show                                       # 묻는 질문 확인
    python chatbot/rlver/jev11.py "I wrote a letter to my daughter." "it's in my drawer"
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
from jev import window_state  # noqa: E402
from jev_client import call_jev, flatten, make_session  # noqa: E402

SPEC = os.path.join(HERE, "1030)jev.md")
THRESHOLD = 0.7
RISK_AXES = ["suicidal_ideation", "suicide_plan", "suicidal_intent", "preparatory_acts",
             "means_access", "self_harm", "cannot_stay_safe"]  # 1–7
SELF_AXES = set(RISK_AXES) - {"self_harm"}  # [1–5, 7번 뒤] 자살 관련 공통 지시
MOD_AXES = ["acute_context", "substance_use_disorder", "psych_history"]
# 옛 15축 → 새 축 (합친 축은 옛 축 P 의 최댓값으로 옮긴다)
FROM15 = {"suicidal_ideation": ["suicidal_ideation"], "suicide_plan": ["method", "specific_plan"],
          "suicidal_intent": ["suicidal_intent"], "preparatory_acts": ["obtain_means", "suicide_note", "put_affairs_in_order"],
          "means_access": ["means_access"], "self_harm": ["nonsuicidal_self_harm", "repeated_self_harm"],
          "cannot_stay_safe": ["cannot_stay_safe"], "depression": ["depression"],
          **{k: [k] for k in MOD_AXES}}


def _common(md, tag):
    m = re.search(r"\*\*\[" + tag + r"\]\*\*\s*\n> (.+)", md)
    assert m, f"1030)jev.md 에 공통 지시 [{tag}] 가 없음"
    return m.group(1).strip()


def load_questions(path=SPEC):
    md = open(path).read()
    pre, post = _common(md, "모든 질문 앞"), _common(md, "모든 질문 뒤")
    self_note = _common(md, r"1–5, 7번 뒤: 자살 관련 질문")
    qs = {}
    for m in re.finditer(r"^## \d+\. (\w+) — .+?$(.+?)(?=^## |\Z)", md, re.M | re.S):
        key, body = m.group(1), m.group(2)
        grab = {t: re.search(rf"^> \*\*{re.escape(t)}\*\* (.+)$", body, re.M) for t in ("Q.", "Yes", "No")}
        assert all(grab.values()), f"{key}: Q./Yes/No 중 빠진 것이 있음"
        tail = post + (" " + self_note if key in SELF_AXES else "")
        qs[key] = {"type": "noul", "instructions": f"{pre} {grab['Q.'].group(1).strip()} {tail}",
                   "criteria": {"true": grab["Yes"].group(1).strip(), "false": grab["No"].group(1).strip()}}
    return qs


QUESTIONS = load_questions()
AXES = list(QUESTIONS)
assert AXES == RISK_AXES + ["depression"] + MOD_AXES, AXES


def judge(session, state):
    """state → ({축: P(예)}, cost)"""
    raw = call_jev(session, state, QUESTIONS)
    a = flatten(raw.get("answers", {}))
    return {k: a.get(k) for k in AXES}, (raw.get("usage") or {}).get("cost") or 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("messages", nargs="*", help="사용자 발화 (순서대로)")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        print(json.dumps(QUESTIONS, ensure_ascii=False, indent=1))
        return
    state = window_state([{"role": "user", "content": m} for m in args.messages])
    probs, cost = judge(make_session(1), state)
    for k, v in probs.items():
        print(f"{'*' if (v or 0) >= THRESHOLD else ' '} {k:24s} {v}")
    print(f"${cost:.4f}")


if __name__ == "__main__":
    main()
