# 효과 있었던 전략·유효한 패널티 모음 (2026-10-13)

gym·sim 에서 돌린 대화 전부를 한 번에 분석했다. 스크립트 [collect_effective.py](collect_effective.py), 숫자는 `out/SR/effective_v1/effective.json` (84번에서 실행, CPU).

| | 대화 | 턴 | 출처 |
|---|---|---|---|
| gym | 6,135 | 60,074 | promptopt p1·p2·p3·test·F7(Qwen/Gemma), gym_rl g1 |
| sim | 8,285 | 106,287 | eval_v2·v3·v4_rejudge·v6_base, refcheck_v7, RL run2·run3 |
| SR 요약 코드 | 3,975 | 39,455 | SR v0 (p1·p2·p3) — 내용(validate·praise…)·화법(stance·directness) |

**방법.** 행동은 턴 단위로 본다. y = 그 턴의 상태 변화(gym: emotion·urge 감소·safety, sim: emotion·위험 감소 칸). X = 그 답의 턴 사실 전부 + 질문 2개 이상·질문 없음·반복·긴 답 + 셀·출처·턴 위치. 모드(대화 안 최고 response)마다 OLS로 돌리고, 95% CI는 대화 단위 부트스트랩 200회로 구했다. 같은 답에 같이 나오는 행동끼리 서로 보정한 값(adj)이다.
패널티는 대화 단위로 본다. 위반한 대화와 안 한 대화의 결과(gym O, sim 패널티 전 R·감정·위험)를 같은 셀·출처 안에서 비교하고, RL 반복에 따라 위반률이 어떻게 바뀌었는지도 본다.

**주의.** 상관이지 인과가 아니다. 두 시뮬레이터 모두 규칙의 영향을 받는다. sim 감정은 공통 규칙(반영 → 오름, 질문 여러 개 → 내림), gym urge·safety는 행동 표를 따른다. 그래서 일부 효과는 설계에서 나온 것이다. **두 시뮬레이터에서 같은 방향**이면 강한 근거, 한쪽에서만 나오면 약한 근거로 표시했다.

---

## 1. 효과 있었던 전략

표의 숫자는 그 행동이 있을 때 그 턴 상태 변화의 차이(adj, 점수 단위)다. ★ = 두 시뮬레이터 모두 같은 방향(CI가 0을 넘지 않음), ☆ = 한쪽만.

### 1a. 모든 모드

| 전략 | gym | sim | 근거 |
|---|---|---|---|
| **반영 먼저** (`reflection`) | 감정 +1.4~+5.2 (모든 모드), urgent safety +1.0 | urgent 감정 +1.0, 위험 감소 +0.05 (normal 은 100% 라 추정 불가) | ★ |
| **타당화 + 해석형 공감** (SR `validate`, `empathy=interpretation`) | normal +0.56/+0.52, support +2.2, other +3.0 | — | ☆ |
| **구체적 강점 인정** (SR `praise`) | normal +1.6, support +2.0, assess +1.0 | — | ☆ (ESConv affirmation 과 같음) |
| **협력적 태도** (SR `stance=collaborative`) | urgent +0.6, support +0.6, other +2.0 | — | ☆ |
| **도움 장벽 다루기** (`barrier_addressed`) | 감정 +1.1~+2.9, safety +0.8~+1.3 (모든 모드). 유저가 `contact_chosen` 하는 경로 | (sim 에 사실 없음) | ☆ |
| **결정 돌려주기** (SR `autonomy_return`) | normal +0.3 | — | ☆ (약함) |

### 1b. 모드별

| 모드 | 효과 있는 전략 | 근거 |
|---|---|---|
| normal | 인지 재구성 +0.9, 지지 인물 묻기(SR `support_person`) +0.8, 탐색 질문(SR `explore`) +0.4 | ☆ |
| support | 지금 안전한지 확인(`asked_safe_now`) 감정 +2.5·urge −0.9, 작은 활동 계획 +1.3, 위험 정도 질문 1개(`risk_inquiry`) sim +0.4 | ☆/☆ |
| assess | **위험 세부 질문 1개** (gym +0.9·urge −0.6, sim +0.4) ★, **안전 계획 단계** (gym urge −1.1·safety +2.2, sim 감정 +0.7) ★, **수단 멀리 두기** (gym 감정 +3.6·safety +4.0) ☆, 그라운딩 (+1.6, normal 에선 −0.4) ☆, 활동 계획 +1.8 ☆ | |
| urgent | **안전 계획 단계** (gym urge −2.4·safety +3.0, sim 감정 +0.6·위험 감소 +0.04) ★, 수단 멀리 두기 (safety +1.6, urge −0.9) ☆, 수단 묻기 (+0.9) ☆, 그라운딩 (urge −0.7) ☆ | |
| other | **유저 본인 상태 확인** (`self_check`, gym +0.9, sim +0.3~+0.5) ★, 도울 방법 안내 (`helper_guidance`, 감정 +1.3·safety +2.9) ☆ | |

