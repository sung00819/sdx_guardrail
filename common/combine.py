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

from rules import ROOT, load_design, respond


def combine(rows, design):
    levels = load_design(design, "levels")
    guard = load_design("base", "guard_rule")
    by_key = defaultdict(dict)
    for r in rows:
        by_key[r["key"]].update({k: v for k, v in r.items() if k not in ("judge", "raw")})
    out = []
    for key, a in by_key.items():
        level, chronic, reasons = levels.judge_level(a)
        response = respond(level, chronic, a)
        if response == "제외(타인)":
            level, chronic, reasons = "제외(타인)", [], ["다른 사람 이야기"]
        out.append({"key": key, "gold": a.get("gold"), "current": a.get("current"), "level": level, "chronic": chronic,
                    "response": response, "reasons": reasons, "v4i_decision": guard.decide_final(a)[0]})
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
