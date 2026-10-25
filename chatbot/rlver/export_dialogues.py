"""bank_jev 대화 → 전문 + 턴별 Jev 판정 + 한국어 번역 md (2026-10-25).

발화마다 원문 아래에 번역을 붙인다. 번역은 시뮬레이터 30B (서버 Qwen), 같은 문장은 한 번만 번역한다 (캐시 jsonl).

    python chatbot/rlver/export_dialogues.py --config "chatbot/rlver/1025)config_84.json" \
        --run 8B "out/rlver/1025)bank_jev_test" --run 30B "out/rlver/1025)bank_jev_test_30b" \
        --out "out/rlver/1025)bank_jev_dialogues.md"
"""

import argparse
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bank import THRESHOLD  # noqa: E402
from check_bank_jev import BG, expected  # noqa: E402
from llm import Chat  # noqa: E402

KO = {"obtain_means": "자살 방법 마련", "suicide_note": "유서 작성", "put_affairs_in_order": "물건 정리", "specific_plan": "구체적 자살 계획",
      "nonsuicidal_self_harm": "자살 의도가 없는 자해", "repeated_self_harm": "반복적 자해", "cannot_stay_safe": "독립적 안전 유지 불가",
      "means_access": "치명적 수단 접근", "method": "자살 방법 고려", "depression": "우울", "acute_context": "급성 맥락",
      "substance_use_disorder": "물질 사용 장애", "psych_history": "정신과 병력"}
PROMPT = """Translate the following {who} message from a mental-health support chat into natural Korean.
Rules:
- Translate the meaning exactly; do not add, drop or soften anything (no extra words, no extra emoji; keep an emoji only if the original has it).
- Keep hesitations ("…"), line breaks, names, places and numbers.
- {register}
Output only the Korean translation.

{text}"""
REGISTER = {"user": "The person speaks casually: use 반말 (e.g. ~어, ~야).",
            "bot": "The chatbot speaks warmly and politely: use 해요체 for every sentence (e.g. ~해요, ~예요, ~할까요?), never 반말.",
            "fact": "This is a neutral description: use plain written Korean (~다)."}


def translate_all(llm, items, cache_path, workers):
    cache = {}
    if os.path.exists(cache_path):
        for l in open(cache_path):
            d = json.loads(l)
            cache[(d["who"], d["en"])] = d["ko"]
    todo = sorted({(w, t) for w, t in items if (w, t) not in cache})
    print(f"번역 {len(set(items))}개 중 남은 {len(todo)}개")

    def one(job):
        who, text = job
        for _ in range(3):
            try:
                ko = llm([{"role": "user", "content": PROMPT.format(who={"user": "person's", "bot": "chatbot's"}.get(who, "background"),
                                                                     register=REGISTER[who], text=text)}]).strip()
                if ko and re.search(r"[가-힣]", ko):
                    return ko
            except Exception:
                continue
        return ""

    with open(cache_path, "a") as f, ThreadPoolExecutor(workers) as ex:
        for (who, text), ko in zip(todo, ex.map(one, todo)):
            cache[(who, text)] = ko
            f.write(json.dumps({"who": who, "en": text, "ko": ko}, ensure_ascii=False) + "\n")
    return cache


def quote(text):
    return "\n".join("> " + l if l.strip() else ">" for l in text.strip().split("\n"))


def episode_md(e, model, bg, tr):
    exp = expected(bg)
    L = [f"## {e['id']} · {model} · {bg['group']} {bg['risk_item']} · {'vanilla' if e['disclosure'] == 'high' else 'challenge'} · "
         f"원하는 방식 {e.get('need')} · 끝 감정 {e['final_emotion']}", "",
         f"- 정답 축: {', '.join(f'{k} ({KO[k]})' for k in sorted(exp)) or '-'}",
         f"- risk_fact: {bg['risk_fact'] or '-'}"]
    if bg["risk_fact"]:
        L.append(f"  - 번역: {tr.get(('fact', bg['risk_fact']), '')}")
    L += [f"- addons: {bg['addons'] or '-'}", ""]
    for i, t in enumerate(e["turns"], 1):
        L += [f"**{i}. User** (감정 {t.get('emotion')})", "", t["user"].strip(), "", quote(tr.get(("user", t["user"].strip()), "")), ""]
        if "bot" not in t:
            break
        j = t.get("jev") or {}
        on = [f"**{KO[k]} {p:.2f}**" for k, p in sorted(j.items(), key=lambda x: -x[1]) if p >= THRESHOLD]
        mid = [f"{KO[k]} {p:.2f}" for k, p in sorted(j.items(), key=lambda x: -x[1]) if 0.3 <= p < THRESHOLD]
        rt = t.get("route") or {}
        mods = ((["위험: " + ", ".join(KO[k] for k in rt["risk"])] if rt.get("risk") else []) + (["정서"] if rt.get("emotional") else [])
                + (["보정: " + ", ".join(KO[k] for k in rt["mods"])] if rt.get("mods") else []) + (["일반"] if rt.get("general") else []))
        L += [f"🔎 Jev 켜짐: {', '.join(on) or '없음'}" + (f" · 애매(0.3–0.7): {', '.join(mid)}" if mid else "") + f" → 모듈: {' + '.join(mods)}", "",
              f"**{i}. Bot**", "", t["bot"].strip(), "", quote(tr.get(("bot", t["bot"].strip()), "")), ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run", nargs=2, action="append", metavar=("NAME", "FOLDER"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=64)
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    llm = Chat({**cfg["simulator"], "temperature": 0.0, "max_tokens": 1500})
    bgs = {r["id"]: r for r in csv.DictReader(open(BG))}
    runs = [(name, [json.loads(l) for l in open(os.path.join(folder, "episodes.jsonl"))]) for name, folder in args.run]
    items = []
    for _, eps in runs:
        for e in eps:
            if bgs[e["id"]]["risk_fact"]:
                items.append(("fact", bgs[e["id"]]["risk_fact"]))
            for t in e["turns"]:
                items.append(("user", t["user"].strip()))
                if "bot" in t:
                    items.append(("bot", t["bot"].strip()))
    tr = translate_all(llm, items, args.out + ".ko_cache.jsonl", args.workers)
    out = ["# bank_jev 대화 전문 + 턴별 Jev 판정 + 번역 (2026-10-25)", "",
           f"test 배경 60 × vanilla/challenge × 챗봇 {', '.join(n for n, _ in runs)}. 발화마다 원문 아래 인용(>)이 한국어 번역 (Qwen3-30B). "
           f"🔎 줄은 그 턴 Jev 13축 중 {THRESHOLD} 이상(켜짐)과 0.3–0.7(애매), 그리고 고른 모듈. 판정은 그 턴까지 사용자 발화 3개 묶음.", ""]
    for name, eps in runs:
        eps.sort(key=lambda e: (bgs[e["id"]]["group"], bgs[e["id"]]["risk_item"], e["id"], e["disclosure"]))
        out += [episode_md(e, name, bgs[e["id"]], tr) for e in eps]
    open(args.out, "w").write("\n".join(out))
    print(f"→ {args.out}  (빈 번역 {sum(1 for v in tr.values() if not v)}개)")


if __name__ == "__main__":
    main()
