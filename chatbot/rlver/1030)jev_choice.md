# Jev 선택형 (2026-10-30: 11축의 합친 위험 축을 선택형으로)

`1030)jev.md` (11축, 모두 예/아니오) 의 위험 축 1·2·3·4·6 을 1014 워드 파일처럼 **항목을 고르는 선택형** 4개로 바꿨다. 합칠 때 잃었던 세부 구분(방법만 / 계획, 수단 / 유서 / 정리, 한 번 / 반복)을 선택지로 되살리고, 뱅크는 옛 절(3.1–3.9, 3.13·3.14)을 그대로 고른다.

- 예/아니오로 남는 것: 5 means_access, 7 cannot_stay_safe, 8 depression, 9–11 보정. 문구는 `1030)jev.md` 그대로 읽는다 (이 파일에는 없음).
- 공통 지시(모든 질문 앞·뒤, 자살 관련 질문 뒤)도 `1030)jev.md` 그대로다. 자살 관련 지시는 자해를 뺀 3개에 붙인다.
- 판정·채점: `jev_choice.py` → `out/rlver/jev_dev/1030)jev_choice_<source>.jsonl`, `1030)jev_choice_dev_eval.md`.

**켜짐 (라우팅)**: '없음' 이 아닌 선택지 확률의 합 ≥ 0.7. 예/아니오의 P(예) ≥ 0.7 과 같은 기준이다. 실행 의도만 `intent + imminent ≥ 0.7` (양가적은 켜지 않음, 결정 11). 워드 파일의 '신뢰도 0.9 이상' 은 쓰지 않는다 (확률이 선택지에 나뉘면 놓침이 는다).
**세부 항목**: '없음' 이 아닌 선택지 중 확률 0.3 이상은 모두 (둘 이상 함께 있을 수 있음). 뱅크는 그 항목들의 절을 넣는다.

| # | key | 선택지 | 대신하는 11축 | 뱅크 |
|---|---|---|---|---|
| 1 | suicidal_thought | none · ideation · method · specific_plan | 1 suicidal_ideation, 2 suicide_plan | ideation 3.13 · method 3.9 · specific_plan 3.4 |
| 2 | suicidal_intent | no_intent · ambivalent · intent · imminent | 3 suicidal_intent | intent·imminent 3.14 |
| 3 | preparatory_acts | none · obtain_means · suicide_note · put_affairs_in_order | 4 preparatory_acts | 3.1 · 3.2 · 3.3 |
| 4 | self_harm | none · once · repeated | 6 self_harm | once 3.5 · repeated 3.5 + 3.6 |

---

## 1. suicidal_thought — 자살 사고 수준

