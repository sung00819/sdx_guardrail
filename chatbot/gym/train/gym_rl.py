"""gym GRPO 반복 실행기 (맥에서). 반복마다:
  1. 학습 프로필에서 셀 가중치로 n 명 뽑기
  2. 롤아웃: gym run.py --samples G (정책 = 84번 8B vLLM 의 런타임 LoRA 'gym_<run>_<it>', 처음은 원래 모델)
  3. 그룹 이점 → 턴 샘플 (batch_itXXX.jsonl)
  4. 학습 서버에서 gym_grpo_step.py (tmux gymgrpo, 끝날 때까지 기다림)
  5. 새 어댑터를 학습 서버 → 맥 → 84 로 옮긴다
단계마다 결과가 있으면 건너뛰므로, 끊겨도 같은 명령으로 이어서 돌린다.

  python chatbot/gym/train/gym_rl.py --run g1 --iters 10
"""

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "common"))
from servers import H27, H54, H84, ROOT27, USER  # noqa: E402  서버 주소·계정은 .env (common/servers.py)
BASE_MODEL = "Qwen/Qwen3-8B"
# 학습 서버.
#  54: 학습 54번 GPU 4–7, 정책 84번 GPU 2 (어댑터를 54 → 84 로 복사), 시뮬레이터는 sim run1 과 공유 → run1 뒤에만
#  27: 전부 27번 (정책 GPU 0, 시뮬레이터 GPU 1–2, 학습 GPU 4–7). run1 과 무관 (2026-10-08 사용자: 27번으로)
TRAIN = {
    "54": {"host": H54, "root": "~/yumin_sim", "env": "$HOME/yumin_sim/train_env",
           "model": "$HOME/yumin_sim/models/Qwen3-8B", "gpus": "4,5,6,7", "hf": "$HOME/yumin_sim/hf",
           "policy": "http://localhost:18602/v1", "adapter_dir": "/data2/yumin/gym_rl", "copy_to": H84,
           "config": "config.json", "wait_run1": True},
    "27": {"host": H27, "root": ROOT27, "env": f"{ROOT27}/train_env",
           "model": f"{ROOT27}/models/Qwen3-8B", "gpus": "4,5,6,7", "hf": f"{ROOT27}/hf",
           "policy": "http://localhost:18702/v1", "adapter_dir": f"{ROOT27}/gym", "copy_to": None,
           "config": "config_27.json", "wait_run1": False},
}
POLICY = None  # main() 에서 학습 서버에 맞게
CELL_W = {"H": .25, "M": .2, "L1": .15, "L0": .1, "N1": .1, "N0": .1, "O": .1}  # 위험 대응 턴이 많이 나오게


def sh(cmd, retries=180):  # 접속 장애가 길어도 (2026-10-07 54번 48분) 최대 1시간 기다린다
    for _ in range(retries):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 255:  # ssh 연결 실패만 다시
            return r
        time.sleep(20)
    raise RuntimeError(f"ssh 실패: {cmd[:100]}")


def etime_min(s):
    """ps etime ([[dd-]hh:]mm:ss) → 분"""
    d, _, s = s.rpartition("-")
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return (int(d or 0) * 24 * 60) + parts[0] * 60 + parts[1] + parts[2] / 60


RUN2_DIR = "/data2/yumin/sdx_guardrail/out/rl"  # 84번에서 도는 sim 쪽 rl_loop.py 의 결과 폴더


