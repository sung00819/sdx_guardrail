"""기존 배경(out/scenes_{train,test}.jsonl, ../gen_scene.py 결과)을 RLVER 프로필로 바꾼다 → out/rlver/profiles_{split}.jsonl

RLVER 그대로 + 더한 것: Big Five 연속 T 점수(+ 신경증 하위 특성), 대화 노력 1~5, C 돕는 사람을 대하는 태도,
D 털어놓는 정도, 숨겨진 욕구 4개 (prompts.NEEDS). 임상 축(셀·가드레일 코드)은 쓰지 않는다.
D 는 사용자마다 고정이고 두 가지다: 배경에 숨긴 위험 사실이 있으면 overt (매우 위험, 직접 말함),
없으면 subtle (은은하게 위험, 끝까지 돌려 말함). 이전 D 의 부인·숨김은 subtle 에 합쳤다.
- 그대로 쓰는 것: 페르소나, 사건 배경, 핵심 고통, 숨긴 위험 사실, 감정별 말투, 직접 물을 때의 반응, 첫 메시지
- 다시 쓰는 것: 숨겨진 욕구 (이전 6개 → 4개, 같은 뜻은 유지하고 나머지로 균등하게 맞춤),
  인물별 감정 규칙 (emotion_rises_when / falls_when, 이전 욕구에 맞춰 썼으므로) — LLM 한 번
- 빼는 것: 다른 사람 이야기 (O 셀), 사용자 자신이 우울한 경우가 아니다

    python chatbot/rlver/convert_scenes.py --split test --limit 5
    python chatbot/rlver/convert_scenes.py              # train, test
"""

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from llm import ROOT, Chat  # noqa: E402
from prompts import BACKGROUND, DISCLOSURE, FIXED_RULES, NEEDS, RULES_PROMPT  # noqa: E402
from sim_text import BIG_FIVE, EFFORT, N_FACET, STANCE  # noqa: E402  기존 행동 설명을 그대로 쓴다

OUT = os.path.join(ROOT, "out", "rlver")
# 이전 욕구 → 새 욕구 (같은 뜻만). be_left_alone · test_if_safe_to_disclose 는 남는 자리에 나눈다
NEED_MAP = {"be_heard": "listen_vent", "feelings_validated": "deep_empathy", "practical_help": "practical_advice",
            "not_be_judged": "not_my_fault"}
FACTOR_NAME = {"O": "Openness", "C": "Conscientiousness", "E": "Extraversion", "A": "Agreeableness",
               "N": "Neuroticism"}


