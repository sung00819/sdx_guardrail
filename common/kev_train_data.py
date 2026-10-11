"""Jev 판정(개발용 데이터)으로 Kev 학습 데이터를 만든다. 질문마다 Jev 확률을 soft target 으로 넣는다 (kev.data.load_records 형식).

개발용(rules.SPLIT["dev"])만 쓴다. ID 보류·OOD 는 학습에도 검증에도 넣지 않는다 (평가 전용).
검증 몫은 CRADLE 은 대화 단위, 나머지는 발화 단위로 떼어 학습 중 과적합을 본다.

--select: 24GB GPU 한 장에서 9B LoRA 가 발화당 ~10초라 어려운 발화 위주로 줄인다 (2026-10-10).
  CRADLE test 는 기본 Kev 와 Jev 의 슬라이드 33 판정이 갈린 발화 전부 + 나머지 일부,
  나머지 데이터는 Jev 판정(unsafe / middle / safe)별로 정한 수만큼.

사용법:
    python3 common/kev_train_data.py                  # → out/judges/kev_train/{train,val}.jsonl
    python3 common/kev_train_data.py --kaggle 6000    # Kaggle 은 너무 많아 일부만 (기본 6000)
    python3 common/kev_train_data.py --select --out kev_train_sel   # → out/judges/kev_train_sel/
    python3 common/kev_train_data.py --select --preset v2 --val 0 --out kev_train_sel2
"""

import argparse
import json
import os
import random

import data
from combine import combine
from rules import ROOT, SPLIT, load_design
from slide33 import cls

DESIGN = "expert11"
# --select 에서 데이터별로 남길 수. {"other": n} = 기본 Kev 와 판정이 갈린 것 전부 + 나머지 n 개, 아니면 Jev 판정별 개수
ALL = 10**9
PRESETS = {
    "v1": {"cradle_test": {"other": 600}, "aegis2": {"unsafe": ALL, "middle": ALL, "safe": 300},
           "kaggle": {"unsafe": 600, "middle": 100, "safe": 400}, "other_check": {"unsafe": ALL, "middle": ALL, "safe": ALL}},
    # v2 (2026-10-11): OOD(Reddit C-SSRS) 격차 때문에 Reddit 글인 Kaggle 을 늘림 — 판정 갈린 1,814개 전부 + 1,200
    "v2": {"cradle_test": {"other": 600}, "aegis2": {"unsafe": ALL, "middle": ALL, "safe": 300},
           "kaggle": {"other": 1200}, "other_check": {"unsafe": ALL, "middle": ALL, "safe": ALL}},
}
SELECT = PRESETS["v1"]


def select(source, rows, jev, rng):
    """Jev 판정별로 정한 수만큼 고른다. {"other": n} 인 데이터는 기본 Kev 와 판정이 갈린 발화를 전부 넣는다."""
    jcls = {r["key"]: cls(r) for r in combine([jev[r["key"]] for r in rows], DESIGN)}
    if "other" in SELECT[source]:
        kev_path = os.path.join(ROOT, "out", "judges", f"kev_{load_design(DESIGN, 'questions').VERSION}_{source}.jsonl")
        kev = {}
        for line in open(kev_path):
            r = json.loads(line)
            kev.setdefault(r["key"], {}).update(r)
        kcls = {r["key"]: cls(r) for r in combine(list(kev.values()), DESIGN)}
        diff = [r for r in rows if kcls.get(r["key"]) != jcls[r["key"]]]
        rest = [r for r in rows if kcls.get(r["key"]) == jcls[r["key"]]]
        return diff + rng.sample(rest, min(len(rest), SELECT[source]["other"]))
    out = []
    for c, n in SELECT[source].items():
        pool = [r for r in rows if jcls[r["key"]] == c]
        out += rng.sample(pool, min(len(pool), n))
    return out


def target(q, a, name):
    """Jev flatten 답 a 에서 질문 하나의 soft target. 없으면 None"""
    if q["type"] == "noul":
        p = a.get(name)
        return None if p is None else {"false": 1 - float(p), "true": float(p)}
    probs = a.get(f"{name}_probs")
    if not probs:
        return None
    return {str(k): float(v) for k, v in probs.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaggle", type=int, default=6000)
    ap.add_argument("--val", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--preset", default="v1", choices=sorted(PRESETS))
    ap.add_argument("--out", default="kev_train")
    args = ap.parse_args()
    global SELECT
    SELECT = PRESETS[args.preset]
    rng = random.Random(args.seed)
    qmod = load_design(DESIGN, "questions")
    questions = qmod.JUDGES["all"]

    train, val, counts = [], [], {}
    for source in SPLIT["dev"]:
        jev = {}
        for line in open(os.path.join(ROOT, "out", f"{qmod.VERSION}_{source}.jsonl")):
            if line.strip():
                r = json.loads(line)
                jev.setdefault(r["key"], {}).update(r)
        rows = [r for r in data.load(source) if r["key"] in jev]
        if args.select:
            rows = select(source, rows, jev, rng)
        elif source == "kaggle" and len(rows) > args.kaggle:
            rows = rng.sample(rows, args.kaggle)
        groups = sorted({r["key"].rsplit(":", 1)[0] if source.startswith("cradle") else r["key"] for r in rows})
        val_groups = set(rng.sample(groups, max(1, int(len(groups) * args.val))))
        for r in rows:
            a = jev[r["key"]]
            qs = {}
            for name, q in questions.items():
                t = target(q, a, name)
                if t is None:
                    continue
                label = max(t, key=t.get)
                qs[name] = {**q, "target": t, "label": label == "true" if q["type"] == "noul" else
                            (int(label) if q["type"] == "score" else label)}
            rec = {"state": {"context": r["context"], "current": r["current"]}, "questions": qs,
                   "_meta": {"key": r["key"]}}
            group = r["key"].rsplit(":", 1)[0] if source.startswith("cradle") else r["key"]
            (val if group in val_groups else train).append(rec)
        counts[source] = len(rows)

    rng.shuffle(train)
    out = os.path.join(ROOT, "out", "judges", args.out)
    os.makedirs(out, exist_ok=True)
    for name, recs in (("train", train), ("val", val)):
        with open(os.path.join(out, f"{name}.jsonl"), "w") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(counts, f"train {len(train)} / val {len(val)} → {out}")


if __name__ == "__main__":
    main()