def train_window(host54, max_age=18):
    """54번 GPU 4–7 에서 학습해도 되는 때까지 기다린다 (gym 학습 1회 ≈ 7분).
    sim 쪽 RL(84번 rl_loop.py, 2026-10-08 run2)은 롤아웃(~29분, ids_itN 생성) → 54번 학습(~12분, batch_itN 생성 뒤)을
    번갈아 한다. 그쪽 롤아웃이 시작된 지 max_age 분이 안 됐고 54번에 그쪽 학습(tmux grpo)이 없을 때만 시작한다."""
    probe = ("p=$(pgrep -f \"[r]l_loop.py --run\" | head -1); [ -z \"$p\" ] && { echo NOLOOP; exit; }; "
             "run=$(ps -o args= -p $p | sed -E \"s/.*--run ([^ ]+).*/\\1/\"); cd " + RUN2_DIR + "/$run || { echo NOLOOP; exit; }; "
             "f=$(ls -t ids_it*.txt 2>/dev/null | head -1); n=${f#ids_}; n=${n%.txt}; "
             "[ -f batch_$n.jsonl ] && echo TRAINING || echo AGE $(( ($(date +%s) - $(stat -c %Y $f)) / 60 ))")
    while True:
        busy54 = sh(f"ssh -o BatchMode=yes {host54} 'tmux has-session -t grpo 2>/dev/null'").returncode == 0
        st = sh(f"ssh -o BatchMode=yes {H84} '{probe}'").stdout.strip().splitlines()
        st = st[-1] if st else "NOLOOP"
        ok = not busy54 and (st == "NOLOOP" or (st.startswith("AGE") and int(st.split()[1]) < max_age))
        if ok:
            return
        print(f"{time.strftime('%H:%M')} 54번 학습 자리 기다림 (sim grpo={busy54}, sim 상태 {st})", flush=True)
        time.sleep(60)


def wait_free(host54):
    """sim 쪽 RL(rl_loop.py)이 돌고 있거나 54번에 그쪽 학습(tmux grpo)이 있으면 끝날 때까지 쉰다 (사용자 결정: run1 뒤에)"""
    while True:
        busy = subprocess.run("pgrep -f 'rl_loop.py'", shell=True, capture_output=True).returncode == 0
        busy = busy or sh(f"ssh -o BatchMode=yes {host54} 'tmux has-session -t grpo 2>/dev/null'").returncode == 0
        if not busy:
            return
        print(f"{time.strftime('%H:%M')} sim RL 이 돌고 있어 기다림", flush=True)
        time.sleep(600)


def pick(profiles, n, rng):
    by = {}
    for p in profiles:
        by.setdefault(p["seed"]["cell"], []).append(p["id"])
    want = Counter(rng.choices(list(CELL_W), weights=list(CELL_W.values()), k=n))
    return [i for c, k in want.items() for i in rng.sample(by[c], min(k, len(by[c])))]


def build_batch(ep_path, out_path):
    """그룹(같은 프로필) 안 표준화 이점. 그룹 보상이 다 같으면 정보가 없어 뺀다"""
    eps = [json.loads(l) for l in open(ep_path) if l.strip()]
    groups = {}
    for e in eps:
        groups.setdefault(e["id"], []).append(e)
    n_rows, used = 0, 0
    with open(out_path, "w") as f:
        for g in groups.values():
            rs = [e["reward"]["R"] for e in g]
            if len(g) < 2 or statistics.pstdev(rs) < 1e-6:
                continue
            mu, sd = statistics.mean(rs), statistics.pstdev(rs)
            used += 1
            for e in g:
                adv = (e["reward"]["R"] - mu) / (sd + 1e-4)
                for t in e["turns"]:
                    msgs = [{"role": "system", "content": e["system"]}] + t["bot_input"]
                    f.write(json.dumps({"messages": msgs, "completion": t["bot"], "adv": adv}, ensure_ascii=False) + "\n")
                    n_rows += 1
    return {"groups": len(groups), "groups_used": used, "samples": n_rows}


def stats(ep_path):
    eps = [json.loads(l) for l in open(ep_path) if l.strip()]
    n = max(1, len(eps))
    r = [e["reward"] for e in eps]
    return {"episodes": len(eps), "R": sum(x["R"] for x in r) / n, "O": sum(x["O"] for x in r) / n,
            "Q": sum(x["Q"] for x in r) / n, "T1": sum(bool(x["t1"]) for x in r) / n,
            "viol": sum(len(x["violations"]) for x in r) / n,
            "d_emotion": sum(x["delta"]["emotion"] for x in r) / n}


