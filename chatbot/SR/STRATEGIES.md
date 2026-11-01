# 발화 전략 사전 (v0, 2026-10-13)

유저 클러스터 × 전략 효과를 보기 위한 전략 목록. **ESConv(Liu et al., ACL 2021) 전략에서만 가져온다** (지지자 전략 8개 중 6개). 단계(탐색·위로·행동)는 쓰지 않는다.
우리 gym·SR 행동 코드(인지 재구성·그라운딩·결정 돌려주기 등)는 넣지 않는다 (사용자 결정 2026-10-13).

## 층 구조

```
[안전 층]  모드별 안전 절차 (promptopt 뱅크 modes·reasons) — 전략과 상관없이 항상 켬
[전략 층]  아래 6개 중 하나 — 같은 위험 모드 안에서 바꿔 끼움
```

전략은 안전 절차를 대신하지 않는다. "고위험 → 문제 해결"이 아니라 "고위험 + 유저 클러스터 → 안전 절차 위에 얹을 전략".

## 전략 6개

| 코드 | ESConv 원래 이름 | 뜻 |
|---|---|---|
| `question` | Question | 상황·감정을 더 말하도록 연다 |
| `restatement` | Restatement or Paraphrasing | 유저가 한 말을 간결하게 되돌려 준다 |
| `reflection` | Reflection of Feelings | 말 뒤의 감정을 짚는다 |
| `affirmation` | Affirmation and Reassurance (인정만) | 유저의 강점·노력·대처를 구체적으로 인정한다 |
| `suggestion` | Providing Suggestions | 해볼 만한 일을 하나 제안한다 |
| `information` | Information | 상황과 관련된 사실·심리교육을 준다 |

## 뺀 것

| ESConv 전략 | 이유 |
|---|---|
| Self-disclosure | AI 가 "저도 그런 적 있어요"라고 하면 지어낸 경험이 된다 |
| Affirmation and Reassurance 중 **안심(Reassurance)** | "괜찮아질 거예요" 같은 보장은 지침의 무근거 확언 금지(gym `false_reassurance`)와 충돌 |
| Others | 인사·맞장구 — 전략이 아니다 |

## 전략 프롬프트 조각 (초안, 영어)

안전 층 뒤에 붙인다. 안전 층이 할 일(위험 질문, 연락처)이 있으면 그것이 먼저다.

| 코드 | 조각 |
|---|---|
| `question` | In this reply, mainly invite them to say more: ask one open question about what happened or how they feel. |
| `restatement` | In this reply, mainly restate what they just told you in your own words, briefly and accurately, so they know you followed. |
| `reflection` | In this reply, mainly name the feeling underneath what they said (e.g., hurt, shame, exhaustion) and check if you got it right. |
| `affirmation` | In this reply, mainly point out a specific strength, effort, or way they have coped. Do not promise things will be fine. |
| `suggestion` | In this reply, mainly offer ONE concrete, small thing they could try, and ask what they think of it. |
| `information` | In this reply, mainly share one relevant, accurate fact or explanation that helps them make sense of what they are going through. No diagnoses or medication advice. |

`[결정 필요]`
- 롤아웃 단위: 대화 전체에 한 전략 고정 / 턴마다 전략 고르기. 효과 행렬 파일럿은 고정이 해석하기 쉽다.
- 인정 조각에서 안심 금지 문구를 넣을지 (안전 층 base 에 이미 "no guarantees" 가 있다).
