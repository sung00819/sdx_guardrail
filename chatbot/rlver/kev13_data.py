"""새 Kev(13축 · 15축) 학습 데이터 (2026-10-29). Jev 축 + need 확률을 soft target 으로 넣는다 (kev.data.load_records 형식).
JEV_SPEC='1029)jev.md' 면 15축: 14 자살 사고 · 15 실행 의도 판정(jev_dev/1029)jev_si_*, bank 포함)을 같은 key 에 합친다.
배경 점검 318개는 14·15번 판정이 없어 그 두 질문은 빼고 넣는다.

출처 (모두 개발용 · 시뮬, ID 보류·OOD 는 넣지 않음):
  jev_dev/1029)jev13_<source>.jsonl  개발용 데이터 Jev 판정 (jev_dev.py). 13축 + need
  1025)bank_jev_*test*/episodes.jsonl  bank 시뮬 대화 턴의 Jev 판정. 13축만 (need 확률은 저장 안 됨)
  jev_bg/answers.jsonl                 배경 v2 점검 318개 (score_jev.py 의 3인칭 틀). 13축만
고르기: 드문 축(우울·급성 맥락 밖) 하나라도 P ≥ 0.3 이면 rare, 우울·급성만 dep_acute, 나머지 neg. 출처마다 정한 수만큼.
검증 몫: CRADLE 은 대화, bank 는 에피소드 id (네 묶음에 같은 id 가 반복됨), 나머지는 글 단위로 뗀다.

    python chatbot/rlver/kev13_data.py                 # → out/rlver/kev13_train/{train,val}.jsonl
    python chatbot/rlver/kev13_data.py --val 0.05 --seed 0
    JEV_SPEC='1029)jev.md' python chatbot/rlver/kev13_data.py   # → out/rlver/kev15_train/
"""

import argparse
import collections
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
from jev import AXES, NEED_QUESTION, QUESTIONS, window_state  # noqa: E402
from score_jev import messages as bg_messages  # noqa: E402

RL = os.path.join(ROOT, "out", "rlver")
ALL = 10**9
RARE = [a for a in AXES if a not in ("depression", "acute_context")]
# 출처별 {분류: 개수}. 24GB 기준 4B 가 발화당 ~7초라 전체(3만여)는 못 돌려 줄인다
SELECT = {
    "cradle_test": {"rare": ALL, "dep_acute": ALL, "neg": ALL},
    "kaggle": {"rare": 2500, "dep_acute": 1000, "neg": 500},
    "aegis2": {"rare": ALL, "dep_acute": ALL, "neg": 300},
    "other_check": {"rare": ALL, "dep_acute": ALL, "neg": ALL},
    "bank": {"rare": 1000, "dep_acute": 600, "neg": 400},
    "bg": {"rare": ALL, "dep_acute": ALL, "neg": ALL},
}


def cat(probs):
    if any((probs.get(a) or 0) >= 0.3 for a in RARE):
        return "rare"
    if any((probs.get(a) or 0) >= 0.3 for a in ("depression", "acute_context")):
        return "dep_acute"
    return "neg"


def load_rows():
    """→ [{source, key, group, state, probs, need_probs}]"""
    rows = []
    for path in sorted(glob.glob(os.path.join(RL, "jev_dev", "1029)jev13_*.jsonl"))):
        for line in open(path):
            r = json.loads(line)
            group = r["key"].rsplit(":", 1)[0] if r["source"].startswith("cradle") else r["key"]
            rows.append({"source": r["source"], "key": r["key"], "group": group, "state": r["state"],
                         "probs": r["probs"], "need_probs": r["need_probs"]})
    for path in sorted(glob.glob(os.path.join(RL, "1025)bank_jev_*test*", "episodes.jsonl"))):
        run = os.path.basename(os.path.dirname(path))
        for line in open(path):
            e = json.loads(line)
            for i, t in enumerate(e["turns"]):
                if "jev" in t:
                    rows.append({"source": "bank", "key": f"bank:{run}:{e['id']}:{i}", "group": f"bank:{e['id']}",
                                 "state": window_state(t["prompt"]), "probs": t["jev"], "need_probs": None})
    for line in open(os.path.join(RL, "jev_bg", "answers.jsonl")):
        r = json.loads(line)
        rows.append({"source": "bg", "key": f"bg:{r['id']}", "group": f"bg:{r['id']}", "state": None, "probs": r["probs"],
                     "need_probs": None, "bg_id": r["id"]})
    if len(AXES) == 15:
        si = {}
        for path in glob.glob(os.path.join(RL, "jev_dev", "1029)jev_si_*.jsonl")):
            si.update((r["key"], r["probs"]) for r in map(json.loads, open(path)))
        for r in rows:
            if r["source"] != "bg":
                r["probs"] = {**r["probs"], **si[r["key"]]}
    return rows


def bg_states(rows):
    """배경 점검 행의 state 를 score_jev 와 같은 틀로 만든다"""
    import csv
    bg = {r["id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data", "rlver", "backgrounds_v2.csv")))}
    for r in rows:
        if r["source"] == "bg":
            r["state"] = window_state(bg_messages(bg[r["bg_id"]]))


def record(r):
    qs = {}
    for name, q in QUESTIONS.items():
        p = r["probs"].get(name)
        if p is not None:
            qs[name] = {**q, "target": {"false": 1 - float(p), "true": float(p)}, "label": float(p) >= 0.5}
    if r["need_probs"]:
        t = {k: float(v) for k, v in r["need_probs"].items()}
        qs["need"] = {**NEED_QUESTION, "target": t, "label": max(t, key=t.get)}
    return {"state": r["state"], "questions": qs, "_meta": {"key": r["key"], "src_set": r["source"]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--val", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=f"kev{len(AXES)}_train")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    rows = load_rows()
    bg_states(rows)

    by_src = collections.defaultdict(list)
    for r in rows:
        by_src[r["source"]].append(r)
    train, val, counts = [], [], {}
    for src, rs in sorted(by_src.items()):
        groups = sorted({r["group"] for r in rs})
        val_groups = set(rng.sample(groups, max(1, int(len(groups) * args.val))))
        picked = []
        for c, n in SELECT[src].items():
            pool = [r for r in rs if cat(r["probs"]) == c]
            picked += rng.sample(pool, min(len(pool), n))
        for r in picked:
            (val if r["group"] in val_groups else train).append(record(r))
        counts[src] = {"picked": len(picked), **collections.Counter(cat(r["probs"]) for r in picked)}

    rng.shuffle(train)
    out = os.path.join(RL, args.out)
    os.makedirs(out, exist_ok=True)
    for name, recs in (("train", train), ("val", val)):
        with open(os.path.join(out, f"{name}.jsonl"), "w") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for src, c in counts.items():
        print(src, c)
    print(f"train {len(train)} / val {len(val)} → {out}")


if __name__ == "__main__":
    main()
