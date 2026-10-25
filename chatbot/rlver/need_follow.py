"""bank_jev 대화에서 챗봇이 원하는 방식을 따라가는지 (2026-10-25). 여러 폴더를 나란히 → 표.

  다시 묻기   정서 지원 턴의 답이 '어떻게 얘기할지·더 얘기할지·다른 걸 원하는지' 를 묻는 비율 (ASK)
  정해진 뒤   Jev 가 방식을 잡은 뒤의 정서 턴에서 다시 묻는 비율
  방식 잡힘   대화 중 Jev 가 방식을 잡은 대화 비율, 잡힌 방식이 사용자 설정 (profile need) 과 같은 비율, 처음 잡힌 턴

    python chatbot/rlver/need_follow.py "old/before_need/1025)bank_jev_test" "out/rlver/1025)bank_jev_test" ...
"""

import argparse
import json
import os
import re
from collections import Counter

ASK = re.compile(r"would you like to (talk|share|sit|vent|explore|think|tell)|do you want to (talk|share|vent|tell)|"
                 r"or (would you|do you) (prefer|want|rather)|if you('d| would) like to (talk|share)|want to talk (more|about)|"
                 r"what would help (most|right now)|tell me more\?", re.I)
NAME = {"listen_vent": "경청", "deep_empathy": "공감", "practical_advice": "조언"}


def pct(n, d):
    return f"{n}/{d} ({n / d:.0%})" if d else "-"


def stats(eps):
    emo = ask = after = after_ask = got = right = 0
    first = []
    conf = Counter()
    for e in eps:
        seen = None
        for i, t in enumerate(e["turns"], 1):
            rt = t.get("route") or {}
            if "bot" not in t or not rt.get("emotional"):
                continue
            emo += 1
            a = bool(ASK.search(t["bot"]))
            ask += a
            if rt.get("need") and seen is None:
                seen = i
            if seen is not None and i > seen:
                after += 1
                after_ask += a
        final = next((t["route"].get("need") for t in reversed(e["turns"]) if (t.get("route") or {}).get("need")), None)
        if final:
            got += 1
            right += final == e.get("need")
            first.append(seen or 0)
            conf[(e.get("need"), final)] += 1
    return emo, ask, after, after_ask, got, right, first, conf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    lines = ["# 원하는 방식 따라가기 (2026-10-25)", "",
             "다시 묻기 = 정서 지원 턴에서 '더 얘기할래 / 어떻게 할까' 를 묻는 답. 정해진 뒤 = Jev 가 방식을 잡은 다음 정서 턴. "
             "방식 일치 = 끝에 잡혀 있던 방식이 사용자 설정과 같음. before_need 는 방식 질문을 넣기 전 (설정 0·3, 공감만).", "",
             "| 폴더 | 대화 | 정서 턴 | 다시 묻기 | 정해진 뒤 다시 묻기 | 방식 잡힌 대화 | 방식 일치 | 처음 잡힌 턴 (중앙) |", "|---|---|---|---|---|---|---|---|"]
    detail = []
    for f in args.folders:
        eps = [json.loads(l) for l in open(os.path.join(f, "episodes.jsonl"))]
        name = f.rstrip("/").replace("old/before_need/", "(이전) ").split("/")[-1]
        for style, sub in (("전체", eps), ("vanilla", [e for e in eps if e["disclosure"] == "high"]), ("challenge", [e for e in eps if e["disclosure"] == "low"])):
            emo, ask, after, after_ask, got, right, first, conf = stats(sub)
            med = sorted(first)[len(first) // 2] if first else "-"
            lines.append(f"| {name if style == '전체' else '└ ' + style} | {len(sub)} | {emo} | {pct(ask, emo)} | {pct(after_ask, after)} | "
                         f"{pct(got, len(sub))} | {pct(right, got)} | {med} |")
            if style == "전체" and conf:
                detail.append(f"- {name}: " + ", ".join(f"설정 {NAME.get(a, a)} → 잡힘 {NAME.get(b, b)} {n}" for (a, b), n in sorted(conf.items())))
    lines += ["", "## 설정 대 잡힌 방식", ""] + detail
    open(args.out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
