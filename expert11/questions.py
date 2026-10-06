"""expert11: 전문가 검수 자료(2026-10-02)의 11개 위험평가 기준 항목. 질문 17개를 한 번의 Jev 호출로 묻는다.

  t_behavior  1 자살 행동, 4 준비 행동
  t_thought   2 자살 의도, 3 자살 계획, 5 자살 사고
  t_selfharm  6 자해 (정도 + 자살 의도)
  t_context   7 치명적 수단 접근, 8 급성 위험 맥락, 9 정신과 병력·위험요인, 10 간접 경고신호, 11 보호요인·안전 유지 불가
  t_time      시점만 따로: 가장 최근 자살 행동 / 준비 행동 / 자살 사고 / 자해

항목 질문은 시점과 상관없이 '있었는지·얼마나'만 본다. 시점은 t_time 이 맡고, 둘의 조합은 combine.py 에서 계산한다.
결정 사항: 자살 의도는 '부인함' 없이 점수(약간 있음 단계 포함, 부인은 챗봇이 판단), 자살 행동은 스스로 멈춘 시도와 남이 막은
시도를 한 단계로 합침, 9번은 전문가 정의대로 넓게, 시점 불명인 자살 사고는 '최근 1개월'로 본다(원칙 5).

질문을 바꾸면 VERSION 을 올린다.
버전 기록: t11a 첫 정의 → t11b 의도 1단계는 실행 언급이 있을 때만, 급성 맥락은 구체적 사건·상태만 → t11c 같은 질문을 한 번에 묻기
          → t11only base(v4i) 질문 13개를 뺌 (2026-10-06, 사용자 결정). 수준 계산에 v4i 답을 쓰지 않아서
            CRADLE test 대응 수준 98.4% 일치(재실행 흔들림 수준), 남 이야기 10개 동일, 비용 약 30% 감소.
            v4i 가 없으니 주체 판정에 따른 '제외(타인)'와 기존 발동 규칙 결과(v4i_decision)는 나오지 않는다.
            남 이야기는 질문마다 붙은 '본인 경험만 센다' 지시로 거른다.
"""

VERSION = "t11only"

PRE = "Judge the 'current' text. Use 'context' (earlier text by the same writer) only to interpret it. "
OWN = "Count only the writer's own experience; do not count someone else's (a friend, partner, family member), fiction, or news. "
ANYTIME = "Rate the most severe level described, whether past or present; timing is asked separately. "


def score(question, criteria):
    return {"type": "score", "instructions": PRE + ANYTIME + question + " " + OWN, "criteria": criteria}


def noul(question, true, false):
    return {"type": "noul", "instructions": PRE + question + " " + OWN, "criteria": {"true": true, "false": false}}


# --- 1, 4: 행동 ----------------------------------------------------------------
T_BEHAVIOR = {
    "suicide_behavior": score(
        "Did the writer act to end their life? This includes attempts that were stopped by themselves or by someone "
        "else before any injury. Thoughts, plans, and preparation alone are not counted here. Non-suicidal self-harm "
        "(e.g. cutting to cope) is not counted.",
        [
            "No suicide attempt described",
            "Started to act toward ending their life but stopped or was stopped before any injury "
            "(e.g. 'I stood on the ledge and stepped back', 'had the pills in my hand and put them down', "
            "'my mom walked in before I could', 'the police stopped me')",
            "Actual attempt: did something potentially self-injurious with at least some intent to die "
            "(e.g. 'I overdosed', 'took 30 pills', 'I tried to hang myself', 'I tried to kill myself last year')",
        ]),
    "preparation": score(
        "Did the writer do something to prepare for suicide, beyond talking or thinking about it?",
        [
            "No preparatory behavior described",
            "Searched for or looked into means (e.g. researched lethal doses, looked up how high a bridge is, "
            "went to look at a place)",
            "Obtained or collected means (e.g. saving up pills, bought a rope or a gun)",
            "Prepared for death (e.g. wrote a suicide note, gave away possessions, said goodbyes, set a date, "
            "put affairs in order)",
        ]),
}

