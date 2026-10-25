"""bank_jev 대화에서 정답인데 안 켜진 축을 '시뮬레이터가 말 안 함' / 'Jev 가 놓침' 으로 나눈다 (2026-10-25).

정답 = risk_item ∪ addons (∪ depression 그룹이면 우울). 대화 중 한 번도 P ≥ 0.7 이 안 된 정답 축마다 시뮬레이터 30B 에게
사용자 발화 전체와 그 축의 정의 (1025)jev.md Q/Yes/No) 를 주고, 사용자가 그 내용을 말하거나 분명히 내비쳤는지 묻는다.
  말함  → Jev 가 놓침 (그 턴의 Jev 확률도 적는다)
  안 함 → 시뮬레이터가 말 안 함

    python chatbot/rlver/miss_split.py --config "chatbot/rlver/1025)config_84.json" "out/rlver/1025)bank_jev_test" "out/rlver/1025)bank_jev_test_30b"
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bank import THRESHOLD  # noqa: E402
from check_bank_jev import BG, expected  # noqa: E402
from jev import SPEC  # noqa: E402
from llm import Chat  # noqa: E402

ASK = """Below are the messages a person wrote in a chat (numbered by turn), and the definition of one risk item.

Messages:
{messages}

Item: {key}
Question: {q}
Counts as yes: {yes}
Does not count: {no}

Did the person themselves say this, or clearly convey it (indirect wording counts when the meaning is clear in context), anywhere in these messages?
Answer with JSON only: {{"said": true | false, "turn": <first turn number where it appears, or 0>, "quote": "the person's words, or empty"}}"""


def axis_text(path=SPEC):
    md = open(path).read()
    out = {}
    for m in re.finditer(r"^## \d+\. (\w+) — .+?$(.+?)(?=^## |\Z)", md, re.M | re.S):
        g = {t: re.search(rf"^> \*\*{re.escape(t)}\*\* (.+)$", m.group(2), re.M).group(1).strip() for t in ("Q.", "Yes", "No")}
        out[m.group(1)] = g
    return out


def ask(llm, ep, key, ax):
    msgs = "\n".join(f"{i}. {' '.join(t['user'].split())}" for i, t in enumerate(ep["turns"], 1))
    prompt = ASK.format(messages=msgs, key=key, q=ax["Q."], yes=ax["Yes"], no=ax["No"])
    for _ in range(3):
        try:
            return json.loads(re.search(r"\{.*\}", llm([{"role": "user", "content": prompt}]), re.S).group(0))
        except Exception:
            continue
    return {"said": None, "turn": 0, "quote": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--config", required=True)
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--out", default=None, help="기본: 첫 폴더/../1025)bank_jev_misses.md")
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    llm = Chat({**cfg["simulator"], "temperature": 0.0, "max_tokens": 300})
    axes = axis_text()
    bgs = {r["id"]: r for r in csv.DictReader(open(BG))}
    lines = ["# bank_jev 놓친 축 나누기 (2026-10-25)", "",
             f"정답인데 대화 중 한 번도 P ≥ {THRESHOLD} 가 안 된 축을 30B 로 다시 봤다. 사용자가 그 내용을 말했으면 'Jev 놓침', "
             "아니면 '말 안 함'. Jev 확률은 30B 가 짚은 턴의 창(그 턴까지 사용자 발화 3개)에서 잰 값이다.", ""]
    examples = []
    for f in args.folders:
        eps = [json.loads(l) for l in open(os.path.join(f, "episodes.jsonl"))]
        jobs = []
        for e in eps:
            on = {k for t in e["turns"] for k, p in (t.get("jev") or {}).items() if p >= THRESHOLD}
            for k in sorted(expected(bgs[e["id"]]) - on):
                jobs.append((e, k))
        with ThreadPoolExecutor(args.workers) as ex:
            res = list(ex.map(lambda j: ask(llm, j[0], j[1], axes[j[1]]), jobs))
        tab = defaultdict(lambda: {"high": [0, 0, 0], "low": [0, 0, 0]})  # 놓침 수, 말 안 함, Jev 놓침
        for (e, k), r in zip(jobs, res):
            c = tab[k][e["disclosure"]]
            c[0] += 1
            if r.get("said"):
                c[2] += 1
                n = int(r.get("turn") or 0)
                p = ((e["turns"][n - 1].get("jev") or {}).get(k) if 0 < n <= len(e["turns"]) else None)
                examples.append((os.path.basename(f.rstrip("/")), k, e["id"], e["disclosure"], n, p, r.get("quote", "")))
            else:
                c[1] += 1
        lines += [f"## {os.path.basename(f.rstrip('/'))}", "",
                  "| 축 | vanilla 놓침 | └ 말 안 함 | └ Jev 놓침 | challenge 놓침 | └ 말 안 함 | └ Jev 놓침 |", "|---|---|---|---|---|---|---|"]
        tot = [0] * 6
        for k in axes:
            if k not in tab:
                continue
            h, lo = tab[k]["high"], tab[k]["low"]
            lines.append(f"| {k} | {h[0]} | {h[1]} | {h[2]} | {lo[0]} | {lo[1]} | {lo[2]} |")
            tot = [a + b for a, b in zip(tot, h + lo)]
        lines += [f"| **합** | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | {tot[4]} | {tot[5]} |", ""]
    lines += ["## Jev 가 놓친 예 (사용자가 말했는데 안 켜짐)", "", "| 폴더 | 축 | 배경 | 방식 | 턴 | 그 턴 Jev P | 사용자 말 |", "|---|---|---|---|---|---|---|"]
    for fo, k, i, d, n, p, q in sorted(examples, key=lambda x: (x[1], x[0])):
        lines.append(f"| {fo[-3:] if fo.endswith('30b') else '8B'} | {k} | {i} | {'vanilla' if d == 'high' else 'challenge'} | {n} | "
                     f"{'-' if p is None else f'{p:.2f}'} | {' '.join(q.split())[:160].replace('|', '/')} |")
    out = args.out or os.path.join(os.path.dirname(args.folders[0].rstrip("/")), "1025)bank_jev_misses.md")
    open(out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:60]))
    print(f"\n→ {out}  (Jev 놓침 예 {len(examples)}개)")


if __name__ == "__main__":
    main()
