"""Jev 와 LLM 판정기들의 턴 판정 일치도 (turn_judge.py 결과, 2026-11-01).

판정기 셋 (GPT-6 Luna · GPT-6.1 Sol · DeepSeek V4 Pro) 모두 Jev 가 그 턴에 받은 입력 그대로 판정했다.
다수결 (셋 중 둘 이상 예) 을 정답으로 Jev 를 채점하고, 쌍마다 Cohen's kappa 를 낸다.

    python chatbot/rlver/judge_agreement.py > "out/rlver/1101)jev_judges_agreement.md"
"""

import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jev import QUESTIONS  # noqa: E402
from turn_gold import MERGE, MNAME, NAME, TH  # noqa: E402

RUNS = ["1025)bank_jev_test_30b", "1025)bank_jev_plan_test_30b_riskplan"]
JUDGES = {"Luna": "turn_judge.jsonl", "Sol": "turn_judge_gpt-6.1-sol.jsonl", "DeepSeek": "turn_judge_deepseek-v4-pro.jsonl"}
OUT = os.path.join(HERE, "..", "..", "out", "rlver")


def load():
    rows = []  # {"run", "group", "Jev": set, 판정기: set}
    for d in RUNS:
        E = {(e["id"], e["setting"]): e for e in map(json.loads, open(f"{OUT}/{d}/episodes.jsonl"))}
        J = {n: {(j["id"], j["setting"], j["turn"]): set(j["yes"]) for j in map(json.loads, open(f"{OUT}/{d}/{f}"))}
             for n, f in JUDGES.items()}
        for k in set.intersection(*(set(v) for v in J.values())):
            e = E[k[:2]]
            grp = "risk" if e["event"] == "severe" else ("depression" if e.get("need") else "normal")
            rows.append({"run": d, "group": grp, "Jev": {a for a, p in e["turns"][k[2]]["jev"].items() if p >= TH},
                         **{n: v[k] for n, v in J.items()}})
    return rows


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    rows = load()
    m = lambda s: {MERGE.get(x, x) for x in s}
    names = ["Jev", *JUDGES]
    pairs = list(itertools.combinations(names, 2))
    axes = list(dict.fromkeys(MERGE.get(k, k) for k in QUESTIONS))
    print("# Jev 와 LLM 판정기 셋의 턴 판정 일치도 (2026-11-01)\n")
    print(f"30B 라우팅 + 30B 계획 칸 (위험 턴만), 네 판정이 다 있는 턴 {len(rows)}개. 판정기 = GPT-6 Luna · GPT-6.1 Sol (프롬프트 캐시) · "
          "DeepSeek V4 Pro (StreamLake, 생각 끔, 캐시). 모두 Jev 가 그 턴에 받은 입력 그대로 (최근 사용자 메시지 3개와 사이 답, Jev 질문 정본 13개).")
    print(f"Jev 는 P ≥ {TH} 면 예. 자살 계획 · 자해는 합친 축. κ = Cohen's kappa (개발계획서 기준 κ ≥ 0.6).\n")
    print("### 다수결 (판정기 셋 중 둘 이상 예) 을 정답으로 본 Jev\n")
    print("| 축 | 다수결 예 턴 | Jev 재현율 | Jev 오탐률 | 오탐 우울/보통/위험 | 정밀도 | 셋 다 예일 때 Jev 재현율 | 셋 다 아니오일 때 Jev 오탐 |")
    print("|---|---|---|---|---|---|---|---|")
    for ax in axes:
        vote = [sum(ax in m(r[n]) for n in JUDGES) for r in rows]
        jv = [ax in m(r["Jev"]) for r in rows]
        pos = [j for j, v in zip(jv, vote) if v >= 2]
        neg = [(j, r["group"]) for j, v, r in zip(jv, vote, rows) if v < 2]
        fp = [g for j, g in neg if j]
        all3 = [j for j, v in zip(jv, vote) if v == 3]
        none = [j for j, v in zip(jv, vote) if v == 0]
        pct = lambda a, b: f"{a / b:.0%}" if b else "-"
        g = {k: fp.count(k) for k in ("depression", "normal", "risk")}
        print(f"| {MNAME.get(ax) or NAME[ax]} | {len(pos)} | {pct(sum(pos), len(pos))} | {pct(len(fp), len(neg))} ({len(fp)}) | "
              f"{g['depression']}/{g['normal']}/{g['risk']} | {pct(sum(pos), sum(pos) + len(fp))} | {pct(sum(all3), len(all3))} ({len(all3)}) | {sum(none)} ({pct(sum(none), len(none))}) |")
    print("\n### 쌍마다 κ\n")
    print("| 축 | 예 턴 수 " + " / ".join(names) + " | " + " | ".join(f"{a}–{b}" for a, b in pairs) + " |")
    print("|---|---|" + "---|" * len(pairs))
    for ax in axes:
        v = {n: [ax in m(r[n]) for r in rows] for n in names}
        print(f"| {MNAME.get(ax) or NAME[ax]} | " + " / ".join(str(sum(v[n])) for n in names) + " | "
              + " | ".join(f"{kappa(v[a], v[b]):.2f}" for a, b in pairs) + " |")


if __name__ == "__main__":
    main()
