"""GRPO 반복 실행기, 롤아웃과 학습을 겹쳐 GPU 를 놀리지 않는다 (84번에서). rl_loop.py 의 단계·파일을 그대로 쓴다.

  롤아웃 쓰레드: it 의 롤아웃 → 배치 → 바로 it+1 롤아웃 (그때 나와 있는 가장 최근 어댑터로)
  학습 쓰레드:   it 배치가 나오면 54번에서 학습 (이전 학습이 끝난 어댑터에서 시작) → 84 로 복사
롤아웃은 정책보다 최대 한 단계 늦을 수 있다 (한 단계 off-policy; 비율 자르기가 그 차이를 다룬다).
학습이 느리면 롤아웃이 기다린다 (it 롤아웃은 it−2 학습이 끝난 뒤).
반복마다 어떤 어댑터로 롤아웃했는지 log.jsonl 의 rollout_policy 에 남긴다.

  python chatbot/train/rl_loop_async.py --run run2 --start 7 --iters 15 --profiles_per_iter 64 --workers 256
"""

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rl_loop import H54, ROOT, SIM, SSH54, episode_stats, pick, sh  # noqa: E402
from servers import HOME54  # noqa: E402  rl_loop 이 common 을 sys.path 에 넣는다

sys.path.insert(0, os.path.join(ROOT, "chatbot", "sim"))
from textsim import max_similarity  # noqa: E402


def key_remaining():
    """OpenRouter 키 남은 한도 ($). 한도가 없거나 확인이 안 되면 inf (막지 않는다). 키가 ps 에 보이지 않게 requests 로"""
    import requests
    sys.path.insert(0, os.path.join(ROOT, "common"))
    from jev_client import api_key
    try:
        d = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {api_key()}"},
                         timeout=15).json()["data"]
    except Exception:  # noqa: BLE001
        return float("inf")
    return float("inf") if d.get("limit") is None else float(d.get("limit_remaining") or 0)


