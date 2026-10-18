"""배경 + 설정 → RLVER 프로필 (페르소나 글 · 배경 글). LLM 은 쓰지 않는다 (2026-10-18 사용자 결정).

배경마다 설정 6개 = 원하는 대응 방식 3개 × 털어놓는 정도 high/low → 배경당 대화 6개.
  setting s (0~5): 방식 = NEEDS[s % 3], 털어놓는 정도 = (high, low)[s // 3]
설정마다 랜덤 (배경 id 와 s 로 고정 시드 → 다시 돌려도 같다):
- C 돕는 사람을 대하는 태도 5개 중 하나 (균등). 출처: 이 저장소 기존 설계 (../SIMULATOR_PERSONA.md C,
  ../SIMULATOR_EVIDENCE.md 4절) — 성인 애착 유형(안정·불안·회피·혼란; Mikulincer & Shaver, Noftle & Shaver 2006)을 대화 행동으로
- 대화 노력 1~5 중 하나 (균등). 시뮬레이터 답 길이가 이를 따른다 (prompts.REPLY, 단어 상한 MAX_WORDS)
사건 event (mild/severe) 는 배경에서 정해진다 (backgrounds.read).
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from prompts import BACKGROUND, DISCLOSURE, FIXED_RULES, NEED_SAY, NEEDS  # noqa: E402
from sim_text import EFFORT, STANCE  # noqa: E402

SETTINGS = [(need, disclosure) for disclosure in ("high", "low") for need in NEEDS]  # 6개
MAX_WORDS = {1: 5, 2: 15, 3: 30, 4: 50, 5: 80}  # 대화 노력별 메시지 단어 상한 (2026-10-19 사용자 결정, 4·5 가 130단어 넘게 나와서)


def sample_traits(bg, setting):
    need, disclosure = SETTINGS[setting]
    rng = random.Random(f"{bg['id']}:{setting}")
    return {"setting": setting, "need": need, "disclosure": disclosure,
            "stance": rng.choice(list(STANCE)), "effort": rng.randint(1, 5)}


def persona_text(bg, t):
    return "\n".join([
        f"* Name: {bg['name']}", f"* Age: {bg['age']}", f"* Gender: {bg['gender']}",
        f"* Occupation: {bg['occupation']}", f"* Lives in: {bg['city'] + ', ' if bg.get('city') else ''}South Korea",
        f"* Message length and form: {EFFORT[t['effort']]}; at most {MAX_WORDS[t['effort']]} words per message",
        f"* Toward someone trying to help: {STANCE[t['stance']]}"])


def hidden_text(bg):
    out = [f"- Real worry: {bg['core_concern']}",
           "- You are depressed: low mood, tiredness and self-blame color how you talk, without naming 'depression'."]
    if bg["event"] == "severe":
        out.append(f"- Risk sign: {bg['risk_fact']}")
    else:  # mild: 자살·자해 신호 없이 우울감만
        out.append("- No thoughts of suicide or self-harm; if asked, you say so honestly.")
    return "\n".join(out)


def build(bg, setting):
    """배경 + 설정 번호 → 시뮬레이터 프로필"""
    t = sample_traits(bg, setting)
    background = BACKGROUND.format(topic=bg["topic"], story=bg["background"], hidden=hidden_text(bg),
                                   disclosure=DISCLOSURE[bg["event"], t["disclosure"]], fixed=FIXED_RULES,
                                   need=NEEDS[t["need"]], need_say=NEED_SAY[t["need"]])
    return {"id": bg["id"], "persona": persona_text(bg, t), "background": background,
            "task": NEEDS[t["need"]], "event": bg["event"], **t}
