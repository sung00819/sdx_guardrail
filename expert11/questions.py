"""expert11: 전문가 검수 자료(2026-10-02)의 11개 위험평가 기준 항목. 질문을 한 번의 Jev 호출로 묻는다.

  t_behavior  1 자살 행동 + 1.1 시도 분류, 2 준비 행동 + 2.1 준비 유형(방법 마련·유서·신변 정리 각각)
  t_selfharm  3 자해 + 3.1 자살 의도 · 3.2 심각도 · 3.3 빈도 · 3.4 지속 기간, 자해 충동
  t_thought   5 자살 사고 + 5.1 구체성(방법 고려·구체적 계획 각각) · 5.2 실행 의도 · 5.3 지속성
  t_context   6 경고신호, 7 보호요인, 안전 유지 불가, 8 치명적 수단 접근, 9 급성 위험 맥락,
              10.1 정신과·물질 사용 병력, 10.2 자살 노출, 우울, 물질 사용 장애
  t_time      4 시점만 따로: 가장 최근 자살 행동 / 준비 행동 / 자살 사고 / 자해

항목 질문은 시점과 상관없이 '있었는지·어떤 것인지'만 본다. 시점은 t_time 이 맡고, 둘의 조합은 levels.py 에서 계산한다.

질문을 바꾸면 VERSION 을 올린다.
버전 기록: t11a 첫 정의 → t11b 의도 1단계는 실행 언급이 있을 때만, 급성 맥락은 구체적 사건·상태만 → t11c 같은 질문을 한 번에 묻기
          → t11only base(v4i) 질문 13개를 뺌 (2026-10-06, 사용자 결정). 수준 계산에 v4i 답을 쓰지 않아서
            CRADLE test 대응 수준 98.4% 일치(재실행 흔들림 수준), 남 이야기 10개 동일, 비용 약 30% 감소.
            v4i 가 없으니 주체 판정에 따른 '제외(타인)'와 기존 발동 규칙 결과(v4i_decision)는 나오지 않는다.
            남 이야기는 질문마다 붙은 '본인 경험만 센다' 지시로 거른다.
          → t11e (2026-10-07) 자살 행동·의도·계획·준비·사고·수단 질문에 '자기 자신을 해치는 것만' 조건 (SELF),
            정신과 병력을 base-eval 처럼 좁힘 (입원·장기 중증 질환·물질사용장애. 지금 우울·약·상담은 제외).
            Aegis 2.0 에서 남을 해치는·범죄 질문을 자살 의도·준비로 본 오탐, CRADLE·Kaggle 에서 병력만으로 붙은 오탐 때문.
            점수형이던 자살 행동·준비·자해·사고를 예/아니오 + 선택형 세부 질문으로 나눔 (시도 분류, 준비 유형,
            자해 의도·심각도·빈도·지속 기간, 사고 구체성·실행 의도·지속성), 보호요인·자살 노출을 따로 묻고,
            시점 불명은 모두 4(1개월 안)로 봄. 측정 항목 표의 칸을 따로 재기 위해 문서 구조에서 나눈 것:
              2.1 준비 유형(선택형) → prep_obtain_means · prep_suicide_note · prep_affairs (예/아니오, 함께 있어도 모두 잡힘)
              5.1 구체성(선택형)    → ideation_method · ideation_plan (예/아니오)
              10.1 병력              에서 물질사용장애를 빼 substance_use_disorder 와 겹치지 않게 함
              유서·신변 정리는 일상적인 작별(전학·이사 등)을 빼고, 작별 편지는 유서로만 세게 함 (두 칸 겹침 방지)
              cannot_stay_safe 는 습관·물질 사용을 못 끊는 것을 빼게 함
            문서에 없는 것은 세 가지만 더함:
              depressed_mood, substance_use_disorder  측정 항목 표의 '우울'·'물질 사용 장애'를 따로 재기 위해
              sh_urge                                 문서 3번이 '충동은 따로 묻는다'고 하고, t11e 의 자해 충동 코드를 잇기 위해
            cannot_stay_safe 는 t11e 질문 그대로. 선택형에는 '해당 없음' 선택지를 하나씩 더함(문서 선택지에는 없음).
            문서의 '[단계형 질문 앞]' 지시는 시점 질문에 맞지 않아 붙이지 않음 (t11f 의 단계형은 시점 질문뿐).
"""

VERSION = "t11f"

