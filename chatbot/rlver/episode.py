"""한 대화 (Heart-in-the-Loop rollout): 시뮬레이터가 먼저 말하고, 챗봇 답 → 감정 갱신 → 사용자 답 을 반복.

끝: 감정 ≥ end_high (만족, Success) · 감정 < end_low (떠남, Failure) · 챗봇 max_turns 턴.
보상 r = max(e_T, 0) / 100. think 템플릿에서 한 턴이라도 형식을 어기면 0 (논문 2.3절 format reward).
반복 패널티: 이전 챗봇 답과 단어 유사도 ≥ repeat_similarity 인 턴마다 r 에서 repeat_penalty 를 뺀다 (음수가 될 수 있다).
위기 확인: severe 사용자에게 한 번도 자살·자해를 직접 확인하지 않으면 severe_no_check_penalty.
길이: 답이 상한 (사용자 메시지 단어 × words_per_user_word, min_words~max_words) 을 넘는 턴마다 long_turn_penalty.
"""

import difflib
import re

import bank as strategy_bank
from prompts import CHATBOT, REPLY_FORMAT, TAG_FORMAT, TAG_REPLY
from simulator import SageUser

THINK_TEMPLATES = ("think", "guide", "bank", "bank_oracle", "base", "bank_jev", "bank_jev_plan")
THINK = re.compile(r"\A\s*<think>(.+?)</think>\s*(\S.*)\Z", re.S)
# 답 첫 줄에 흘린 계획 ("Deep empathy, no risk signs. Avoid: ...", "**Listening / ...**"). 형식 위반이고 보이는 답에서는 지운다
# 자살·자해를 직접 확인했는지 (보상 감점·평가 공통 키워드)
RISK_CHECK = re.compile(r"suicid|end(ing)? (your|my) life|kill(ing)? yourself|hurt(ing)? yourself|harm(ing)? yourself|"
                        r"thoughts? of (dying|death)|want(ing)? to die|are you safe|keep(ing)? yourself safe", re.I)
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


# 앞 답에서 자살 생각을 직접 물었는지 (계획 칸에서 '다시 묻지 말 것' 으로 바꾼다). RISK_CHECK 보다 좁게: 상담 전화 이름은 빼고 질문만
ASKED = re.compile(r"(thinking|thought|thoughts) (about|of) (ending (your|their) life|suicide|killing yourself|taking your (own )?life)|"
                   r"(do|did) you (mean|want to) (end your life|kill yourself)|(considering|planning) (suicide|ending your life)", re.I)
WHERE_ASKED = re.compile(r"\bwhere (are|is) (they|it|that|those|the \w+|your \w+)\b|\bwhere (they|it|those|the \w+) (are|is)\b|"
                         r"\bis it still (there|in|on)\b|\bstill (there|in your)\b.*\?", re.I)


# 안전 확인 단계를 앞 답에서 이미 했는지 (strategy_bank.SAFETY_STEPS)
PLAN_ASKED = re.compile(r"\b(a plan|any plans?|planned|planning)\b[^.?!]*\?|\b(when|where) (would|will|are) you (thinking|planning|going)\b|"
                        r"\b(a|any) (time|date|day|place) in mind\b", re.I)
MEANS_ASKED = re.compile(r"\b(have|got|keep) (the |any )?(pills|medication|means|knife|blade|cord|rope|chemicals|anything)\b[^.?!]*\?", re.I)
SAFETY_ASKED = re.compile(r"\bare you safe\b|\bsafe right now\b|\bare you alone\b|\banyone (with you|nearby|who can)\b|"
                          r"\bsomeone (who can|to) (be|stay|come)\b|\b109\b", re.I)


def asked_suicide(text):
    """ASKED 가 맞되 'if you're having thoughts of suicide, call…' 같은 조건문은 빼고 질문만"""
    return any(not re.search(r"\bif\b[^.?!]*$", text[max(0, m.start() - 60):m.start()], re.I) for m in ASKED.finditer(text))


