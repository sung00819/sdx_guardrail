"""한 대화 (Heart-in-the-Loop rollout): 시뮬레이터가 먼저 말하고, 챗봇 답 → 감정 갱신 → 사용자 답 을 반복.

끝: 감정 ≥ end_high (만족, Success) · 감정 < end_low (떠남, Failure) · 챗봇 max_turns 턴.
보상 r = max(e_T, 0) / 100. think 템플릿에서 한 턴이라도 형식을 어기면 0 (논문 2.3절 format reward).
반복 패널티: 이전 챗봇 답과 단어 유사도 ≥ repeat_similarity 인 턴마다 r 에서 repeat_penalty 를 뺀다 (음수가 될 수 있다).
"""

import difflib
import re

import bank as strategy_bank
from prompts import CHATBOT, REPLY_FORMAT, TAG_FORMAT, TAG_REPLY
from simulator import SageUser

THINK_TEMPLATES = ("think", "guide", "bank", "bank_oracle", "base")
THINK = re.compile(r"\A\s*<think>(.+?)</think>\s*(\S.*)\Z", re.S)
# 답 첫 줄에 흘린 계획 ("Deep empathy, no risk signs. Avoid: ...", "**Listening / ...**"). 형식 위반이고 보이는 답에서는 지운다
PLAN_LEAK = re.compile(r"\A\W*(listening|deep empathy|advice)\s*[,/.:]|\brisk signs?\b|\bavoid:|\bsay:\s", re.I)


def strip_plan(reply):
    """→ (계획을 지운 답, 계획이 있었는지). 'Say: \"...\"' 면 따옴표 안만, 아니면 계획 줄을 지운다"""
    lines = [l for l in reply.split("\n") if l.strip()]
    if not lines or not PLAN_LEAK.search(lines[0]):
        return reply, False
    said = re.search(r"\bsay:\s*[\"“](.+?)[\"”]?\s*\Z", reply, re.I | re.S)
    if said:
        return said.group(1).strip(), True
    rest = "\n".join(lines[1:]).strip()
    return (rest or reply), True


def parse_bot(raw, template):
    """→ (사용자에게 보일 답, 형식 맞음). 형식이 틀려도 대화는 이어 간다 (공식 extract_content: 마지막 </think> 뒤)"""
    if template not in THINK_TEMPLATES:
        reply = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        return reply, "<think>" not in raw
    m = THINK.match(raw)
    ok = bool(m) and "<think>" not in m.group(2) and "</think>" not in m.group(2)
    reply, leaked = strip_plan(raw.split("</think>")[-1].replace("<think>", "").strip())
    return reply, ok and not leaked


def max_similarity(reply, previous):
    """reply 와 이전 답들 중 가장 비슷한 것의 유사도 (0~1). 단어 단위 difflib, autojunk 끔 (../sim/textsim.py 와 같은 계산)"""
    w = reply.lower().split()
    return max((difflib.SequenceMatcher(None, w, p.lower().split(), autojunk=False).ratio() for p in previous if p),
               default=0.0)


def system_prompt(profile, template, native=False):
    """bank: 전략 뱅크 meta (챗봇이 원하는 방식·위험을 스스로 판단), bank_oracle: 프로필의 방식·위험 조각까지 (상한).
    native: 자체 생각 모드 챗봇 (Qwen3) 용 답 형식"""
    if template == "bank":
        return strategy_bank.assemble(strategy_bank.load(), native=native)
    if template == "base":  # bank 와 같은 시작·답 형식, 전략 뱅크만 뺌
        return strategy_bank.assemble_base(strategy_bank.load(), native)
    if template == "bank_oracle":
        return strategy_bank.assemble(strategy_bank.load(), profile.get("need"), profile.get("event"), native)
    text = CHATBOT[template]
    if TAG_REPLY in text:  # think·guide: bank 와 같은 답 형식 (생각 100단어 · 답 40단어, 자체 생각 모델이면 native)
        text = text.replace(TAG_FORMAT, "").replace(TAG_REPLY, REPLY_FORMAT["native" if native else "tags"])
    return text


def run_episode(profile, bot, sim_llm, cfg, template="think", use_first_talk=True):
    emo, ep = cfg["emotion"], cfg["episode"]
    user = SageUser(profile, sim_llm, emo)
    first, first_thinking = user.open(profile.get("first_talk") if use_first_talk else None)
    messages = [{"role": "system", "content": system_prompt(profile, template, getattr(bot, "native_think", False))}, {"role": "user", "content": first}]
    turns, end = [{"user": first, "user_thinking": first_thinking, "emotion": user.emotion}], "max_turns"
    for _ in range(ep["max_turns"]):
        raw = bot(messages)
        reply, ok = parse_bot(raw, template)
        if not reply:
            reply, ok = "...", False
        step = user.step(reply)
        # 학습 샘플: 이 턴의 입력(messages) + 원문 답(raw, 생각 블록 포함). 지난 턴의 생각 블록은 입력에 남기지 않는다 (공식 코드)
        turns[-1].update(prompt=[dict(m) for m in messages], bot_raw=raw, bot=reply, format_ok=ok)
        turns.append({"user": step["user"], "user_thinking": step["user_thinking"], "change": step["change"],
                      "emotion": step["emotion"], "state": step["state"], "planning": step["planning"]})
        messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": step["user"]}]
        if user.emotion >= emo["end_high"]:
            end = "success"
            break
        if user.emotion < emo["end_low"]:
            end = "failure"
            break
    format_ok = all(t.get("format_ok", True) for t in turns)
    reward = max(user.emotion, 0) / 100
    if template in THINK_TEMPLATES and cfg["reward"].get("format_zero", True) and not format_ok:
        reward = 0.0
    # 반복 패널티 (2026-10-19 사용자 결정): 감정 체계는 그대로 두고 챗봇 보상에서 직접 뺀다.
    # 이전 챗봇 답과 단어 유사도가 문턱 이상인 턴마다 repeat_penalty (같은 답 6번에도 감정은 −2~−4 였다, eval_bank_8b)
    rc, bots = cfg["reward"], []
    n_repeat = 0
    for t in turns:
        if "bot" not in t:
            continue
        t["repeat_similarity"] = round(max_similarity(t["bot"], bots), 3)
        t["repeated"] = t["repeat_similarity"] >= rc.get("repeat_similarity", 1.01)
        n_repeat += t["repeated"]
        bots.append(t["bot"])
    reward -= rc.get("repeat_penalty", 0.0) * n_repeat
    return {"id": profile["id"], "task": profile.get("task"), "event": profile.get("event"), "disclosure": profile.get("disclosure"),
            "template": template, "turns": turns,
            "final_emotion": user.emotion, "end": end, "format_ok": format_ok, "repeats": n_repeat, "reward": reward}