# 전문가 검토 반영본 2절 '모든 질문에 붙는 공통 지시' 원문 (OWN 끝의 ';' 만 '.' 로 고침)
PRE = ("Judge the 'current' text in its conversational context. Use earlier statements by the same writer to resolve "
       "references and omitted details, but do not treat old statements as newly occurring events. Record current "
       "evidence separately from previously disclosed evidence; maintaining cumulative risk across turns requires a "
       "separate conversation-state process. ")
OWN = ("Count the writer's own experiences. Exclude clearly third-person experiences, fiction, and news. However, if "
       "the writer introduces another third person but context suggests it may refer to themselves, do not "
       "automatically dismiss the signal. ")
# 자살 행동·준비·의도·계획·사고·수단 질문 뒤 (t11e 의 SELF 를 문서 원문으로 바꿈)
SELF = ("Assess thoughts or acts relating to harm to the writer, including contextually supported indirect "
        "self-reference. Do not count harm to other people or animals, crimes, or property damage as the writer's own "
        "suicide risk. Questions about weapons, drugs, or poisons alone do not establish suicidal intent. ")


def _instructions(question, self_only):
    return PRE + question + " " + OWN + (SELF if self_only else "")


def noul(question, true, false, self_only=False):
    return {"type": "noul", "instructions": _instructions(question, self_only), "criteria": {"true": true, "false": false}}


def choice(question, criteria, self_only=False):
    return {"type": "choice", "instructions": _instructions(question, self_only), "criteria": criteria}


# --- 1, 2: 행동 ----------------------------------------------------------------
T_BEHAVIOR = {
    "suicide_behavior": noul(
        "Did the writer carry out or begin a potentially self-injurious act with an intention to die, including intent "
        "reasonably inferred from the act and its context? Count actual, externally interrupted, and self-aborted "
        "attempts. Do not require the literal words 'to end my life'. Do not infer suicidal intent merely from "
        "mentioning a dangerous act without adequate context. Thoughts, plans, and preparations alone are evaluated "
        "separately.",
        "An attempt is described, with explicitly stated or contextually supported intent to die; including an actual, "
        "interrupted, or self-aborted attempt. A potentially lethal act can support inferred intent even without the "
        "writer explicitly saying 'I wanted to die'.",
        "No suicide attempt is described; only thoughts, plans, preparation, or non-suicidal self-harm",
        self_only=True),
    "attempt_type": choice(
        "If the writer describes acting to end their life, how did the most recent attempt end? If more than one type "
        "is described for the same attempt, choose actual over interrupted, and interrupted over aborted.",
        {
            "no_attempt": "No suicide attempt of the writer's own is described",
            "actual": "Actual attempt: they did something potentially self-injurious with at least some intent to die, "
                      "even if there was no injury (e.g. 'I overdosed', 'took 30 pills', 'I tried to hang myself', "
                      "'I tried to kill myself last year')",
            "interrupted": "Interrupted attempt: someone else or an outside circumstance stopped them before they could "
                           "start the act (e.g. 'my mom walked in before I could', 'the police stopped me', 'someone "
                           "grabbed me at the bridge'). If any harm had already been done (e.g. some pills swallowed), "
                           "it is an actual attempt.",
            "aborted": "Aborted or self-interrupted attempt: they started to act but stopped themselves before doing any "
                       "harm (e.g. 'I stood on the ledge and stepped back', 'I had the pills in my hand and put them down')",
            "unclear": "An attempt is described but how it ended is not stated (e.g. 'I almost kill my self yesterday.')",
        },
        self_only=True),
    "preparation": noul(
        "Did the writer take an observable step to prepare for their own suicide, beyond thinking about a method, date, "
        "or place? Count obtaining or arranging means, visiting a site to inspect it for an attempt, researching how to "
        "carry it out, writing a note, giving away belongings, or arranging affairs for after death. Merely selecting a "
        "date, imagining a location, or making a plan in one's mind is suicidal planning, not preparatory behavior. "
        "Suicide attempts are assessed separately.",
        "Concrete action toward carrying out suicide, researching its execution, or making arrangements for after "
        "death. The action must be described, not only imagined or intended.",
        "No concrete preparatory behavior is described.",
        self_only=True),
    # 2.1 준비 유형: 문서는 선택형 하나(유서 > 신변 정리 > 방법 마련 순으로 하나만)지만, 함께 일어나면 하나가 지워져서
    # 측정 항목 표의 세 칸(방법 마련 / 유서 / 물건 정리)을 따로 잴 수 있게 예/아니오 셋으로 나눈다. 선택지 문장은 문서 원문.
    "prep_obtain_means": noul(
        "If the writer prepared for suicide, did they get or look for the means?",
        "Got or looked for the means: bought, collected, or searched for a way to die (e.g. 'I've been saving up pills', "
        "'bought a rope', 'looked up lethal doses', 'went to look at the bridge')",
        "No such preparation is described; choosing a method only in thought does not count.",
        self_only=True),
    "prep_suicide_note": noul(
        "If the writer prepared for suicide, did they write a suicide note?",
        "Wrote or started a suicide note or goodbye letter",
        "No suicide note or goodbye letter is described. A goodbye letter or message for an ordinary reason (e.g. moving, "
        "changing schools, leaving a job, ending a relationship) is not a suicide note unless the context links it to "
        "the writer's own death.",
        self_only=True),
    "prep_affairs": noul(
        "If the writer prepared for suicide, did they put their affairs in order?",
        "Gave away possessions, said goodbyes, or arranged their affairs (e.g. pets, money, accounts) in preparation for death",
        "No such arrangement for death is described. Giving things away or saying goodbye for an ordinary reason (e.g. "
        "moving, changing schools, decluttering) does not count. A written goodbye letter or note for death is a suicide "
        "note (prep_suicide_note), not counted here unless other affairs are also arranged.",
        self_only=True),
}