# --- 2, 3, 5: 사고·의도·계획 ----------------------------------------------------
T_THOUGHT = {
    "suicide_intent": score(
        "How much intent does the writer express to act on suicidal thoughts? Intent need not be firm and can "
        "coexist with wanting to live.",
        [
            "No intent to act is expressed: thoughts or wishes only, knowing ways to do it, or wishing they had done "
            "it, without saying anything about actually acting (e.g. 'I want to die', 'I know ways I could do it')",
            "Some or ambivalent intent: says something about possibly acting (e.g. 'I might actually do it', "
            "'I don't know if I'll stop myself', 'part of me wants to go through with it')",
            "Clear intent (e.g. 'I'm going to kill myself', 'I've decided', 'tonight is the night')",
        ]),
    "suicide_plan": score(
        "How worked-out is the writer's plan for suicide (when, where, how)?",
        [
            "No plan described",
            "Has thought of a method only, without working out when or where (e.g. 'I've thought about pills')",
            "Has worked out some details beyond the method (time or place) (e.g. 'pills, probably this weekend')",
            "Has worked out the method, time, and place (e.g. 'Friday night, at the bridge near my house, I'll jump')",
        ]),
    "suicide_ideation": score(
        "What is the most severe suicidal ideation the writer expresses, following the C-SSRS ideation categories "
        "(1 to 3)? Intent and plans are asked separately.",
        [
            "No suicidal ideation",
            "Wish to be dead: wishes to be dead, not wake up, never have been born, or disappear "
            "(e.g. 'I wish I was never born', 'I want to die', 'I wish I could just not wake up')",
            "Non-specific active suicidal thoughts: thoughts of killing oneself, without thinking about how "
            "(e.g. 'I want to kill myself', 'I've been thinking about suicide')",
            "Thinks about a method: has thought of how they might kill themselves (method, means, place)",
        ]),
}

# --- 6: 자해 -------------------------------------------------------------------
T_SELFHARM = {
    "sh_level": score(
        "How severe is the writer's self-harm (deliberately injuring their own body, e.g. cutting, burning, hitting)? "
        "Do not count suicidal thoughts, wishes to die, or suicide plans as self-harm urges, and do not count suicide "
        "attempts by other means (overdose, hanging, etc.); those are asked separately.",
        [
            "No self-harm",
            "Urges only, without acting, including urges during a clean streak "
            "(e.g. 'I want to cut', '7 days sh free but the urges are getting strong', 'scared I'm gonna relapse')",
            "Self-harm acts, including indirect wording when the context is self-harm (e.g. 'I relapsed', 'broke my "
            "streak', 'I messed up again') and cuts, wounds, or marks on their own body that they made, even without "
            "naming self-harm (e.g. 'tiny lines, I tell people it's the cat'); past acts count too",
            "Repeated, habitual, or severe self-harm: many times or for a long period, escalating injuries or new "
            "methods, wounds needing medical care, or loss of control",
        ]),
    "sh_intent": {
        "type": "choice",
        "instructions": PRE + "Did the writer's self-harm (deliberately injuring their body, e.g. cutting, burning) "
                              "involve intent to die? Suicide attempts by other means are asked separately. " + OWN,
        "criteria": {
            "no_self_harm": "No self-harm of the writer's own is described",
            "suicidal": "The writer says they hurt themselves wanting or trying to die",
            "non_suicidal": "The writer says it was to cope, release, or punish themselves, not to die",
            "unclear": "Self-harm is described but whether there was intent to die is not stated",
        },
    },
}