### 1c. 손해 본 전략 (피할 것)

| 행동 | gym | sim | 근거 |
|---|---|---|---|
| **같은 답 반복** | 모든 모드·상태 −0.9~−4.7 | 감정 −2.9~−5.3, 위험 감소 −0.1 | ★ 가장 큰 효과 |
| **위기 연락처를 매번 언급** (`named_crisis_contact`) | 감정 −0.3~−1.6, urge·safety 도 − | 감정 −0.8~−4.4 | ★ → 한 번, 필요할 때만 |
| **normal 에서 자살 직접 질문** | 감정 −7.4, safety −3.1 | — | ☆ 매우 큼 (= X3) |
| support·assess 에서 자살 질문 | −1.2~−1.5 | −0.5~−0.6 | ★ 비용은 있으나 지침상 필요 (공감 뒤에 한 번) |
| **지시형 태도** (SR `stance=directive`) | normal −3.6, assess −7.3, urgent −0.7 | — | ☆ |
| assess·urgent 에서 열린 탐색 질문 계속 (SR `explore`) | assess −0.8, urgent −0.6, other −3.9 | — | ☆ 위험 모드에선 탐색보다 안전 |
| assess 에서 정보·심리교육 (SR `info`) | −1.0 | — | ☆ (ESConv `information` 은 위험 모드에서 주의) |
| 질문 여러 개 | assess −0.9, urge·safety − | urgent +0.3 (!) | 엇갈림 |
| 부상 확인 (`injury_check`) | 0 | −0.4~−0.7 | ☆ 비용 있으나 U4 지침상 필요 |
| 불가능한 행동 요구 | — | −0.4 | ☆ |
| urgent 에서 지금 안전한지 확인 | +0.4 | −1.6 | 엇갈림 |
| 거절 뒤 계속 권유 (`encouraged_help_after_refusal`) | −0.3~−0.6 (`pushed` 로 인정됨) | — | ☆ 거절 자체(`user_refused_help`)가 −1~−3 이라 해석 주의 |
| 대화 끊기·주제 바꾸기 | normal 감정 −0.5, safety −1.9 | — | ☆ |
| other 모드의 긴 답 | −6.9 | — | ☆ |

### 1d. STRATEGIES.md(ESConv 6개)와 연결

| ESConv | 데이터에서 |
|---|---|
| `reflection` (감정 짚기) | ★ 가장 일관된 효과 |
| `restatement` | 측정 코드가 따로 없다 (`reflection` 에 섞임) |
| `affirmation` (인정) | SR `praise` 로 normal·support·assess 에서 + |
| `question` | normal 에서만 + (`explore`). assess·urgent·other 에서는 − |
| `suggestion` | 효과 없음 (0 근처). 안전 계획·수단 같은 **구체적 안전 단계**만 + |
| `information` | assess 에서 −1.0, urgent 에서 −0.3 (CI가 0에 걸침) |

→ 전략 층의 기본값 후보: **반영 + (위험 모드면) 안전 단계 하나 + 구체적 인정, 반복하지 않기**. `question` 은 normal 에서만 쓰고 `information` 은 위험 모드에서 뺀다.

---

## 2. 유효한 패널티

위반 대화의 결과 차이는 diff(위반 − 정상, 같은 셀·출처 안)로 적었다. gym 은 O, sim 은 패널티 전 R 이다.

### 2a. 결과로 확인됨 — 시뮬레이터도 독립적으로 나쁘게 본다

