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
OFFERED = ("You have already offered them a choice of how to talk earlier in this conversation. Do not offer it again or ask "
           "what would help; keep listening (Listening is the safe default) and follow whatever they show.")


def assemble_route(bank, on, need=None, native=False, offered=False):
    """1025)bank.json 라우팅: meta 항상 + 정서 지원 + 보정 + 위험 대응(켜진 축 전부, 순서 없음, 맨 뒤) / 아니면 일반 대화.
    위기 지침은 맨 뒤에 둔다 (2026-10-25: 앞에 두면 8B 가 뒤의 긴 정서 모듈에 묻혀 안전 확인을 안 했다).
    need: 원하는 방식 (Jev 가 잡았거나 oracle) → 그 전략 하나 + 다시 묻지 말 것 (2026-10-25: 8B 가 정서 턴의 28% 에서 방식을 다시 물었다).
    모르면 2.0 과 전략 3개, offered (이미 정서 모듈이 한 번 들어갔음) 면 '다시 묻지 말고 들어라' 를 붙인다"""
    r = route(on)
    out = [bank["meta"].replace("{REPLY_FORMAT}", bank["reply_format"]["native" if native else "tags"])]
    if r["emotional"]:
        out.append(bank["style"])
        if need:
            out.append(bank["strategies"][need]["text"] + "\n\n" + FOLLOW.format(label=bank["strategies"][need]["label"]))
        else:
            out.append("\n\n".join([bank["strategy_intro"]] + [v["text"] for v in bank["strategies"].values()]
                                     + ([OFFERED] if offered else [])))
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