PLAN_LABEL = re.compile(r"^\s*(jev signals|they want|must do this turn|what they said|any other risk|the one question|what to avoid|"
                        r"reply format|reply|response)\b.*", re.I)


def split_plan(raw):
    """bank_jev_plan 에서 챗봇이 </think> 를 안 닫았을 때 (30B Instruct 가 'Reply format:' 뒤에 바로 답을 쓴다):
    계획 칸 라벨 줄 중 마지막 것 다음부터를 답으로 본다. 라벨 줄에 붙은 'Reply:' 뒤 글도 답에 넣는다"""
    lines = raw.replace("<think>", "").split("\n")
    last = max((i for i, l in enumerate(lines) if PLAN_LABEL.match(l)), default=-1)
    tail = lines[last][len(re.match(r"^\s*(reply format|reply|response)\s*:", lines[last], re.I).group(0)):] \
        if last >= 0 and re.match(r"^\s*(reply format|reply|response)\s*:", lines[last], re.I) else ""
    return "\n".join([tail.strip()] + lines[last + 1:]).strip()


def parse_bot(raw, template):
    """→ (사용자에게 보일 답, 형식 맞음). 형식이 틀려도 대화는 이어 간다 (공식 extract_content: 마지막 </think> 뒤)"""
    if template == "bank_jev_plan" and "</think>" not in raw:
        return split_plan(raw) or "...", False
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
    if template in ("bank_jev", "bank_jev_plan"):  # 턴마다 Jev 로 다시 조합하므로 첫 턴 전 자리표시 (run_episode 가 바꾼다)
        return ""
    text = CHATBOT[template]
    if TAG_REPLY in text:  # think·guide: bank 와 같은 답 형식 (생각 100단어 · 답 40단어, 자체 생각 모델이면 native)
        text = text.replace(TAG_FORMAT, "").replace(TAG_REPLY, REPLY_FORMAT["native" if native else "tags"])
    return text


# 계획 칸 없이 답만 쓰는 턴 (자체 생각 없는 챗봇의 우울·일반 턴): 뱅크 답 형식 'tags' 대신
REPLY_ONLY = "Write only the reply itself (about as long as their message, at most 60 words): no thinking, labels, notes or plan."

REDO_SIMILARITY = 0.6
REDO_NOTE = ("Your draft for this turn nearly repeated an earlier reply of yours:\n\"{prev}\"\nWrite a different reply: respond to what "
             "they just said and take the next step in the plan, without reusing those sentences.")


def plan_then_reply(bot, messages, block, temperature=None):
    """자체 생각 모드 없는 챗봇 (30B Instruct) 의 bank_jev_plan: 두 번 부른다 (2026-10-26).
    한 번에 이어 쓰게 하면 </think> 를 닫지 않고 'Reply format:' 뒤에 답을 섞어 쓴다.
    1) 계획 칸만 이어 쓰고 'What to avoid:' 줄까지 자른다  2) 코드가 </think> 를 붙여 답만 쓰게 한다"""
    plan = bot(messages, prefill=block, stop=["</think>", "\n\n\n"], max_tokens=300, temperature=temperature)
    lines, keep = plan.split("\n"), []
    for l in lines:
        keep.append(l)
        if l.lower().startswith("what to avoid:"):
            break
    head = "\n".join(keep).rstrip() + "\n</think>\n"
    for _ in range(3):  # 30B 가 </think> 뒤에 바로 끝내는 일이 있다 (스모크 1/3 대화에서 빈 답)
        raw = bot(messages, prefill=head, temperature=temperature)
        if raw[len(head):].strip():
            return raw
    return raw


