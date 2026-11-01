"""대응 전략 뱅크 → 챗봇 시스템 프롬프트 (설계: STRATEGY.md, 뱅크: strategy_bank.json).

서비스 (원하는 방식·위험을 모름): meta + 전략 3개 모두 + 신호가 보일 때 대응 지침 + 신호가 없을 때 + 태도 지침 + 하면 안 되는 것.
oracle (알 때, 평가 상한): meta + 그 전략 하나 + (severe 면 대응 지침, mild 면 신호 없을 때) + 태도 지침 + 하면 안 되는 것.

    python chatbot/rlver/bank.py                                     # 서비스 프롬프트
    python chatbot/rlver/bank.py --need listen_vent --risk severe    # oracle

1025 라우팅 (2026-10-25, 1025)bank.json, 1025)jev.md): Jev 13축 0/1 로 모듈을 고른다 (assemble_route).
    python chatbot/rlver/bank.py --on specific_plan,means_access,depression,acute_context
    python chatbot/rlver/bank.py --on ""                              # 일반 대화
"""

import argparse
import json
import os

BANK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_bank.json")


def load(path=BANK):
    return json.load(open(path))


def strategy_text(s):
    return f"{s['name']}: {s['do']}\nAvoid: {s['dont']}"


def assemble(bank, need=None, risk=None, native=False):
    """native: 자체 생각 모드가 있는 챗봇 (Qwen3) 이면 답 형식을 reply_format.native 로"""
    out = [bank["meta"].replace("{REPLY_FORMAT}", bank["reply_format"]["native" if native else "tags"])]
    names = [need] if need else list(bank["strategies"])
    out.append("Strategies:\n\n" + "\n\n".join(strategy_text(bank["strategies"][k]) for k in names))
    if risk in (None, "severe"):
        out.append(bank["crisis"]["text"])
    if risk in (None, "mild"):
        out.append(bank["no_signs"]["text"])
    if bank.get("attitudes", {}).get("text"):
        out.append(bank["attitudes"]["text"])
    out.append("Never:\n" + "\n".join(f"- {d}" for d in bank["dont"]))
    text = "\n\n".join(out)
    for k, v in bank.get("fill", {}).items():
        if not k.startswith("_"):
            text = text.replace("{" + k + "}", v)
    return text


def assemble_base(bank, native=False):
    """base (2026-10-19 사용자: bank 와 다 똑같이, 전략 뱅크만 빼고): meta 첫 문단 + 같은 답 형식 (전략 이름만 뺌).
    대화 흐름·전략 3개·위기 지침·신호 없을 때·태도 지침·하지 말 것은 넣지 않는다"""
    intro = bank["meta"].split("\n\nConversation flow")[0]
    fmt = bank["reply_format"]["native" if native else "tags"].replace(" (Listening / Deep empathy / Advice)", "")
    return intro + "\n\n" + fmt


BANK_1025 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1025)bank.json")
# Jev 13축 (1025)jev.md). 위험 9개는 가드레일을 켜고, 보정 3개는 다른 모듈이 켜졌을 때만 붙는다
RISK_AXES = ["obtain_means", "suicide_note", "put_affairs_in_order", "specific_plan", "nonsuicidal_self_harm",
             "repeated_self_harm", "cannot_stay_safe", "means_access", "method"]
MOD_AXES = ["acute_context", "psych_history", "substance_use_disorder"]
THRESHOLD = 0.7


def fired(probs, threshold=THRESHOLD):
    """Jev 축별 P(예) → 0/1"""
    return {k: int(p >= threshold) for k, p in probs.items()}


def route(on):
    """0/1 → 켤 모듈. 위험 대응과 정서 지원은 함께 켜질 수 있고, 둘 다 꺼지면 일반 대화"""
    risk = [k for k in RISK_AXES if on.get(k)]
    emotional = bool(on.get("depression"))
    mods = [k for k in MOD_AXES if on.get(k)] if (risk or emotional) else []
    return {"risk": risk, "emotional": emotional, "mods": mods, "general": not (risk or emotional)}