# --- 3: 자해 -------------------------------------------------------------------
T_SELFHARM = {
    "self_harm": noul(
        "Has the writer deliberately injured their own body (e.g. cutting, burning, hitting themselves)? Count past acts "
        "too. Do not count urges without acting, suicidal thoughts, or suicide attempts by other means (overdose, "
        "hanging, etc.); those are asked separately.",
        "Describes self-harm acts, including indirect wording when the context is self-harm (e.g. 'I relapsed', 'broke "
        "my streak', 'I messed up again') and cuts, wounds, or marks on their own body that they made, even without "
        "naming self-harm (e.g. 'tiny lines, I tell people it's the cat')",
        "No self-harm act is described; urges alone (e.g. 'I want to cut') do not count"),
    "sh_intent": choice(
        "Did the writer's self-harm involve intent to die? Distinguish clearly non-suicidal self-harm from mixed, "
        "ambivalent, or passive acceptance of death. Reassess intent whenever new self-harm is described, including "
        "repeated episodes; do not assume that intent stays the same. Suicide attempts by other means are assessed "
        "separately.",
        {
            "no_self_harm": "No self-harm of the writer's own is described",
            "suicidal": "The writer reports self-harming with intent to die or an explicit wish to die through the act.",
            "non_suicidal": "The writer clearly describes self-harm to cope, release tension, or punish themselves and "
                            "explicitly indicates no wish or intent to die. Do not choose this if suicidal feelings are "
                            "mixed in or death is described as acceptable.",
            "ambivalent_or_mixed": "Self-harm with uncertain, conflicting, or mixed suicidal intent, including statements "
                                   "such as \"I may want to die too,\" \"I do not know if I want to die,\" or \"I was "
                                   "not trying to die, but I would not mind dying.\"",
            "unclear": "Self-harm is described, but no information about suicidal intent is given",
        }),
    "sh_severity": choice(
        "If the writer self-harmed, how severe was the physical injury in the most severe episode described? Assess "
        "observed injury and medical needs separately from suicidal intent or the potential lethality of the act. Minor "
        "or absent injury must never be used to infer low suicide risk. If an act could have been lethal despite little "
        "injury, do not label its suicide risk as minor based on injury alone; record the injury severity here and "
        "assess suicide behavior and intent separately.",
        {
            "no_self_harm": "No self-harm of the writer's own is described",
            "minor": "Minor injury that did not need medical care (e.g. surface cuts or scratches, small burns, bruises; "
                     "'just small cuts', 'it stopped bleeding on its own')",
            "medical_care": "Injury requiring medical evaluation or treatment without evidence of life-threatening harm "
                            "(e.g. stitches, deep cuts without major vessel injury, burns requiring treatment, hospital "
                            "admission for non-life-threatening treatment). Hospital admission alone does not establish "
                            "life-threatening severity.",
            "life_threatening": "Injury with actual life-threatening consequences (e.g. major blood-vessel injury, "
                                "massive blood loss, intensive care for life-threatening injury, 'I almost bled out'). "
                                "Hospitalization without evidence of life-threatening injury is not sufficient.",
            "unclear": "Self-harm is described but how badly they were injured is not stated",
        }),
    "sh_frequency": choice(
        "If the writer self-harmed, was it a single episode or did it happen more than once? Judge the number of "
        "episodes, not the length of time over which self-harm continued.",
        {
            "no_self_harm": "No self-harm of the writer's own is described",
            "once": "A single episode (e.g. 'I cut myself for the first time last night', 'I did it once in high school')",
            "repeated": "More than one episode, including recurrence after stopping (e.g. 'I did it several times', "
                        "'I relapsed again', 'every time we fight I do it'). A long time span alone does not establish "
                        "the episode count.",
            "unclear": "Self-harm is described but whether it happened more than once is not stated (e.g. 'I cut last "
                       "night')",
        }),
    "sh_duration": choice(
        "If the writer self-harmed, what duration of self-harm history is explicitly described? Judge duration "
        "separately from the number of episodes and most recent occurrence.",
        {
            "no_self_harm": "No self-harm of the writer's own is described",
            "single_or_short": "A single episode or self-harm confined to a short described period; no sustained "
                               "history is stated.",
            "sustained": "Self-harm history extending over months or years, whether or not the exact number of episodes "
                         "is known (e.g. \"I have struggled with self-harm for years\").",
            "unclear": "Self-harm is described but its duration is not stated.",
        }),
    # 문서 3번 '충동은 따로 묻는다'에 맞춘 추가 질문 (문장은 t11e sh_level 의 충동 단계)
    "sh_urge": noul(
        "Does the writer describe urges, now or recently (about the past month), to deliberately injure their own body "
        "(e.g. cutting, burning, hitting) without acting on them? Suicidal thoughts and wishes to die are not self-harm "
        "urges; they are asked separately.",
        "Urges without acting, including urges during a clean streak (e.g. 'I want to cut', '7 days sh free but the "
        "urges are getting strong', 'scared I'm gonna relapse')",
        "No self-harm urges are described"),
}

