"""배경 v2 (318개) 로 Jev 13축 과잉·누락 판정 확인 (2026-10-25). 대화를 돌리기 전 축 정의 점검용.

배경은 3인칭이라 LLM 으로 바꾸지 않고 '내 얘기를 남 얘기처럼 쓴다' 는 틀로 3개 발화 창에 넣는다 (사용자 결정):
  발화 1 = 틀 + background, 발화 2 = core_concern, 발화 3 = risk_fact (있을 때)
실제 말투가 아니라 축 정의가 배경 사실을 제대로 가르는지만 본다.

정답:
  1–9   risk_item (설계값, 배경마다 하나) 로 감지율, risk_item ∪ crisis_items (Luna 라벨) 밖이면 음성
  10    group: depression 예, normal 아니오, risk 는 채점 안 함
  11–13 addons (설계값) 로 감지율, addons ∪ crisis_items 밖이면 음성

    python chatbot/rlver/score_jev.py                 # 돌리기 (이미 한 id 는 건너뜀) + 요약
    python chatbot/rlver/score_jev.py --summary       # 요약만
"""

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bank import MOD_AXES, RISK_AXES, THRESHOLD  # noqa: E402
from jev import AXES, Jev  # noqa: E402
from llm import ROOT  # noqa: E402

BG = os.path.join(ROOT, "data", "rlver", "backgrounds_v2.csv")
OUT = os.path.join(ROOT, "out", "rlver", "jev_bg", "answers.jsonl")
REPORT = os.path.join(HERE, "1025)jev_score.md")
FRAME = "I'll write about my situation as if it's someone else's, but this is all about me. "


def messages(r):
    texts = [FRAME + r["background"], r["core_concern"]] + ([r["risk_fact"]] if r["risk_fact"].strip() else [])
    out = []
    for t in texts:
        out += [{"role": "user", "content": t}, {"role": "assistant", "content": "I'm listening."}]
    return out[:-1]


def gold(r):
    items = set(filter(None, r["crisis_items"].split(";")))
    addons = set(filter(None, r["addons"].split(";")))
    g = {}
    for k in RISK_AXES:
        g[k] = 1 if r["risk_item"] == k else (None if k in items else 0)  # Luna 만 잡은 곁가지는 채점 안 함
    g["depression"] = {"depression": 1, "normal": 0}.get(r["group"])
    for k in MOD_AXES:
        g[k] = 1 if k in addons else (None if k in items else 0)
    return g


def run(rows, workers):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = {json.loads(l)["id"] for l in open(OUT)} if os.path.exists(OUT) else set()
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)}개 중 남은 {len(todo)}개")
    j = Jev(workers=workers)
    with open(OUT, "a") as f, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(j.probs, messages(r)): r for r in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            r = futs[fu]
            try:
                f.write(json.dumps({"id": r["id"], "probs": fu.result()}) + "\n")
                f.flush()
            except Exception as e:  # 다시 돌리면 이어서
                print(f"  실패 {r['id']}: {e}")
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}")
    print(f"Jev 비용 ${j.cost:.3f}")


def summarize(rows):
    by = {r["id"]: r for r in rows}
    ans = [json.loads(l) for l in open(OUT)]
    lines = ["# Jev 13축 × 배경 v2 점검 (2026-10-25)", "",
             f"배경 {len(ans)}개, 3인칭 틀 (score_jev.py). P(예) ≥ {THRESHOLD} 이면 예. "
             "감지율 = 정답 예 중 예, 과잉 = 정답 아니오 중 예. 곁가지(Luna 만 잡은 항목)는 채점에서 뺌.", "",
             "| 축 | 정답 예 | 감지율 | 정답 아니오 | 과잉 | 과잉이 많은 그룹 |", "|---|---|---|---|---|---|"]
    fp_examples = {}
    for k in AXES:
        tp = fn = fp = tn = 0
        fp_group = {}
        for a in ans:
            r = by[a["id"]]
            g = gold(r)[k]
            if g is None:
                continue
            on = a["probs"][k] >= THRESHOLD
            if g:
                tp += on
                fn += not on
            else:
                fp += on
                tn += not on
                if on:
                    key = r["risk_item"] or r["group"]
                    fp_group[key] = fp_group.get(key, 0) + 1
                    fp_examples.setdefault(k, []).append((a["probs"][k], r))
        top = ", ".join(f"{g} {n}" for g, n in sorted(fp_group.items(), key=lambda x: -x[1])[:3])
        rec = f"{tp / (tp + fn):.0%}" if tp + fn else "-"
        fpr = f"{fp / (fp + tn):.0%} ({fp})" if fp + tn else "-"
        lines.append(f"| {k} | {tp + fn} | {rec} | {fp + tn} | {fpr} | {top} |")
    lines += ["", "## 과잉 예시 (축마다 확률 높은 3개)", ""]
    for k, ex in fp_examples.items():
        lines.append(f"**{k}**")
        for p, r in sorted(ex, key=lambda x: -x[0])[:3]:
            fact = (r["risk_fact"] or r["core_concern"])[:220].replace("\n", " ")
            lines.append(f"- {p:.2f} · {r['id']} ({r['risk_item'] or r['group']}; addons {r['addons'] or '-'}) — {fact}")
        lines.append("")
    open(REPORT, "w").write("\n".join(lines))
    print("\n".join(lines[:5 + len(AXES)]))
    print(f"\n→ {REPORT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    rows = list(csv.DictReader(open(BG)))[: args.n or None]
    if not args.summary:
        run(rows, args.workers)
    summarize(rows)


if __name__ == "__main__":
    main()