| 플래그 | gym diff | sim diff (감정) | RL 추세 | 판단 |
|---|---|---|---|---|
| **R1_repeat** (반복) | (턴 효과 −1~−4.7) | −0.13 (−0.26), 위험 감소도 −0.05 | run2 0.38→0.20 줄어듦 | **유효, 학습됨** |
| **Q1_no_reflection** | −0.087 | −0.076 (−0.19) | run2 0.12→0.33 **늘어남** | 유효, 지금 무게로는 약함 |
| **C4_dependency** | −0.022 (경계) | −0.095 (−0.20) | 낮게 유지 | 유효 |
| **X2_hotline_spam** | −0.080 | −0.049 (−0.16) | 낮음 | 유효 |
| **C6_judgment** | −0.128 | (n 적음) | — | 유효 |
| **C7_impossible_action** | — | −0.053 (−0.14) | run2 0.06~0.15 | 유효 |
| **Q3_ignored_disclosure** | — | −0.198 (n=9) | 거의 0 | 유효하지만 드물다 (판정이 관대함, 기존 메모와 같음) |
| **X1_overreaction** | −0.088 | — | — | 유효 |
| **A2·U3 수단 확인/분리** | −0.09 / −0.08 | −0.036 / −0.017, 위험 감소도 − | run2 U3 0.16→0.05 | 유효 |
| **A3_no_safety_plan** | −0.093 | 위험 −0.009 | run2 0.40→0.19 | 유효 (gym 에선 88% 가 위반 → 구분력 낮음) |
| **Q2_multi_question** | −0.023 | −0.013 (−0.05) | run2 0.16→0.48 **늘어남** | 유효하지만 작다. RL 이 무시함 → 무게를 올리거나 턴 이점에 넣기 |
| **L1_long_risk_reply** | — | 감정 −0.038 | 평평 | 약하게 유효 |

### 2b. 안전 규범 — 시뮬레이터 결과는 오히려 **위반을 보상**한다 → 패널티가 반드시 있어야 한다

위반한 대화의 결과가 더 좋았다. 안전 행동은 그 턴 감정을 깎는다(1c). 그래서 결과 보상만 있으면 RL 이 안전을 버린다. 이 플래그들은 결과로 검증되는 게 아니라 **결과 보상에 맞서는 균형추**로서 유효하다. 근거는 전문가 지침이다.

| 플래그 | gym diff | sim diff | RL 추세 (run2) |
|---|---|---|---|
| A1_no_risk_inquiry | +0.041 | +0.026 | 0.66→0.53 |
| S1_no_direct_check | +0.083 | +0.043 | 0.11→0.04 |
| A4_no_referral | +0.010 | +0.054 | 0.12→0.03 |
| A5_recovery_technique (위험 대신 기분 운동) | +0.097 | +0.032 | 평평 |
| L1_premature_deescalation | +0.075 | — | g1 0.41→0.32 |
| U6_long_or_offtopic | +0.061 | — | g1 0.46→0.18 |
| M1_missed_risk / M1_missed_cue | — | +0.038 / +0.036 | 평평 (cue 는 73%) |
| U1·U2 (T1) | ≈0 | ≈0~+0.03 | run2 U2 0.16→0.03 |
| U4_no_injury_check | gym 99% 위반 | 위험 −0.03 | 낮음 |

→ 2b 패널티가 크면 RL 이 배운다(run2 에서 A4·S1·U2 감소). 결과 보상과 반대 방향이라 **무게를 줄이면 바로 무너질 것**이다.

### 2c. 정보가 없거나 다시 정의해야 하는 것

| 플래그 | 문제 |
|---|---|
| C1·C2·C3·C5·C7_leading_method·O2·Q4_reasked | 14k 대화에서 0~3건. 지금 챗봇들은 안 한다. 안전망으로 두되 학습 신호는 없다 |
| R2_template (sim) | 33% 가 위반. 감정 diff +0.047(위반 쪽이 더 좋음), run3 내내 0.65 평평 → **정의 재검토** |
| M1_missed_cue (sim run3) | 73% 고정, 줄지 않음 → 판정이 너무 넓다 |
| U4_no_injury_check (gym) | 99% 위반. 어떤 뱅크도 못 고침 (promptopt 12건 그대로) → 지시문이나 판정 기준 점검 |
| A3·A2·U3 (gym) | 82~88% 위반 → 대화 단위 구분력이 낮다. 턴 기한을 늘리거나 부분 점수로 바꾸는 것 검토 |
| C8_foreign_number | 결과 차이 없음. 사실 오류 방지용으로만 둔다 |

---

## 3. 한 줄 요약

- **전략**: 반영 먼저, 구체적 인정, 장벽 다루기를 기본으로 깐다. 위험 모드에서는 탐색·정보 대신 **안전 계획 한 단계 / 수단 멀리 두기**, other 모드에서는 **유저 본인 상태 확인 + 도울 방법**. 반복·지시형 태도·연락처 남발은 피한다.
- **패널티**: 결과로 확인된 것은 R1·Q1·C4·C6·C7·X1·X2·A2/U3·A3, 작지만 Q2·L1. 결과와 반대지만 꼭 필요한 안전 균형추는 A1·S1·A4·A5·L1·U1·U2·U4·M1. 다시 봐야 할 것은 R2_template·M1_missed_cue·U4(gym)·드물게만 나오는 C 계열.
