"""대화 롤아웃 · 평가. 프로필마다 --samples 번 → <out>/episodes.jsonl, 끝나면 요약 (논문 표 1: Score · Success · Failure).

    python chatbot/rlver/run.py --split test --chatbot qwen2.5-7b --template think --out out/rlver/eval_base_think
    python chatbot/rlver/run.py --summary out/rlver/eval_base_think

사용자 = 배경(data/rlver/backgrounds.csv) + 조합(compose.py, --combo 번호). 같은 번호면 같은 성격·태도·욕구라 챗봇 비교가 된다.
RLVER 원래 프로필로는 --profiles out/rlver/profiles_test.jsonl (profiles.py).
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
from backgrounds import OUT as BACKGROUNDS, read  # noqa: E402
from compose import Combos, assign_rank, sample_traits  # noqa: E402
from episode import run_episode  # noqa: E402
from llm import ROOT, Chat  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load_episodes(folder):
    path = os.path.join(folder, "episodes.jsonl")
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def mean_by(eps, key):
    tot, cnt = Counter(), Counter()
    for e in eps:
        tot[e.get(key)] += e["final_emotion"]
        cnt[e.get(key)] += 1
    return {str(k): round(tot[k] / cnt[k], 1) for k in sorted(cnt, key=str)}


def summarize(eps):
    n = max(1, len(eps))
    return {"episodes": len(eps),
            "score": sum(e["final_emotion"] for e in eps) / n,
            "success": sum(e["final_emotion"] >= 100 for e in eps) / n,
            "failure": sum(e["final_emotion"] < 10 for e in eps) / n,
            "reward": sum(e["reward"] for e in eps) / n,
            "format_fail": sum(not e["format_ok"] for e in eps) / n,
            "turns": sum(len(e["turns"]) - 1 for e in eps) / n,
            "by_cell": mean_by([{**e, "cell": f"{e.get('event')}·{e.get('disclosure')}"} for e in eps], "cell"),
            "by_need": mean_by(eps, "need"),
            "by_stance": mean_by(eps, "stance"), "by_task": mean_by(eps, "task")}


def print_summary(s):
    print(f"대화 {s['episodes']} · Score {s['score']:.1f} · Success {s['success']:.0%} · Failure {s['failure']:.0%}"
          f" · 보상 {s['reward']:.3f} · 형식 위반 {s['format_fail']:.0%} · 평균 턴 {s['turns']:.1f}")
    for t, v in {**s["by_cell"], **s["by_need"], **s["by_stance"]}.items():
        print(f"  {v:5.1f}  {t}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--split", default="test", help="train / test")
    ap.add_argument("--backgrounds", default=BACKGROUNDS)
    ap.add_argument("--combo", type=int, default=0, help="조합 번호 (같은 번호 = 같은 성격·태도·욕구)")
    ap.add_argument("--profiles", help="이미 만든 프로필 jsonl (RLVER 원래 프로필 등, 배경 대신)")
    ap.add_argument("--ids", help="쓸 프로필 id 목록 파일 (한 줄에 하나)")
    ap.add_argument("--n", type=int, default=0, help="앞에서 n 명만 (0 = 전부)")
    ap.add_argument("--per_cell", type=int, default=0, help="사건 × 털어놓는 정도 × 원하는 방식 칸마다 k 명만 (발화 맛보기)")
    ap.add_argument("--chatbot", default="qwen2.5-7b", help="config chatbots 의 이름")
    ap.add_argument("--model", help="챗봇 model 이름을 바꾼다 (vLLM 런타임 LoRA 어댑터 이름)")
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--template", choices=["bank", "bank_oracle", "guide", "think", "nothink", "sage"], default="bank",
                    help="bank = 전략 뱅크 (STRATEGY.md), bank_oracle = 원하는 방식·위험을 알려 준 상한, guide = 짧은 지침, think·nothink = RLVER 원래")
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
    if args.profiles:
        profiles = [json.loads(l) for l in open(args.profiles)]
    else:
        bgs = read(args.backgrounds)  # id 복구·event 계산은 read 가 한다
        profiles = [r for r in assign_rank(bgs) if r["split"] == args.split]
    if args.ids:
        keep = [l.strip() for l in open(args.ids) if l.strip()]
        by = {p["id"]: p for p in profiles}
        profiles = [by[i] for i in keep]
    if args.per_cell and not args.profiles:
        seen = {}
        for bg in profiles:
            t = sample_traits(bg, args.combo)
            seen.setdefault((bg["event"], t["disclosure"], t["need"]), []).append(bg)
        profiles = [bg for v in seen.values() for bg in v[:args.per_cell]]
    profiles = profiles[: args.n or None]

    os.makedirs(args.out, exist_ok=True)
    if not args.profiles:  # 배경 + 조합 (조합 생성은 캐시, 처음 한 번만 LLM)
        combos = Combos(os.path.join(ROOT, "out", "rlver", "combos.jsonl"), sim)
        with ThreadPoolExecutor(args.workers) as ex:
            profiles = list(ex.map(lambda bg: combos.get(bg, args.combo), profiles))
    done = {(e["id"], e["sample"]) for e in load_episodes(args.out)}
    jobs = [(p, s) for p in profiles for s in range(args.samples) if (p["id"], s) not in done]
    random.Random(0).shuffle(jobs)  # 같은 프로필 표본이 한꺼번에 몰리지 않게
    json.dump({**vars(args), "chatbot_cfg": bot_cfg}, open(os.path.join(args.out, "run_args.json"), "w"), indent=1)
    print(f"프로필 {len(profiles)} × {args.samples} → 남은 대화 {len(jobs)}")

    def one(job):
        p, s = job
        ep = run_episode(p, bot, sim, cfg, args.template, use_first_talk=not args.no_first_talk)
        extra = {k: p.get(k) for k in ("combo", "need", "stance", "effort")}  # event·disclosure 는 episode 가 넣는다
        return {**ep, **extra, "sample": s, "chatbot": bot_cfg["model"]}

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