> **Q.** What is the most specific level of the writer's own suicidal thinking described, past or present? Choose the most specific level that is described anywhere in 'current'. A time or place set without a method still counts as specific_plan. Whether they intend to act is asked separately. A past attempt or self-harm act alone is not suicidal thinking.
> **none** No suicidal thoughts are described. Feeling sad, hopeless, or tired of everything without wishing to die does not count, nor do idiomatic expressions without an actual death wish or suicide context ('I'm dying to do it', 'this is so hard I could die').
> **ideation** Wishes to be dead or thinks about ending their life, with no method and no set time or place (e.g. 'I want to die', 'I wish I could just not wake up', 'I want to kill myself', 'I've been thinking about suicide', 'I wish I could disappear').
> **method** Has thought about how they might end their life, without a set time or place (e.g. 'I've thought about taking all my pills', 'I keep thinking about jumping', 'I've wondered about the gas in the car', 'would sleeping pills be enough?').
> **specific_plan** Has set a time or place for ending their life, with or without a method (e.g. 'next Wednesday, I've been saving pills for it', 'the bridge near my house', 'some night when I'm alone in the house', 'after the exams, that's when'). When the thoughts are happening ('tonight I keep thinking about it') is not a set time for the act.

> **질문.** 작성자 본인의 자살 사고가, 과거든 현재든, 가장 구체적으로 어느 단계까지 드러납니까? 'current' 어디에든 드러난 가장 구체적인 단계를 고르세요. 방법 없이 시기·장소만 정해도 구체적 계획입니다. 실행 의도는 따로 묻습니다. 과거 시도나 자해 행동만으로는 자살 사고가 아닙니다.
> **없음** 자살 사고가 드러나지 않음. 죽고 싶다는 말 없는 슬픔·절망·지침, 실제 죽음 소망 없는 관용 표현('~하고 싶어 죽겠다', '힘들어서 죽을 것 같아')은 해당하지 않음.
> **사고만** 죽고 싶거나 생을 끝내는 생각을 하지만 방법도, 정한 시기·장소도 없음 ('죽고 싶어', '안 깨어났으면 좋겠어', '자살하고 싶어', '자살을 생각하고 있어', '사라지고 싶어').
> **방법 고려** 어떻게 할지는 생각했지만 시기·장소는 정하지 않음 ('약을 다 먹는 걸 생각해 봤어', '뛰어내리는 생각을 자꾸 해', '차 안에서 가스를 생각해 봤어', '수면제로 충분하겠지?').
> **구체적 계획** 생을 끝낼 시기나 장소를 정함, 방법은 있든 없든 ('다음 주 수요일, 그날 쓰려고 약을 모아 놨어', '집 근처 다리', '집에 혼자 있는 밤에', '시험 끝나면, 그때'). 생각이 드는 때('오늘 밤 자꾸 생각나')는 실행 시기가 아님.

정렬: 워드 5.1 `ideation_specificity` (nonspecific · method · specific_plan) 에 none 을 더했다. 예시는 11축 1·2번 그대로.

## 2. suicidal_intent — 자살 실행 의도

> **Q.** Does the writer express a decision or intention to act on suicide, separately from whether they have a method or plan? Assess intent only when the wording or context supports acting, not merely wishing to be dead. Choose the strongest level described.
> **no_intent** No stated intention to act, including no suicidal thoughts at all. Passive death wishes or suicidal thoughts alone are not intent (e.g. 'I wish I would not wake up, but I will not act on it').
> **ambivalent** Unsure or torn about acting, without a decision (e.g. 'I might do it, but I am not sure', 'part of me wants to go through with it', 'I don't know if I'll stop myself next time').
> **intent** A clear decision or intention to attempt suicide with no near-term time stated (e.g. 'I intend to end my life', 'I've decided I'm going to do it eventually', 'I'm really going to end it all' in a suicide context).
> **imminent** A decision or intention to act now or in the near term: today, tonight, or within days (e.g. 'I have decided to end my life tonight', 'I've made up my mind, this is the last week', 'I'm going to do it as soon as everyone's asleep').

> **질문.** 작성자가 방법·계획과 별개로 실제 자살 행동을 하겠다는 결심이나 의도를 드러냅니까? 죽고 싶다는 바람만으로 의도를 판단하지 마세요. 드러난 가장 강한 단계를 고르세요.
> **의도 없음** 실행 의도가 드러나지 않음 (자살 사고가 아예 없는 경우 포함). 수동적 죽음 소망·자살 사고만으로는 의도가 아님 ('안 깨어났으면 좋겠지만 실제로 하지는 않을 거야').
> **양가적** 결심 없이 실행을 두고 망설임 ('하게 될지도 모르지만 확실하지 않아', '끝까지 하고 싶은 마음도 있어', '다음엔 내가 멈출지 모르겠어').
> **의도** 자살하기로 결심했거나 하려는 의도가 분명하지만 가까운 시점은 없음 ('실제로 목숨을 끊을 생각이야', '언젠가는 할 거라고 정했어', 자살 맥락에서 '나 이제 진짜 다 그만하려고').
> **임박** 지금이나 가까운 시점(오늘, 오늘 밤, 며칠 안)에 하겠다는 결심 ('오늘 밤 자살하기로 결심했어', '마음 정했어, 이번 주가 마지막이야', '다들 자면 바로 할 거야').

정렬: 워드 5.2 (imminent · intent · ambivalent_or_unclear · no_intent) 원형이다. 11축 3번의 예 = intent + imminent. 양가적은 결정 11 대로 켜지 않지만 확률은 따로 남긴다.

## 3. preparatory_acts — 준비 행동

> **Q.** Did the writer take a concrete step, beyond thinking or intending, that prepares for ending their own life? If more than one kind is described, choose the one described most clearly; the others are kept from the probabilities.
> **none** No such act. Only thinking about a method or about writing a note, or already having medication or an ordinary object at home without doing anything toward using it, does not count. Tidying, giving away, or paperwork for everyday reasons (moving, decluttering, a gift, routine finances), a diary, a complaint letter, or an ordinary will without suicidal context do not count.
> **obtain_means** Got or looked for the means: buying, collecting, or setting aside means, getting extra medication for this, researching how to carry it out, or visiting or checking a place for an attempt (e.g. 'I've been saving up pills', 'I got extra pills from two clinics', 'bought a rope', 'searched online for which pills to use', 'I went up to the rooftop a few times to look').
> **suicide_note** Wrote or started a suicide note or goodbye letter meant to be read after their death, in any form (paper, a phone memo, an unsent message, an email draft, a letter to one person) (e.g. 'I wrote a letter to my daughter, it's in my drawer', 'there's a memo on my phone for when I'm gone').
> **put_affairs_in_order** Gave away possessions, said quiet goodbyes, or arranged affairs (who will care for a pet or child, money, insurance, a will, bank accounts, deleting accounts, photos, or messages) in a way that context links to preparing for their death (e.g. 'I gave my cat to my sister, she'll need him more than me', 'I've been sorting out my insurance so no one has to deal with it', 'I deleted all my photos and accounts', 'I called everyone to thank them, properly').

> **질문.** 작성자가 생각이나 의향을 넘어 스스로 생을 끝낼 준비가 되는 실제 행동을 했습니까? 여러 가지가 드러나면 가장 분명한 것을 고르세요 (나머지는 확률로 남깁니다).
> **없음** 그런 행동이 없음. 방법이나 유서를 생각만 함, 집에 약·일상 물건이 있을 뿐 쓰려고 한 행동이 없음, 일상적 이유의 정리, 일기, 항의 편지, 자살 맥락 없는 유언장은 해당하지 않음.
> **수단 마련** 수단을 사거나 모으거나 따로 둠, 이 목적으로 약을 더 받음, 실행 방법 검색, 실행 장소를 가 보거나 확인함.
> **유서** 죽은 뒤 읽힐 유서나 작별 편지를 썼거나 쓰기 시작함 (형식 무관).
> **신변 정리** 물건 나눠 주기, 조용한 작별 인사, 신변(반려동물·아이 돌봄, 돈, 보험, 유언, 계좌, 계정·사진·메시지 삭제) 정리가 맥락상 죽음 준비로 이어짐.

정렬: 워드 2.1 `preparation_type` 에 none 을 더하고 other 는 뺐다 (워드의 other 예시 '날짜를 정함' 은 1번 구체적 계획). 예시는 11축 4번 그대로. 결정 1 유지.

## 4. self_harm — 자해

> **Q.** Has the writer deliberately hurt their own body, now or in the past, and if so, once or more than once? Count cutting, burning, hitting themselves, and taking extra pills to hurt themselves, whether it was to cope, release tension, punish themselves, feel something, or with an unclear or mixed intent. Urges without acting do not count.
> **none** No self-harm act is described, or urges only ('I want to cut').
> **once** One self-harm episode, or an act with no sign that it happened more than once, including indirect wording when the context is self-harm and marks on their own body that they made (e.g. 'I cut last night', 'the first time was last night', 'I did it once', 'I took a few extra pills, I wasn't trying to die, I just wanted to feel something', 'tiny lines, I tell people it's the cat').
> **repeated** More than one episode, a recurring pattern, or recurrence after stopping (e.g. 'I've done it several times in the past two months', 'a few times a month for about a year', 'I started again after stopping for months', 'I relapsed', 'broke my streak', 'every time there's a fight at home', 'on and off since high school').

> **질문.** 작성자가 지금이나 과거에 일부러 자기 몸을 다치게 한 적이 있다면, 한 번입니까 여러 번입니까? 긋기, 화상, 스스로 때리기, 다치려고 약 더 먹기를 목적·의도와 상관없이 셉니다. 행동 없는 충동은 세지 않습니다.
> **없음** 자해 행동이 없거나 충동만 있음 ('긋고 싶어').
> **한 번** 한 번이거나 반복 기색이 없는 행동. 맥락상 자해인 간접 표현, 스스로 낸 흔적 포함 ('어젯밤에 그었어', '어젯밤이 처음이었어', '한 번 했어', '죽으려던 건 아니고 뭔가 느끼고 싶어서 약을 몇 알 더 먹었어', '작은 줄들, 고양이가 그랬다고 해').
> **반복** 두 번 이상, 되풀이되는 패턴, 멈췄다가 다시 함 ('두 달 동안 여러 번 했어', '1년 정도 한 달에 몇 번씩', '몇 달 멈췄다가 다시 시작했어', '또 했어(relapse)', '기록이 깨졌어', '집에서 싸울 때마다', '고등학교 때부터 했다 말았다').

정렬: 워드 3.3 `sh_frequency` (once · repeated · unclear) 에 none 을 더하고, unclear 는 once 에 넣었다 (1029 6번에서 '반복 기색 없는 한 번' 은 반복 아님). 'relapsed'·'기록이 깨졌어' 는 다시 했다는 뜻이라 반복으로 옮겼다. 결정 14 (죽으려 한 과거 시도는 넣지 않음) 유지.
