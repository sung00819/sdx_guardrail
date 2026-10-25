"""bank_jev 대화의 턴별 Jev 라우팅 점검 (2026-10-25) → <out>/routing.md

턴마다: 사용자 발화 · 켜진 축 (P ≥ 0.7) · 고른 모듈 · 챗봇 답. 배경의 정답 (risk_item·addons·group) 과 대조:
  잡힘 = 대화 중 한 번이라도 그 축이 켜짐, 첫 턴 = 처음 켜진 턴, 놓침 = 정답인데 끝까지 안 켜짐, 정답 밖 = 정답에 없는데 켜진 축

    python chatbot/rlver/check_bank_jev.py "out/rlver/1025)bank_jev_smoke"
"""

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bank import THRESHOLD  # noqa: E402
from llm import ROOT  # noqa: E402

BG = os.path.join(ROOT, "data", "rlver", "backgrounds_v2.csv")
STYLE = {"high": "vanilla", "low": "challenge"}


def expected(r):
    exp = {r["risk_item"]} if r["risk_item"] else set()
    exp |= set(filter(None, r["addons"].split(";")))
    if r["group"] == "depression":
        exp.add("depression")
    return exp


def cut(t, n=220):
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    args = ap.parse_args()
    bgs = {r["id"]: r for r in csv.DictReader(open(BG))}
    eps = [json.loads(l) for l in open(os.path.join(args.folder, "episodes.jsonl"))]
    eps.sort(key=lambda e: (e["id"], e.get("setting", 0)))
    head = ["# bank_jev 대화 라우팅 점검", "",
            f"대화 {len(eps)}개. 축은 P(예) ≥ {THRESHOLD} 이면 켜짐. 정답 = risk_item ∪ addons (∪ depression 그룹이면 우울).", "",
            "| 배경 | 그룹·정답 | 방식 | 턴 | 잡힘 (첫 턴) | 놓침 | 정답 밖 | 끝 감정 |", "|---|---|---|---|---|---|---|---|"]
    body = []
    miss_total = hit_total = 0
    for e in eps:
        r = bgs[e["id"]]
        exp = expected(r)
        first = {}
        for i, t in enumerate(e["turns"], 1):
            for k, p in (t.get("jev") or {}).items():
                if p >= THRESHOLD and k not in first:
                    first[k] = i
        hit = sorted(k for k in exp if k in first)
        miss = sorted(k for k in exp if k not in first)
        extra = sorted(k for k in first if k not in exp)
        hit_total += len(hit)
        miss_total += len(miss)
        style = STYLE.get(e.get("disclosure"), e.get("disclosure"))
        head.append(f"| {e['id']} | {r['group']}: {', '.join(sorted(exp)) or '-'} | {style} | {len([t for t in e['turns'] if 'bot' in t])} | "
                    f"{', '.join(f'{k} ({first[k]})' for k in hit) or '-'} | {', '.join(miss) or '-'} | "
                    f"{', '.join(f'{k} ({first[k]})' for k in extra) or '-'} | {e['final_emotion']} |")
        body += ["", f"## {e['id']} · {r['group']} {r['risk_item'] or ''} · {style} · need {e.get('need')}", "",
                 f"정답: {', '.join(sorted(exp)) or '-'}  ", f"risk_fact: {cut(r['risk_fact'] or '-', 300)}", ""]
        for i, t in enumerate(e["turns"], 1):
            if "bot" not in t:
                body.append(f"{i}. **User:** {cut(t['user'])}")
                continue
            on = [k for k, p in (t.get("jev") or {}).items() if p >= THRESHOLD]
            rt = t.get("route") or {}
            mods = ["위험 " + "·".join(rt.get("risk", []))] if rt.get("risk") else []
            mods += ["정서"] if rt.get("emotional") else []
            mods += ["보정 " + "·".join(rt.get("mods", []))] if rt.get("mods") else []
            mods += ["일반"] if rt.get("general") else []
            body += [f"{i}. **User:** {cut(t['user'])}", f"   - Jev: {', '.join(on) or '없음'} → {' + '.join(mods)}",
                     f"   - **Bot:** {cut(t['bot'])}"]
    head += ["", f"정답 축 {hit_total + miss_total}개 중 잡힘 {hit_total}, 놓침 {miss_total}."]
    out = os.path.join(args.folder, "routing.md")
    open(out, "w").write("\n".join(head + body) + "\n")
    print("\n".join(head))
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
