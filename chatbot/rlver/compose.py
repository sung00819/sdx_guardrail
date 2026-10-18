"""배경 + 나중에 조합하는 속성 → RLVER 프로필 (페르소나 글 · 배경 글).

배경은 고정, 나머지는 조합 (배경 id 와 --combo 번호로 고정 시드, 같은 조합 = 같은 사용자):
- 원하는 대응 방식 3개 × 털어놓는 정도 high/low: j = (rank + combo) mod 6 → 방식 j mod 3, 털어놓는 정도 j // 3.
  rank 는 split·event 안 순번 (assign_rank) → split·event 안에서 6칸 균등, 조합 0~5 이면 배경마다 6칸을 한 번씩
- C 태도: ../build_profile.py STANCE 비율
- Big Five T 점수: 나이·성별 보정 + 우울 이동 (severe 0.8 · mild 0.6 배, severe 10% 는 이동 없음 = 겉으로 멀쩡) + 태도 보정,
  N ≥ 60 이면 신경증 하위 특성 (자해 위험이면 충동성·취약성 2배). ../build_profile.py 와 같은 상수
- 대화 노력 1~5: 3 + 0.5·zE + 0.3·zC + 잡음 + 태도 보정
- 사건 event (mild/severe): 배경에 고정 (backgrounds.py)
조합마다 LLM 한 번: 습관·취미·말투·감정별 말투·직접 물을 때의 반응·인물별 감정 규칙. 결과는 캐시 파일에 남긴다.
"""

import hashlib
import json
import os
import random
import re
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import build_profile as bp  # noqa: E402
from prompts import (BACKGROUND, DISCLOSURE, FIXED_RULES, NEED_SAY, NEEDS, RULES_EXTRA, RULES_EXTRA_KEYS,  # noqa: E402
                     RULES_PROMPT)
from sim_text import BIG_FIVE, EFFORT, N_FACET, STANCE  # noqa: E402

DEPRESSED_SCALE = {"severe": 0.8, "mild": 0.6}
MASKED_P = {"severe": 0.10}
FACTOR_NAME = {"O": "Openness", "C": "Conscientiousness", "E": "Extraversion", "A": "Agreeableness",
               "N": "Neuroticism"}
SELF_HARM = re.compile(r"self-harm|cutting|cut (him|her)self|hurt (him|her)self|burn", re.I)


def assign_rank(bgs):
    """split·event 안 순번 (id 해시 순). 방식·털어놓는 정도를 고르게 나누는 데 쓴다"""
    groups = {}
    for bg in sorted(bgs, key=lambda b: hashlib.md5(b["id"].encode()).hexdigest()):
        groups.setdefault((bg.get("split"), bg["event"]), []).append(bg)
    for g in groups.values():
        for i, bg in enumerate(g):
            bg["rank"] = i
    return bgs


