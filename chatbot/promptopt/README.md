# promptopt — 프롬프트 뱅크 최적화 (A안)

2026-10-08 방향 전환: 개발계획서(산학) 요구사항 때문에 챗봇 LoRA 학습 대신 **베이스 LLM 은 고정하고 시스템 프롬프트만 상태별로 바꾸는 외부 모듈**로 간다.

| 요구사항 | 이 모듈에서 |
|---|---|
| F2 추정 상태에 따라 System Prompt 동적 조정 | 가드레일 출력 → 조각 조립 → 턴마다 시스템 프롬프트 |
| F4 베이스 LLM 가중치 수정 금지 | 텍스트만 바꾼다 |
| F7 재학습 없이 다른 베이스 LLM 적용 | 뱅크(JSON)를 그대로 다른 모델에 붙인다 |
| NF1 추가 지연 500ms 이내 | 표 조회 + 문자열 조립만 (~0ms) |

다음 단계: B안(뱅크 + 학습된 선택기), C안(작은 프롬프트 생성기 RL).

## 구조

- [bank.py](bank.py): 뱅크 = `base` + `modes.<response>` + `reasons.<묶음>`.
  - 모드는 대화 안 최고 `response` 를 코드가 유지한다 (LLM 에 맡기지 않음).
  - reasons 는 지금까지 드러난 코드 묶음 9개(method, plan, means, injury, unsafe, urge, past, history, warning)마다 조각 하나.
  - `--position system`: 시스템 프롬프트 하나를 턴마다 다시 조립 (F2 문구 그대로). `turn`: base 는 맨 앞, 상태 지시는 마지막 시스템 메시지.
  - 베이스 LLM 은 가드레일 코드를 보지 않는다. 지시문만 본다.
- [seed_bank.json](seed_bank.json): v0 = gym `run.py` 의 SHORT 프롬프트를 조각으로 나눈 것 (+ 새 reasons 묶음 4개 초안).
- [optimize.py](optimize.py): 평가(`eval`)와 최적화(`opt`). 보상·플래그·시뮬레이터는 [../gym](../gym) 를 그대로 쓴다.

## 최적화 한 반복 (GEPA 식 반성 → 변이)

1. 현재 최고 뱅크의 검증 대화에서 위반을 조각별로 탓한다 (위반 턴에 켜져 있던 모드 조각, A2→method, U3→means, U4→injury, C·Q 는 base 도).
2. 탓이 큰 조각을 가중 추첨 → 그 조각이 켜졌던 나쁜 대화 3개 + 좋은 대화 1개 발췌를 반성 LLM(Qwen3-30B)에 주고 후보 문구 2개를 받는다.
3. 미니배치(그 조각이 켜질 인물 8명, 학습 쪽)에서 원래 뱅크와 후보를 같은 인물로 돌려 평균 R 비교 (+0.03 이상이어야 다음 단계).
4. 이긴 후보를 검증 세트(셀마다 4명 × 2표본 = 56 대화)에서 돌려 지금까지 최고 검증 R 보다 높으면 채택. 실패한 조각은 2반복 동안 덜 뽑는다.

데이터: `out/scenes_train.jsonl` 중 검증 28명은 [out/promptopt/val_ids.txt](../../out/promptopt/val_ids.txt) 로 고정, 나머지 572명이 미니배치 풀. `scenes_test.jsonl` 은 마지막 평가에만 쓴다.

## 실행 (84번 안에서 — 맥 ↔ 연구실 네트워크가 자주 끊긴다)

```
cd /data2/yumin/sdx_guardrail
PY=/data2/yumin/env/bin/python
$PY chatbot/promptopt/optimize.py eval --bank chatbot/promptopt/seed_bank.json --config config_po.json --out out/promptopt/eval_seed_system
$PY chatbot/promptopt/optimize.py opt --run p1 --config config_po.json --iters 20
```

`config_po.json` = 84번 30B 세 대 + 54번 두 대(시뮬레이터·심판), 84번 8B(챗봇). 결과 폴더는 덮어쓰지 않는다. 같은 `--run` 은 `state.json` 에서 이어 돈다.
빠진 에피소드(네트워크 끊김)는 60초 뒤 최대 5번 다시 돌려 비교 대상이 같은 인물 집합이 되게 한다.

## 결과 (2026-10-09, run p1_turn, 챗봇 Qwen3-8B, 가드레일 Jev expert11)

