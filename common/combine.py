"""Jev 채점 결과에 설계별 판정 규칙(<설계>/levels.py)을 적용해 발화마다 급성 수준·만성 표지·대응 수준을 정한다.
세 설계 모두 v4i 질문을 포함하므로, 어제 최종 발동 규칙(base/guard_rule.py decide_final)의 결과도 함께 남긴다.

사용법:
    python3 common/combine.py --design base-eval --source cradle_test   # → out/combined_base-eval_cradle_test.jsonl
    python3 common/combine.py --design base --source cradle_test --input out/el3c_cradle_test.jsonl
        (base 질문은 base-eval·expert11 질문 안에 그대로 있어서, 그 결과로 base 를 계산할 수 있다)
"""

import argparse
import json
import os
from collections import defaultdict

from rules import EXCLUDED, ROOT, load_design, respond, yes

# 출력 필드 (사용자 결정 2026-10-05: 측정값과 규칙 결과를 나눈다)
#   reasons     측정: 수준을 정한 임상 신호. 상향 코드(escalated_*)는 빼서 upgraded_by 로 옮긴다
#   context     측정: Jev 가 '예'라고 한 맥락 요인. 상향 여부와 상관없이 항상 넣는다 (상향 때만 남기면 수단 정보가 85~97% 빠졌다)
#   upgraded_by 규칙: 맥락 요인으로 한 단계 올렸으면 그 요인, 아니면 null
CONTEXT_QUESTIONS = ("means_access", "acute_context")
UPGRADE_CODE = {"escalated_means_access": "means_access", "escalated_acute_context": "acute_context"}

# base/guard_rule.py decide_final 의 판정 이름 → 영어 코드
V4I_DECISION = {"발동": "alert", "과거(병렬 전달)": "past_info_only", "제외(타인)": "other_person", "미발동": "no_alert"}


def codes(a, levels):
    """발화 하나의 Jev 답(flatten) → 출력 코드. 챗봇 시뮬레이션(chatbot/sim/guardrail.py)도 이 함수를 쓴다."""
    level, chronic, reasons = levels.judge_level(a)
    response = respond(level, chronic, a)
    upgraded_by = next((UPGRADE_CODE[c] for c in reasons if c in UPGRADE_CODE), None)
    reasons = [c for c in reasons if c not in UPGRADE_CODE]
    context = [q for q in CONTEXT_QUESTIONS if yes(a, q)]
    if response == EXCLUDED:  # 다른 사람 이야기: 사용자 본인의 신호·맥락이 아니다
        level, chronic, reasons, context, upgraded_by = EXCLUDED, [], ["other_person"], [], None
    return {"level": level, "response": response, "reasons": reasons, "context": context,
            "upgraded_by": upgraded_by, "chronic": chronic}


def combine(rows, design):
    levels = load_design(design, "levels")
    guard = load_design("base", "guard_rule")
    by_key = defaultdict(dict)
    for r in rows:
        by_key[r["key"]].update({k: v for k, v in r.items() if k not in ("judge", "raw")})
    out = []
    for key, a in by_key.items():
        # v4i 질문이 있는 설계(base, base-eval)만 기존 발동 규칙 결과를 낸다. expert11 은 v4i 를 묻지 않아 null
        v4i = V4I_DECISION[guard.decide_final(a)[0]] if "suicide_risk" in a else None
        out.append({"key": key, "gold": a.get("gold"), "current": a.get("current"), **codes(a, levels),
                    "v4i_decision": v4i})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--input", help="기본: out/<설계 VERSION>_<source>.jsonl")
    args = ap.parse_args()
    version = load_design(args.design, "questions").VERSION
    src = args.input or os.path.join(ROOT, "out", f"{version}_{args.source}.jsonl")
    rows = [json.loads(l) for l in open(src) if l.strip()]
    out = combine(rows, args.design)
    dst = os.path.join(ROOT, "out", f"combined_{args.design}_{args.source}.jsonl")
    with open(dst, "w") as f:  # Jev 결과에서 매번 다시 계산하는 파일이라 덮어써도 원본은 그대로다
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(out)} 발화 → {dst}")


if __name__ == "__main__":
    main()