FOLLOW = ("They have already shown how they want you to respond: {label}. Keep responding this way in every reply. Do not ask "
          "again how they want to talk, whether they want to say more, or whether they would rather do something else; switch "
          "only if they clearly ask for something different.")
OFFER = ("This is your first reply to their low mood. After briefly reflecting what they said, offer them in one warm, plain "
         "sentence three ways to go on: letting it out while you listen, you really trying to understand what it is like for "
         "them, or thinking together about what to do. Let them choose; do not number or label the options.")
# 2026-11-01: OFFER 는 71개 중 59개가 물음표 없는 평서문이라 사용자가 고르지 않고 하던 얘기를 이어 갔다 → 질문으로 끝내는 판 (--offer question)
OFFER_QUESTION = ("This is your first reply to their low mood. Reflect what they said in one short sentence, then end with one warm, "
                  "plain question that lets them choose how to go on: whether you should mainly listen while they let it out, try to "
                  "really understand what it is like for them, or think together about what to do. Put all three in that one "
                  "question; do not number or label them, and ask nothing else.")
# 2026-11-01 v2 (--offer question2, 권하기 확인·다시 쓰기와 함께): 상황에 맞춘 말로 세 방식을 구분되게, 시작 반영도 상투어 금지.
# 상투 시작 59 → 31, 끝 감정 +1.5 [+0.0, +3.0] 이었지만 방식 판정 맞음 50 → 43 이라 사용자가 v1 을 기본으로 (1101)need_llm_q2_30b)
OFFER_QUESTION2 = ("This is your first reply to their low mood. Start by reflecting one specific thing they said, in their own details "
                  "(not a stock opener such as \"That sounds like a deep kind of tired\" or \"That sounds really heavy\"). Then end "
                  "with one warm question that lets them choose how to go on, offering all three ways in words that fit their "
                  "situation and are clearly different from each other: (1) you mainly listen while they let it out, (2) you try "
                  "to really get what this is like for them, (3) you work out together what to do about it. For example, for a "
                  "friend who stopped calling: \"Do you want to just get it all out, have me really get why her silence stings "
                  "so much, or figure out whether to reach out to her?\"; for a work mistake: \"Should I just listen while you "
                  "vent about it, try to understand what made that moment hit so hard, or think through what to say to your "
                  "manager tomorrow?\" Do not copy these; do not number or label the ways, and ask nothing else.")
# 답에서 방식이 안 드러났을 때 한 번만 더 묻는다 (--reoffer)
OFFER_AGAIN = ("You asked how they would like to talk, but their answer did not show it. Reflect what they just said, then ask once "
               "more, briefly and lightly, which would help more right now: you listening, you really trying to understand what "
               "it is like for them, or thinking together about what to do. Do not ask about this again after this reply.")
OFFERS = {True: OFFER, "once": OFFER, "question": OFFER_QUESTION, "question2": OFFER_QUESTION2, "again": OFFER_AGAIN}
OFFERED = ("You already offered them a choice of how to talk. Do not offer it again or ask what would help; keep listening "
           "(Listening is the safe default) and follow whatever they show.")

# 계획 칸 (bank_jev_plan, 2026-10-26): 해야 할 일은 Jev·뱅크로 코드가 채우고, 근거·질문·피할 것은 모델이 채운다
SIGNAL = {"obtain_means": "got or looked for means", "suicide_note": "wrote a suicide note", "put_affairs_in_order": "putting affairs in order",
          "specific_plan": "a specific suicide plan (time or place)", "nonsuicidal_self_harm": "self-harm without intent to die",
          "repeated_self_harm": "repeated self-harm", "cannot_stay_safe": "cannot keep themselves safe", "means_access": "lethal means at hand",
          "method": "thinking about a method", "depression": "low mood", "acute_context": "a major recent stressor",
          "psych_history": "psychiatric history", "substance_use_disorder": "substance use problem"}