검증 28명×2 에서 위치 비교: 지금 방식(SHORT + [guardrail] 블록) R +0.079, seed system +0.065, seed turn +0.161 → turn 으로 최적화.
20반복(1–14: 조각 1개씩, 15–20: 조각 3개 병렬 + 현재 최고 재평가 평균). 채택: assess 3번, reasons.past 1번.

**test 150명 × 1 (최적화에 안 쓴 인물)**

| | R | T1 대화 비율 | 대화당 위반 |
|---|---|---|---|
| 지금 방식 (SHORT + 블록) | +0.082 | 13.3% | 1.46 |
| seed 뱅크 (turn) | +0.091 | 12.0% | 1.64 |
| 최적 뱅크 (turn) | **+0.145** | **8.0%** | 1.57 |

같은 인물 짝 부트스트랩: 최적 − 지금 = +0.064 (95% CI −0.005 ~ +0.133, 한쪽 p 0.035), seed − 지금 = +0.009 (차이 없음 — 검증의 0.08 차이는 노이즈였다).
T1 감소는 L1(위험 대화 중 안전 행동 끊김) 11 → 5, U2(urgent 첫 답 연락처 없음) 5 → 0, U1 5 → 2 가 대부분. C4(의존 표현) 17 → 12.
나빠진 것: Q2(한 답에 질문 2개 이상) 26 → 62 (seed 59 — 뱅크 방식 자체에서 생김), X2(핫라인 반복) 11 → 18.
최적 reasons.past 가 과거 이력만 있어도 지금 위험을 묻고 연락처를 주게 바뀌었다 → X1 은 1건뿐이지만 과잉 대응인지 사람이 확인 필요.

`out/promptopt/<run>/`: `bank_itXXX.json`(후보·채택 뱅크), `val_itXXX.jsonl`(검증 대화), `itXXX/mb_*.jsonl`(미니배치), `log.jsonl`(반복마다 조각·진단·후보·점수·채택 여부), `bank_best.json`.

## F7: 다른 베이스 LLM 에 그대로 (2026-10-09, 가드레일 oracle)

OpenRouter 키 한도 초과로 Jev 대신 oracle(시뮬레이터 실제 코드)로 Qwen 도 다시 돌렸다. oracle 은 첫 턴부터 위험이 보여 절대값은 Jev 결과와 비교하지 않는다.
test 150명 × 1, 뱅크는 모두 Qwen3-8B 에서 만든 것 그대로 (Gemma 는 대화 중간 system 을 못 받아 상태 지시를 마지막 user 메시지 끝에 붙임, client `merge_system`).

| 모델 | 프롬프트 | R | T1 | 위반/대화 | Q2 질문 여러 개 | X2 핫라인 반복 |
|---|---|---|---|---|---|---|
| Qwen3-8B | 지금 방식 | −0.172 | 26.7% | 2.37 | 35 | 24 |
| | seed 뱅크 | −0.066 | 14.0% | 2.22 | 64 | 30 |
| | p1 최적 | **−0.044** | **13.3%** | 2.16 | 87 | 27 |
| | p1 최적 + suffix | −0.066 | 16.0% | **1.49** | 24 | 15 |
| Gemma-3-12B | 지금 방식 | −0.052 | 26.0% | 2.01 | 41 | 6 |
| | seed 뱅크 | +0.012 | 18.7% | 2.41 | 106 | 32 |
| | p1 최적 | **+0.102** | **13.3%** | 2.18 | 130 | 33 |
| | p1 최적 + suffix | −0.014 | 14.0% | **1.53** | 35 | 0 |

짝 부트스트랩(같은 인물): p1 최적 − 지금 방식 = Qwen +0.127 (95% CI +0.052~+0.206), **Gemma +0.154 (+0.065~+0.244)** → Qwen 에서 최적화한 뱅크가 재학습 없이 Gemma 에서도 같은 크기로 통한다 (F7).
suffix 는 형식 위반을 크게 줄이지만 R 은 낮춘다 (Gemma −0.116, CI −0.185~−0.047): 답이 짧아져 상태 변화·품질 점수가 떨어진다. → p3_oracle 최적화가 suffix 뱅크에서 시작해 이 균형을 찾는 중.
U4(최근 자해 → 첫 urgent 답에 부상 확인) 는 모든 조건에서 12건 그대로 — 어떤 뱅크도 못 고침, 따로 볼 것.