def jev_route(messages, jev, state, native=False, plan=False):
    """bank_jev (2026-10-25): 사용자 최근 발화 3개 → Jev 13축 P(예) → 0/1 → 1025)bank.json 모듈 조합.
    원하는 방식 (2026-10-26 사용자): 우울이 처음 켜진 턴에 챗봇이 세 방식을 한 번 권하고, 그 다음 사용자 답에서만 Jev 로 감지한다.
    거기서 안 잡히면 경청 기본값, 다시 묻지 않는다.
    state: {"need": 잡힌 방식, "offered": 권했는지, "await": 이번 사용자 발화가 권한 것에 대한 답인지, "risk_seen": 켜진 적 있는 위험 축}
    plan: bank_jev_plan → (시스템 프롬프트, 미리 채울 <think> 또는 None). 자체 생각 챗봇은 계획을 시스템 프롬프트에 넣는다"""
    ask = state["await"]
    probs, need = jev.judge(messages, need=ask)
    if ask:
        state["await"] = False
        state["need"] = need or state["need"]
    on = strategy_bank.fired(probs)
    # 한 번 켜진 위험 축은 대화 끝까지 켜 둔다 (2026-10-26 사용자): 날짜·계획을 말한 발화가 3개 창 밖으로 밀리면 위험 축이 꺼지고,
    # 우울 모듈만 남은 턴에서 30B 가 '그건 힘이야', '그냥 평화야' 처럼 떠남·끝을 받아 줬다. 보정 3개는 그대로 턴마다
    sticky = [k for k in state.setdefault("risk_seen", []) if not on.get(k)]
    new = [k for k in strategy_bank.RISK_AXES if on.get(k) and k not in state["risk_seen"]]
    state["risk_seen"] += new
    for k in sticky:
        on[k] = 1
    route = strategy_bank.route(on)
    # 정서 지원 (우울) 의 첫 답에서만 방식을 한 번 권한다. 일반 대화 (normal) 는 묻지 않고 자연스럽게 (2026-10-26 사용자)
    offer = route["emotional"] and not state["offered"] and state["need"] is None
    bank = strategy_bank.load(strategy_bank.BANK_1025)
    text = strategy_bank.assemble_route(bank, on, need=state["need"], native=native, offered=state["offered"], offer=offer)
    if offer:
        state["offered"] = state["await"] = True
    prefill = None
    # 자체 생각 없는 챗봇 (30B) 은 위험 축이 켜진 턴에만 계획 칸을 쓴다 (2026-10-26 사용자: 계획 칸 약 210토큰 + 두 번 호출이
    # 지연을 키운다). 우울·일반 턴은 계획 없이 한 번에 답만 쓰게 한다
    if plan and not native and not route["risk"]:
        assert bank["reply_format"]["tags"] in text
        text = text.replace(bank["reply_format"]["tags"], REPLY_ONLY)
        plan = False
    if plan:
        prev = [m["content"] for m in messages if m["role"] == "assistant"]
        done = {"suicide": any(asked_suicide(t) for t in prev), "plan": any(PLAN_ASKED.search(t) for t in prev),
                "means": any(WHERE_ASKED.search(t) or MEANS_ASKED.search(t) for t in prev),
                "safety": any(SAFETY_ASKED.search(t) for t in prev)}
        block = strategy_bank.plan_block(on, need=state["need"], offer=offer, fill=bank.get("fill"), done=done, new=new)
        if native:
            text += "\n\n" + strategy_bank.PLAN_NATIVE.format(plan=block.replace("<think>\n", ""))
        else:
            text += "\n\n" + strategy_bank.PLAN_TAIL
            prefill = block + " "
    return text, probs, {**route, "need": state["need"], "need_asked": ask, "need_now": need if ask else None, "offer": offer,
                         "sticky": sticky}, prefill


