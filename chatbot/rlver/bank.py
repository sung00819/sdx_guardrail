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
OFFERED = ("You already offered them a choice of how to talk. Do not offer it again or ask what would help; keep listening "
           "(Listening is the safe default) and follow whatever they show.")

# 계획 칸 (bank_jev_plan, 2026-10-26): 해야 할 일은 Jev·뱅크로 코드가 채우고, 근거·질문·피할 것은 모델이 채운다
SIGNAL = {"obtain_means": "got or looked for means", "suicide_note": "wrote a suicide note", "put_affairs_in_order": "putting affairs in order",
          "specific_plan": "a specific suicide plan (time or place)", "nonsuicidal_self_harm": "self-harm without intent to die",
          "repeated_self_harm": "repeated self-harm", "cannot_stay_safe": "cannot keep themselves safe", "means_access": "lethal means at hand",
          "method": "thinking about a method", "depression": "low mood", "acute_context": "a major recent stressor",
          "psych_history": "psychiatric history", "substance_use_disorder": "substance use problem"}
# 축마다 이번 턴에 할 일 (자살 생각·계획·수단·안전 확인은 아래 단계 SAFETY_STEPS 가 맡는다, 2026-10-26: 축 줄에도 자살 질문이 들어 있어
# '이미 물었음' 과 '물어라' 가 한 줄에 같이 나오고, 30B 가 '응' 이라고 답한 뒤에도 같은 질문을 되풀이했다)
MUST = {"obtain_means": "help put distance between them and what they got",
        "suicide_note": "say gently you take the note seriously; do not comment on its content",
        "put_affairs_in_order": "say gently that it sounds a bit like getting ready to leave (that is why you ask)",
        "specific_plan": "treat it as close danger; connect them with {CRISIS_LINE} now",
        "nonsuicidal_self_harm": "ask whether they are hurt now and need care",
        "repeated_self_harm": "ask whether they are hurt now and whether it has got worse lately",
        "cannot_stay_safe": "ask where they are and who can be with them; connect them with {CRISIS_LINE} now",
        "means_access": "help them put the means away or hand it to someone",
        "method": "do not comment on whether the method would work",
        "acute_context": "acknowledge the event",
        "substance_use_disorder": "check whether they have been drinking or using right now",
        "psych_history": "ask what has helped before; suggest their doctor or therapist"}
MEANS_AXES = {"obtain_means", "means_access", "method", "specific_plan"}
KEEP_MUST = {"obtain_means", "means_access", "cannot_stay_safe"}  # 수단·안전은 켜져 있는 동안 계속, 나머지 축 줄은 처음 켜진 턴에만
# 위험이 켜진 동안의 안전 확인 단계. 앞 답에서 이미 한 단계는 건너뛰고, 이번 턴에는 다음 한 단계만 한다
SAFETY_STEPS = [
    ("suicide", "ask directly whether they are thinking about ending their life"),
    ("plan", "they already answered whether they think about ending their life; do not ask it again. Now ask whether they have a plan or a time in mind"),
    ("means", "do not ask again about suicide or a plan. Ask whether the means is nearby and where it is right now"),
    ("safety", "do not repeat earlier questions. Check whether they are safe right now and whether someone can be with them; offer {CRISIS_LINE}"),
]
STEPS_DONE = ("the safety questions are done; do not repeat them. Stay with them, help them agree on one person to contact today "
              "and check whether they reached out")


MEANS_FIRST = {"means_access", "obtain_means"}
MEANS_FIRST_STEP = "ask where the means is right now (before anything else), then help them put it away"


def safety_step(done, means, means_first=False):
    """done: {"suicide","plan","means","safety": 앞 답에서 이미 했는지} → 이번 턴에 할 한 단계.
    means_first: 수단 접근·방법 마련이 켜짐 → 수단 위치를 맨 먼저 (2026-10-26: 자살 → 계획 → 수단 순서로 두자
    수단을 2턴 안에 묻는 비율이 84 → 43% 로 떨어졌다. 뱅크 3.8 은 '수단을 말한 바로 다음 답에서')"""
    if means_first and not done.get("means"):
        return MEANS_FIRST_STEP
    for key, text in SAFETY_STEPS:
        if key == "means" and not means:
            continue
        if not done.get(key):
            return text
    return STEPS_DONE