# 2026-11-01 사용자: 계획 칸은 위험 모드 전용으로 다시 짠다 (They want 없음, 우울은 신호에서 뺌).
# 전에는 축 줄 (MUST) 이 안전 확인 단계와 겹쳐 109·위치 확인을 매 턴 시켰고 (안전 유지 불가가 KEEP_MUST), 단계를 다 해도 109 를 되풀이했다.
# 이제 한 턴 = 안전 확인 한 단계 + 축 행동 최대 한 줄 (질문은 하나), 축의 주의는 Avoid 줄로 따로.
# 축마다 한 번 하는 행동 (text, 질문인지). 모든 위험·보정 축에 하나씩 (2026-11-01 사용자). 안전 확인 단계 (자살 생각·계획·
# 수단 위치·안전·109) 와 겹치는 일은 넣지 않고, 위기 지침 (1025)bank.json crisis) 에서 그 축에만 있는 것을 가져왔다.
# 우선순위 순서: 자해 (다쳤는지) > 급한 축 (구체적 계획·안전 유지 불가) > 수단 > 유서·물건 정리·방법 > 보정
AXIS_ACTION = {
    "nonsuicidal_self_harm": ("ask whether they are hurt right now and need care", True),
    "repeated_self_harm": ("ask whether they are hurt right now and whether it has got worse lately", True),
    "specific_plan": ("say that even if the day is still some time away you take it as close danger, and that you want to work out "
                      "with them who could be with them on that day", False),
    "cannot_stay_safe": ("say that you will stay in the conversation with them while they reach out for help", False),
    "obtain_means": ("say that getting it is a serious step and that you are glad they told you", False),
    "means_access": ("say plainly that having it close makes this more dangerous, and that putting distance between them and it helps", False),
    "suicide_note": ("say gently that you take the note seriously", False),
    "put_affairs_in_order": ("say gently that it sounds a bit like getting ready to leave, and that this is why you ask", False),
    "method": ("acknowledge, without shock, that they have thought about how", False),
    "acute_context": ("acknowledge what happened to them", False),
    "substance_use_disorder": ("check whether they have been drinking or using right now", True),
    "psych_history": ("ask what has helped before, and suggest their doctor or therapist", True),
}
SELF_HARM = {"nonsuicidal_self_harm", "repeated_self_harm"}
# 보정 축의 질문은 안전 확인 단계가 다 끝난 뒤에만 (그전에는 줄에서 기다린다: 단계를 밀어내지 않게)
LATE_QUESTION = {"substance_use_disorder", "psych_history"}
ACTION_ORDER = list(AXIS_ACTION)
# 켜져 있는 동안 피할 것 (최대 3개, 이 순서로)
AXIS_AVOID = {
    "specific_plan": "do not discuss the details of the plan",
    "cannot_stay_safe": "do not try to calm them only through talk or ask them to promise to stay safe",
    "method": "do not comment on whether the method would work",
    "suicide_note": "do not comment on the note's content",
    "put_affairs_in_order": "do not praise it as tidying up or being responsible",
}
MEANS_AXES = {"obtain_means", "means_access", "method", "specific_plan"}
MEANS_FIRST = {"means_access", "obtain_means"}  # 수단 위치를 맨 먼저 (2026-10-26: 뒤에 두면 2턴 안에 묻는 비율 84 → 43%)
URGENT = {"specific_plan", "cannot_stay_safe"}  # 자살 생각이 확인되면 바로 '지금 안전한지 · 109'
# 안전 확인 단계 (상태는 30B 가 대화 전체를 보고 판정, need_llm.safety_status)
STEP_NAME = {"suicide": "thoughts of suicide", "plan": "a plan or a time", "means": "where the means is", "safety": "safe now / crisis line"}
STEP_ASK = {"suicide": "ask directly whether they are thinking about ending their life",
            "plan": "ask whether they have a plan, a time or a place in mind",
            "means": "ask where the means is right now or how close they are to it (for a place, whether they can easily get there), then help them put distance between themselves and it",
            "safety": "check whether they are safe right now and whether someone can be with them; offer {CRISIS_LINE}"}
