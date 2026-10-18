"""배경 표: 정본은 data/rlver/backgrounds.csv (read). 750개에서 다시 만들면 out/rlver/backgrounds_from750.csv

backgrounds_750.csv → (배경만, 성격·태도·욕구는 compose.py 가 나중에 조합)

- 남기는 열 (10개): split, id, name, age, gender, occupation, topic, core_concern, risk_fact, background
- event (사건) 는 열로 두지 않고 읽을 때 계산한다 (read): risk_fact 가 있으면 severe (심한 사건 + 자살·자해 위험), 없으면 mild (약한 사건, 우울감만)
- mild·severe 를 같은 수로: split 마다 작은 쪽 수만큼 id 해시 순으로 남긴다 (--no_balance 면 전부)
- 페르소나·털어놓는 정도(high/low)·원하는 대응 방식은 compose.py 가 나중에 조합한다
- 지우는 열: cell, true_codes, means (임상 축), stance, effort, hidden_need, reveal_level (나중에 조합), city,
  opening_message (이전 대화 노력·태도로 쓴 것. 첫 발화는 RLVER 처럼 시뮬레이터가 연다)
- 빼는 행: O (다른 사람 이야기), 직장·가게 주제 중 서로 비슷한 것 절반 (--drop_work, 직장 주제가 58% 로 쏠려 있어서)
- --clean: core_concern·background 에 남은 이전 설정 문장(공개 문턱 "emotion ≥ 60 이면 말한다", 이전 욕구
  "그냥 들어주길 원한다", 태도 "다그치면 물러난다")을 LLM 으로 지운다 (남긴 행마다 한 번). mild 는 죽음 소망·자해 언급도 지운다.
  없으면 열 정리만 하고 needs_clean 표시

    python chatbot/rlver/backgrounds.py --csv backgrounds_750.csv            # 열 정리만
    python chatbot/rlver/backgrounds.py --csv backgrounds_750.csv --clean    # + 문장 정리
"""

import argparse
import csv
import hashlib
import math
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import ROOT, Chat  # noqa: E402
from prompts import CLEAN_MILD, CLEAN_PROMPT  # noqa: E402

OUT = os.path.join(ROOT, "data", "rlver", "backgrounds.csv")  # 저장소에 올린 정본 (문장 정리까지 끝난 336개, 사용자 결정 2026-10-18)
REBUILD = os.path.join(ROOT, "out", "rlver", "backgrounds_from750.csv")  # 750개에서 다시 만들 때 (정본을 덮어쓰지 않게)
KEEP = ["split", "id", "name", "age", "gender", "occupation", "topic", "core_concern", "risk_fact", "background"]
# 이전 설정이 남은 문장 (대충 찾기용, 실제 정리는 LLM)
LEAK = re.compile(r"\b(reveal|emotion (reaches|is at least|>=|≥|of)|feels? understood|strong trust|only after|"
                  r"wants? (someone|to be|the listener|room)|partly wants|left alone|stop press|without trying to fix|"
                  r"not be judged|safe to (say|tell|disclose)|deflect)", re.I)
DEATH = re.compile(r"\b(die|dying|dead|death|suicid\w*|self-harm|hurt (him|her)self|disappear|stop existing|not wake up)", re.I)


WORK = re.compile(r"laid off|layoff|fired|resign|retire|manager|supervisor|boss|coworker|shift|job|work|office|client|order|"
                  r"shipment|deadline|report|shop|store|customer|delivery|warehouse|plant|team", re.I)
STOP = set("the a an and of to in on at for with her his she he they their was is it that this by from as be been but "
           "not or had has have after before about into while".split())


def drop_similar_work(rows, frac):
    """직장 주제 행 중 frac 만큼, 남은 것들과 가장 비슷한 행부터 뺀다 (단어 빈도 코사인)"""
    work = [r for r in rows if WORK.search(r["topic"])]
    vec = {}
    for r in work:
        c = Counter(w for w in re.findall(r"[a-z]+", (r["topic"] + " " + r["core_concern"] + " " + r["background"]).lower())
                    if w not in STOP and len(w) > 2)
        vec[r["id"]] = (c, math.sqrt(sum(v * v for v in c.values())))
    ids = [r["id"] for r in work]
    sim = {i: {j: sum(n * vec[j][0][k] for k, n in vec[i][0].items()) / (vec[i][1] * vec[j][1]) for j in ids if j != i}
           for i in ids}
    keep, drop = set(ids), set()
    while len(drop) < int(len(ids) * frac):
        i = max(keep, key=lambda i: max(sim[i][j] for j in keep if j != i))
        keep.discard(i)
        drop.add(i)
    print(f"직장 주제 {len(work)} 중 비슷한 {len(drop)} 제외")
    return [r for r in rows if r["id"] not in drop]


