"""한 대화 (Heart-in-the-Loop rollout): 시뮬레이터가 먼저 말하고, 챗봇 답 → 감정 갱신 → 사용자 답 을 반복.

끝: 감정 ≥ end_high (만족, Success) · 감정 < end_low (떠남, Failure) · 챗봇 max_turns 턴.
보상 r = max(e_T, 0) / 100. think 템플릿에서 한 턴이라도 형식을 어기면 0 (논문 2.3절 format reward).
"""

import re

import bank as strategy_bank
from prompts import CHATBOT
from simulator import SageUser

THINK_TEMPLATES = ("think", "guide", "bank", "bank_oracle")
THINK = re.compile(r"\A\s*<think>(.+?)</think>\s*(\S.*)\Z", re.S)


def parse_bot(raw, template):
    """→ (사용자에게 보일 답, 형식 맞음). 형식이 틀려도 대화는 이어 간다 (공식 extract_content: 마지막 </think> 뒤)"""
    if template not in THINK_TEMPLATES:
        reply = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        return reply, "<think>" not in raw
    m = THINK.match(raw)
    if m and "<think>" not in m.group(2) and "</think>" not in m.group(2):
        return m.group(2).strip(), True
    return raw.split("</think>")[-1].replace("<think>", "").strip(), False


def system_prompt(profile, template):
    """bank: 전략 뱅크 meta (챗봇이 원하는 방식·위험을 스스로 판단), bank_oracle: 프로필의 방식·위험 조각까지 (상한)"""
    if template == "bank":
        return strategy_bank.assemble(strategy_bank.load())
    if template == "bank_oracle":
        return strategy_bank.assemble(strategy_bank.load(), profile.get("need"), profile.get("event"))
    return CHATBOT[template]


def run_episode(profile, bot, sim_llm, cfg, template="think", use_first_talk=True):
    emo, ep = cfg["emotion"], cfg["episode"]
    user = SageUser(profile, sim_llm, emo)
    first, first_thinking = user.open(profile.get("first_talk") if use_first_talk else None)
    messages = [{"role": "system", "content": system_prompt(profile, template)}, {"role": "user", "content": first}]
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
    return {"id": profile["id"], "task": profile.get("task"), "event": profile.get("event"), "disclosure": profile.get("disclosure"),
            "template": template, "turns": turns,
            "final_emotion": user.emotion, "end": end, "format_ok": format_ok, "reward": reward}
