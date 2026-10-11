"""판정기(Jev / 기본 Kev / 학습한 Kev)를 데이터 구분(개발용 / ID 보류 / OOD)별로 나란히 본다. 저장된 결과만 읽음.

학습한 Kev 는 개발용 데이터의 Jev 답으로 학습했으므로 개발용 수치는 낙관적이다. 일반화는 ID 보류·OOD 로만 본다.
칸: 정답이 있는 데이터는 정밀도 / 감지율 / 특이도, 없는 데이터는 unsafe 비율(오탐 후보). 모두 Jev 와의 세 분류 κ 를 붙인다.

사용법:
    python3 common/judge_split.py --judges kev kev4b_ft1 kev9b_ft1   # → out/judges/split_summary.md
"""

import argparse
import json
import os

from combine import combine
from judge_agree import kappa
from rules import ROOT, SPLIT, load_design
from slide33 import NAMES, SPLIT_KO, cls, gold

DESIGN = "expert11"


def load(path):
    by_key = {}
    for line in open(path):
        if line.strip():
            d = json.loads(line)
            by_key.setdefault(d["key"], {}).update(d)
    return by_key


def cell(rows, pos):
    flag = [cls(r) == "unsafe" for r in rows]
    if not pos:
        return f"unsafe {sum(flag) / len(rows):.1%}"
    g = [pos(r) for r in rows]
    tp = sum(f and x for f, x in zip(flag, g))
    fp = sum(f and not x for f, x in zip(flag, g))
    fn = sum(x and not f for f, x in zip(flag, g))
    tn = len(rows) - tp - fp - fn
    pct = lambda a, b: f"{a / b:.0%}" if b else "-"  # noqa: E731
    return f"{pct(tp, tp + fp)} / {pct(tp, tp + fn)} / {pct(tn, tn + fp)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", nargs="+", default=["kev"])
    args = ap.parse_args()
    version = load_design(DESIGN, "questions").VERSION
    judges = ["jev"] + args.judges
    L = [f"# 판정기 비교 · {DESIGN} ({version}) · 데이터 구분별", "",
         "- 칸: 정답 있는 데이터 = 정밀도 / 감지율 / 특이도 (unsafe 만 양성), 정답 없는 데이터 = unsafe 비율. 괄호 = Jev 와 세 분류 κ.",
         "- 판정 규칙·임계값은 Jev 에 맞춘 그대로. 학습한 Kev(*_ft*)는 개발용 데이터의 Jev 답으로 학습 → 개발용 수치는 낙관적.",
         "- 발화 수는 Jev 기준. 판정기마다 Jev 와 같은 발화로 센다. 채점이 덜 끝난 판정기는 '-'."]
    for split, sources in SPLIT.items():
        L += ["", f"## {SPLIT_KO[split]}", "", "| 데이터 | 발화 | " + " | ".join(judges) + " |", "|---|---|" + "---|" * len(judges)]
        for s in sources:
            paths = {"jev": os.path.join(ROOT, "out", f"{version}_{s}.jsonl")}
            paths.update({j: os.path.join(ROOT, "out", "judges", f"{j}_{version}_{s}.jsonl") for j in args.judges})
            have = {j: load(p) for j, p in paths.items() if os.path.exists(p)}
            if "jev" not in have:
                continue
            keys = sorted(have["jev"])
            comb = {j: {r["key"]: r for r in combine([v[k] for k in keys if k in v], DESIGN)} for j, v in have.items()}
            cells = []
            for j in judges:
                if j not in comb or not set(comb[j]) >= set(keys):  # 아직 채점 안 했거나 덜 끝남
                    cells.append("-")
                    continue
                rows, pos = gold(s, [comb[j][k] for k in keys])
                kp = "" if j == "jev" else f" (κ {kappa([cls(comb['jev'][k]) for k in keys], [cls(comb[j][k]) for k in keys]):.2f})"
                cells.append(cell(rows, pos) + kp)
            L.append(f"| {NAMES.get(s, s)} | {len(keys):,} | " + " | ".join(cells) + " |")
    dst = os.path.join(ROOT, "out", "judges", "split_summary.md")
    open(dst, "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("→", dst)


if __name__ == "__main__":
    main()