def fix_id(s):
    """Numbers·Excel 이 숫자처럼 보이는 id 를 바꾼 것 되돌리기: '44678179.0' → '44678179', '84964800000000.0' → '849648e8'"""
    s = str(s).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if s.isdigit() and len(s) > 8:  # id 는 8자리 16진수. 더 길면 지수 표기('849648e8')가 풀린 것
        mant = s.rstrip("0")
        s = f"{mant}e{len(s) - len(mant)}"
    return s


def read(path):
    """배경 표 읽기 (+ id·나이 복구, event 계산). backgrounds.py 결과든 Numbers 에서 내보낸 csv 든"""
    csv.field_size_limit(10 ** 9)
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    for r in rows:
        r["id"] = fix_id(r["id"])
        if r.get("age"):  # Numbers 는 나이도 '39.0' 으로 바꾼다
            r["age"] = str(int(float(r["age"])))
        r["event"] = "severe" if (r.get("risk_fact") or "").strip() else "mild"
    return rows


def prune(r):
    out = {k: r.get(k, "") for k in KEEP}
    out["event"] = "severe" if r["risk_fact"].strip() else "mild"
    text = r["core_concern"] + " " + r["background"]
    out["needs_clean"] = int(bool(LEAK.search(text) or (out["event"] == "mild" and DEATH.search(text))))
    return out


def clean(r, llm):
    prompt = CLEAN_PROMPT.format(core_concern=r["core_concern"], background=r["background"],
                                 extra=CLEAN_MILD if r["event"] == "mild" else "")
    for _ in range(3):
        text = llm([{"role": "user", "content": prompt}])
        try:
            got = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if got.get("core_concern") and got.get("background"):
                return {**r, "core_concern": got["core_concern"].strip(), "background": got["background"].strip()}
        except (AttributeError, json.JSONDecodeError):
            pass
    raise ValueError(f"{r['id']}: 정리 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default=REBUILD)
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--no_balance", action="store_true")
    ap.add_argument("--drop_work", type=float, default=0.5, help="직장 주제 중 뺄 비율 (0 이면 안 뺌)")
    args = ap.parse_args()
    src = read(args.csv)
    rows = [prune(r) for r in src if r["cell"] != "O"]
    if args.drop_work:
        rows = drop_similar_work(rows, args.drop_work)
    n_all = len(rows)
    by_cell = {}
    for r in sorted(rows, key=lambda r: hashlib.md5(r["id"].encode()).hexdigest()):
        by_cell.setdefault((r["split"], r["event"]), []).append(r)
    for split in ("train", "test"):
        cells = [v for k, v in by_cell.items() if k[0] == split]
        n = min(len(v) for v in cells)
        for v in cells:
            for i, r in enumerate(v):
                r["slot"] = i
            if not args.no_balance:
                del v[n:]
    rows = [r for v in by_cell.values() for r in v]
    if args.clean:
        llm = Chat({**json.load(open(args.config))["simulator"], "temperature": 0.2, "max_tokens": 3000})
        with ThreadPoolExecutor(args.workers) as ex:
            rows = list(ex.map(lambda r: clean(r, llm), rows))
    rows.sort(key=lambda r: (r["split"] != "train", r["event"], r["slot"]))  # slot 은 순서에만 쓰고 저장하지 않는다
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEEP, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(src)} → O·직장 일부 제외 {n_all} → 4칸 맞춰 {len(rows)} → {args.out}")
    for split in ("train", "test"):
        sub = [r for r in rows if r["split"] == split]
        cells = Counter(r["event"] for r in sub)
        print(f"  {split} {len(sub)}: {dict(sorted(cells.items()))} · 정리 필요 (대충) {sum(r['needs_clean'] for r in sub)}")


if __name__ == "__main__":
    main()