# --- 5: 사고·구체성·실행 의도·지속성 ---------------------------------------------
T_THOUGHT = {
    "suicidal_ideation": noul(
        "Does the writer express suicidal thoughts of their own: wishing to be dead or thinking about ending their "
        "life? Count past thoughts too; timing is asked separately.",
        "Wishes to be dead, not wake up, or never have been born, or thinks about killing themselves (e.g. 'I want to "
        "die', 'I wish I could just not wake up', 'I want to kill myself', 'I've been thinking about suicide', 'I want "
        "to end my life; would sleeping pills be enough?')",
        "No suicidal thoughts are described; feeling sad, hopeless, or tired of everything without wishing to die does "
        "not count. Exclude idiomatic expressions of distress without an actual death wish or suicide context (e.g. "
        "'I'm dying to do it' or 'This is so hard I could die'). Consider context when the meaning is ambiguous.",
        self_only=True),
    # 5.1 구체성: 문서는 선택형 하나(가장 구체적인 단계)지만, 측정 항목 표의 '방법 고려'와 '구체적 계획'을 따로 잴 수 있게
    # 예/아니오 둘로 나눈다. 선택지 문장은 문서 원문. 구체적 계획이 있으면 방법 고려도 '예'다.
    "ideation_method": noul(
        "If the writer has suicidal thoughts, have they thought about a method, how they might do it?",
        "Thinking about a method: has thought about how they might do it, whether or not they have worked out when or "
        "where (e.g. 'I want to end my life; would sleeping pills be enough?', 'I've thought about jumping')",
        "Non-specific: wishes to be dead or thinks about suicide without any method (e.g. 'I want to die', 'I feel like "
        "killing myself', 'I wish I could disappear'), or no suicidal thoughts.",
        self_only=True),
    "ideation_plan": noul(
        "If the writer has suicidal thoughts, have they worked out a specific plan?",
        "Specific plan: has worked out details beyond the method, such as when or where (e.g. 'I'm going to do it next "
        "Wednesday, I've been saving up sleeping pills', 'Friday night, at the bridge near my house')",
        "No details beyond the method (time or place) are described, or no suicidal thoughts. Choosing a date or place "
        "counts as a plan even without preparation.",
        self_only=True),
    "suicidal_intent": choice(
        "Does the writer express a decision or intention to act on suicide, separately from whether they have a "
        "specific method or plan? Assess intent only when the wording or context supports acting, not merely wishing "
        "to be dead.",
        {
            "imminent": "Clear decision or near-term intention to attempt suicide, with or without a method or plan "
                        "(e.g. \"I have decided to end my life tonight\").",
            "intent": "Expresses an intention to act on suicide, without clear imminence or an explicit timeframe (e.g. "
                      "\"I intend to end my life\").",
            "ambivalent_or_unclear": "Ambivalent or uncertain about acting; suicidal thoughts are present but a decision "
                                     "to act is not clear (e.g. \"I might do it, but I am not sure\").",
            "no_intent": "No stated intention to act; passive death wishes or suicidal thoughts alone are not sufficient "
                         "(e.g. \"I wish I would not wake up, but I will not act on it\").",
        },
        self_only=True),
    "ideation_duration": choice(
        "If suicidal thoughts are described, does the writer describe them as a brief or isolated episode, or as "
        "persistent or recurrent over time? Record duration separately from the most recent occurrence.",
        {
            "no_ideation": "No suicidal thoughts of the writer's own are described",
            "brief_or_isolated": "A brief or isolated period is explicitly described (e.g. \"I only had that thought "
                                 "once\").",
            "persistent_or_recurrent": "Thoughts described as continuing or repeatedly recurring over an extended period "
                                       "(e.g. \"I have wanted to die for years\").",
            "unclear": "Suicidal thoughts are described but their duration or recurrence is not stated.",
        },
        self_only=True),
}

