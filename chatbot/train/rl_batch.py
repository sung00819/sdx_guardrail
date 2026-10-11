"""GRPO 반복 하나의 롤아웃(run_episode --samples G) → 턴 샘플 + 그룹 이점.

이점 = (R − 그룹 평균) / (그룹 표준편차 + eps), 그룹 = 같은 프로필의 G 개 에피소드. 모두 같은 보상이면 버린다.
에피소드의 모든 챗봇 턴이 같은 이점을 받는다 (입력 = bot_input, 정답 = 그 턴의 답).

  python chatbot/train/rl_batch.py out/rl/it001 out/rl/batch_it001.jsonl
"""

import glob
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
from textsim import max_similarity, question_head  # noqa: E402

# 턴 단위 보정: 에피소드 이점만 쓰면 보상 높은 대화 안의 반복 턴까지 강화된다 (run2 it001→003: 반복 턴 11→17%).
# 이전 답 되풀이(유사도 ≥ 0.8)·할 수 없는 행동을 약속한 턴은 이점에서 TURN_PENALTY 를 뺀다.
TURN_PENALTY = 1.0
# 2026-10-09 (run3): 질문 여러 개(run2 에서 4→15%)·같은 질문 틀 세 턴 연속(normal/support)도 턴 단위로 작게 뺀다
MULTI_Q_PENALTY = 0.5
TEMPLATE_PENALTY = 0.3
LONG_PENALTY = 0.3  # urgent·assess 답 450자 초과


def main(folder, out_path, eps_std=0.05):
    groups = defaultdict(list)
    for p in glob.glob(os.path.join(folder, "*.json")):
        e = json.load(open(p))
        groups[e["id"]].append(e)
    rows, used, flat = [], 0, 0
    for gid, eps in groups.items():
        if len(eps) < 2:
            continue
        rs = [e["reward"]["total"] for e in eps]
        mu, sd = statistics.mean(rs), statistics.pstdev(rs)
        if sd < 1e-6:
            flat += 1
            continue
        used += 1
        for e, r in zip(eps, rs):
            adv = (r - mu) / (sd + eps_std)  # eps_std: 거의 같은 보상 그룹에서 이점이 튀지 않게
            prev, heads = [], []
            for i, t in enumerate(e["turns"]):
                if "bot_input" not in t or not t.get("bot", "").strip():
                    continue
                bad = max_similarity(t["bot"], prev) >= 0.8 or (t.get("check") or {}).get("impossible_action")
                prev.append(t["bot"])
                h = question_head(t["bot"])
                template = h is not None and heads[-2:] == [h, h]
                heads.append(h)
                pen = (TURN_PENALTY if bad else 0) + (MULTI_Q_PENALTY if t["bot"].count("?") > 1 else 0) \
                    + (TEMPLATE_PENALTY if template else 0) \
                    + (LONG_PENALTY if t["guardrail"]["response"] in ("urgent", "assess") and len(t["bot"]) > 450 else 0)
                rows.append({"messages": t["bot_input"], "completion": t["bot"], "adv": adv, "pen": pen,
                             "meta": {"id": gid, "sample": e.get("sample"), "turn": i + 1, "cell": e["cell"],
                                      "response": t["guardrail"]["response"], "R": r}})
    # 턴 감점은 배치 평균을 빼서 넣는다: 그대로 빼면 이점 평균이 음수가 되어 모든 답의 확률을 함께 낮춘다
    mean_pen = sum(r["pen"] for r in rows) / max(1, len(rows))
    for r in rows:
        r["adv"] = round(r["adv"] - r.pop("pen") + mean_pen, 4)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"그룹 {len(groups)} (사용 {used}, 보상 같아 버림 {flat}) → 턴 샘플 {len(rows)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
