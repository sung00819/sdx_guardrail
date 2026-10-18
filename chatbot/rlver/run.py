"""대화 롤아웃 · 평가. 프로필마다 --samples 번 → <out>/episodes.jsonl, 끝나면 요약 (논문 표 1: Score · Success · Failure).

    python chatbot/rlver/run.py --split test --chatbot qwen2.5-7b --template think --out out/rlver/eval_base_think
    python chatbot/rlver/run.py --summary out/rlver/eval_base_think

이미 있는 (id, sample) 는 건너뛰므로 끊겨도 같은 명령으로 이어 간다.
"""

import argparse
import json
import os
import random
import sys
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from episode import run_episode  # noqa: E402
from llm import ROOT, Chat  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load_episodes(folder):
    path = os.path.join(folder, "episodes.jsonl")
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def summarize(eps):
    n = max(1, len(eps))
    by_task = Counter()
    for e in eps:
        by_task[e["task"]] += e["final_emotion"]
    tasks = Counter(e["task"] for e in eps)
    return {"episodes": len(eps),
            "score": sum(e["final_emotion"] for e in eps) / n,
            "success": sum(e["final_emotion"] >= 100 for e in eps) / n,
            "failure": sum(e["final_emotion"] < 10 for e in eps) / n,
            "reward": sum(e["reward"] for e in eps) / n,
            "format_fail": sum(not e["format_ok"] for e in eps) / n,
            "turns": sum(len(e["turns"]) - 1 for e in eps) / n,
            "by_task": {t: round(by_task[t] / tasks[t], 1) for t in sorted(tasks)}}


def print_summary(s):
    print(f"대화 {s['episodes']} · Score {s['score']:.1f} · Success {s['success']:.0%} · Failure {s['failure']:.0%}"
          f" · 보상 {s['reward']:.3f} · 형식 위반 {s['format_fail']:.0%} · 평균 턴 {s['turns']:.1f}")
    for t, v in s["by_task"].items():
        print(f"  {v:5.1f}  {t}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--split", default="test", help="train / test (out/rlver/profiles_<split>.jsonl)")
    ap.add_argument("--profiles", help="프로필 파일을 직접 (split 대신)")
    ap.add_argument("--ids", help="쓸 프로필 id 목록 파일 (한 줄에 하나)")
    ap.add_argument("--n", type=int, default=0, help="앞에서 n 명만 (0 = 전부)")
    ap.add_argument("--chatbot", default="qwen2.5-7b", help="config chatbots 의 이름")
    ap.add_argument("--model", help="챗봇 model 이름을 바꾼다 (vLLM 런타임 LoRA 어댑터 이름)")
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--template", choices=["think", "nothink", "sage"], default="think")
    ap.add_argument("--samples", type=int, default=1, help="프로필마다 대화 수 (GRPO 그룹 크기)")
    ap.add_argument("--no_first_talk", action="store_true", help="테스트 프로필의 고정 첫 발화 대신 시뮬레이터가 연다")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--out")
    ap.add_argument("--summary", help="이미 돌린 폴더 요약만")
    args = ap.parse_args()
    if args.summary:
        print_summary(summarize(load_episodes(args.summary)))
        return

    cfg = json.load(open(args.config))
    bot_cfg = dict(cfg["chatbots"][args.chatbot])
    if args.model:
        bot_cfg["model"] = args.model
    if args.temperature is not None:
        bot_cfg["temperature"] = args.temperature
    bot, sim = Chat(bot_cfg), Chat(cfg["simulator"])
    path = args.profiles or os.path.join(ROOT, "out", "rlver", f"profiles_{args.split}.jsonl")
    profiles = [json.loads(l) for l in open(path)]
    if args.ids:
        keep = [l.strip() for l in open(args.ids) if l.strip()]
        by = {p["id"]: p for p in profiles}
        profiles = [by[i] for i in keep]
    profiles = profiles[: args.n or None]

    os.makedirs(args.out, exist_ok=True)
    done = {(e["id"], e["sample"]) for e in load_episodes(args.out)}
    jobs = [(p, s) for p in profiles for s in range(args.samples) if (p["id"], s) not in done]
    random.Random(0).shuffle(jobs)  # 같은 프로필 표본이 한꺼번에 몰리지 않게
    json.dump({**vars(args), "chatbot_cfg": bot_cfg}, open(os.path.join(args.out, "run_args.json"), "w"), indent=1)
    print(f"프로필 {len(profiles)} × {args.samples} → 남은 대화 {len(jobs)}")

    def one(job):
        p, s = job
        ep = run_episode(p, bot, sim, cfg, args.template, use_first_talk=not args.no_first_talk)
        return {**ep, "sample": s, "chatbot": bot_cfg["model"]}

    fails = 0
    with open(os.path.join(args.out, "episodes.jsonl"), "a") as f, ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                f.write(json.dumps(fu.result(), ensure_ascii=False) + "\n")
                f.flush()
            except Exception:
                fails += 1
                traceback.print_exc()
            if i % 10 == 0:
                print(f"  {i}/{len(jobs)}")
    if fails:
        print(f"실패 {fails}개 (다시 돌리면 이어서)")
    s = summarize(load_episodes(args.out))
    json.dump(s, open(os.path.join(args.out, "summary.json"), "w"), indent=1, ensure_ascii=False)
    print_summary(s)


if __name__ == "__main__":
    main()
