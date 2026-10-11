"""Jev 채점 결과에 설계별 판정 규칙(<설계>/levels.py)을 적용해 발화마다 급성 수준·만성 표지·대응 수준을 정한다.

사용법:
    python3 common/combine.py --design expert11 --source cradle_test   # → out/combined_expert11_cradle_test.jsonl
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
    by_key = defaultdict(dict)
    for r in rows:
        by_key[r["key"]].update({k: v for k, v in r.items() if k not in ("judge", "raw")})
    out = []
    for key, a in by_key.items():
        out.append({"key": key, "gold": a.get("gold"), "current": a.get("current"), **codes(a, levels)})
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
