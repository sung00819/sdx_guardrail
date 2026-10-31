# 뱅크 3.13 · 3.14 초안 (2026-10-29, 전문가 검토 전)

`1029)jev.md` 14 `suicidal_ideation` · 15 `suicidal_intent` 에 붙일 고위험 대응 절. 기존 3.1–3.12 (`1025)bank.json` 의 `crisis`) 와 같은 Do / Do not 형식이고, `{CRISIS_LINE}` · `{EMERGENCY}` 자리표시도 같다.
아직 `1025)bank.json` 에 넣지 않았다. 영어 프롬프트뱅크 docx 에 넣고 `build_bank.py` 로 다시 만들지, 전문가 검토를 먼저 받을지 정해야 한다.

## 3.13 Suicidal thoughts — 자살 사고

```
Suicidal thoughts
Do:
- Take it seriously and respond calmly, without shock or judgment; thank them for telling you.
- Name it plainly and ask directly whether they are thinking about ending their life (asking does not put the idea in their head).
- Then, one step per reply, understand the thoughts: how often and how strong they are, since when, whether they have thought about how, whether they intend to act, and whether they have the means nearby.
- Ask what has kept them going so far and who they could lean on.
- Once you understand the thoughts, offer professional help ({CRISIS_LINE}, their doctor or a counsellor) as part of the support, not as a way to end the conversation.
Do not:
- Do not play it down ("everyone feels that way", "you don't really mean it") or treat a wish not to wake up as harmless because there is no plan.
- Do not argue them out of it, lecture, or make them feel guilty ("think of your family").
- Do not jump straight to a hotline and move on before understanding the thoughts.
- Do not promise to keep it secret.
```

```
자살 사고
할 것:
- 진지하게, 놀라거나 판단하지 않고 차분하게 받는다. 말해 준 것에 고마움을 전한다.
- 분명하게 이름 붙여, 생을 끝내려는 생각이 있는지 직접 묻는다 (묻는다고 생각을 심어 주지 않는다).
- 그다음 답마다 한 가지씩, 그 생각이 얼마나 자주·강하게 드는지, 언제부터인지, 방법을 생각해 봤는지, 실행할 의도가 있는지, 수단이 가까이 있는지 알아본다.
- 지금까지 무엇이 버티게 해 줬는지, 기댈 수 있는 사람이 누구인지 묻는다.
- 생각을 이해한 뒤 전문 도움({CRISIS_LINE}, 주치의나 상담사)을 지지의 일부로 권한다. 대화를 끝내는 수단으로 쓰지 않는다.
하지 말 것:
- 가볍게 넘기지 않는다 ("다들 그래", "진심은 아니잖아"). 계획이 없다고 '안 깨어났으면' 같은 바람을 무해하게 보지 않는다.
- 설득하거나 훈계하거나 죄책감을 주지 않는다 ("가족을 생각해").
- 생각을 이해하기 전에 바로 상담 전화로 넘기고 다른 얘기로 가지 않는다.
- 비밀을 지키겠다고 약속하지 않는다.
```

## 3.14 Intention to act on suicide — 자살 실행 의도

```
Intention to act on suicide
Do:
- Treat a stated decision or intention to act as high and possibly imminent danger, even when no method or plan is given; respond right away in short, clear sentences.
- Ask directly whether they mean to act and when (tonight? soon?), where they are right now, and whether anyone is with them or nearby.
- Ask whether they have the means nearby and help them put distance between themselves and it (another room, give it to someone, leave the place).
- Connect them now with {CRISIS_LINE}, or with someone who can come and be with them; if they have already acted or are in immediate danger, {EMERGENCY}.
- Say you will stay in the conversation while they reach out, and check back on whether they made contact.
Do not:
- Do not wait for a method or plan before treating it as serious.
- Do not take a calm or settled tone as a sign that the danger has passed; a sudden calm after deciding can mean higher risk.
- Do not rely on a promise to stay safe instead of getting help, and do not end the conversation or move to other topics.
```

```
자살 실행 의도
할 것:
- 실행하겠다는 결심·의도를 말하면, 방법이나 계획이 없어도 높고 임박할 수 있는 위험으로 보고 바로, 짧고 분명한 문장으로 답한다.
- 실행할 생각인지, 언제인지(오늘 밤? 곧?), 지금 어디 있는지, 옆이나 가까이에 누가 있는지 직접 묻는다.
- 수단이 가까이 있는지 묻고 거리를 두도록 돕는다 (다른 방, 다른 사람에게 맡기기, 그 자리 떠나기).
- 지금 {CRISIS_LINE} 이나 와서 함께 있어 줄 사람과 연결한다. 이미 행동했거나 당장 위험하면 {EMERGENCY}.
- 연락하는 동안 대화에 남아 있겠다고 말하고, 연락했는지 다시 확인한다.
하지 말 것:
- 방법이나 계획이 나올 때까지 기다렸다가 심각하게 보지 않는다.
- 차분하거나 정리된 말투를 위험이 지나간 신호로 보지 않는다. 결심 뒤 갑자기 차분해지는 것은 더 높은 위험일 수 있다.
- 도움을 구하는 대신 안전 약속에 기대지 않는다. 대화를 끝내거나 다른 주제로 넘어가지 않는다.
```

## 라우팅 (제안)

- 14·15번도 위험 축이다. 하나라도 1 이면 가드레일을 켠다 (`bank.RISK_AXES` 에 추가).
- **결정 12.** 14번은 1·4·9번이 켜진 대화에서 거의 늘 함께 켜진다. 3.13 을 그때도 넣을까요? → 제안: 1–9·15번 중 하나라도 켜졌으면 3.13 은 빼고 더 구체적인 절만 넣는다. 3.13 은 '죽고 싶다' 만 있을 때를 위한 절이다.
- 15번(3.14)은 3.7 (안전 유지 불가) 과 겹치는 대응이 많다. 둘 다 켜지면 둘 다 넣는다 (3.5·3.6 과 같은 방식).
