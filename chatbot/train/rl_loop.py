"""GRPO 반복 실행기 (맥에서). 반복마다:
  1. 학습 프로필에서 셀 가중치로 n 명 뽑기
  2. 롤아웃: run_episode --policies rl --samples G (멀티쓰레드, 정책 = 84번 GPU 2 의 런타임 LoRA 'rl')
  3. rl_batch.py: 그룹 이점 → 턴 샘플
  4. 54번 GPU 4–7 에서 grpo_step.py (tmux, 끝날 때까지 기다림)
  5. 새 어댑터를 54 → 맥 → 84 로 옮긴다 (다음 반복 시작에서 'rl' 로 다시 올린다)
단계마다 결과 파일이 있으면 건너뛰므로, 끊겨도 같은 명령으로 이어서 돌린다.

  python chatbot/train/rl_loop.py --run run1 --iters 15
84번에서 돌릴 때: 84 명령은 그 자리에서, 54 는 ~/.ssh/id_yumin_to54 로, Jev 키는 /data2/yumin/.env (권한 600).
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "common"))
from servers import H54, H84  # noqa: E402  서버 주소는 .env (SDX_HOST54 / SDX_HOST84)
ON84 = os.uname().nodename.startswith("convei-rack0-84")  # 84번에서 돌리면 맥 네트워크와 무관 (2026-10-08)
SSH54 = "ssh -o BatchMode=yes" + (" -i ~/.ssh/id_yumin_to54" if ON84 else "")
SIM = "http://localhost:18602/v1"
CELL_W = {"H": .25, "M": .25, "L1": .15, "L0": .10, "N1": .10, "N0": .10, "O": .05}  # 위험 대응 턴이 많이 나오게


def sh(cmd, retries=180, **kw):
    """네트워크가 끊겨도 최대 1시간 기다렸다가 다시 (ssh 실패는 255)"""
    for i in range(retries):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
        if r.returncode != 255:
            return r
        time.sleep(20)
    raise RuntimeError(f"ssh 실패: {cmd[:80]}")


def on84(cmd):
    return sh(cmd if ON84 else f"ssh -o BatchMode=yes {H84} '{cmd}'")


def pick(profiles, n, rng):
    by = {}
    for p in profiles:
        by.setdefault(p["seed"]["cell"], []).append(p["id"])
    want = Counter(rng.choices(list(CELL_W), weights=list(CELL_W.values()), k=n))
    ids = []
    for c, k in want.items():
        ids += rng.sample(by[c], min(k, len(by[c])))
    return ids


def episode_stats(folder):
    eps = [json.load(open(os.path.join(folder, f))) for f in os.listdir(folder) if f.endswith(".json")]
    sys.path.insert(0, os.path.join(ROOT, "chatbot", "sim"))
    from penalty import TIER
    turns = [t for e in eps for t in e["turns"] if t.get("bot")]
    n = max(1, len(eps))
    return {"episodes": len(eps), "R": sum(e["reward"]["total"] for e in eps) / n,
            "R_pre": sum(e["reward"].get("before_penalty", e["reward"]["total"]) for e in eps) / n,
            "emotion": sum(e["reward"]["emotion"] for e in eps) / n,
            "risk_drop": sum(e["reward"]["risk_drop"] for e in eps) / n,
            "T1": sum(any(TIER.get(f) == "T1" for f in e.get("flags", {})) for e in eps) / n,
            "bot_chars": sum(len(t["bot"]) for t in turns) / max(1, len(turns)),
            "multi_q": sum(t["bot"].count("?") > 1 for t in turns) / max(1, len(turns))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    ap.add_argument("--iters", type=int, default=15)
    ap.add_argument("--profiles_per_iter", type=int, default=32)
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--workers", type=int, default=128)
    ap.add_argument("--init", default="lora_sft_v1", help="54번 ~/yumin_sim 기준 시작 어댑터 (= KL 기준)")
    ap.add_argument("--init84", default="/data2/yumin/rl/sft_v1", help="같은 시작 어댑터의 84번 경로 (정책 서버가 읽는다)")
    ap.add_argument("--train_args", default="", help="grpo_step.py 에 더 넘길 인자 (예: '--lr 5e-6')")
    args = ap.parse_args()

    local = os.path.join(ROOT, "out", "rl", args.run)
    os.makedirs(local, exist_ok=True)
    profiles = [json.loads(l) for l in open(os.path.join(ROOT, "out", "scenes_train.jsonl"))]
    log_path = os.path.join(local, "log.jsonl")
    sh(f"{SSH54} {H54} 'mkdir -p ~/yumin_sim/rl/{args.run}'")
    on84(f"mkdir -p /data2/yumin/rl/{args.run}")

    for it in range(1, args.iters + 1):
        tag = f"it{it:03d}"
        prev = args.init if it == 1 else f"rl/{args.run}/it{it - 1:03d}"
        ep_dir, batch = os.path.join(local, tag), os.path.join(local, f"batch_{tag}.jsonl")
        ids_path = os.path.join(local, f"ids_{tag}.txt")
        if not os.path.exists(ids_path):
            ids = pick(profiles, args.profiles_per_iter, random.Random(1000 + it))
            open(ids_path, "w").write("\n".join(ids) + "\n")

        # 2) 롤아웃 (이미 있는 에피소드는 건너뛴다). 이어서 돌릴 때도 맞는 정책이 올라가 있게 매번 prev 를 다시 올린다
        path84 = args.init84 if it == 1 else f"/data2/yumin/rl/{args.run}/it{it - 1:03d}"
        for body in ({"lora_name": "rl"}, {"lora_name": "rl", "lora_path": path84}):
            url = SIM + ("/load_lora_adapter" if "lora_path" in body else "/unload_lora_adapter")
            r = sh(f"curl -s -X POST {url} -H 'Content-Type: application/json' -d '{json.dumps(body)}'", retries=5)
        if "Success" not in r.stdout:
            raise RuntimeError(f"어댑터 올리기 실패: {r.stdout[:200]}")
        print(f"[{tag}] 롤아웃 (정책 {path84})", flush=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "chatbot/sim/run_episode.py"), "--profiles",
                        os.path.join(ROOT, "out/scenes_train.jsonl"), "--ids", ids_path, "--out", ep_dir,
                        "--policies", "rl", "--samples", str(args.samples), "--workers", str(args.workers)],
                       check=True, stdout=open(os.path.join(local, f"rollout_{tag}.log"), "a"), stderr=subprocess.STDOUT)
        stats = episode_stats(ep_dir)
        print(f"[{tag}] {json.dumps({k: round(v, 3) for k, v in stats.items()})}", flush=True)

        # 3) 이점
        if not os.path.exists(batch):
            subprocess.run([sys.executable, os.path.join(ROOT, "chatbot/train/rl_batch.py"), ep_dir, batch], check=True)

        # 4) 학습 (54번)
        remote_out = f"rl/{args.run}/{tag}"
        done = sh(f"{SSH54} {H54} 'test -f ~/yumin_sim/{remote_out}/step_stats.json'").returncode == 0
        if not done:
            sh(f"{SSH54} {H54} 'cat > ~/yumin_sim/rl/{args.run}/batch_{tag}.jsonl' < {batch}")
            cmd = (f"cd ~/yumin_sim; R=$HOME/yumin_sim; export CUDA_VISIBLE_DEVICES=4,5,6,7 HF_HOME=$R/hf HF_HUB_OFFLINE=1; "
                   f"$R/train_env/bin/accelerate launch --num_processes 4 --mixed_precision bf16 grpo_step.py "
                   f"--batch rl/{args.run}/batch_{tag}.jsonl --policy_in {prev} --ref {args.init} --out {remote_out} "
                   f"{args.train_args} > logs/grpo_{args.run}_{tag}.log 2>&1")
            cmd = cmd.replace("$", "\\$")  # 맥 셸이 아니라 54번에서 펼쳐지게
            sh(f"{SSH54} {H54} \"tmux kill-session -t grpo 2>/dev/null; tmux new-session -d -s grpo '{cmd}'\"")
            print(f"[{tag}] 학습 시작 (54 tmux grpo)", flush=True)
            while True:
                time.sleep(30)
                r = sh(f"{SSH54} {H54} 'test -f ~/yumin_sim/{remote_out}/step_stats.json && echo DONE; "
                       f"tmux has-session -t grpo 2>/dev/null && echo RUNNING'")
                if "DONE" in r.stdout:
                    break
                if "RUNNING" not in r.stdout:
                    tail = sh(f"{SSH54} {H54} 'tail -20 ~/yumin_sim/logs/grpo_{args.run}_{tag}.log'").stdout
                    raise RuntimeError(f"학습이 결과 없이 끝남:\n{tail}")
        step = json.loads(sh(f"{SSH54} {H54} 'cat ~/yumin_sim/{remote_out}/step_stats.json'").stdout)
        print(f"[{tag}] 학습 {json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in step.items()})}", flush=True)

        # 5) 어댑터 54 → 맥 → 84, 다시 올리기
        dest = f"/data2/yumin/rl/{args.run}/{tag}"
        files = "adapter_config.json adapter_model.safetensors"
        if ON84:  # 54 → 84 바로
            sh(f"mkdir -p {dest} && {SSH54} {H54} 'cd ~/yumin_sim/{remote_out} && tar -cf - {files}' | tar -xf - -C {dest}")
        else:  # 54 → 맥 → 84
            tar = os.path.join(local, f"adapter_{tag}.tar")
            if not os.path.exists(tar) or os.path.getsize(tar) < 1e6:
                sh(f"{SSH54} {H54} 'cd ~/yumin_sim/{remote_out} && tar -cf - {files}' > {tar}")
            sh(f"ssh -o BatchMode=yes {H84} 'mkdir -p {dest} && cd {dest} && tar -xf -' < {tar}")
            os.remove(tar)  # 84 에 올리는 건 다음 반복 시작에서
        with open(log_path, "a") as f:
            f.write(json.dumps({"iter": it, "rollout": stats, "train": step}) + "\n")
        print(f"[{tag}] 어댑터 84 로 복사 완료", flush=True)


if __name__ == "__main__":
    main()
