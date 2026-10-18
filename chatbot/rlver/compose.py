"""배경 + 나중에 조합하는 속성 → RLVER 프로필 (페르소나 글 · 배경 글).

배경은 고정, 나머지는 조합 (배경 id 와 --combo 번호로 고정 시드, 같은 조합 = 같은 사용자):
- 원하는 대응 방식 3개 × 털어놓는 정도 high/low: j = (rank + combo) mod 6 → 방식 j mod 3, 털어놓는 정도 j // 3.
  rank 는 split·event 안 순번 (assign_rank) → split·event 안에서 6칸 균등, 조합 0~5 이면 배경마다 6칸을 한 번씩
- C 돕는 사람을 대하는 태도 5개: ../build_profile.py STANCE 비율 (협조 30 · 불안·매달림 20 · 회피·축소 20 · 적대·시험 15 · 양가 15).
  출처: 이 저장소 기존 설계 (../SIMULATOR_PERSONA.md C, ../SIMULATOR_EVIDENCE.md 4절) — 성인 애착 유형(안정·불안·회피·혼란,
  Mikulincer & Shaver; Noftle & Shaver 2006)을 대화 행동으로 옮긴 것. 비율은 설계값
- 대화 노력 1~5: 3 + 태도 보정 (회피 −1 · 적대 −0.5 · 불안·매달림 +0.5) + 잡음 (표준편차 1), 반올림해 1~5로 자름
- Big Five·신경증 하위 특성은 쓰지 않는다 (2026-10-18 사용자 결정)
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
from sim_text import EFFORT, STANCE  # noqa: E402



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
    effort = int(min(5, max(1, round(3 + bp.STANCE_EFFORT.get(stance, 0) + rng.gauss(0, 1.0)))))
    return {"need": need, "disclosure": disclosure, "stance": stance, "effort": effort}


def persona_text(bg, t, details):
    return "\n".join([
        f"* Name: {bg['name']}", f"* Age: {bg['age']}", f"* Gender: {bg['gender']}",
        f"* Occupation: {bg['occupation']}", f"* Lives in: {bg['city'] + ', ' if bg.get('city') else ''}South Korea",
        "* Personal hobbies:\n" + "\n".join(f"{i}. {h}" for i, h in enumerate(details.get("hobbies", []), 1)),
        f"* Habits and behavioral characteristics:\n{details.get('habits_and_behavior', '')}",
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
