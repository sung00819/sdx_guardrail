"""세 설계의 대응 수준 개수를 한 표에 나란히 놓는다 (비율 말고 개수, '통상 대응' 포함).
CRADLE 은 정답 라벨 그룹별로, 다른 데이터는 전체 개수만.

사용법 (먼저 common/combine.py 로 세 설계의 combined 파일을 만든다):
    python3 common/compare.py --source cradle_test      # → out/compare_cradle_test.md
"""

import argparse
import json
import os
from collections import Counter, defaultdict

from rules import DESIGNS, RESPONSES, ROOT

SHORT = ["즉시", "확인", "지지", "통상", "제외"]
GROUPS = ["능동적 자살 사고 (현재)", "수동적 자살 사고 (현재)", "자해 (현재)", "자살·자해 (과거)", "경고 신호 (alert)",
          "기타 위기 (폭력·학대 등)", "위기 이전 발화", "위기 이후 발화 (라벨 없음)"]


def cradle_group(rows):
    """CRADLE 라벨 → 그룹. CRADLE 은 위기가 처음 드러난 발화에만 라벨을 붙이므로, 그 뒤 라벨 없는 발화는 '위기 이후'."""
    by_d = defaultdict(list)
    for r in rows:
        by_d[r["gold"]["dialogue"]].append(r)
    for R in by_d.values():
        R.sort(key=lambda r: r["gold"]["turn_id"])
        seen = False
        for r in R:
            labs = r["gold"]["labels"]
            if "confirm_SI_active_ongoing" in labs:
                g = GROUPS[0]
            elif "confirm_SI_passive_ongoing" in labs:
                g = GROUPS[1]
            elif "confirm_SH_ongoing" in labs:
                g = GROUPS[2]
            elif any(x.startswith("confirm_SI") and x.endswith("_past") for x in labs) or "confirm_SH_past" in labs:
                g = GROUPS[3]
            elif any(x.startswith("alert") for x in labs):
                g = GROUPS[4]
            elif labs:
                g = GROUPS[5]
            elif not seen:
                g = GROUPS[6]
            else:
                g = GROUPS[7]
            seen = seen or bool(labs)
            r["group"] = g


def cell(R):
    c = Counter(r["response"] for r in R)
    return " / ".join(str(c[k]) for k in RESPONSES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    args = ap.parse_args()
    designs = {}
    for d in DESIGNS:
        path = os.path.join(ROOT, "out", f"combined_{d}_{args.source}.jsonl")
        if os.path.exists(path):
            designs[d] = [json.loads(l) for l in open(path)]
    if not designs:
        raise SystemExit("combined 파일이 없습니다. common/combine.py 를 먼저 실행하세요.")
    cradle = args.source.startswith("cradle_")
    if cradle:
        for R in designs.values():
            cradle_group(R)
    L = [f"# 설계 비교 · {args.source}", "", f"칸 = {' / '.join(SHORT)} (대응 수준별 개수)", "",
         f"| {'정답 라벨 그룹' if cradle else '데이터'} | 전체 | " + " | ".join(designs) + " |",
         "|---|---|" + "---|" * len(designs)]
    rows_of = [(g, lambda r, g=g: r["group"] == g) for g in GROUPS] if cradle else []
    for g, keep in rows_of + [("**전체**", lambda r: True)]:
        parts = [[r for r in R if keep(r)] for R in designs.values()]
        L.append(f"| {g} | {len(parts[0])} | " + " | ".join(cell(p) for p in parts) + " |")
    dst = os.path.join(ROOT, "out", f"compare_{args.source}.md")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("→", dst)


if __name__ == "__main__":
    main()
