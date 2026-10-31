"""배경 + 설정 → RLVER 프로필 (페르소나 글 · 배경 글). LLM 은 쓰지 않는다 (2026-10-18 사용자 결정).

배경마다 설정 6개 = 원하는 대응 방식 3개 × 털어놓는 정도 high/low → 배경당 대화 6개.
  setting s (0~5): 방식 = NEEDS[s % 3], 털어놓는 정도 = (high, low)[s // 3]
설정마다 랜덤 (배경 id 와 s 로 고정 시드 → 다시 돌려도 같다):
- 대화 노력: vanilla(high) 3~5, challenging(low) 1~3 중 하나 (균등, 2026-10-28 사용자 결정. 그 전에는 털어놓는 정도와 따로 1~5). 시뮬레이터 답 길이가 이를 따른다 (prompts.REPLY, 단어 상한 MAX_WORDS)
사건 event (mild/severe) 는 배경에서 정해진다 (backgrounds.read).
돕는 사람을 대하는 태도(애착 유형 5개)는 2026-10-27 뺐다: 시뮬레이터 태도는 털어놓는 정도 (vanilla = high, challenging = low) 하나다.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from prompts import (BACKGROUND, DISCLOSURE, DISCLOSURE_NORMAL, FIXED_RULES, FIXED_RULES_NORMAL, HIDDEN_INTENTION_NORMAL,  # noqa: E402
                     HIDDEN_NORMAL, NEED_SAY, NEED_SAY_NORMAL, NEEDS, PURPOSE_NORMAL)
from sim_text import EFFORT  # noqa: E402

SETTINGS = [(need, disclosure) for disclosure in ("high", "low") for need in NEEDS]  # 6개
EFFORT_RANGE = {"high": (3, 5), "low": (1, 3)}  # vanilla 는 길게, challenging 은 짧게 (발표 17쪽 예시)
MAX_WORDS = {1: 5, 2: 15, 3: 30, 4: 50, 5: 80}  # 대화 노력별 메시지 단어 상한 (2026-10-19 사용자 결정, 4·5 가 130단어 넘게 나와서)


def sample_traits(bg, setting):
    need, disclosure = SETTINGS[setting]
    rng = random.Random(f"{bg['id']}:{setting}")
    return {"setting": setting, "need": need, "disclosure": disclosure, "effort": rng.randint(*EFFORT_RANGE[disclosure])}


def persona_text(bg, t):
    return "\n".join([
        f"* Name: {bg['name']}", f"* Age: {bg['age']}", f"* Gender: {bg['gender']}",
        f"* Occupation: {bg['occupation']}", f"* Lives in: {bg['city'] + ', ' if bg.get('city') else ''}South Korea",
        f"* Message length and form: {EFFORT[t['effort']]}; at most {MAX_WORDS[t['effort']]} words per message"])


def hidden_text(bg):
    out = [f"- Real worry: {bg['core_concern']}",
           "- You are depressed: low mood, tiredness and self-blame color how you talk, without naming 'depression'."]
    if bg["event"] == "severe":
        out.append(f"- Risk sign: {bg['risk_fact']}")
    else:  # mild: 자살·자해 신호 없이 우울감만
        out.append("- No thoughts of suicide or self-harm; if asked, you say so honestly.")
    return "\n".join(out)


def build(bg, setting):
    """배경 + 설정 번호 → 시뮬레이터 프로필. 배경 v2 의 group=normal 은 우울 없는 일상 대화용 지시를 쓴다 (2026-10-25).
    normal 은 원하는 대응 방식이 없다 (2026-10-26): need=None, 설정 번호는 털어놓는 정도만 뜻한다"""
    t = sample_traits(bg, setting)
    if bg.get("group") == "normal":
        background = BACKGROUND.format(topic=bg["topic"], story=bg["background"],
                                       hidden=HIDDEN_NORMAL.format(core_concern=bg["core_concern"]),
                                       disclosure=DISCLOSURE_NORMAL[t["disclosure"]], fixed=FIXED_RULES_NORMAL,
                                       need=HIDDEN_INTENTION_NORMAL, need_say=NEED_SAY_NORMAL)
        background = background.replace("## Hidden worry and signals (never state these directly at the start)", "## What you bring to the chat")
        return {"id": bg["id"], "persona": persona_text(bg, t), "background": background, "purpose": PURPOSE_NORMAL,
                "task": HIDDEN_INTENTION_NORMAL, "event": bg["event"], "group": "normal", **t, "need": None}
    background = BACKGROUND.format(topic=bg["topic"], story=bg["background"], hidden=hidden_text(bg),
                                   disclosure=DISCLOSURE[bg["event"], t["disclosure"]], fixed=FIXED_RULES,
                                   need=NEEDS[t["need"]], need_say=NEED_SAY[t["need"]])
    return {"id": bg["id"], "persona": persona_text(bg, t), "background": background,
            "task": NEEDS[t["need"]], "event": bg["event"], **t}
