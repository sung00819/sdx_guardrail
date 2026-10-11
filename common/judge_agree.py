"""오픈소스 판정기(Kev, CLM)가 Jev 와 얼마나 같은 답을 내는지 본다. 이미 만든 결과 파일만 읽음 (호출 없음).

  1. 질문별 일치: choice·score 는 가장 높은 확률의 답, noul 은 '예'(≥ 0.5) 기준. noul 은 확률 차이 평균도.
  2. 판정 일치: 같은 규칙(combine.codes)을 적용한 급성 수준·대응 수준·슬라이드 33 세 분류. 세 분류는 Cohen κ 도.
  3. 정답 라벨 기준 성능: slide33 와 같은 계산 (CRADLE 은 개발용 데이터라 낙관적일 수 있음).

사용법:
    python3 common/judge_agree.py --source cradle_test               # → out/judges/agree_cradle_test.md
    python3 common/judge_agree.py --source cradle_test --judges kev clm
"""

import argparse
import json
import os
from collections import Counter

from combine import combine
from rules import ROOT, load_design
from slide33 import cls, gold, metrics

DESIGN = "expert11"


def load_raw(path):
    by_key = {}
    for line in open(path):
        if line.strip():
            d = json.loads(line)
            by_key.setdefault(d["key"], {}).update(d)
    return by_key


def top(a, q):
    """질문 q 의 답을 비교용 값 하나로: 확률이 있으면 가장 높은 답, noul 은 '예' 여부."""
    probs = a.get(f"{q}_probs")
    if probs:
        return max(probs, key=probs.get)
    v = a.get(q)
    return None if v is None else v >= 0.5


def kappa(xs, ys):
    n = len(xs)
    po = sum(x == y for x, y in zip(xs, ys)) / n
    cx, cy = Counter(xs), Counter(ys)
    pe = sum(cx[k] * cy[k] for k in cx) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="cradle_test")
    ap.add_argument("--judges", nargs="+", default=["kev", "clm"])
    args = ap.parse_args()
    version = load_design(DESIGN, "questions").VERSION
    questions = list(load_design(DESIGN, "questions").JUDGES["all"])

    ref = load_raw(os.path.join(ROOT, "out", f"{version}_{args.source}.jsonl"))
    runs = {j: load_raw(os.path.join(ROOT, "out", "judges", f"{j}_{version}_{args.source}.jsonl"))
            for j in args.judges if os.path.exists(os.path.join(ROOT, "out", "judges", f"{j}_{version}_{args.source}.jsonl"))}
    keys = sorted(set(ref).intersection(*[set(r) for r in runs.values()]))
    L = [f"# 판정기 일치율 · {args.source} · {DESIGN} ({version})", "",
         f"- 기준 = Jev (typesafe/jev-1.13). 비교 = {', '.join(runs)}. 세 판정기가 모두 답한 발화 {len(keys):,}개만 센다"
         f" (Jev {len(ref):,} / " + " / ".join(f"{j} {len(r):,}" for j, r in runs.items()) + ").",
         "- 판정 규칙·임계값은 Jev 에 맞춰 정한 그대로 (다시 맞추지 않음)."]

    # 1. 질문별
    L += ["", "## 1. 질문별 Jev 와 같은 답 비율", "", "| 질문 | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
    for q in questions:
        cells = []
        for j, R in runs.items():
            pairs = [(top(ref[k], q), top(R[k], q)) for k in keys]
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            s = f"{sum(x == y for x, y in pairs) / len(pairs):.1%}" if pairs else "-"
            if pairs and isinstance(pairs[0][0], bool):  # noul: 확률 차이 평균
                diffs = [abs(ref[k][q] - R[k][q]) for k in keys if ref[k].get(q) is not None and R[k].get(q) is not None]
                s += f" (확률 차 {sum(diffs) / len(diffs):.2f})"
            cells.append(s)
        L.append(f"| {q} | " + " | ".join(cells) + " |")

    # 2. 판정
    combined = {"jev": {r["key"]: r for r in combine([ref[k] for k in keys], DESIGN)}}
    for j, R in runs.items():
        combined[j] = {r["key"]: r for r in combine([R[k] for k in keys], DESIGN)}
    L += ["", "## 2. 판정 일치 (같은 규칙 적용)", "", "| | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
    for name, f in [("급성 수준 (level)", lambda r: r["level"]), ("대응 수준 (response)", lambda r: r["response"]),
                    ("슬라이드 33 세 분류", cls)]:
        cells = []
        for j in runs:
            xs = [f(combined["jev"][k]) for k in keys]
            ys = [f(combined[j][k]) for k in keys]
            cells.append(f"{sum(x == y for x, y in zip(xs, ys)) / len(xs):.1%}" + (f" (κ {kappa(xs, ys):.2f})" if f is cls else ""))
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    for j in runs:
        L += ["", f"슬라이드 33 세 분류 교차표 (행 Jev, 열 {j})", "", "| Jev \\ " + j + " | unsafe | middle | safe | other |", "|---|---|---|---|---|"]
        c = Counter((cls(combined["jev"][k]), cls(combined[j][k])) for k in keys)
        for a in ("unsafe", "middle", "safe", "other"):
            L.append(f"| {a} | " + " | ".join(str(c[(a, b)]) for b in ("unsafe", "middle", "safe", "other")) + " |")

    # 3. 정답 기준
    L += ["", "## 3. 정답 라벨 기준 (unsafe 만 양성)", "",
          "| 판정기 | 정답 양성 / 전체 | 정밀도 | 감지율 | 특이도 | 정확도 | 오탐 / 놓침 |", "|---|---|---|---|---|---|---|"]
    for j, C in combined.items():
        R, pos = gold(args.source, [C[k] for k in keys])
        if pos:
            L.append(f"| {j} | " + " | ".join(metrics(R, pos)) + " |")

    dst = os.path.join(ROOT, "out", "judges", f"agree_{args.source}.md")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("→", dst)


if __name__ == "__main__":
    main()
