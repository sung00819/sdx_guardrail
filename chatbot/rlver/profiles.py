"""공식 RLVER 프로필(학습 500 · 테스트 100, 중국어)을 받아 영어로 옮긴다 → out/rlver/profiles_{train,test}.jsonl

원본: https://github.com/Tencent/DigitalHuman/tree/main/RLVER/data (MIT). 저장소에는 올리지 않는다.
숨겨진 의도 8개 (논문 표 5) 는 고정 번역, 인물 설명·배경·첫 발화는 시뮬레이터 LLM 으로 번역한다.

    python chatbot/rlver/profiles.py                        # 둘 다
    python chatbot/rlver/profiles.py --split test --limit 5 # 시험
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import ROOT, Chat  # noqa: E402
from prompts import TRANSLATE  # noqa: E402

URL = "https://raw.githubusercontent.com/Tencent/DigitalHuman/main/RLVER/data/{split}_profile.jsonl"
OUT = os.path.join(ROOT, "out", "rlver")
TASKS = {  # 논문 표 5
    "你认为自己在事件中没有任何责任和错误，你想要对方也认同你没有错": "You believe you bear no responsibility or fault in the situation, and you want the other person to agree that you are not at fault.",
    "你希望对方引导你针对事件进行自我反思，收获自我成长": "You hope the other person will guide you to engage in self-reflection regarding the incident and help you achieve personal growth.",
    "你希望对方辩证地分析事件中的问题": "You hope the other person will critically analyze the underlying problems in the incident.",
    "你希望对方深刻共情你的感受，而不是简单的安慰": "You hope the other person will deeply empathize with your feelings, rather than simply offering comfort.",
    "你希望对方用心倾听你的情绪宣泄": "You want the other person to attentively listen to your emotional outpouring.",
    "你想分析事件中其他人物这么做的原因": "You want to analyze the reasons behind the actions of other individuals involved in the incident.",
    "你想获得能真实帮助你解决当下困境的建议": "You hope to receive advice that can genuinely help you overcome your current difficulties.",
    "你希望对方真诚地夸奖你在事件中的具体行为": "You hope the other person will sincerely praise your specific actions in the situation.",
}
CHARACTER = {"负面型": "negative", "被动型": "passive", "回避型": "avoidant"}


def download(split):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"official_{split}_zh.jsonl")
    if not os.path.exists(path):
        r = requests.get(URL.format(split=split), timeout=120)
        r.raise_for_status()
        open(path, "w", encoding="utf-8").write(r.text)
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def convert(row, llm):
    tr = lambda s: llm([{"role": "user", "content": TRANSLATE.format(text=s)}]).strip() if s else s  # noqa: E731
    background = tr(row["scene"])
    if "Hidden intention" not in background:  # 배경 끝의 '####隐藏主题' 가 빠지면 붙인다 (시뮬레이터가 의도를 알아야 한다)
        background += "\n#### Hidden intention:\n* " + TASKS[row["task"]]
    return {"id": row["id"], "persona": tr(row["player"]), "background": background,
            "task": TASKS[row["task"]], "character": CHARACTER.get(row["main_cha"], row["main_cha"]),
            "traits": tr("、".join(row.get("cha_group", []))), "first_talk": tr(row.get("first_talk")),
            "source": "official_zh"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
    ap.add_argument("--split", choices=["train", "test", "both"], default="both")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    llm = Chat({**cfg["simulator"], "temperature": 0.2, "max_tokens": 4000})
    for split in (["train", "test"] if args.split == "both" else [args.split]):
        rows = download(split)[: args.limit or None]
        out = os.path.join(OUT, f"profiles_{split}.jsonl")
        done = {json.loads(l)["id"] for l in open(out)} if os.path.exists(out) else set()
        todo = [r for r in rows if r["id"] not in done]
        print(f"{split}: {len(rows)}개 중 {len(todo)}개 번역")
        with open(out, "a", encoding="utf-8") as f, ThreadPoolExecutor(args.workers) as ex:
            for i, p in enumerate(ex.map(lambda r: convert(r, llm), todo), 1):
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
                f.flush()
                if i % 20 == 0:
                    print(f"  {i}/{len(todo)}")


if __name__ == "__main__":
    main()
