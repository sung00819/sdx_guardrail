"""설계 하나의 질문으로 데이터의 사용자 발화를 Jev 채점한다. 발화 하나 = Jev 호출 한 번.

사용법 (저장소 맨 위에서):
    python3 common/run_judge.py --design expert11 --source cradle_test --dry-run
    python3 common/run_judge.py --design expert11 --source cradle_test       # → out/t11e_cradle_test.jsonl
    python3 common/run_judge.py --design expert11 --source attunebench
    python3 common/run_judge.py --design expert11 --source cradle_test --judge kev   # → out/judges/kev_t11e_cradle_test.jsonl
    python3 common/run_judge.py ... --judge kev --tag kev9b_ft1   # 학습한 Kev → out/judges/kev9b_ft1_t11e_cradle_test.jsonl

출력: 한 줄 = 발화 하나. {key, judge, source, gold, <질문 답>, current, raw}
      옆에 <출력>.questions.json 으로 그때 쓴 질문을 남기고, 다른 질문으로 같은 파일에 이어 쓰면 막는다 (결과 덮어쓰기 방지).
      중단 후 같은 명령으로 다시 실행하면 남은 것만 이어서 채점한다.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import data
from jev_client import JUDGE_MODELS, call_jev, flatten, make_session
from rules import DESIGNS, ROOT, load_design


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True, choices=DESIGNS)
    ap.add_argument("--source", required=True, help="cradle_test / cradle_validation / cradle_train / attunebench / "
                                                    "empathetic_dialogues / esconv / other_check")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--keys", help="이 파일에 적힌 key(한 줄에 하나)만 채점. --output 과 함께 쓴다")
    ap.add_argument("--judge", default="jev", choices=sorted(JUDGE_MODELS), help="jev(OpenRouter) / kev / clm (54번 서버)")
    ap.add_argument("--tag", help="출력 파일 이름 앞에 붙일 이름 (기본: --judge, kev 는 확정 판정기 kev4b_ft2). "
                                  "out/judges/kev_* 는 학습 전 공개 Kev-9B 기준선이라 다른 이름으로 둔다")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--output")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    args.tag = args.tag or {"kev": "kev4b_ft2"}.get(args.judge)

    q = load_design(args.design, "questions")
    judges, version = q.JUDGES, q.VERSION
    rows = data.load(args.source, args.sample, args.seed)
    if args.keys:
        keep = set(open(args.keys).read().split())
        rows = [r for r in rows if r["key"] in keep]
        if not args.output:
            sys.exit("--keys 를 쓸 때는 --output 을 주세요")
    name = f"{version}_{args.source}{f'_s{args.sample}' if args.sample else ''}.jsonl"
    # Jev 결과는 예전 자리, 다른 판정기는 out/judges/ 에 이름 앞에 판정기를 붙여 따로 둔다 (결과를 섞지 않는다)
    out_path = args.output or (os.path.join(ROOT, "out", name) if args.judge == "jev"
                               else os.path.join(ROOT, "out", "judges", f"{args.tag or args.judge}_{name}"))

    jobs = [(r, n) for r in rows for n in judges]
    if args.dry_run:
        chars = sum(len(r["context"]) + len(r["current"]) for r, _ in jobs)
        print(f"{len(rows)} 발화 × {len(judges)} 호출 = {len(jobs)} 호출, 보낼 글자 {chars:,} (≈{chars // 4:,} 토큰 + 질문)")
        return

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    spec_path = out_path + ".questions.json"
    spec = {"version": version, "model": args.tag or JUDGE_MODELS[args.judge][1], "judges": judges}
    if os.path.exists(spec_path):
        with open(spec_path) as f:
            if json.load(f) != spec:
                sys.exit(f"{out_path} 는 다른 질문으로 만든 결과입니다. --output 을 새 이름으로 주세요.")
    else:
        with open(spec_path, "w") as f:
            json.dump(spec, f, ensure_ascii=False, indent=1)

    done = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            done = {(d["key"], d["judge"]) for d in map(json.loads, f) if d}
    todo = [(r, n) for r, n in jobs if (r["key"], n) not in done]
    print(f"호출 {len(jobs)}, 완료 {len(done)}, 남음 {len(todo)} → {out_path}")

    session = make_session(args.workers, args.judge)
    cost = 0.0
    with open(out_path, "a") as out, ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(call_jev, session, {"context": r["context"], "current": r["current"]}, judges[n]): (r, n)
                   for r, n in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            r, n = futures[fut]
            try:
                raw = fut.result()
            except Exception as e:
                print(f"[{r['key']} {n}] 실패: {e}", file=sys.stderr)
                continue  # 저장하지 않음 → 재실행 시 다시 시도
            cost += (raw.get("usage") or {}).get("cost") or 0
            rec = {"key": r["key"], "judge": n, "source": r["source"], "gold": r["gold"],
                   **flatten(raw.get("answers", {})), "current": r["current"], "raw": raw}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 500 == 0:
                out.flush()
                print(f"{i}/{len(todo)}  누적 비용 ${cost:.4f}")
    print(f"완료. 이번 실행 비용 ${cost:.4f}")


if __name__ == "__main__":
    main()
