"""gym 고정 평가: 같은 평가 인물(학습에 안 쓴 scenes_test)로 여러 정책(원래 모델 + 학습 어댑터)을 비교한다.

반복마다 다른 인물을 뽑는 학습 롤아웃은 인물 구성 차이가 섞여 회차 비교가 어렵다 (2026-10-08 g1: R −0.19 → +0.10 → −0.05).
→ 셀마다 per_cell 명을 고정하고, 정책마다 같은 인물 × samples 번 대화시킨다.

  python chatbot/gym/train/gym_eval.py --run g1 --iters 2,5,10
  python chatbot/gym/train/gym_eval.py --run g1 --summary      # 표만 다시
"""

import argparse
import json
import os
import random
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import gym_rl  # noqa: E402

CELLS = ["N0", "N1", "L0", "L1", "M", "H", "O"]


def eval_ids(path, per_cell, seed=7):
    if os.path.exists(path):
        return open(path).read().split()
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "out", "scenes_test.jsonl")) if l.strip()]
    rng = random.Random(seed)
    ids = []
    for c in CELLS:
        pool = sorted(r["id"] for r in rows if r["seed"]["cell"] == c)
        ids += rng.sample(pool, min(per_cell, len(pool)))
    open(path, "w").write("\n".join(ids) + "\n")
    return ids


def summarize(out_dir, policies):
    def agg(eps):
        n = max(1, len(eps))
        r = [e["reward"] for e in eps]
        d = lambda k: [x["delta"][k] for x in r if k in x["delta"]]  # noqa: E731
        return {"n": len(eps), "R": sum(x["R"] for x in r) / n, "T1": sum(bool(x["t1"]) for x in r) / n,
                "viol": sum(len(x["violations"]) for x in r) / n, "O": sum(x["O"] for x in r) / n,
                "Q": sum(x["Q"] for x in r) / n,
                **{f"d_{k}": (statistics.mean(d(k)) if d(k) else None) for k in ("emotion", "urge", "safety")}}

    lines = ["| 정책 | n | R | T1 비율 | 위반/대화 | O | Q | Δ감정 | Δ충동(감소+) | Δ안전 |", "|---|---|---|---|---|---|---|---|---|---|"]
    by_cell = {}
    for p in policies:
        path = os.path.join(out_dir, f"episodes_{p}.jsonl")
        if not os.path.exists(path):
            continue
        eps = [json.loads(l) for l in open(path) if l.strip()]
        a = agg(eps)
        f = lambda v: "-" if v is None else f"{v:+.3f}"  # noqa: E731
        lines.append(f"| {p} | {a['n']} | {a['R']:+.3f} | {a['T1']:.0%} | {a['viol']:.2f} | {a['O']:+.3f} | {a['Q']:.3f} | "
                     f"{f(a['d_emotion'])} | {f(a['d_urge'])} | {f(a['d_safety'])} |")
        for c in CELLS:
            ce = [e for e in eps if e["cell"] == c]
            if ce:
                by_cell.setdefault(c, {})[p] = agg(ce)
    lines += ["", "셀별 R (T1 비율)", "", "| 셀 | " + " | ".join(policies) + " |", "|---" * (len(policies) + 1) + "|"]
    for c in CELLS:
        if c in by_cell:
            lines.append(f"| {c} | " + " | ".join(
                f"{by_cell[c][p]['R']:+.2f} ({by_cell[c][p]['T1']:.0%})" if p in by_cell[c] else "-" for p in policies) + " |")
    text = "\n".join(lines)
    open(os.path.join(out_dir, "summary.md"), "w").write(text + "\n")
    print(text, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="g1")
    ap.add_argument("--iters", default="2,5,10", help="평가할 학습 회차 (원래 모델은 항상 포함)")
    ap.add_argument("--per_cell", type=int, default=3)
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--workers", type=int, default=42)
    ap.add_argument("--train_host", default="54")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    T = gym_rl.TRAIN[args.train_host]
    gym_rl.POLICY = T["policy"]
    out_dir = os.path.join(ROOT, "out", "gym_rl", f"{args.run}_eval")
    os.makedirs(out_dir, exist_ok=True)
    ids_path = os.path.join(out_dir, "eval_ids.txt")
    eval_ids(ids_path, args.per_cell)
    iters = [int(x) for x in args.iters.split(",") if x]
    policies = ["base"] + [f"it{i:03d}" for i in iters]
    if not args.summary:
        for p in policies:
            model = gym_rl.BASE_MODEL
            if p != "base":
                model = f"gym_{args.run}_{p}"
                gym_rl.adapter(model)
                out = gym_rl.adapter(model, f"{T['adapter_dir']}/{args.run}/{p}")
                if "Success" not in out:
                    raise RuntimeError(f"어댑터 올리기 실패 {p}: {out[:200]}")
            print(f"평가 {p} ({model})", flush=True)
            subprocess.run([sys.executable, os.path.join(ROOT, "chatbot/gym/run.py"), "--profiles",
                            os.path.join(ROOT, "out", "scenes_test.jsonl"), "--ids-file", ids_path,
                            "--samples", str(args.samples), "--chatbot", "qwen8b", "--model", model, "--prompt", "short",
                            "--out", out_dir, "--tag", p, "--workers", str(args.workers), "--config", T["config"]],
                           check=True, stdout=open(os.path.join(out_dir, f"run_{p}.log"), "a"), stderr=subprocess.STDOUT)
            if p != "base":
                gym_rl.adapter(model)
    summarize(out_dir, policies)


if __name__ == "__main__":
    main()