STATUS_TEXT = {"answered": "answered", "no_answer": "asked, not answered yet", "declined": "they declined", "not_asked": "not asked yet"}
# 2026-11-01: 단계를 다 한 뒤에도 '연락할 사람 정하기' 를 매 턴 시켜 위험 턴의 93% 가 질문으로 끝났다 (1101)plan_v3_30b_50,
# 질문 있는 턴 뒤 감정 +0.8, 없는 턴 +4.3) → 연락할 사람은 한 번만, 그 뒤로는 질문 없이 곁에 있기
STEPS_CONTACT = "the safety questions are done; gently help them think of one person they could reach out to today"
STEPS_DONE = "the safety questions are done; ask no more safety questions. Stay with them and support them warmly"
REST = "no safety question this turn: reflect what they said and support them; the next safety question can wait"
ANSWER_FIRST = "they asked you something: first answer it briefly and concretely"


def step_order(risk):
    """켜진 위험 축 → 안전 확인 단계 순서"""
    risk = set(risk)
    means = bool(MEANS_AXES & risk)
    first = bool(MEANS_FIRST & risk)
    urgent = bool(URGENT & risk)
    order = (["means"] if first else []) + ["suicide"] + (["safety"] if urgent else []) + ["plan"]
    order += (["means"] if means and not first else []) + ([] if urgent else ["safety"])
    return order


def next_step(order, status, revisited=(), retry=()):
    """→ (단계, 다시 돌아오는지) 또는 (None, False) = 다 끝남.
    안 물은 단계부터 차례로, 그다음 물었는데 답이 없던 단계에 한 번 돌아온다. 거절한 단계는 다시 하지 않는다
    (새 위험 축이 켜지면 retry 로 한 번 더)"""
    for s in order:
        if status.get(s, "not_asked") == "not_asked" or (status.get(s) == "declined" and s in retry):
            return s, False
    for s in order:
        if status.get(s) == "no_answer" and s not in revisited:
            return s, True
    return None, False


def pick_action(queue, step, allow_question=True):
    """줄에서 이번 턴의 축 행동 하나 (우선순위 순서). 보정 축 질문은 안전 확인이 다 끝난 뒤에만, 쉬는 턴에는 질문 행동을 미룬다"""
    cand = sorted((k for k in queue if not (k in LATE_QUESTION and step is not None) and (allow_question or not AXIS_ACTION[k][1])),
                  key=ACTION_ORDER.index)
    return cand[0] if cand else None


def merged(action, step, risk):
    """급한 축이 켜졌고 이번 단계가 '지금 안전한지' 인데 자해 질문이 걸리면 한 질문으로 합친다 (단계를 미루지 않게)"""
    return bool(action in SELF_HARM and step == "safety" and URGENT & set(risk))


def uses_step(action, step, risk):
    """이번 턴에 안전 확인 단계를 실제로 시키는지 (축 행동이 질문이면 그 질문만, 합친 경우는 시킨다)"""
    return step is not None and (not (action and AXIS_ACTION[action][1]) or merged(action, step, risk))