def adapter(name, path=None):
    """84번 8B 서버에 런타임 어댑터 올리기/내리기"""
    if path is None:
        body, ep = {"lora_name": name}, "unload_lora_adapter"
    else:
        body, ep = {"lora_name": name, "lora_path": path}, "load_lora_adapter"
    cmd = (f"curl -s -m 120 -X POST {POLICY.rsplit('/v1', 1)[0]}/v1/{ep} -H 'Content-Type: application/json' "
           f"-d '{json.dumps(body)}'")
    for _ in range(60):  # 터널이 끊기면 curl 이 빈 응답 → 10초 간격으로 최대 10분 (2026-10-08 15:55 끊김에 실패)
        out = sh(cmd, retries=5).stdout
        if out.strip():
            return out
        time.sleep(10)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="g1")
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--profiles_per_iter", type=int, default=16)
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--train_host", default="54", choices=list(TRAIN))
    ap.add_argument("--train_args", default="")
    args = ap.parse_args()

    global POLICY
    T = TRAIN[args.train_host]
    POLICY = T["policy"]
    local = os.path.join(ROOT, "out", "gym_rl", args.run)
    os.makedirs(local, exist_ok=True)
    profiles = [json.loads(l) for l in open(os.path.join(ROOT, "out", "scenes_train.jsonl"))]
    sh(f"ssh -o BatchMode=yes {T['host']} 'mkdir -p {T['root']}/gym/{args.run} {T['root']}/logs'")
    sh(f"ssh -o BatchMode=yes {T['host']} 'cat > {T['root']}/gym/gym_grpo_step.py' < {os.path.join(HERE, 'gym_grpo_step.py')}")
    if T["copy_to"]:
        sh(f"ssh -o BatchMode=yes {T['copy_to']} 'mkdir -p {T['adapter_dir']}/{args.run}'")

    for it in range(1, args.iters + 1):
        tag = f"it{it:03d}"
        prev = None if it == 1 else f"it{it - 1:03d}"
        ids_path = os.path.join(local, f"ids_{tag}.txt")
        if not os.path.exists(ids_path):
            open(ids_path, "w").write("\n".join(pick(profiles, args.profiles_per_iter, random.Random(2000 + it))) + "\n")

        # 롤아웃 (sim run2 와 시뮬레이터를 같이 쓴다. 2026-10-08: run1 은 끝났고 run2 는 84번에서 계속 돈다)
        model = BASE_MODEL
        if prev:
            model = f"gym_{args.run}_{prev}"
            adapter(model)  # 이어서 돌릴 때를 위해 내렸다가 다시
            out = adapter(model, f"{T['adapter_dir']}/{args.run}/{prev}")
            if "Success" not in out:
                raise RuntimeError(f"어댑터 올리기 실패: {out[:200]}")
        ep_path = os.path.join(local, f"episodes_{tag}.jsonl")
        print(f"[{tag}] 롤아웃 (정책 {model})", flush=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "chatbot/gym/run.py"), "--ids-file", ids_path,
                        "--samples", str(args.samples), "--chatbot", "qwen8b", "--model", model, "--prompt", "short",
                        "--out", local, "--tag", tag, "--workers", str(args.workers), "--config", T["config"]],
                       check=True, stdout=open(os.path.join(local, f"rollout_{tag}.log"), "a"), stderr=subprocess.STDOUT)
        st = stats(ep_path) if os.path.exists(ep_path) else {"episodes": 0}
        want = len(open(ids_path).read().split()) * args.samples
        if st["episodes"] < 0.75 * want:  # 서버 장애로 롤아웃이 비면 학습하지 않고 멈춘다 (감시 스크립트가 이어서 다시)
            raise RuntimeError(f"롤아웃 부족: {st['episodes']}/{want}")
        print(f"[{tag}] {json.dumps({k: round(v, 3) for k, v in st.items()})}", flush=True)
        if prev:
            adapter(f"gym_{args.run}_{prev}")  # 롤아웃이 끝나면 내린다 (vLLM --max-loras 2)

        # 이점 → 샘플
        batch = os.path.join(local, f"batch_{tag}.jsonl")
        bs = build_batch(ep_path, batch)
        print(f"[{tag}] 샘플 {json.dumps(bs)}", flush=True)

        # 학습
        remote = f"{T['root']}/gym/{args.run}/{tag}"
        done = sh(f"ssh -o BatchMode=yes {T['host']} 'test -f {remote}/step_stats.json'").returncode == 0
        if not done:
            if T["wait_run1"]:
                train_window(TRAIN["54"]["host"])  # sim run2 와 54번 GPU 4–7 이 겹치지 않게
            sh(f"ssh -o BatchMode=yes {T['host']} 'cat > {T['root']}/gym/{args.run}/batch_{tag}.jsonl' < {batch}")
            pin = f"{T['root']}/gym/{args.run}/{prev}" if prev else "none"
            cmd = (f"cd {T['root']}/gym; export CUDA_VISIBLE_DEVICES={T['gpus']} HF_HOME={T['hf']} HF_HUB_OFFLINE=1; "
                   f"{T['env']}/bin/accelerate launch --num_processes {len(T['gpus'].split(','))} --mixed_precision bf16 "
                   f"gym_grpo_step.py --model {T['model']} --batch {args.run}/batch_{tag}.jsonl --policy_in {pin} "
                   f"--out {remote} {args.train_args} > {T['root']}/logs/gymgrpo_{args.run}_{tag}.log 2>&1")
            cmd = cmd.replace("$", "\\$")
            sh(f"ssh -o BatchMode=yes {T['host']} \"tmux kill-session -t gymgrpo 2>/dev/null; "
               f"tmux new-session -d -s gymgrpo '{cmd}'\"")
            print(f"[{tag}] 학습 시작 ({args.train_host} tmux gymgrpo)", flush=True)
            while True:
                time.sleep(30)
                r = sh(f"ssh -o BatchMode=yes {T['host']} 'test -f {remote}/step_stats.json && echo DONE; "
                       f"tmux has-session -t gymgrpo 2>/dev/null && echo RUNNING'")
                if "DONE" in r.stdout:
                    break
                if "RUNNING" not in r.stdout:
                    tail = sh(f"ssh -o BatchMode=yes {T['host']} 'tail -30 {T['root']}/logs/gymgrpo_{args.run}_{tag}.log'").stdout
                    raise RuntimeError(f"학습이 결과 없이 끝남:\n{tail}")
        step = json.loads(sh(f"ssh -o BatchMode=yes {T['host']} 'cat {remote}/step_stats.json'").stdout)
        print(f"[{tag}] 학습 {json.dumps(step)}", flush=True)

        # 어댑터 → 정책 서버 (27 은 같은 서버라 그대로)
        if T["copy_to"]:
            # 맥 디스크에 임시 파일을 두지 않고 바로 흘려보낸다 (2026-10-08: 맥 디스크가 차서 tar 가 잘려 어댑터 탑재 실패)
            dst = f"{T['adapter_dir']}/{args.run}/{tag}"
            unpack = f"rm -rf {dst} && mkdir -p {dst} && cd {dst} && tar -xf - && stat -c %s adapter_model.safetensors"
            pack = f"cd {remote} && tar -cf - adapter_config.json adapter_model.safetensors"
            # 서버끼리 직접 (맥 키를 에이전트로 빌려 씀, ~32MB/s). 2026-10-08: 맥 경유가 ~65KB/s 로 느려져 175MB 에 40분
            r = sh(f"ssh -A -o BatchMode=yes {T['host']} \"{pack} | ssh -o BatchMode=yes {USER}@{T['copy_to']} '{unpack}'\"")
            if r.returncode != 0:  # 에이전트에 키가 없으면 맥 경유
                r = sh(f"ssh -o BatchMode=yes {T['host']} '{pack}' | ssh -o BatchMode=yes {T['copy_to']} '{unpack}'")
            want = sh(f"ssh -o BatchMode=yes {T['host']} 'stat -c %s {remote}/adapter_model.safetensors'").stdout.strip()
            if r.returncode != 0 or r.stdout.strip().splitlines()[-1:] != [want]:
                raise RuntimeError(f"어댑터 복사 실패 (크기 {r.stdout.strip()} ≠ {want}): {r.stderr[-200:]}")
        with open(os.path.join(local, "log.jsonl"), "a") as f:
            f.write(json.dumps({"iter": it, "rollout": st, "batch": bs, "train": step}) + "\n")
        print(f"[{tag}] 반복 완료", flush=True)


if __name__ == "__main__":
    main()
