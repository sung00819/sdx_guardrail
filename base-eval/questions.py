"""base-eval: base(v4i) + 전문가 추가 제언 신호 + 자살 행동·자해의 경험과 시점. 질문 27개를 한 번의 Jev 호출로 묻는다.

  j1_axes        : v4i 13개 + 추가 신호 9개 (C-SSRS 사고 ①~⑤ 점수, 수단 접근, 급성 위험 맥락, 정신과 병력, 간접 경고신호,
                   안전 유지 불가, 부인 진술, 만성적 자살 사고, 보호요인)
  j2_suicide_beh : 자살 행동 경험 정도(C-SSRS 행동 유형) + 가장 최근 행동의 시점
  j3_self_harm   : 자해 경험 정도 + 가장 최근 자해의 시점 + 자해의 자살 의도

시점 단계는 전문가 자료 슬라이드 7 의 시간 창(3개월 / 3~12개월 / 12개월 이전)을 따른다.
시점이 드러나지 않으면 '3~12개월 전'과 같은 단계에 둔다 (슬라이드 8: 급성 중 '시점 불명 포함').

질문을 바꾸면 VERSION 을 올린다. 결과 파일 이름에 VERSION 이 들어가 이전 결과를 덮지 않는다.
버전 기록: el1 첫 정의 → el2 자해와 자살 구분, 시점 = 가장 최근 일, 부인·만성 사고 추가 → el3 자해 간접 표현 예시, 병력 좁힘
          → el3c 같은 질문을 한 번에 묻기
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from rules import load_design  # noqa: E402

V4I = load_design("base", "questions").QUESTIONS

VERSION = "el3c"

PRE = "Judge the 'current' text. Use 'context' (earlier text by the same writer) only to interpret it. "
OWN = "Count only the writer's own experience; do not count someone else's (a friend, partner, family member), fiction, or news. "

TIME_NOTE = ("Judge when the most recent occurrence happened, not when it first started or how long it has gone on: "
             "'I've been cutting for a year' means it is ongoing, and 'I relapsed after a year clean, 13 hours clean now' "
             "means today. ")

TIME_CRITERIA = [
    "No such experience is described",
    "More than 12 months ago (e.g. 'in high school', 'years ago', 'two years ago')",
    "3 to 12 months ago, or the time is not stated or unclear (e.g. 'last summer', 'earlier this year', 'I've tried before')",
    "Within the past 3 months but not today (e.g. 'last month', 'a few weeks ago', 'last week', 'a couple of days ago')",
    "Ongoing, today, or just now (e.g. 'I just took the pills', 'an hour ago', 'tonight', 'right now', 'last night')",
]


def noul(question, true, false):
    return {"type": "noul", "instructions": PRE + question, "criteria": {"true": true, "false": false}}


# --- J1: v4i + 전문가 추가 제언 신호 ---------------------------------------------
J1_EXTRA = {
    "si_ideation_stage": {
        "type": "score",
        "instructions": PRE + "Rate the most severe suicidal ideation of the writer's own within the past month, "
                              "following the C-SSRS ideation categories. " + OWN,
        "criteria": [
            "No suicidal ideation in the past month, or none described",
            "Wish to be dead: wishes to be dead, not wake up, never have been born, or disappear; no thoughts of killing oneself",
            "Non-specific active suicidal thoughts: thoughts of killing oneself or wanting to die by suicide, without a method, intent, or plan",
            "Thinks about a method without intent to act: has thought of how they might do it (method, means, place) but no intent to act",
            "Suicidal intent without a specific plan: says they intend or have decided to act on the thoughts",
            "Specific plan with intent: has worked out details (method with time, place, or steps) and intends to carry it out",
        ],
    },
    "means_access": noul(
        "Does the writer say they have or can readily get lethal means for suicide? " + OWN,
        "Has or can get lethal means: a firearm, a stockpile of pills or medication, poison, rope, access to a high place or "
        "bridge they mention, a car or other means they plan to use",
        "No access to lethal means is mentioned"),
    "acute_context": noul(
        "Does the writer describe an acute risk context right now or very recently? " + OWN,
        "A recent acute stressful event (loss, breakup, bereavement, job loss, legal or financial crisis, humiliation, "
        "being abused), being drunk or high now, or severe agitation, panic, or not sleeping",
        "No acute stressful event, intoxication, or severe agitation or insomnia is described"),
    "psych_history": noul(
        "Does the writer mention a psychiatric history risk factor of their own? " + OWN,
        "Past psychiatric hospitalization or inpatient stay, a long-standing serious mental illness (e.g. bipolar disorder, "
        "schizophrenia, psychosis, borderline personality disorder, depression lasting for years), or a substance use "
        "disorder (addiction, rehab, long-term heavy use)",
        "None of these. Feeling depressed now, taking an antidepressant, seeing a therapist, or drinking to cope with a "
        "recent event do not count by themselves"),
    "warning_signs": noul(
        "Does the writer show indirect suicide warning signs, whether or not they mention suicide? " + OWN,
        "Hopelessness about the future, feeling trapped or that there is no way out, feeling a burden to others, "
        "no reason or purpose to live, withdrawing from people, or saying goodbye or giving things away",
        "None of these warning signs; ordinary sadness or stress alone does not count"),
    "cannot_stay_safe": noul(
        "Does the writer say they cannot keep themselves safe on their own? " + OWN,
        "Says they cannot stay safe, cannot stop themselves, don't trust themselves tonight, or cannot promise to be safe",
        "No such statement"),
    "denial": noul(
        "Does the writer deny suicidal thoughts or intent? " + OWN,
        "Says they are not suicidal, will not kill themselves, or could never do it (e.g. 'I'm not going to kill myself', "
        "'I'd never actually do it', 'I'm not doing anything right now')",
        "No denial of suicidal thoughts or intent"),
    "si_chronic": noul(
        "Does the writer describe long-standing or recurring suicidal thoughts of their own? " + OWN,
        "Suicidal thoughts or wishes to die that have lasted or come back for many months or years "
        "(e.g. 'I've wanted to die since I was 12', 'these thoughts come and go for years')",
        "No long-standing or recurring suicidal thoughts are described"),
    "protective": noul(
        "Does the writer mention protective factors of their own? " + OWN,
        "Reasons for living (family, children, pets, faith, future plans), supportive people they can turn to, "
        "or ongoing treatment they engage with",
        "No protective factors are mentioned"),
}
J1 = {**V4I, **J1_EXTRA}


# --- J2: 자살 행동 경험 ---------------------------------------------------------
J2 = {
    "sb_level": {
        "type": "score",
        "instructions": PRE + "What is the most severe suicidal behavior of the writer's own that is described, past or "
                              "present? Timing is asked separately. Thoughts or wishes alone are not behavior. "
                              "Non-suicidal self-harm (e.g. cutting to cope) is not counted here. " + OWN,
        "criteria": [
            "No suicidal behavior: none described, or only thoughts, wishes, or plans without action",
            "Preparatory behavior: acts to get ready for suicide, such as getting or collecting means (pills, rope, a gun), "
            "writing a suicide note, giving away possessions, saying goodbye, or going to a place to die",
            "Self-interrupted (aborted) attempt: started to act toward killing themselves but stopped on their own "
            "before any harm (e.g. 'I stood on the ledge and stepped back', 'I had the pills in my hand and put them down')",
            "Interrupted attempt: was stopped by someone or something else before any harm "
            "(e.g. 'my mom walked in', 'the police stopped me', 'the rope broke before…')",
            "Actual attempt: did something potentially self-injurious with at least some intent to die "
            "(e.g. 'I overdosed', 'took 30 pills', 'I tried to hang myself', 'I tried to kill myself last year')",
        ],
    },
    "sb_time": {
        "type": "score",
        "instructions": PRE + "When was the most recent suicidal behavior (preparation, aborted, interrupted, or actual "
                              "attempt) of the writer's own? If none is described, choose the first option. " + TIME_NOTE + OWN,
        "criteria": TIME_CRITERIA,
    },
}


# --- J3: 자해 경험 -------------------------------------------------------------
J3 = {
    "sh_level": {
        "type": "score",
        "instructions": PRE + "What is the most severe self-harm of the writer's own that is described, past or present? "
                              "Self-harm means deliberately injuring their own body (cutting, burning, hitting, etc.). "
                              "Do not count suicidal thoughts, wishes to die, or suicide plans as self-harm urges, and do "
                              "not count suicide attempts (overdose, hanging, etc.) here; those are asked separately. "
                              "Timing is asked separately. " + OWN,
        "criteria": [
            "No self-harm: none described",
            "Urges only: urges or thoughts of self-harm without acting, including urges during a clean streak "
            "(e.g. 'I want to cut', '7 days sh free but the urges are getting strong', 'scared I'm gonna relapse')",
            "Self-harm acts, including indirect wording when the context is self-harm (e.g. 'I relapsed', 'broke my streak', "
            "'I messed up again', 'did it last night') and cuts, wounds, or marks on their own body that they made, even "
            "without naming self-harm (e.g. 'tiny lines, I tell people it's the cat', 'new marks everywhere'); past acts count "
            "too (e.g. 'I used to burn myself')",
            "Repeated, habitual, or severe self-harm: many times or for a long period, escalating injuries or new methods, "
            "wounds needing medical care, or loss of control",
        ],
    },
    "sh_time": {
        "type": "score",
        "instructions": PRE + "When was the most recent self-harm of the writer's own (the most recent act; if there was "
                              "never an act, the most recent urges)? If no self-harm is described, choose the first "
                              "option. " + TIME_NOTE + OWN,
        "criteria": TIME_CRITERIA,
    },
    "sh_suicidal_intent": {
        "type": "choice",
        "instructions": PRE + "Did the writer's own self-harm (deliberately injuring their body, e.g. cutting, burning) "
                              "involve intent to die? Suicide attempts by other means are asked separately. " + OWN,
        "criteria": {
            "no_self_harm": "No self-harm of the writer's own is described",
            "suicidal": "The writer says they hurt themselves wanting or trying to die",
            "non_suicidal": "The writer says it was to cope, release, or punish themselves, not to die",
            "unclear": "Self-harm is described but whether there was intent to die is not stated",
        },
    },
}

PARTS = {"j1_axes": J1, "j2_suicide_beh": J2, "j3_self_harm": J3}

# 세 부분을 한 번의 Jev 호출로 묻는다 (나눠 물어도 결과가 재실행 흔들림 수준으로 같았음: 대응 수준 98.9% 일치)
ALL = {}
for _qs in PARTS.values():
    for _q, _spec in _qs.items():
        assert _q not in ALL, f"질문 이름 겹침: {_q}"
        ALL[_q] = _spec

JUDGES = {"all": ALL}