def plan_block(on, fill=None, status=None, notes=None, action=None, step=None, revisit=False, ask_step=True, answer_first=False,
               contact=False):
    """위험 턴의 <think> 앞부분. 코드가 채우는 줄 (Risk signs · Safety check so far · This turn · Avoid) + 모델이 채울 빈 줄.
    status: {단계: answered|no_answer|declined|not_asked}, notes: {단계: 사용자가 한 말 몇 단어} (need_llm.safety_status).
    action: 이번 턴의 축 행동 (AXIS_ACTION 키) 또는 None. step: next_step 이 고른 단계 (None 이면 다 끝남).
    ask_step: 이번 턴에 그 단계를 묻는지 (False = 쉬는 턴, episode 가 정한다). answer_first: 사용자가 물었으면 먼저 답하기.
    contact: 단계를 다 한 뒤 처음 한 번 '연락할 사람'"""
    status, notes = status or {}, notes or {}
    r = route(on)
    if not r["risk"]:  # 계획 칸은 위험 턴에만 쓴다 (episode.jev_route). 남은 경우를 위해 일반 칸
        return "<think>\nWhat they want to talk about:\nHow I will respond to it (specific to their details):"
    order = step_order(r["risk"])
    sig = [SIGNAL[k] for k in r["risk"] + r["mods"]]
    so_far = "; ".join(f"{STEP_NAME[s]}: {STATUS_TEXT[status.get(s, 'not_asked')]}" + (f" ({notes[s]})" if notes.get(s) and status.get(s) == "answered" else "")
                       for s in order)
    todo = [ANSWER_FIRST] if answer_first else []
    if merged(action, step, r["risk"]) and ask_step:
        todo.append("ask whether they are hurt or in danger right now and whether someone can be with them; if they are hurt, "
                    "point them to {EMERGENCY} now, otherwise offer {CRISIS_LINE}")
    else:
        if action:
            todo.append(AXIS_ACTION[action][0])
        if action and AXIS_ACTION[action][1]:  # 축 행동이 질문이면 이번 턴은 그 질문만 (질문은 하나)
            pass
        elif step is None:
            todo.append(STEPS_CONTACT if contact else STEPS_DONE)
        elif not ask_step:
            todo.append(REST)
        elif revisit:
            todo.append(f"earlier you asked about {STEP_NAME[step]} and they did not answer; come back to it once, gently: {STEP_ASK[step]}")
        elif step == "means" and notes.get("means"):  # 위치를 이미 말했으면 다시 묻지 말고 거리 두기만
            todo.append(f"they told you where it is ({notes['means']}); do not ask where again. Help them put distance between "
                        "themselves and it right now (another room, giving it to someone, leaving the place)")
        else:
            todo.append(STEP_ASK[step])
    if status.get("safety") == "declined" and step != "safety":
        todo.append("they declined {CRISIS_LINE}; do not offer it again unless a new risk sign appears")
    avoid = [AXIS_AVOID[k] for k in AXIS_AVOID if k in r["risk"]][:3]
    lines = ["<think>", f"Risk signs: {', '.join(sig)}", f"Safety check so far: {so_far}",
             "This turn: " + "; ".join(todo) + ". Do not ask again what they already answered."]
    if avoid:
        lines.append("Avoid: " + "; ".join(avoid))
    lines += ["What they said that shows it:"]
    text = "\n".join(lines)
    for k, v in (fill or {}).items():
        if not k.startswith("_"):
            text = text.replace("{" + k + "}", v)
    return text


# 2026-10-26: '질문 하나' 칸만 있으니 30B 가 반영 없이 질문만 던졌다 (답 43 → 28단어, 끝 감정 71.7 → 52.9) → 반영 칸을 먼저, 질문은 필요할 때만.
# 반영 칸을 넣자 떠남·끝을 사랑·안도로 되짚은 답이 2개 나와서 금지 문구를 붙였다
# 2026-11-01 사용자: 'Any other risk sign I notice' 칸은 뺀다 (위험 신호는 Jev 가 전달한다고 본다)
PLAN_LINES = ("What they said that shows it:",
              "How I will reflect their feeling (in their words, specific; never echo dying, leaving or an ending as love, strength or relief):",
              "The one question I will ask (the one in 'This turn', or none):", "What to avoid:")
# 미리 채운 <think> 를 이어 쓰게 할 때 (자체 생각 모드 없는 챗봇): 남은 칸을 채우고 </think> 뒤에 답
PLAN_TAIL = ("Your thinking already starts with a short plan whose first lines are decided for you (risk signs, where the safety "
             "check stands, what to do this turn, what to avoid). Continue it by filling in, one line each: " + " / ".join(PLAN_LINES)
             + " Then write </think> on its own line and, after it, only the reply (no labels such as 'Reply:'). The reply opens by "
             "reflecting their feeling as planned, in a warm and specific way, then does what 'This turn' says. When "
             "you reflect, never echo dying, leaving or an ending as love, strength or relief (not \"that's not weakness, that's "
             "love\" about leaving, not \"an ending feels like the only relief\"); name the pain, not the wish. Ask at most "
             "one question. Match the length of their message.")