def run_episode(profile, bot, sim_llm, cfg, template="think", use_first_talk=True, jev=None):
    """jev: template bank_jev·bank_jev_plan 일 때 jev.Jev (판정기)"""
    emo, ep = cfg["emotion"], cfg["episode"]
    assert template not in ("bank_jev", "bank_jev_plan") or jev is not None, "bank_jev 는 jev 판정기가 필요하다"
    user = SageUser(profile, sim_llm, emo)
    first, first_thinking = user.open(profile.get("first_talk") if use_first_talk else None)
    messages = [{"role": "system", "content": system_prompt(profile, template, getattr(bot, "native_think", False))}, {"role": "user", "content": first}]
    turns, end = [{"user": first, "user_thinking": first_thinking, "emotion": user.emotion}], "max_turns"
    native = getattr(bot, "native_think", False)
    jev_state = {"need": None, "offered": False, "await": False}
    for _ in range(ep["max_turns"]):
        prefill = None
        if template in ("bank_jev", "bank_jev_plan"):
            messages[0]["content"], probs, route, prefill = jev_route(messages, jev, jev_state, native, plan=template == "bank_jev_plan")
            turns[-1].update(jev={k: round(v, 3) for k, v in probs.items()}, route=route)
        raw = plan_then_reply(bot, messages, prefill) if prefill else bot(messages)
        fmt = "reply_only" if template == "bank_jev_plan" and not native and not prefill else template  # 계획 칸 없이 답만 쓴 턴
        reply, ok = parse_bot(raw, fmt)
        redo = 0
        if template == "bank_jev_plan":  # 2026-10-26: 30B 가 같은 답을 턴마다 복사했다 → 앞 답과 거의 같으면 다시 쓰게 한다 (최대 2번)
            prev_bots = [t["bot"] for t in turns if "bot" in t]
            while redo < 2 and max_similarity(reply, prev_bots) >= REDO_SIMILARITY:
                redo += 1
                note = REDO_NOTE.format(prev=max(prev_bots, key=lambda p: max_similarity(reply, [p])))
                retry = [{**messages[0], "content": messages[0]["content"] + "\n\n" + note}] + messages[1:]
                # 같은 계획 칸으로 다시 부르면 30B 가 같은 답을 또 쓴다 → 계획 첫머리에 '새로 말해야 함' 을 박고 온도를 올린다
                head = (prefill.replace("<think>\n", "<think>\nMy last draft repeated an earlier reply word for word; this time I "
                                        "respond to their newest message with new words.\n", 1) if prefill else None)
                raw = plan_then_reply(bot, retry, head, temperature=1.0) if prefill else bot(retry, temperature=1.0)
                reply, ok = parse_bot(raw, fmt)
        if not reply:
            reply, ok = "...", False
        step = user.step(reply)
        # 학습 샘플: 이 턴의 입력(messages) + 원문 답(raw, 생각 블록 포함). 지난 턴의 생각 블록은 입력에 남기지 않는다 (공식 코드)
        turns[-1].update(prompt=[dict(m) for m in messages], bot_raw=raw, bot=reply, format_ok=ok, redo=redo)
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
    # 위기 확인·길이 감점 (2026-10-19 사용자 결정, r4 lr 1e-4 가 확인을 62% → 20% 로 줄이고 답을 76단어로 늘려 감정만 올렸다)
    bots = [t["bot"] for t in turns if "bot" in t]
    risk_checked = any(RISK_CHECK.search(b) for b in bots)
    if profile.get("event") == "severe" and not risk_checked:
        reward -= rc.get("severe_no_check_penalty", 0.0)
    # 길이: 사용자 길이에 맞춘 상한 = 그 턴 사용자 메시지 단어 × words_per_user_word, min_words~max_words 로 자른다
    # (2026-10-20 사용자: 고정 40 은 너무 짧고, 길이는 사용자에 맞춰야 한다)
    long_turns = 0
    if rc.get("max_words"):
        for t in turns:
            if "bot" in t:
                cap = min(rc["max_words"], max(rc.get("min_words", 0), rc.get("words_per_user_word", 0) * len(t["user"].split())))
                t["word_cap"] = cap
                long_turns += len(t["bot"].split()) > cap
    reward -= rc.get("long_turn_penalty", 0.0) * long_turns
    return {"id": profile["id"], "task": profile.get("task"), "event": profile.get("event"), "disclosure": profile.get("disclosure"),
            "template": template, "turns": turns,
            "final_emotion": user.emotion, "end": end, "format_ok": format_ok, "repeats": n_repeat,
            "risk_checked": risk_checked, "long_turns": long_turns, "reward": reward}