def repeat_rate(folder):
    n = r = 0
    for f in os.listdir(folder):
        if not f.endswith(".json"):
            continue
        prev = []
        for t in json.load(open(os.path.join(folder, f)))["turns"]:
            if t.get("bot"):
                n += 1
                r += max_similarity(t["bot"], prev) >= 0.8
                prev.append(t["bot"])
    return r / max(1, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run2")
    ap.add_argument("--start", type=int, required=True, help="이 반복부터 (앞 반복의 어댑터가 있어야 한다)")
    ap.add_argument("--iters", type=int, default=15)
    ap.add_argument("--profiles_per_iter", type=int, default=64)
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--workers", type=int, default=256)
    ap.add_argument("--init", default="lora_sft_v2")
    ap.add_argument("--init84", default="/data2/yumin/rl/sft_v2")
    ap.add_argument("--train_args", default="--minibatches 8", help="배치가 2배라 스텝도 2배")
    ap.add_argument("--policy54", default="18615,18616", help="54번 정책 복제본 포트 (84 터널). 84 의 18602 와 같이 어댑터를 올린다")
    ap.add_argument("--train_gpus", default="4,5", help="54번 학습 GPU (6·7 은 정책 복제본)")
    ap.add_argument("--iter_cost", type=float, default=0.8, help="반복당 Jev 비용 추정 ($, 256 에피소드 기준)")
    ap.add_argument("--reserve", type=float, default=1.5, help="끝난 뒤 평가에 남겨 둘 키 한도 ($)")
    args = ap.parse_args()

    local = os.path.join(ROOT, "out", "rl", args.run)
    profiles = [json.loads(l) for l in open(os.path.join(ROOT, "out", "scenes_train.jsonl"))]
    log_path = os.path.join(local, "log.jsonl")
    lock = threading.Lock()
    latest = {"it": args.start - 1}  # 84 에 올라와 있는(복사된) 가장 최근 학습 반복
    batch_ready = {}                  # it → (stats, rollout_policy)
    cond = threading.Condition(lock)
    errors = []
    stop = {}  # 키 한도 때문에 멈춘 반복

    def adapter84(it):
        return args.init84 if it == 0 else f"/data2/yumin/rl/{args.run}/it{it:03d}"

    def adapter54(it):
        return f"{HOME54}/yumin_sim/{args.init}" if it == 0 else f"{HOME54}/yumin_sim/rl/{args.run}/it{it:03d}"

    # 정책 서버: 84 GPU 2 + 54 GPU 6·7 (정책 하나에 요청 300개가 밀려 시뮬레이터가 놀았다). 어댑터 경로는 서버마다
    endpoints = [(SIM, adapter84)] + [(f"http://localhost:{p}/v1", adapter54) for p in args.policy54.split(",") if p]

    def roller():
        try:
            for it in range(args.start, args.iters + 1):
                tag = f"it{it:03d}"
                ids_path = os.path.join(local, f"ids_{tag}.txt")
                if not os.path.exists(ids_path):
                    ids = pick(profiles, args.profiles_per_iter, random.Random(1000 + it))
                    open(ids_path, "w").write("\n".join(ids) + "\n")
                left = key_remaining()
                if left < args.iter_cost * len(open(ids_path).read().split()) / 64 + args.reserve:
                    print(f"[{tag}] 키 한도 ${left:.2f} 남음 → 평가 몫 ${args.reserve} 를 남기고 롤아웃 중단", flush=True)
                    with cond:
                        stop["at"] = it
                        cond.notify_all()
                    return
                with cond:  # 정책이 한 단계보다 더 늦지 않게: it 롤아웃은 it−2 학습이 끝난 뒤에 (run2 it014·015 가 it011 로 돌았다)
                    while latest["it"] < it - 2 and not errors:
                        cond.wait(30)
                    if errors:  # 학습이 실패했으면 롤아웃도 멈춘다 (run3: 학습 없이 롤아웃만 15번 돌아 Jev $11 낭비)
                        print(f"[{tag}] 학습 쓰레드 오류로 롤아웃 중단", flush=True)
                        return
                    pol = latest["it"]
                for url0, adapter in endpoints:
                    for body in ({"lora_name": "rl"}, {"lora_name": "rl", "lora_path": adapter(pol)}):
                        url = url0 + ("/load_lora_adapter" if "lora_path" in body else "/unload_lora_adapter")
                        r = sh(f"curl -s -X POST {url} -H 'Content-Type: application/json' -d '{json.dumps(body)}'", retries=5)
                    if "Success" not in r.stdout:
                        raise RuntimeError(f"어댑터 올리기 실패 ({url0}): {r.stdout[:200]}")
                print(f"[{tag}] 롤아웃 시작 (정책 it{pol:03d}, 프로필 {len(open(ids_path).read().split())})", flush=True)
                ep_dir = os.path.join(local, tag)
                subprocess.run([sys.executable, os.path.join(ROOT, "chatbot/sim/run_episode.py"), "--profiles",
                                os.path.join(ROOT, "out/scenes_train.jsonl"), "--ids", ids_path, "--out", ep_dir,
                                "--policies", "rl", "--samples", str(args.samples), "--workers", str(args.workers)],
                               check=True, stdout=open(os.path.join(local, f"rollout_{tag}.log"), "a"),
                               stderr=subprocess.STDOUT)
                stats = episode_stats(ep_dir)
                stats["repeat"] = repeat_rate(ep_dir)
                batch = os.path.join(local, f"batch_{tag}.jsonl")
                if not os.path.exists(batch):
                    subprocess.run([sys.executable, os.path.join(ROOT, "chatbot/train/rl_batch.py"), ep_dir, batch], check=True)
                print(f"[{tag}] 롤아웃 끝 {json.dumps({k: round(v, 3) for k, v in stats.items()})}", flush=True)
                with cond:
                    batch_ready[it] = (stats, pol)
                    cond.notify_all()
        except Exception as e:  # noqa: BLE001
            errors.append(e)
            with cond:
                cond.notify_all()
            raise

    def trainer():
        try:
            for it in range(args.start, args.iters + 1):
                tag = f"it{it:03d}"
                with cond:
                    while it not in batch_ready and not errors and stop.get("at", 10 ** 9) > it:
                        cond.wait(30)
                    if errors or it not in batch_ready:
                        return
                    stats, pol = batch_ready[it]
                prev = args.init if it == 1 else f"rl/{args.run}/it{it - 1:03d}"
                remote_out = f"rl/{args.run}/{tag}"
                batch = os.path.join(local, f"batch_{tag}.jsonl")
                done = sh(f"{SSH54} {H54} 'test -f ~/yumin_sim/{remote_out}/step_stats.json'").returncode == 0
                if not done:
                    sh(f"{SSH54} {H54} 'cat > ~/yumin_sim/rl/{args.run}/batch_{tag}.jsonl' < {batch}")
                    cmd = (f"cd ~/yumin_sim; R=$HOME/yumin_sim; export CUDA_VISIBLE_DEVICES={args.train_gpus} HF_HOME=$R/hf "
                           f"HF_HUB_OFFLINE=1; $R/train_env/bin/accelerate launch --num_processes {len(args.train_gpus.split(','))} "
                           f"--mixed_precision bf16 "
                           f"grpo_step.py --batch rl/{args.run}/batch_{tag}.jsonl --policy_in {prev} --ref {args.init} "
                           f"--out {remote_out} {args.train_args} > logs/grpo_{args.run}_{tag}.log 2>&1").replace("$", "\\$")
                    sh(f"{SSH54} {H54} \"tmux kill-session -t grpo 2>/dev/null; tmux new-session -d -s grpo '{cmd}'\"")
                    print(f"[{tag}] 학습 시작", flush=True)
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
                dest = adapter84(it)
                sh(f"mkdir -p {dest} && {SSH54} {H54} 'cd ~/yumin_sim/{remote_out} && tar -cf - adapter_config.json "
                   f"adapter_model.safetensors' | tar -xf - -C {dest}")
                with cond:
                    latest["it"] = it
                    cond.notify_all()
                    with open(log_path, "a") as f:
                        f.write(json.dumps({"iter": it, "rollout": stats, "rollout_policy": pol, "train": step,
                                            "async": True}) + "\n")
                print(f"[{tag}] 학습 끝 {json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in step.items()})}",
                      flush=True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
            raise

    threads = [threading.Thread(target=roller), threading.Thread(target=trainer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("RL_EXIT" + (f" 오류: {errors}" if errors else ""), flush=True)


if __name__ == "__main__":
    main()