def sample_traits(bg, combo):
    rng = random.Random(f"{bg['id']}:{combo}")
    j = (int(bg["rank"]) + combo) % (2 * len(NEEDS))
    need, disclosure = list(NEEDS)[j % len(NEEDS)], ("high", "low")[j // len(NEEDS)]
    stance = bp.pick(rng, bp.STANCE)
    age, kind = int(bg["age"]), bg["event"]
    masked = rng.random() < MASKED_P.get(kind, 0)
    scores = {}
    for f in bp.FACTORS:
        mu = 50 + bp.AGE_SLOPE.get(f, 0) * (age - 25) / 10 + (bp.FEMALE_SHIFT.get(f, 0) if bg["gender"] == "female" else 0)
        if not masked:
            mu += bp.CLINICAL_SHIFT.get(f, 0) * DEPRESSED_SCALE[kind]
        mu += bp.STANCE_SHIFT[stance].get(f, 0)
        scores[f] = round(min(80, max(20, rng.gauss(mu, 10))))
    salient = {f: ("high" if t > 50 else "low") for f, t in scores.items() if abs(t - 50) >= bp.SALIENT_T}
    if not salient:
        f = max(scores, key=lambda f: abs(scores[f] - 50))
        salient = {f: "high" if scores[f] >= 50 else "low"}
    facet = None
    if scores["N"] >= 60:
        boost = bp.SELF_HARM_FACET_BOOST if SELF_HARM.search(bg.get("risk_fact", "")) else {}
        facet = bp.pick(rng, {x: boost.get(x, 1.0) for x in bp.N_FACETS})
    effort = bp.conversation_effort(rng, scores, stance)
    return {"need": need, "disclosure": disclosure, "stance": stance, "big_five": scores, "big_five_salient": salient, "n_facet": facet,
            "masked": masked, "effort": effort}


def persona_text(bg, t, details):
    traits = [BIG_FIVE[(f, lv)] for f, lv in t["big_five_salient"].items()]
    if t["n_facet"]:
        traits.append(N_FACET[t["n_facet"]])
    return "\n".join([
        f"* Name: {bg['name']}", f"* Age: {bg['age']}", f"* Gender: {bg['gender']}",
        f"* Occupation: {bg['occupation']}", f"* Lives in: {bg['city'] + ', ' if bg.get('city') else ''}South Korea",
        "* Personal hobbies:\n" + "\n".join(f"{i}. {h}" for i, h in enumerate(details.get("hobbies", []), 1)),
        f"* Habits and behavioral characteristics:\n{details.get('habits_and_behavior', '')}",
        "* Personality (Big Five, T scores, mean 50, SD 10): "
        + ", ".join(f"{FACTOR_NAME[f]} {t['big_five'][f]}" for f in "OCEAN"),
        "\n".join(f"  - {x}" for x in traits),
        f"* Speaking style:\n{details.get('speaking_style', '')}",
        f"* Message length and form: {EFFORT[t['effort']]}",
        f"* Toward someone trying to help: {STANCE[t['stance']]}"])


def hidden_text(bg):
    out = [f"- Real worry: {bg['core_concern']}",
           "- You are depressed: low mood, tiredness and self-blame color how you talk, without naming 'depression'."]
    if bg["event"] == "severe":
        out.append(f"- Risk sign: {bg['risk_fact']}")
    else:  # mild: 자살·자해 신호 없이 우울감만
        out.append("- No thoughts of suicide or self-harm; if asked, you say so honestly.")
    return "\n".join(out)


def bullets(xs):
    return "\n".join(f"  * {x}" for x in xs)


def generate(bg, t, llm):
    """LLM 한 번: 페르소나 세부 + 감정별 말투 + 직접 물을 때의 반응 + 인물별 감정 규칙"""
    prompt = RULES_PROMPT.format(persona=persona_text(bg, t, {}), background=bg["background"], hidden=hidden_text(bg),
                                 disclosure=DISCLOSURE[bg["event"], t["disclosure"]], need=NEEDS[t["need"]], fixed=FIXED_RULES,
                                 extra=RULES_EXTRA, extra_keys=RULES_EXTRA_KEYS.replace("{{", "{").replace("}}", "}"))
    keys = ("emotion_rises_when", "emotion_falls_when", "habits_and_behavior", "hobbies", "speaking_style",
            "style_by_emotion", "safety_check_reaction")
    for _ in range(3):
        text = llm([{"role": "user", "content": prompt}])
        try:
            got = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if all(got.get(k) for k in keys):
                return {k: got[k] for k in keys}
        except (AttributeError, json.JSONDecodeError):
            pass
    raise ValueError(f"{bg['id']}: 조합 생성 실패")


def build(bg, combo, gen):
    """조합 시드 + 생성 결과 → 시뮬레이터 프로필"""
    t = sample_traits(bg, combo)
    style = gen["style_by_emotion"]
    background = BACKGROUND.format(
        topic=bg["topic"], story=bg["background"], hidden=hidden_text(bg), disclosure=DISCLOSURE[bg["event"], t["disclosure"]],
        safety_reaction=gen["safety_check_reaction"], high=style.get("high", ""), medium=style.get("medium", ""),
        low=style.get("low", ""), rises=bullets(gen["emotion_rises_when"]), falls=bullets(gen["emotion_falls_when"]),
        fixed=FIXED_RULES, need=NEEDS[t["need"]], need_say=NEED_SAY[t["need"]])
    return {"id": bg["id"], "combo": combo, "persona": persona_text(bg, t, gen), "background": background,
            "task": NEEDS[t["need"]], "event": bg["event"], **t}


class Combos:
    """조합 캐시 (out/rlver/combos.jsonl). 키 = id:combo"""

    def __init__(self, path, llm):
        self.path, self.llm, self.cache, self.lock = path, llm, {}, threading.Lock()
        if os.path.exists(path):
            for l in open(path):
                r = json.loads(l)
                self.cache[f"{r['id']}:{r['combo']}"] = r["gen"]

    def get(self, bg, combo):
        key = f"{bg['id']}:{combo}"
        if key not in self.cache:
            gen = generate(bg, sample_traits(bg, combo), self.llm)
            with self.lock:
                self.cache[key] = gen
                with open(self.path, "a") as f:
                    f.write(json.dumps({"id": bg["id"], "combo": combo, "gen": gen}, ensure_ascii=False) + "\n")
        return build(bg, combo, self.cache[key])
