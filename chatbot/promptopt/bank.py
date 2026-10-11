"""프롬프트 뱅크: 가드레일 코드 → 베이스 LLM 시스템 프롬프트 (GALAXY 의 System Prompt Optimizer, A안).

베이스 LLM 은 가드레일 코드를 보지 않는다. 이 모듈이 코드를 지시문으로 바꿔 넣는다 →
가중치를 안 건드리고(F4) 어떤 베이스 LLM 에도 그대로 붙는다(F7). 조회만 하므로 추가 지연 ~0 (NF1).

조립 = base + modes[대화 안 최고 response] + reasons[지금까지 드러난 코드 묶음].
최고 response 유지는 LLM 에 맡기지 않고 코드가 한다 (gym judge.effective_modes 와 같은 규칙).
"""

import json

RANK = {"normal": 0, "support": 1, "assess": 2, "urgent": 3}

# 가드레일 코드 → reasons 조각 이름. INJURY 는 gym flags.py U4 와 같은 묶음
GROUPS = {
    "method": {"suicidal_ideation_method"},
    "plan": {"suicidal_ideation_plan", "suicidal_ideation_active_intent"},
    "means": {"means_access"},
    "injury": {"self_harm_behavior", "self_harm_suicidal_within_3m", "suicidal_behavior_within_3m"},
    "unsafe": {"unable_to_stay_safe"},
    "urge": {"self_harm_urge", "self_harm_severe"},
    "past": {"self_harm_over_12m", "suicidal_behavior_over_12m", "self_harm_within_12m_or_unknown",
             "suicidal_behavior_3_12m_or_unknown", "suicidal_ideation_chronic", "suicidal_ideation_over_1m"},
    "history": {"psychiatric_history"},
    "warning": {"indirect_warning", "acute_context"},
}
POSITIONS = ("system", "turn")


def load(path):
    return json.load(open(path))


def save(bank, path):
    with open(path, "w") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
        f.write("\n")


def codes(g):
    return set(g["reasons"]) | set(g.get("context") or []) | set(g["chronic"]) | (
        {g["upgraded_by"]} if g.get("upgraded_by") else set())


def state(guards):
    """지금까지 받은 가드레일 출력들 → (모드, 켜진 reasons 조각 이름들)"""
    best, seen = "normal", set()
    for g in guards:
        if RANK.get(g["response"], -1) > RANK[best]:
            best = g["response"]
        seen |= codes(g)
    mode = "other" if best == "normal" and guards and guards[-1]["response"] == "other" else best
    return mode, [k for k, v in GROUPS.items() if seen & v]


def parts(bank, guards):
    """이번 턴에 켜지는 조각 이름 목록 ('base', 'modes.assess', 'reasons.means', ..., 'suffix')
    suffix: 상태 지시 맨 끝에 항상 붙는 형식 규칙 (p1 test 에서 turn 위치는 상태 지시의 할 일 목록을 한 답에
    다 물어 '질문 여러 개'가 26 → 62 로 늘었다 — base 의 '질문 하나' 규칙은 너무 멀다)"""
    mode, rs = state(guards)
    out = ["base", f"modes.{mode}"] + [f"reasons.{r}" for r in rs if r in bank["reasons"]]
    return out + (["suffix"] if bank.get("suffix") else [])


def get(bank, name):
    if name in ("base", "suffix"):
        return bank[name]
    sec, key = name.split(".", 1)
    return bank[sec][key]


def put(bank, name, text):
    out = json.loads(json.dumps(bank))
    if name in ("base", "suffix"):
        out[name] = text
    else:
        sec, key = name.split(".", 1)
        out[sec][key] = text
    return out


def compose(bank, guards):
    """(base, 상태 지시) 두 덩어리"""
    names = parts(bank, guards)
    return get(bank, "base"), "\n".join(get(bank, n) for n in names[1:])


def messages(bank, history, guards, position="system"):
    """system: 시스템 프롬프트 하나를 턴마다 다시 조립 (계획서 F2 그대로).
    turn: base 는 맨 앞 시스템, 상태 지시는 마지막 시스템 메시지 (8B 가 긴 지침보다 이걸 잘 따랐다)"""
    base, now = compose(bank, guards)
    conv = [{"role": "user" if r == "user" else "assistant", "content": t} for r, t in history]
    if position == "system":
        return [{"role": "system", "content": f"{base}\n\n{now}"}] + conv
    return [{"role": "system", "content": base}] + conv + [{"role": "system", "content": now}]