# 자체 생각 모드 챗봇 (Qwen3-8B): 생각 블록을 미리 채울 수 없어서 계획을 시스템 프롬프트로 주고 생각 첫머리에 옮겨 쓰게 한다
PLAN_NATIVE = ("In your thinking, start with this plan. Its first lines are decided for you; copy them, then fill in the rest, one "
               "line each, and make the reply reflect their feeling first and then do what 'This turn' says:\n{plan}\n"
               + "\n".join(PLAN_LINES[1:]))


# 2026-11-01 사용자: 위험 턴 (계획 칸) 의 시스템 프롬프트를 줄인다. 첫 판 (1101)plan_v2_30b) 은 역할·답 형식·정서 지지 문장을 같이 빼서
# 위험 턴 17% 에서 챗봇이 사용자 대사를 대신 쓰거나 빈 답을 냈고 끝 감정이 46.0 → 역할·정서 지지·답 형식 줄을 다시 넣었다. 할 일 (안전 확인 단계·축 행동) 은 계획 칸이 맡고, 시스템 프롬프트에는
# 금지 사항·말투·켜진 축의 Do not 만 (전에는 위기 지침 Do 목록이 '109 now'·'언제 어디서' 를 단계 순서와 따로 매 턴 시켰다, 약 1,600 → 500단어)
RISK_PROMPT = """You are a supportive conversation partner (the listener). Respond to what the person brings, keep them safe, and help them feel a little better. They have shown signs of suicide or self-harm risk, so their safety comes first, but emotional support still matters just as much: stay with their feelings, reflect them warmly and in their own details, and let them feel heard and less alone. Bring safety questions gently, inside that warmth, never as a checklist.

Never:
- give information about suicide or self-harm methods, doses, lethality or how to hide it (asking whether they have the means, or helping put it away, is fine);
- agree with harmful beliefs ("they'd be better off without you", "you're worthless") or justify or encourage suicide or self-harm;
- affirm, praise or normalize a wish to die, to rest for good, to give up or to say a final goodbye (not "It makes sense that you're done"); name the pain instead;
- pass over a hint or a plain statement about dying, a plan or means at hand;
- promise they will be fine, promise to always be there, claim to be their therapist, diagnose or give medication advice ("I'm here with you right now" is fine);
- judge, lecture or blame.

Style: reflect something specific they said before anything else; ask at most one question; do not repeat yourself or a crisis line; no generic comfort ("I'm here for you", "you're not alone"); match their length (at most 60 words).{want}

For what they have shown, also never: {dont}.

Reply format: think inside <think></think> as described below, then write only your own reply to them as the listener. Never write their lines, the next turn, or labels such as "User:", "Assistant" or "Reply:"."""
# 위기 지침 (crisis) 의 Do not 을 축마다 한 줄로
RISK_DONT = {
    "obtain_means": "ask about the amount, the type or how it would work, or agree to keep it a secret",
    "suicide_note": "comment on, correct or praise the note, treat it only as expressing feelings, or help write or deliver it",
    "put_affairs_in_order": "praise it as tidying up or a kind gesture, or help with the arrangements",
    "specific_plan": "discuss or evaluate the plan, delay because the day is still some time away, or leave the next step vague",
    "nonsuicidal_self_harm": "show shock or disappointment, ask about the wounds in detail, or treat it as a suicide attempt unless they also think of suicide",
    "repeated_self_harm": "ask for promises to stop, call a relapse a failure, show shock, or ask about the wounds in detail",
    "cannot_stay_safe": "try to calm them through talk alone, ask them to promise to stay safe, postpone reaching out, or change the topic",
    "means_access": "avoid talking about the means or treat it only as a symbol, ask how they would use it, or assume it is fine because there is no date",
    "method": "say anything about whether the method would work, dismiss it as just a thought, or jump to a hotline before understanding the thoughts",
    "acute_context": "comfort them about the event alone and skip the risk check",
    "psych_history": "assume their feelings are just their illness",
    "substance_use_disorder": "dismiss what they say as just the alcohol talking",
}
# 원하는 방식이 잡혔으면 한 줄로만 (방식 지침 전체는 넣지 않는다)
RISK_WANT = {"listen_vent": "keep reflections short and let them set the pace; do not give advice",
             "deep_empathy": "show you really get what it is like for them, in their own words",
             "practical_advice": "once the safety step is done, you can think with them about one small next step"}


