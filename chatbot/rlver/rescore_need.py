"""저장된 bank_jev 대화에 지금 문구의 need 질문만 다시 물어 원하는 방식 감지를 비교한다 (2026-10-25).

턴마다 그 턴까지의 사용자 발화 3개 창으로 need 만 묻고, 대화 동안 유지(sticky)한 마지막 값을 사용자 설정과 비교한다.
대화 내용은 이전 문구로 만든 그대로라 챗봇 답은 바뀌지 않는다 (감지 문구만 비교).

    python chatbot/rlver/rescore_need.py "out/rlver/1025)bank_jev_test" "out/rlver/1025)bank_jev_test_30b"
"""

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jev import NEED_CONF, NEED_QUESTION, Jev, window_state  # noqa: E402
from jev_client import call_jev, flatten  # noqa: E402

NAME = {"listen_vent": "경청", "deep_empathy": "공감", "practical_advice": "조언", None: "없음"}


def messages_upto(turns, i):
    out = []
    for t in turns[: i + 1]:
        out.append({"role": "user", "content": t["user"]})
        if "bot" in t and t is not turns[i]:
            out.append({"role": "assistant", "content": t["bot"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()
    j = Jev(workers=args.workers)

    def need_at(job):
        turns, i = job
        a = flatten(call_jev(j.session, window_state(messages_upto(turns, i)), {"need": NEED_QUESTION}).get("answers", {}))
        return a.get("need") if (a.get("need_conf") or 0) >= NEED_CONF and a.get("need") != "unclear" else None

    for f in args.folders:
        eps = [json.loads(l) for l in open(os.path.join(f, "episodes.jsonl"))]
        jobs = [(e["turns"], i) for e in eps for i, t in enumerate(e["turns"]) if "bot" in t]
        with ThreadPoolExecutor(args.workers) as ex:
            res = list(ex.map(need_at, jobs))
        k = 0
        old_c, new_c = Counter(), Counter()
        for e in eps:
            new = None
            for i, t in enumerate(e["turns"]):
                if "bot" in t:
                    new = res[k] or new
                    k += 1
            old = next((t["route"].get("need") for t in reversed(e["turns"]) if (t.get("route") or {}).get("need")), None)
            old_c[(e["need"], old)] += 1
            new_c[(e["need"], new)] += 1
        print(f"## {f}")
        for want in ("deep_empathy", "listen_vent", "practical_advice"):
            n = sum(v for (a, _), v in old_c.items() if a == want)
            fmt = lambda c: ", ".join(f"{NAME[b]} {v}" for (a, b), v in sorted(c.items(), key=lambda x: -x[1]) if a == want)  # noqa: E731
            print(f"  설정 {NAME[want]} {n}명: 이전 문구 {old_c[(want, want)]} 맞음 ({fmt(old_c)}) → 새 문구 {new_c[(want, want)]} 맞음 ({fmt(new_c)})")
    print(f"Jev 비용 ${j.cost:.3f}" if j.cost else "")


if __name__ == "__main__":
    main()