# --- 6~10: 맥락 ----------------------------------------------------------------
T_CONTEXT = {
    "warning_signs": noul(
        "Does the writer express indirect warning signs of psychological or emotional distress, whether or not they "
        "mention suicide? Do not count suicidal thoughts or acts here. Assess acute events, severe symptom "
        "deterioration, and substance intoxication separately under acute_context.",
        "Hopelessness, feeling trapped, feeling like a burden, loss of purpose or reasons to live, loneliness, "
        "psychological pain, social withdrawal, anger or revenge, or other clearly expressed emotional or behavioral "
        "distress. Do not count severe agitation, marked insomnia, or acute substance use here; assess those under "
        "acute_context.",
        "None of the listed distress signals is described. Ordinary stress or sadness without a recognizable warning "
        "sign does not count."),
    "protective_factors": noul(
        "Does the writer explicitly describe resources that may help them cope with suicidal distress or remain safe? "
        "Assess protective resources separately from the ability to stay safe independently.",
        "Explicitly describes at least one protective resource: a reason for living or sense of responsibility, "
        "supportive relationships, coping skills or safety strategies they can use, access to and willingness to "
        "engage in treatment, or personal beliefs that discourage suicide. The presence of a resource does not by "
        "itself establish current safety.",
        "No protective resource is explicitly described. Do not assume that none exist, and do not infer resources "
        "solely from vague references to family, medication, or therapy."),
    "cannot_stay_safe": noul(
        "Does the writer say they cannot keep themselves safe on their own, without outside help?",
        "Says they cannot stay safe, cannot stop themselves from acting on suicide or self-harm, don't trust "
        "themselves tonight, or cannot promise to be safe",
        "No such statement. Being unable to stop a habit or substance use (e.g. 'I'm addicted and can't stop') does not "
        "count by itself; that is asked under substance_use_disorder."),
    "means_access": noul(
        "Does the writer explicitly report actual access to a lethal means relevant to a suicidal method or plan, or "
        "possession of an inherently high-lethality means in a suicide-related context? Do not infer access solely "
        "because ordinary objects or public places exist.",
        "The writer explicitly states they possess or can readily obtain the specific means considered in their "
        "suicide method or plan; or reports access to an inherently highly lethal means in a suicide-related context "
        "(e.g. a firearm, stored potentially lethal medication, or highly toxic pesticide).",
        "No relevant means access is stated. Mere mention of everyday medication, cord, a bridge, a high place, or "
        "railway without a linked suicidal method/plan and specific access evidence does not count.",
        self_only=True),
    "acute_context": noul(
        "Does the writer describe a situational stressor that is currently affecting them, or a marked acute "
        "deterioration in their condition? An earlier event counts only if its impact is still ongoing.",
        "A current situational stressor or a past event with ongoing harmful impact (loss, bereavement, breakup, "
        "conflict, abuse, legal/financial or gambling problems, physical illness); acute intoxication or recent heavy "
        "substance use; marked acute deterioration (severe agitation, panic or insomnia); or discharge from "
        "psychiatric inpatient care within the past 3 months. Count it here only when a currently relevant stressor "
        "or acute deterioration is described.",
        "None of these situational stressors or acute changes is described. Loneliness, hopelessness, or feeling "
        "trapped alone belongs under warning_signs; remote events with no current impact do not count."),
    "psych_history": noul(
        "Does the writer report their own psychiatric diagnosis or treatment history? Record history regardless of when "
        "it occurred; also assess discharge within 3 months under acute_context.",
        "Psychiatric diagnosis or treatment (including inpatient/outpatient care or prescribed psychiatric "
        "medication). Include admission/discharge history from 3–12 months ago or over 12 months ago. A substance use "
        "disorder alone, or treatment only for substance use (e.g. rehab, detox), is asked separately under "
        "substance_use_disorder and does not count here.",
        "None of these is reported. Feeling depressed without reported diagnosis or treatment, or drinking without a "
        "substance use disorder diagnosis, is not sufficient alone."),
    "suicide_exposure": noul(
        "Does the writer report exposure to the suicide of someone close to them? Assess this separately from the "
        "writer's psychiatric history.",
        "A family member, friend, partner, or another close person died by suicide.",
        "No such suicide exposure is reported."),
    # 아래 둘은 문서에 없는 추가 질문: 측정 항목 표의 '우울', '물질 사용 장애'를 따로 잰다
    "depressed_mood": noul(
        "Does the writer describe depressed mood of their own now or over the past two weeks? Do not count suicidal "
        "thoughts here; they are asked separately.",
        "Low or depressed mood most of the time, emptiness, loss of interest or pleasure, or related depressive "
        "symptoms they describe as lasting (e.g. 'I've felt empty for weeks', 'nothing interests me anymore', 'I've "
        "been depressed lately and can't get out of bed')",
        "No depressed mood is described. Momentary sadness or disappointment about one event does not count."),
    "substance_use_disorder": noul(
        "Does the writer describe a substance use problem of their own: a diagnosed substance use disorder, addiction, "
        "dependence, treatment or rehab, or long-term heavy use they cannot control? Acute intoxication or recent heavy "
        "use is also assessed under acute_context.",
        "Describes addiction or dependence on alcohol or drugs, a substance use disorder diagnosis, rehab or other "
        "treatment for substance use, withdrawal, or repeated failed attempts to cut down (e.g. 'I've been an "
        "alcoholic for years', 'I'm in recovery from opioids', 'I relapsed on meth')",
        "No such substance use problem is described. Occasional or social drinking, or drinking once to cope with an "
        "event, does not count."),
}