def assign_needs(rows, rng):
    """4개를 균등하게. 이전 욕구가 같은 뜻이면 할당량 안에서 유지한다"""
    quota = {k: len(rows) // 4 + (i < len(rows) % 4) for i, k in enumerate(NEEDS)}
    need, left = {}, []
    order = rows[:]
    rng.shuffle(order)
    for r in order:
        k = NEED_MAP.get(r["seed"]["hidden_need"])
        if k and quota[k] > 0:
            need[r["id"]], quota[k] = k, quota[k] - 1
        else:
            left.append(r["id"])
    pool = [k for k, q in quota.items() for _ in range(q)]
    rng.shuffle(pool)
    need.update(zip(left, pool))
    return need


def persona_text(seed, persona):
    """SAGE 인물 묘사 형식 + 성격 수치·말투 시드"""
    b5 = seed["big_five"]
    traits = [BIG_FIVE[(f, lv)] for f, lv in seed["big_five_salient"].items()]
    if seed.get("n_facet"):
        traits.append(N_FACET[seed["n_facet"]])
    lines = [f"* Name: {persona.get('name', seed['name'])}", f"* Age: {persona.get('age', seed['age'])}",
             f"* Gender: {persona.get('gender', seed['gender'])}", f"* Occupation: {persona.get('occupation', seed['occupation'])}",
             f"* Living situation: {persona.get('living_situation', seed.get('life_situation', ''))}",
             "* Personal hobbies:\n" + "\n".join(f"{i}. {h}" for i, h in enumerate(persona.get("hobbies", []), 1)),
             f"* Habits and behavioral characteristics:\n{persona.get('habits_and_behavior', '')}",
             "* Personality (Big Five, T scores, mean 50, SD 10): "
             + ", ".join(f"{FACTOR_NAME[f]} {round(b5[f])}" for f in "OCEAN"),
             "\n".join(f"  - {t}" for t in traits),
             f"* Speaking style:\n{persona.get('speaking_style', '')}",
             f"* Message length and form: {EFFORT[seed['effort']]}",
             f"* Toward someone trying to help: {STANCE[seed['stance']]}"]
    if persona.get("example_messages"):
        lines.append("* Example messages to a friend:\n" + "\n".join(f"  - {m}" for m in persona["example_messages"]))
    return "\n".join(lines)


def disclosure_type(scene):
    return "overt" if scene.get("risk_fact") else "subtle"


def hidden_text(scene):
    out = [f"- Real worry: {scene['core_concern']}",
           "- You are depressed: low mood, tiredness and self-blame color how you talk, without naming 'depression'."]
    if scene.get("risk_fact"):
        out.append(f"- Risk sign: {scene['risk_fact']}")
    else:
        out.append("- Quiet signs: hopelessness and a vague wish to disappear for a while, never a plan.")
    return "\n".join(out)


def bullets(xs):
    return "\n".join(f"  * {x}" for x in xs)


def convert(row, need, llm):
    seed, persona, scene = row["seed"], row["persona"], row["scene"]
    p_text, hidden = persona_text(seed, persona), hidden_text(scene)
    kind = disclosure_type(scene)
    prompt = RULES_PROMPT.format(persona=p_text, background=scene["background"], hidden=hidden, disclosure=DISCLOSURE[kind],
                                 need=NEEDS[need], fixed=FIXED_RULES)
    rules = None
    for _ in range(3):
        text = llm([{"role": "user", "content": prompt}])
        try:
            got = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if got["emotion_rises_when"] and got["emotion_falls_when"]:
                rules = got
                break
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
            pass
    if not rules:
        raise ValueError(f"{row['id']}: 감정 규칙 생성 실패")
    style = scene.get("style_by_emotion", {})
    background = BACKGROUND.format(
        topic=scene["topic"], story=scene["background"], hidden=hidden, disclosure=DISCLOSURE[kind],
        safety_reaction=scene.get("safety_check_reaction", ""), high=style.get("high", ""),
        medium=style.get("medium", ""), low=style.get("low", ""), rises=bullets(rules["emotion_rises_when"]),
        falls=bullets(rules["emotion_falls_when"]), fixed=FIXED_RULES, need=NEEDS[need])
    return {"id": row["id"], "persona": p_text, "background": background, "task": NEEDS[need], "need": need,
            "first_talk": scene.get("opening_message"), "disclosure": kind,
            "big_five": seed["big_five"], "n_facet": seed.get("n_facet"), "effort": seed["effort"],
            "stance": seed["stance"], "old_disclosure": seed.get("disclosure"), "old_need": seed["hidden_need"],
            "rules": rules, "source": "scenes"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
    ap.add_argument("--split", choices=["train", "test", "both"], default="both")
    ap.add_argument("--scenes", help="배경 파일 (기본 out/scenes_<split>.jsonl)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    llm = Chat({**cfg["simulator"], "temperature": 0.7, "max_tokens": 1500})
    os.makedirs(OUT, exist_ok=True)
    for split in (["train", "test"] if args.split == "both" else [args.split]):
        src = args.scenes or os.path.join(ROOT, "out", f"scenes_{split}.jsonl")
        rows = [json.loads(l) for l in open(src)]
        rows = [r for r in rows if not r.get("error") and not r.get("dup") and r.get("scene")]
        other = sum(r["seed"]["cell"] == "O" for r in rows)
        rows = [r for r in rows if r["seed"]["cell"] != "O"][: args.limit or None]
        need = assign_needs(rows, random.Random(args.seed))  # 할당은 전체(limit 뒤) 기준이라 결과 파일에 need 를 남긴다
        out = os.path.join(OUT, f"profiles_{split}.jsonl")
        done = {json.loads(l)["id"] for l in open(out)} if os.path.exists(out) else set()
        todo = [r for r in rows if r["id"] not in done]
        print(f"{split}: 배경 {len(rows)} (다른 사람 이야기 {other} 제외), 새로 {len(todo)}")
        print("  털어놓는 정도", dict(Counter(disclosure_type(r["scene"]) for r in rows)))
        print("  욕구", dict(Counter(need.values())), "· 유지",
              sum(NEED_MAP.get(r["seed"]["hidden_need"]) == need[r["id"]] for r in rows))
        with open(out, "a", encoding="utf-8") as f, ThreadPoolExecutor(args.workers) as ex:
            for i, p in enumerate(ex.map(lambda r: convert(r, need[r["id"]], llm), todo), 1):
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
                f.flush()
                if i % 50 == 0:
                    print(f"  {i}/{len(todo)}")


if __name__ == "__main__":
    main()
