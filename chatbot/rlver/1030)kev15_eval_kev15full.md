# 새 Kev 15축 평가 — ID 보류 · OOD (2026-10-30)

기준 = Jev 15축 (`1029)jev.md`, 같은 데이터에 새로 돌림, $2.11). 축마다 P(예) ≥ 0.7. 라우팅: 위험 축 1–9 · 14–15 → 가드레일, 아니면 우울 → 정서 지원, 아니면 일반 대화. ID 보류 · OOD 는 학습에 안 넣었고, 여기 오답으로 고치지 않는다.

Kev: `kev15full` (`kev15full` = kev-4b LoRA 를 합쳐 full fine-tuning, `kev15lora` = kev-4b 에서 LoRA)

## 1. Jev 와 얼마나 같은가

라우팅 일치 = 세 갈래 라우팅이 같은 비율. 가드레일 κ = 가드레일 여부의 κ. 축 κ 평균 = 15축 κ 평균 (양쪽 다 한쪽으로 몰린 축 제외).

| 데이터 | n | kev15full 라우팅 일치 | kev15full 가드레일 κ | kev15full 축 κ 평균 |
|---|---|---|---|---|
| cradle_validation | 3529 | 90.8% | 0.88 | 0.80 |
| attunebench | 300 | 90.3% | 0.00 | 0.62 |
| empathetic_dialogues | 300 | 90.7% | - | 0.68 |
| esconv | 300 | 92.3% | - | 0.74 |
| sim_vail_turn_scores | 300 | 90.0% | 0.65 | 0.59 |
| reddit_cssrs | 2680 | 85.3% | 0.85 | 0.71 |
| **ID 보류** | 4729 | 90.8% | 0.89 | 0.80 |
| **OOD** | 2680 | 85.3% | 0.85 | 0.71 |

### 축별 κ (ID 보류 전체 / OOD)

| 축 | Jev 예 (ID) | kev15full κ ID | kev15full κ OOD |
|---|---|---|---|
| obtain_means | 23 | 0.44 | 0.61 |
| suicide_note | 21 | 0.89 | 0.75 |
| put_affairs_in_order | 0 | - | 1.00 |
| specific_plan | 35 | 0.86 | 0.43 |
| nonsuicidal_self_harm | 381 | 0.87 | 0.86 |
| repeated_self_harm | 314 | 0.88 | 0.69 |
| cannot_stay_safe | 38 | 0.74 | 0.50 |
| means_access | 44 | 0.73 | 0.52 |
| method | 106 | 0.88 | 0.76 |
| suicidal_ideation | 472 | 0.89 | 0.85 |
| suicidal_intent | 65 | 0.81 | 0.74 |
| depression | 3134 | 0.85 | 0.71 |
| acute_context | 1316 | 0.80 | 0.70 |
| psych_history | 282 | 0.86 | 0.83 |
| substance_use_disorder | 40 | 0.70 | 0.66 |

## 2. CRADLE validation (임상가 라벨, 대화 단위)

위기 그룹이 일반 대화로 가면 놓침, 위기 이전 발화가 가드레일로 가면 과잉.

| 그룹 | n | jev15 가드레일 | jev15 일반 대화 | kev15full 가드레일 | kev15full 일반 대화 |
|---|---|---|---|---|---|
| 능동적 자살 사고 (현재) | 41 | 100% | 0% | 100% | 0% |
| 수동적 자살 사고 (현재) | 52 | 98% | 0% | 98% | 0% |
| 자해 (현재) | 46 | 100% | 0% | 100% | 0% |
| 자살·자해 (과거) | 32 | 100% | 0% | 100% | 0% |
| 경고 신호 (alert) | 240 | 21% | 18% | 15% | 15% |
| 기타 위기 (폭력·학대 등) | 115 | 0% | 9% | 0% | 9% |
| 위기 이전 발화 | 1368 | 2% | 34% | 1% | 36% |
| 위기 이후 발화 (라벨 없음) | 1635 | 37% | 15% | 32% | 13% |

위기 그룹(앞 4개) 놓침: jev15 0%, kev15full 0%

## 3. Reddit C-SSRS (OOD, 임상 척도 라벨)

supportive · uninformative 는 위험 아님, indicator 이상은 위험 신호.

| 라벨 | n | jev15 가드레일 | kev15full 가드레일 |
|---|---|---|---|
| supportive | 1352 | 1% | 2% |
| uninformative | 445 | 0% | 0% |
| indicator | 420 | 4% | 6% |
| ideation | 337 | 50% | 53% |
| behavior | 77 | 55% | 45% |
| attempt | 49 | 69% | 63% |

## 4. 일상 · 정서 대화 (ID 보류, 위기 없음이 대부분)

| 데이터 | n | jev15 가드레일 | jev15 정서 지원 | kev15full 가드레일 | kev15full 정서 지원 |
|---|---|---|---|---|---|
| attunebench | 300 | 1% | 37% | 0% | 38% |
| empathetic_dialogues | 300 | 0% | 16% | 0% | 16% |
| esconv | 300 | 0% | 52% | 0% | 51% |
| sim_vail_turn_scores | 300 | 5% | 44% | 4% | 49% |
