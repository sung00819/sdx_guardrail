"""대화 읽기: episodes.jsonl → 사람이 읽기 좋은 markdown (사용자 설정, 턴마다 발화·감정 변화·이유, 챗봇 생각).

    python chatbot/rlver/peek.py out/rlver/peek              # → out/rlver/peek/dialogues.md
    python chatbot/rlver/peek.py out/rlver/peek --no_think   # 챗봇 생각 블록 빼고
"""

import argparse
import json
import os
import re

NEED_KO = {"listen_vent": "쏟아내기 들어주기", "deep_empathy": "깊은 공감", "practical_advice": "실질적 조언"}
EVENT_KO = {"mild": "우울 (약한 사건)", "severe": "매우 위험 (심한 사건)"}
DISC_KO = {"high": "잘 털어놓음", "low": "안 털어놓음"}


def think_of(raw):
    m = re.search(r"<think>(.*?)</think>", raw or "", re.S)
    return m.group(1).strip() if m else ""


def render(e, show_think=True):
    head = (f"## {e['id']} · {EVENT_KO.get(e.get('event'), e.get('event'))} · {DISC_KO.get(e.get('disclosure'), e.get('disclosure'))}"
            f" · 원하는 방식: {NEED_KO.get(e.get('need'), e.get('need'))}\n"
            f"대화 노력 {e.get('effort')} · 끝 **{e['end']}** · 마지막 감정 **{e['final_emotion']}** · 보상 {e['reward']:.2f}"
            + ("" if e.get("format_ok", True) else " · ⚠ 형식 위반") + "\n")
    out = [head]
    for t in e["turns"]:
        if "change" in t:
            why = (t.get("planning") or {}).get("Analyze", "").replace("\n", " ")
            out.append(f"> 감정 {t['change']:+d} → **{t['emotion']}** ({t.get('state', '')}) — {why[:300]}\n")
        out.append(f"**사용자**: {t['user']}\n")
        if t.get("bot") is not None:
            if show_think and think_of(t.get("bot_raw")):
                out.append(f"<details><summary>챗봇 생각</summary>\n\n{think_of(t['bot_raw'])}\n</details>\n")
            out.append(f"**챗봇**: {t['bot']}\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--no_think", action="store_true")
    args = ap.parse_args()
    eps = [json.loads(l) for l in open(os.path.join(args.folder, "episodes.jsonl"))]
    eps.sort(key=lambda e: (e.get("event") or "", e.get("disclosure") or "", e.get("need") or ""))
    path = os.path.join(args.folder, "dialogues.md")
    with open(path, "w") as f:
        f.write("\n\n---\n\n".join(render(e, not args.no_think) for e in eps) + "\n")
    print(f"대화 {len(eps)}개 → {path}")


if __name__ == "__main__":
    main()
