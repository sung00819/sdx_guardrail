"""rlver GRPO 반복 실행기 (84번 서버 안에서). RLVER 설정 (train_rlver.sh, 논문 부록 B.3) + gym LoRA 학습 스텝.

반복마다:
  1. 학습 split 에서 사용자 (배경 id, 설정) 32 명 뽑기 (data.train_batch_size=32)
  2. 롤아웃: run.py --samples 4 (rollout.n=4, 8턴, 온도 1.0). 정책 = 84번 8B vLLM (GPU 2, 18602) 의 런타임 LoRA, 처음은 원래 모델
  3. 그룹 이점 (같은 사용자 4개 안 표준화, 보상 r = max(e_T, 0)/100, 형식 위반이면 0) → 턴 샘플 (챗봇 토큰만 학습)
  4. 학습: 30B 시뮬레이터 3대(GPU 0·1·3–6)를 내리고 6장에서 grpo_step.py (LoRA, KL 0, 업데이트 한 번), 끝나면 다시 올린다
단계마다 결과가 있으면 건너뛰므로 끊겨도 같은 명령으로 이어서 돌린다.

  python chatbot/rlver/train/rlver_rl.py --run r1 --iters 20
"""

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RLVER = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(RLVER, "..", ".."))
sys.path.insert(0, RLVER)
from backgrounds import OUT as BACKGROUNDS, read  # noqa: E402
from compose import SETTINGS  # noqa: E402

BASE = "Qwen/Qwen3-8B"
# 서버별 설정 (--host). sims = 학습 동안 내리는 시뮬레이터 (tmux 창 이름, 띄우는 명령, 포트), policies = 런타임 LoRA 정책 서버
HOSTS = {
    "84": {  # 3090 × 7: 시뮬레이터 3대 (TP2) + 정책 GPU 2, 학습 6장 (2026-10-19 사용자: GPU 최대한)
        "py": "/data2/yumin/env/bin/python", "train_env": "/data2/yumin/train_env", "hf": "/data2/yumin/hf",
        "logs": "/data2/yumin/logs", "tmux": "yumin_rlver", "config": "config_84_one.json",
        "policies": ["http://localhost:18602"], "train_gpus": "0,1,3,4,5,6",
        "sims": [("sim", "bash /data2/yumin/serve_30b.sh", 18601), ("sim_b", "bash /data2/yumin/serve_30b_b.sh", 18603),
                 ("sim_c", "bash /data2/yumin/serve_30b_c.sh", 18604)]},
    "43": {  # Ada 48GB × 6 + A100: 시뮬레이터 5대 GPU 0–4 (한 장씩), 정책 2대 GPU 5·6 (A100 은 FP8 30B 가 안 뜬다), 학습 GPU 0–4
        "py": "/home/minseok/.conda/envs/vllm_qwen/bin/python", "train_env": "/home/minseok/yumin/train_env",
        "hf": "/home/minseok/yumin/hf", "logs": "/home/minseok/yumin/logs", "tmux": "yumin_eval", "config": "config_43.json",
        "policies": ["http://localhost:18611", "http://localhost:18612"], "train_gpus": "0,1,2,3,4",
        "sims": [(f"sim{g}", f"bash /home/minseok/yumin/serve.sh {g} Qwen/Qwen3-30B-A3B-Instruct-2507-FP8 {18601 + g}", 18601 + g)
                 for g in range(5)]},
}
PY = TRAIN_ENV = HF = LOGS = TMUX = CONFIG = TRAIN_GPUS = None
POLICIES, SIMS = [], []


def set_host(name):
    global PY, TRAIN_ENV, HF, LOGS, TMUX, CONFIG, TRAIN_GPUS, POLICIES, SIMS
    h = HOSTS[name]
    PY, TRAIN_ENV, HF, LOGS, TMUX = h["py"], h["train_env"], h["hf"], h["logs"], h["tmux"]
    CONFIG, TRAIN_GPUS, POLICIES, SIMS = os.path.join(RLVER, h["config"]), h["train_gpus"], h["policies"], h["sims"]


def sh(cmd, check=False):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)


def up(port):
    return '"id"' in sh(f"curl -s -m 5 localhost:{port}/v1/models").stdout


def wait_up(ports, timeout=900):
    t0 = time.time()
    while not all(up(p) for p in ports):
        if time.time() - t0 > timeout:
            raise RuntimeError(f"서버가 안 뜸: {ports}")
        time.sleep(10)