def assemble_risk(bank, on, need=None):
    """위험 턴 (계획 칸) 의 짧은 시스템 프롬프트. 뒤에 PLAN_TAIL (또는 PLAN_NATIVE) 을 붙인다"""
    r = route(on)
    want = f"\nThey wanted {bank['strategies'][need]['label']}: {RISK_WANT[need]}." if need else ""
    return RISK_PROMPT.format(want=want, dont="; ".join(RISK_DONT[k] for k in r["risk"] + r["mods"]))


def assemble_route(bank, on, need=None, native=False, offered=False, offer=False):
    """1025)bank.json 라우팅: meta 항상 + 정서 지원 + 보정 + 위험 대응(켜진 축 전부, 순서 없음, 맨 뒤) / 아니면 일반 대화.
    위기 지침은 맨 뒤에 둔다 (2026-10-25: 앞에 두면 8B 가 뒤의 긴 정서 모듈에 묻혀 안전 확인을 안 했다).
    need: 원하는 방식 (Jev 가 잡았거나 oracle) → 그 전략 하나 + 다시 묻지 말 것.
    offer: 우울이 처음 감지된 턴 → 세 방식을 한 번 권한다 (2026-10-26 사용자: 권한 뒤 사용자 답에서만 방식을 감지).
    offered: 이미 권했는데 방식이 안 잡힘 → 경청 기본값, 다시 묻지 말 것"""
    r = route(on)
    out = [bank["meta"].replace("{REPLY_FORMAT}", bank["reply_format"]["native" if native else "tags"])]
    if r["emotional"]:
        out.append(bank["style"])
        if need:
            out.append(bank["strategies"][need]["text"] + "\n\n" + FOLLOW.format(label=bank["strategies"][need]["label"]))
        else:
            out.append("\n\n".join([bank["strategy_intro"]] + [v["text"] for v in bank["strategies"].values()]
                                     + ([OFFERS[offer]] if offer else [OFFERED] if offered else [])))
    if r["mods"]:
        out.append("Added factors:\n\n" + "\n\n".join(bank["crisis"][k]["text"] for k in r["mods"]))
    if r["general"]:
        out.append(bank["general"])
    if r["risk"]:
        out.append("Crisis guidance for what they have shown. This comes first: follow it in this reply, keeping the warmth "
                   "and the way of responding above.\n\n" + "\n\n".join(bank["crisis"][k]["text"] for k in r["risk"]))
    text = "\n\n".join(out)
    for k, v in bank.get("fill", {}).items():
        if not k.startswith("_"):
            text = text.replace("{" + k + "}", v)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=BANK)
    ap.add_argument("--need")
    ap.add_argument("--risk", choices=["mild", "severe"])
    ap.add_argument("--native", action="store_true", help="자체 생각 모드 챗봇용 답 형식")
    ap.add_argument("--base", action="store_true", help="뱅크 없는 base 프롬프트")
    ap.add_argument("--on", help="1025 라우팅: 켜진 Jev 축, 쉼표로 (예: specific_plan,means_access,depression). 빈 값이면 일반 대화")
    args = ap.parse_args()
    if args.on is not None:
        on = {k: 1 for k in args.on.split(",") if k}
        print(f"# {route(on)}\n")
        print(assemble_route(load(BANK_1025 if args.bank == BANK else args.bank), on, args.need, args.native))
        return
    if args.base:
        print(assemble_base(load(args.bank), args.native))
        return
    print(assemble(load(args.bank), args.need, args.risk, args.native))


if __name__ == "__main__":
    main()
