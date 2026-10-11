"""기준 봇 에피소드로 보상을 검증한다: 정책별 평균, 같은 프로필 안에서의 순위 일치.

  python chatbot/sim/analyze.py out/sim_runs/refcheck

보상 변형도 같이 계산한다 (같은 에피소드, 공식만 다름):
  now     0.4·감정_끝/100 + 0.6·위험감소                 (지금)
  gain    0.4·(감정_끝−시작)/(100−시작) + 0.6·위험감소     (감정 상승폭)
"""

import glob
import json
import os
import sys
from collections import defaultdict
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from policies import ORDER  # noqa: E402
from sim_text import INITIAL_EMOTION  # noqa: E402


def variants(e):
    start = INITIAL_EMOTION[e["cell"]]
    risk = e["reward"]["risk_drop"]
    if e["checkin_start"]["text"] == e["checkin_end"]["text"]:
        risk = 0.0  # 상태가 그대로면 Jev 잡음을 지운다
    return {"now": 0.4 * e["emotion_end"] / 100 + 0.6 * risk,
            "gain": 0.4 * (e["emotion_end"] - start) / (100 - start) + 0.6 * risk,
            "emotion": e["emotion_end"], "risk_drop": risk}


def main(folder):
    eps = [json.load(open(f)) for f in glob.glob(os.path.join(folder, "*.json"))]
    pols = [p for p in ORDER if any(e["policy"] == p for e in eps)]
    by = defaultdict(dict)  # 프로필 → 정책 → 변형
    for e in eps:
        by[e["id"]][e["policy"]] = {**variants(e), "cell": e["cell"]}

    print(f"에피소드 {len(eps)}개, 프로필 {len(by)}개\n")
    print(f"{'정책':12s} {'n':>3s} {'감정_끝':>7s} {'위험감소':>8s} {'R_now':>7s} {'R_gain':>7s}  H셀 R_gain")
    for p in pols:
        rows = [v[p] for v in by.values() if p in v]
        h = [r for r in rows if r["cell"] == "H"]
        mean = lambda k, rs=rows: sum(r[k] for r in rs) / len(rs)  # noqa: E731
        print(f"{p:12s} {len(rows):3d} {mean('emotion'):7.1f} {mean('risk_drop'):8.3f} {mean('now'):7.3f} "
              f"{mean('gain'):7.3f}  {mean('gain', h) if h else float('nan'):.3f}")

    # 같은 프로필 안에서 기대 순위(ORDER)와 맞는 쌍의 비율
    print("\n같은 프로필 안에서 기대 순서와 맞는 쌍 (앞 정책 R > 뒤 정책 R)")
    for k in ("now", "gain"):
        agree = total = 0
        for v in by.values():
            for a, b in combinations([p for p in pols if p in v], 2):
                total += 1
                agree += v[a][k] > v[b][k]
        print(f"  R_{k}: {agree}/{total} = {agree / max(total, 1):.0%}")
    print("\n쌍별 (R_gain 기준, 앞이 이긴 프로필 수)")
    for a, b in combinations(pols, 2):
        both = [v for v in by.values() if a in v and b in v]
        print(f"  {a:>10s} > {b:<10s} {sum(v[a]['gain'] > v[b]['gain'] for v in both)}/{len(both)}")


if __name__ == "__main__":
    main(sys.argv[1])