def gpu_used(gpus):
    out = sh(f"nvidia-smi -i {gpus} --query-gpu=memory.used --format=csv,noheader,nounits").stdout.split()
    return max(int(x) for x in out)


def sims_down():
    for _, _, port in SIMS:
        sh(f"pkill -f '[v]llm serve .*--port {port}'")
    t0 = time.time()
    while gpu_used(TRAIN_GPUS) > 1000:
        if time.time() - t0 > 180:
            for _, _, port in SIMS:
                sh(f"pkill -9 -f '[v]llm serve .*--port {port}'")
        if time.time() - t0 > 400:
            raise RuntimeError(f"GPU {TRAIN_GPUS} 가 안 비워짐")
        time.sleep(5)


def sims_up():
    for win, cmd, port in SIMS:
        if not up(port):
            sh(f"tmux kill-window -t {TMUX}:{win} 2>/dev/null")
            sh(f"tmux new-window -d -t {TMUX} -n {win} '{cmd} 2>&1 | tee -a {LOGS}/rlver_{win}.log'")
    wait_up([p for _, _, p in SIMS])


def adapter(name, path=None):
    """정책 서버 모두에 런타임 어댑터 올리기 (path) / 내리기. 올리기는 모두 성공해야 'Success'"""
    body = {"lora_name": name, **({"lora_path": path} if path else {})}
    ep = "load_lora_adapter" if path else "unload_lora_adapter"
    outs = [sh(f"curl -s -m 120 -X POST {p}/v1/{ep} -H 'Content-Type: application/json' -d '{json.dumps(body)}'").stdout
            for p in POLICIES]
    return "Success" if path and all("Success" in o for o in outs) else " | ".join(outs)


def pick(train_ids, n, rng):
    pool = [(i, k) for i in train_ids for k in range(len(SETTINGS))]
    return rng.sample(pool, n)


def build_batch(ep_path, out_path):
    """같은 사용자 (id, 설정) 그룹 안 표준화 이점. 그룹 보상이 다 같으면 정보가 없어 뺀다"""
    eps = [json.loads(l) for l in open(ep_path) if l.strip()]
    groups = {}
    for e in eps:
        groups.setdefault((e["id"], e["setting"]), []).append(e)
    rows = used = 0
    with open(out_path, "w") as f:
        for g in groups.values():
            rs = [e["reward"] for e in g]
            if len(g) < 2 or statistics.pstdev(rs) < 1e-6:
                continue
            mu, sd = statistics.mean(rs), statistics.pstdev(rs)
            used += 1
            for e in g:
                adv = (e["reward"] - mu) / (sd + 1e-4)
                for t in e["turns"]:
                    if "bot_raw" not in t:
                        continue
                    f.write(json.dumps({"messages": t["prompt"], "completion": t["bot_raw"], "adv": adv},
                                       ensure_ascii=False) + "\n")
                    rows += 1
    return {"groups": len(groups), "groups_used": used, "samples": rows}


