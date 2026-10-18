"""배경 표 정리: backgrounds_750.csv → out/rlver/backgrounds.csv (배경만, 성격·태도·욕구는 compose.py 가 나중에 조합)

- 남기는 열: split, id, name, age, gender, occupation, city, topic, core_concern, risk_fact, background, disclosure
- slot: split 안 순번 (id 해시 순, overt·subtle 따로 섞음). compose.py 가 욕구를 (slot + combo) mod 4 로 고르므로 split·D 안에서 균등
- disclosure (D, 사용자마다 고정): risk_fact 가 있으면 overt (매우 위험), 없으면 subtle (은은하게 위험)
- 지우는 열: cell, true_codes, means (임상 축), stance, reveal_level, effort, hidden_need (나중에 조합),
  opening_message (이전 대화 노력·태도로 쓴 것. 첫 발화는 RLVER 처럼 시뮬레이터가 연다)
- 빼는 행: O (다른 사람 이야기)
- --clean: core_concern·background 에 남은 이전 설정 문장(공개 문턱 "emotion ≥ 60 이면 말한다", 이전 욕구
  "그냥 들어주길 원한다", 태도 "다그치면 물러난다")을 LLM 으로 지운다 (행마다 한 번). 없으면 열 정리만 하고 needs_clean 표시

    python chatbot/rlver/backgrounds.py --csv backgrounds_750.csv            # 열 정리만
    python chatbot/rlver/backgrounds.py --csv backgrounds_750.csv --clean    # + 문장 정리
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import ROOT, Chat  # noqa: E402
from prompts import CLEAN_PROMPT  # noqa: E402

OUT = os.path.join(ROOT, "out", "rlver", "backgrounds.csv")
KEEP = ["split", "id", "name", "age", "gender", "occupation", "city", "topic", "core_concern", "risk_fact",
        "background", "disclosure"]
# 이전 설정이 남은 문장 (대충 찾기용, 실제 정리는 LLM)
LEAK = re.compile(r"\b(reveal|emotion (reaches|is at least|>=|≥|of)|feels? understood|strong trust|only after|"
                  r"wants? (someone|to be|the listener|room)|partly wants|left alone|stop press|without trying to fix|"
                  r"not be judged|safe to (say|tell|disclose)|deflect)", re.I)


def read(path):
    csv.field_size_limit(10 ** 9)
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def prune(r):
    out = {k: r.get(k, "") for k in KEEP}
    out["disclosure"] = "overt" if r["risk_fact"].strip() else "subtle"
    out["needs_clean"] = int(bool(LEAK.search(r["core_concern"]) or LEAK.search(r["background"])))
    return out


def clean(r, llm):
    prompt = CLEAN_PROMPT.format(core_concern=r["core_concern"], background=r["background"])
    for _ in range(3):
        text = llm([{"role": "user", "content": prompt}])
        try:
            got = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if got.get("core_concern") and got.get("background"):
                return {**r, "core_concern": got["core_concern"].strip(), "background": got["background"].strip(),
                        "needs_clean": 0}
        except (AttributeError, json.JSONDecodeError):
            pass
    raise ValueError(f"{r['id']}: 정리 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    src = read(args.csv)
    rows = [prune(r) for r in src if r["cell"] != "O"]
    if args.clean:
        llm = Chat({**json.load(open(args.config))["simulator"], "temperature": 0.2, "max_tokens": 3000})
        with ThreadPoolExecutor(args.workers) as ex:
            rows = list(ex.map(lambda r: clean(r, llm), rows))
    for split in ("train", "test"):
        for kind in ("overt", "subtle"):
            sub = sorted((r for r in rows if r["split"] == split and r["disclosure"] == kind),
                         key=lambda r: hashlib.md5(r["id"].encode()).hexdigest())
            for i, r in enumerate(sub):
                r["slot"] = i
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEEP + ["slot", "needs_clean"])
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    print(f"{len(src)} → {n} (O {len(src) - n} 제외) → {args.out}")
    for split in ("train", "test"):
        sub = [r for r in rows if r["split"] == split]
        print(f"  {split} {len(sub)}: overt {sum(r['disclosure'] == 'overt' for r in sub)} · "
              f"subtle {sum(r['disclosure'] == 'subtle' for r in sub)} · 정리 필요 {sum(r['needs_clean'] for r in sub)}")


if __name__ == "__main__":
    main()