# --- 7~11: 맥락 ----------------------------------------------------------------
T_CONTEXT = {
    "means_access": noul(
        "Does the writer have actual access to means that could be used for suicide?",
        "Has or can readily get lethal means: medication or pills, a firearm, poison, rope, or access to a high "
        "place, bridge, or railway they mention",
        "No access to lethal means is mentioned"),
    "acute_context": noul(
        "Does the writer describe a situation or state that raises risk right now?",
        "A specific recent stressful or triggering event they name (loss, bereavement, breakup, conflict, legal or "
        "financial problems, abuse), drinking or using drugs now or heavily lately, or clearly worsening symptoms "
        "such as severe agitation, panic, or not sleeping",
        "None of these. Feeling sad, tired, hopeless, trapped, or lonely without a named event does not count "
        "(those are warning signs, asked separately)"),
    "psych_history": noul(
        "Does the writer mention psychiatric history or other suicide risk factors of their own?",
        "Current or past mental illness or its treatment (including therapy, medication, or hospitalization), "
        "a chronic physical illness, or the suicide of someone close to them",
        "None of these is mentioned"),
    "warning_signs": noul(
        "Does the writer show indirect warning signs of near-term suicide risk, whether or not they mention suicide?",
        "Hopelessness, feeling trapped, feeling a burden, loss of purpose or no reason to live, social withdrawal, "
        "anxiety or agitation, sudden mood changes, sleep problems, reckless behavior, anger or revenge, "
        "or increased substance use",
        "None of these warning signs; ordinary sadness or stress alone does not count"),
    "protective": noul(
        "Does the writer mention protective factors?",
        "Reasons for living, supportive relationships, coping skills, access to treatment, or beliefs that keep "
        "them safe",
        "No protective factors are mentioned"),
    "cannot_stay_safe": noul(
        "Does the writer say they cannot keep themselves safe on their own, without outside help?",
        "Says they cannot stay safe, cannot stop themselves, don't trust themselves tonight, or cannot promise to "
        "be safe",
        "No such statement"),
}

# --- 시점 ----------------------------------------------------------------------
TIME_NOTE = ("Judge when the most recent occurrence happened, not when it first started or how long it has gone on: "
             "'I've been doing this for a year' means it is ongoing, and 'I relapsed after a year clean, 13 hours "
             "clean now' means today. ")
OLDER = ["None of this is described",
         "More than 12 months ago (e.g. 'in high school', 'years ago', 'two years ago')"]
RECENT = ["1 to 3 months ago (e.g. 'a couple of months ago', 'in the spring' when that was months ago)",
          "Within the past month but not today (e.g. 'last week', 'a few days ago', 'two weeks ago')",
          "Ongoing, today, or just now (e.g. 'right now', 'tonight', 'an hour ago', 'last night', 'I just took them')"]
# 행동은 시점 불명을 3~12개월과 같은 단계에 둔다 (슬라이드 8: 급성 중 '시점 불명 포함')
TIME_BEHAVIOR = OLDER + ["3 to 12 months ago, or the time is not stated or unclear (e.g. 'last summer', "
                         "'earlier this year', 'I've tried before')"] + RECENT
# 사고는 시점 불명을 '최근 1개월'에 둔다 (원칙 5)
TIME_THOUGHT = OLDER + ["3 to 12 months ago (e.g. 'last summer', 'earlier this year')", RECENT[0],
                        "Within the past month, or the time is not stated (thoughts described without a time are "
                        "taken as recent)", RECENT[2]]


def when(what, criteria):
    return {"type": "score", "instructions": PRE + f"When was the most recent {what} of the writer's own? If none is "
                                                   "described, choose the first option. " + TIME_NOTE + OWN,
            "criteria": criteria}


T_TIME = {
    "t_behavior": when("suicide attempt (actual, or stopped by themselves or someone else)", TIME_BEHAVIOR),
    "t_preparation": when("preparation for suicide (searching for or getting means, a note, giving things away)",
                          TIME_BEHAVIOR),
    "t_ideation": when("suicidal thought, wish to die, suicidal intent, or suicide plan", TIME_THOUGHT),
    "t_self_harm": when("self-harm (the most recent act; if there was never an act, the most recent urges)",
                        TIME_BEHAVIOR),
}

PARTS = {"t_behavior": T_BEHAVIOR, "t_thought": T_THOUGHT, "t_selfharm": T_SELFHARM,
         "t_context": T_CONTEXT, "t_time": T_TIME}

# 다섯 부분을 한 번의 Jev 호출로 묻는다 (나눠 물은 결과와 CRADLE test 100개에서 대응 수준 99/100 일치)
ALL = {}
for _qs in PARTS.values():
    for _q, _spec in _qs.items():
        assert _q not in ALL, f"질문 이름 겹침: {_q}"
        ALL[_q] = _spec

JUDGES = {"all": ALL}