def stats(ep_path):
    eps = [json.loads(l) for l in open(ep_path) if l.strip()]
    n = max(1, len(eps))
    return {"episodes": len(eps), "reward": sum(e["reward"] for e in eps) / n,
            "score": sum(e["final_emotion"] for e in eps) / n,
            "format_fail": sum(not e["format_ok"] for e in eps) / n,
            "repeat_turns": sum(e.get("repeats", 0) for e in eps) / max(1, sum(len(e["turns"]) - 1 for e in eps)),
            "success": sum(e["end"] == "success" for e in eps) / n,
            "failure": sum(e["end"] == "failure" for e in eps) / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="r1")
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--users", type=int, default=32, help="반복마다 사용자 수 (train_batch_size)")
    ap.add_argument("--samples", type=int, default=4, help="GRPO 그룹 크기 (rollout.n)")
    ap.add_argument("--temperature", type=float, default=1.0, help="RLVER rollout.temperature")
    ap.add_argument("--workers", type=int, default=128)
    ap.add_argument("--host", default="84", choices=list(HOSTS), help="서버 설정 (HOSTS)")
    ap.add_argument("--template", default="bank")
    ap.add_argument("--lr", type=float, default=1e-5, help="LoRA (gym 과 같은 값; RLVER 1e-6 은 전체 미세조정)")
    ap.add_argument("--train_args", default="")
    args = ap.parse_args()
    set_host(args.host)

    run_dir = os.path.join(ROOT, "out", "rlver_rl", args.run)
    os.makedirs(run_dir, exist_ok=True)
    train_ids = sorted(bg["id"] for bg in read(BACKGROUNDS) if bg["split"] == "train")
    sims_up()  # 앞 실행이 학습 중에 끊겼으면 시뮬레이터가 내려가 있다
    wait_up([int(p.rsplit(":", 1)[1]) for p in POLICIES] + [p for _, _, p in SIMS])

    for it in range(1, args.iters + 1):
        tag, prev = f"it{it:03d}", (f"it{it - 1:03d}" if it > 1 else None)
        d = os.path.join(run_dir, tag)
        os.makedirs(d, exist_ok=True)
        pairs_path = os.path.join(d, "pairs.txt")
        if not os.path.exists(pairs_path):
            pairs = pick(train_ids, args.users, random.Random(1000 + it))
            open(pairs_path, "w").write("".join(f"{i} {k}\n" for i, k in pairs))

        # 1. 롤아웃
        model = BASE
        if prev:
            model = f"rlver_{args.run}_{prev}"
            adapter(model)
            out = adapter(model, os.path.join(run_dir, prev, "adapter"))
            if "Success" not in out:
                raise RuntimeError(f"어댑터 올리기 실패: {out[:300]}")
        roll = os.path.join(d, "rollout")
        print(f"[{tag}] 롤아웃 (정책 {model})", flush=True)
        subprocess.run([PY, "-u", os.path.join(RLVER, "run.py"), "--config", CONFIG, "--chatbot", "qwen3-8b",
                        "--model", model, "--template", args.template, "--split", "train", "--pairs", pairs_path,
                        "--samples", str(args.samples), "--temperature", str(args.temperature),
                        "--workers", str(args.workers), "--out", roll],
                       check=True, stdout=open(os.path.join(d, "rollout.log"), "a"), stderr=subprocess.STDOUT)
        ep_path = os.path.join(roll, "episodes.jsonl")
        st = stats(ep_path)
        if st["episodes"] < 0.75 * args.users * args.samples:
            raise RuntimeError(f"롤아웃 부족: {st['episodes']}")
        print(f"[{tag}] {json.dumps({k: round(v, 3) for k, v in st.items()})}", flush=True)
        if prev:
            adapter(model)  # vLLM --max-loras 2

        # 2. 이점 → 샘플
        batch = os.path.join(d, "batch.jsonl")
        bs = build_batch(ep_path, batch)
        print(f"[{tag}] 샘플 {json.dumps(bs)}", flush=True)

        # 3. 학습 (시뮬레이터 3대를 잠시 내린다)
        out_dir = os.path.join(d, "adapter")
        if not os.path.exists(os.path.join(out_dir, "step_stats.json")):
            sims_down()
            pin = os.path.join(run_dir, prev, "adapter") if prev else "none"
            cmd = (f"cd {HERE} && CUDA_VISIBLE_DEVICES={TRAIN_GPUS} HF_HOME={HF} HF_HUB_OFFLINE=1 "
                   f"{TRAIN_ENV}/bin/accelerate launch --num_processes {len(TRAIN_GPUS.split(','))} --mixed_precision bf16 grpo_step.py "
                   f"--model {BASE} --batch {batch} --policy_in {pin} --out {out_dir} --lr {args.lr} --native_think "
                   f"{args.train_args} > {os.path.join(d, 'train.log')} 2>&1")
            print(f"[{tag}] 학습 시작", flush=True)
            r = subprocess.run(cmd, shell=True)
            sims_up()
            if r.returncode != 0 or not os.path.exists(os.path.join(out_dir, "step_stats.json")):
                raise RuntimeError(f"학습 실패, {os.path.join(d, 'train.log')}")
        if prev:  # 이어서 학습할 때는 최신 optimizer 만 필요하다 (반복마다 350MB, 43번 디스크 97%)
            old_opt = os.path.join(run_dir, prev, "adapter", "optimizer.pt")
            if os.path.exists(old_opt):
                os.remove(old_opt)
        step = json.load(open(os.path.join(out_dir, "step_stats.json")))
        print(f"[{tag}] 학습 {json.dumps(step)}", flush=True)
        with open(os.path.join(run_dir, "log.jsonl"), "a") as f:
            f.write(json.dumps({"iter": it, "rollout": st, "batch": bs, "train": step}) + "\n")


if __name__ == "__main__":
    main()