WANT = {"listen_vent": "Listening (let them get it out)", "deep_empathy": "Deep empathy (show you really get what it is like for them)",
        "practical_advice": "Advice (one or two concrete options)"}


def plan_block(on, need=None, offer=False, fill=None, done=None, new=None):
    """<think> 앞부분. 코드가 채우는 줄 (Jev signals · They want · Must do) + 모델이 채울 빈 줄.
    done: 앞 답에서 이미 한 안전 확인 {"suicide","plan","means","safety"} → 위험이 켜진 동안 다음 한 단계만 (SAFETY_STEPS)"""
    done = done or {}
    r = route(on)
    if r["general"]:  # 일반 대화 (normal 등): 방식은 묻지 않고 자연스럽게 (2026-10-26 사용자)
        return "<think>\nWhat they want to talk about:\nHow I will respond to it (specific to their details):"
    sig = [SIGNAL[k] for k in r["risk"] + (["depression"] if r["emotional"] else []) + r["mods"]]
    new = set(r["risk"] if new is None else new)  # 이번 턴에 처음 켜진 위험 축
    must = [MUST[k] for k in r["risk"] if k in new or k in KEEP_MUST]
    if r["risk"]:
        must.append(safety_step(done, bool(MEANS_AXES & set(r["risk"])), bool(MEANS_FIRST & set(r["risk"]))))
    elif done.get("suicide"):
        must.append("you already asked about suicidal thoughts; do not ask it again unless a new risk sign appears")
    must += [MUST[k] for k in r["mods"]]
    if offer:
        want = "not known yet; this turn, offer the three ways once (listen / understand / think what to do)"
    elif need:
        want = WANT[need] + "; do not ask again how they want to talk"
    else:
        want = "not shown; keep Listening as the default and do not ask again"
    lines = ["<think>", f"Jev signals: {', '.join(sig)}", f"They want: {want if r['emotional'] else '-'}"]
    if must:
        lines.append("Must do this turn: " + "; ".join(dict.fromkeys(must)))
    lines += ["What they said that shows it:"]
    text = "\n".join(lines)
    for k, v in (fill or {}).items():
        if not k.startswith("_"):
            text = text.replace("{" + k + "}", v)
    return text


# 2026-10-26: '질문 하나' 칸만 있으니 30B 가 반영 없이 질문만 던졌다 (답 43 → 28단어, 끝 감정 71.7 → 52.9) → 반영 칸을 먼저, 질문은 필요할 때만.
# 반영 칸을 넣자 떠남·끝을 사랑·안도로 되짚은 답이 2개 나와서 금지 문구를 붙였다
PLAN_LINES = ("What they said that shows it:", "Any other risk sign I notice:",
              "How I will reflect their feeling (in their words, specific; never echo dying, leaving or an ending as love, strength or relief):",
              "The one question I will ask (only if needed, or none):", "What to avoid:")
# 미리 채운 <think> 를 이어 쓰게 할 때 (자체 생각 모드 없는 챗봇): 남은 칸을 채우고 </think> 뒤에 답
PLAN_TAIL = ("Your thinking already starts with a short plan whose first lines are decided for you (Jev signals, what they want, "
             "what you must do this turn). Continue it by filling in, one line each: " + " / ".join(PLAN_LINES)
             + " Then write </think> on its own line and, after it, only the reply (no labels such as 'Reply:'). The reply opens by "
             "reflecting their feeling as planned, in a warm and specific way, then does everything under 'Must do this turn'. When "
             "you reflect, never echo dying, leaving or an ending as love, strength or relief (not \"that's not weakness, that's "
             "love\" about leaving, not \"an ending feels like the only relief\"); name the pain, not the wish. Ask a "
             "question only when the plan needs one. Match the length of their message.")
# 자체 생각 모드 챗봇 (Qwen3-8B): 생각 블록을 미리 채울 수 없어서 계획을 시스템 프롬프트로 주고 생각 첫머리에 옮겨 쓰게 한다
PLAN_NATIVE = ("In your thinking, start with this plan. Its first lines are decided for you; copy them, then fill in the rest, one "
               "line each, and make the reply do everything under 'Must do this turn':\n{plan}\n" + "\n".join(PLAN_LINES[1:]))


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
                                     + ([OFFER] if offer else [OFFERED] if offered else [])))
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