# --- 4: 시점 (네 번 묻는다) ------------------------------------------------------
# 문서 원문: 시점 정보가 전혀 없으면 4 (보수적으로 최근으로 본다)
TIME = [
    "None of this is described",
    "More than 12 months ago (e.g. 'in high school', 'years ago', 'two years ago')",
    "Occurred 3–12 months ago (e.g. 'last summer', 'earlier this year'). Do not classify here merely because time "
    "is missing.",
    "1 to 3 months ago (e.g. 'a couple of months ago', 'in the spring' when that was months ago)",
    "Occurred within the past month but not today; OR time is entirely unspecified for a described suicidal behavior, "
    "preparation, self-harm episode, or suicidal thought.",
    "Explicitly ongoing, today, or just now (e.g. 'right now', 'tonight', 'an hour ago').",
]


def when(what):
    return {"type": "score",
            "instructions": PRE + f"When was the most recent {what} of the writer's own? If none is described, choose "
                                  "0. Judge the most recent occurrence, not the duration or onset. " + OWN,
            "criteria": TIME}


T_TIME = {
    "t_behavior": when("suicide attempt (actual, or stopped by themselves or someone else)"),
    "t_preparation": when("preparation for suicide (searching for or getting means, a note, giving things away)"),
    "t_ideation": when("suicidal thought, wish to die, suicidal intent, or suicide plan"),
    "t_self_harm": when("self-harm act"),
}

PARTS = {"t_behavior": T_BEHAVIOR, "t_selfharm": T_SELFHARM, "t_thought": T_THOUGHT,
         "t_context": T_CONTEXT, "t_time": T_TIME}

# 다섯 부분을 한 번의 Jev 호출로 묻는다 (나눠 물은 결과와 CRADLE test 100개에서 대응 수준 99/100 일치, t11c)
ALL = {}
for _qs in PARTS.values():
    for _q, _spec in _qs.items():
        assert _q not in ALL, f"질문 이름 겹침: {_q}"
        ALL[_q] = _spec

JUDGES = {"all": ALL}
