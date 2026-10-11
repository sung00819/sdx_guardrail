"""선생 에피소드(policy turn_strong) → SFT 샘플. 입력은 챗봇이 실제로 받은 형식 그대로(bot_input), 정답은 선생 답.

거르기
  에피소드: T1 플래그가 없음
  턴: 이전 답 되풀이 아님(유사도 < 0.8) · 그 답에 해로운 분류가 없음 · 질문 ≤ 1개 · 사용자가 받아들임(감정 변화 ≥ 0)
      · assess/urgent 턴에서 대화를 끝내거나 화제를 돌리지 않음

  python chatbot/sim/build_sft.py out/sim_runs/sft_gen out/sft/train.jsonl
"""

import glob
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from penalty import TIER  # noqa: E402
from textsim import max_similarity  # noqa: E402

BAD = ["harmful_info", "harmful_validation", "false_reassurance", "dependency", "medical_advice", "judgment",
       "keep_secret"]


def turn_ok(t, prev_bots=()):
    c, g = t.get("check") or {}, t["guardrail"]
    if max_similarity(t["bot"], prev_bots) >= 0.8:  # 이전 답 되풀이 (선생도 14% 턴에서 했다 → SFT 가 반복을 배웠다)
        return False, "repeat"
    if any(c.get(k) for k in BAD):
        return False, "harmful"
    if c.get("questions", t["bot"].count("?")) > 1:
        return False, "multi_question"
    if t["sim"]["change"] < 0:
        return False, "not_accepted"
    if g["response"] in ("assess", "urgent") and c.get("ended_or_switched"):
        return False, "abandon"
    if not t["bot"].strip():
        return False, "empty"
    return True, ""


def main(folder, out_path):
    eps = [json.load(open(p)) for p in glob.glob(os.path.join(folder, "*.json"))]
    samples, why = [], Counter()
    for e in eps:
        if any(TIER.get(f) == "T1" for f in e.get("flags", {})):
            why["episode_T1"] += 1
            continue
        prev = []
        for i, t in enumerate(e["turns"]):
            if "bot_input" not in t:
                continue
            ok, reason = turn_ok(t, prev)
            prev.append(t["bot"])
            if not ok:
                why[reason] += 1
                continue
            samples.append({"messages": t["bot_input"] + [{"role": "assistant", "content": t["bot"]}],
                            "meta": {"id": e["id"], "turn": i + 1, "cell": e["cell"], "response": t["guardrail"]["response"],
                                     "context": t["guardrail"]["context"], "episode_reward": e["reward"]["total"]}})
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"에피소드 {len(eps)} → 샘플 {len(samples)} (제외: {dict(why)})")
    print("대응 수준별:", dict(Counter(s["meta"]["response"] for s in samples)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
