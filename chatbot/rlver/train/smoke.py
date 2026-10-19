"""학습 전 점검 (84번): 평가 대화에서 턴 샘플 16개 (긴 것 위주, 이점은 ±1) → grpo_step 한 번 → 어댑터를 정책 서버에 올려 답 하나.
GPU 3–6 시뮬레이터를 내렸다가 다시 올린다. 통과하면 SMOKE_OK 를 찍는다.

  python chatbot/rlver/train/smoke.py --episodes out/rlver/eval_bank_8b/episodes.jsonl
"""

import argparse
import json
import os
import subprocess

import rlver_rl as rl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", required=True)
    ap.add_argument("--out", default=os.path.join(rl.ROOT, "out", "rlver_rl", "smoke"))
    ap.add_argument("--host", default="84", choices=list(rl.HOSTS))
    args = ap.parse_args()
    rl.set_host(args.host)
    os.makedirs(args.out, exist_ok=True)
    eps = [json.loads(l) for l in open(args.episodes)]
    turns = sorted((t for e in eps for t in e["turns"] if "bot_raw" in t),
                   key=lambda t: -len(json.dumps(t["prompt"])) - len(t["bot_raw"]))[:16]
    batch = os.path.join(args.out, "batch.jsonl")
    with open(batch, "w") as f:
        for i, t in enumerate(turns):
            f.write(json.dumps({"messages": t["prompt"], "completion": t["bot_raw"], "adv": 1.0 if i % 2 else -1.0},
                               ensure_ascii=False) + "\n")
    out_dir = os.path.join(args.out, "adapter")
    rl.sims_down()
    cmd = (f"cd {rl.HERE} && CUDA_VISIBLE_DEVICES={rl.TRAIN_GPUS} HF_HOME={rl.HF} HF_HUB_OFFLINE=1 "
           f"{rl.TRAIN_ENV}/bin/accelerate launch --num_processes {len(rl.TRAIN_GPUS.split(','))} --mixed_precision bf16 grpo_step.py "
           f"--model {rl.BASE} --batch {batch} --policy_in none --out {out_dir} --native_think "
           f"> {os.path.join(args.out, 'train.log')} 2>&1")
    r = subprocess.run(cmd, shell=True)
    peak = rl.gpu_used(rl.TRAIN_GPUS)
    rl.sims_up()
    if r.returncode != 0 or not os.path.exists(os.path.join(out_dir, "step_stats.json")):
        raise SystemExit(f"SMOKE_FAIL 학습 ({os.path.join(args.out, 'train.log')})")
    print("학습", open(os.path.join(out_dir, "step_stats.json")).read(), "끝난 뒤 GPU", peak, flush=True)
    rl.adapter("rlver_smoke")
    out = rl.adapter("rlver_smoke", out_dir)
    if "Success" not in out:
        raise SystemExit(f"SMOKE_FAIL 어댑터 ({out[:300]})")
    body = json.dumps({"model": "rlver_smoke", "messages": turns[0]["prompt"], "max_tokens": 300})
    open(os.path.join(args.out, "req.json"), "w").write(body)
    ans = rl.sh(f"curl -s -m 300 {rl.POLICIES[0]}/v1/chat/completions -H 'Content-Type: application/json' "
                f"-d @{os.path.join(args.out, 'req.json')}").stdout
    rl.adapter("rlver_smoke")
    if '"choices"' not in ans:
        raise SystemExit(f"SMOKE_FAIL 생성 ({ans[:300]})")
    print("SMOKE_OK", json.loads(ans)["choices"][0]["message"]["content"][-200:], flush=True)


if __name__ == "__main__":
    main()
