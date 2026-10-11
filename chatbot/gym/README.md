# gym — 독립 시뮬레이터 (상태 3개 + 품질 8축 + 지침 플래그)

`../sim/` (RLVER 방식, 감정 + expert11 체크인 위험)과 **별개**인 시뮬레이터. 코드를 공유하지 않는다.
입력 데이터(페르소나·배경 `out/scenes_*.jsonl`)와 가드레일(`common/`, expert11)만 같이 쓴다.

설계 문서:
- 상태 3개: [../SIMULATOR_PERSONA.md](../SIMULATOR_PERSONA.md) "대화 중 상태 3개"
- 품질 축·보상: [../QUALITY_AXES.md](../QUALITY_AXES.md)
- 지침 플래그: [../GUIDE_FLAGS.md](../GUIDE_FLAGS.md) (+ `C7_leading_method` 제안)

| 파일 | 하는 일 |
|---|---|
| [config.json](config.json) | 모델 주소, 상태 시작값·한도, 공개 문턱, 모드별 α·β·w, λ |
| [simulator.py](simulator.py) | 가상 사용자. 한 턴에 LLM 한 번: 상태마다 −2~+2 단계 + 인용 → 코드가 점수(×5)·한도 적용 → 다음 발화 |
| [judge.py](judge.py) | 대화 끝 심판 한 번: 플래그 30개 + 축 8개. 적용 여부(na)는 코드가 가드레일 코드로 정함 |
| [reward.py](reward.py) | `R = α·O + β·Q − Σλ·위반`, T1 이면 −1. 6 = 3·6a + 6b/2 |
| [run.py](run.py) | 에피소드: 가드레일 → 챗봇 → 시뮬레이터 → … → 심판 → 보상 |

## 한 턴
1. 사용자 발화 → expert11 Jev (또는 `--guardrail oracle`: 실제 코드 그대로) → `[guardrail]` 블록
2. 챗봇: RESPONSE_GUIDE.md 0~4절 + 대화 + 블록
3. 시뮬레이터: emotion·urge·safety 단계 판단 → 코드 적용 → 다음 발화
   - urge·safety 한 턴 ±10, urge 바닥 = 시작값 × 0.5
   - 같은 행동 반복은 0, 감정을 내린 답은 urge 를 못 내린다
   - 공개는 지난 턴까지의 emotion ≥ 문턱(공개 수준 1/2/3 → 0/60/75)
4. emotion ≥ 100 이면 만족하고 끝, ≤ 10 이면 떠남

## 실행
서버 터널(18601·18602·18603·18611)이 열려 있어야 한다.
```
python chatbot/gym/run.py --per-cell 1 --chatbot qwen8b --out out/gym_runs/pilot_v1
python chatbot/gym/run.py --per-cell 1 --chatbot qwen30b --out out/gym_runs/pilot_v1
```
같은 `--seed` 면 같은 인물을 뽑는다 → 챗봇 비교.

## 파일럿 (2026-10-07, 셀마다 1명 × 7, 같은 인물로 8B·30B, 가드레일 Jev expert11)

| | v1 8B | v1 30B | v2 8B | v2 30B |
|---|---|---|---|---|
| 평균 R | +0.05 | +0.68 | +0.28 | +0.63 |
| 평균 Q (과정) | 0.81 | 1.00 | 0.64 | 0.87 |
| T2 위반 | 7 | 1 | 5 | 3 |

v1 → v2 바꾼 것: urge·safety 를 행동 목록 + 코드 규칙으로 (공감만으로 urge 60→30 되던 것 막음), 위험을 다루기 전 urge 는 −10 까지만,
품질 축을 체크리스트(z·q2·q4·q6) + 코드 점수로, λ T2 0.5→0.2·T3 0.1→0.05, 위험 모드 감정 가중치 상향(사용자: 상태 호전이 목표라 감정만 좋아져도 보상).
결과는 `out/gym_runs/pilot_v1`, `pilot_v2` (v2 는 `--rejudge` 로 고친 심판을 다시 적용, 원본 .bak).

남은 문제: 축 점수가 'repeated'(같은 문장 반복) 여부로 거의 2 아니면 6 으로 갈린다. A2 따뜻함·A5 수준 적합성은 14개 모두 6 → 구분력 없음.

## v3 (2026-10-07): 턴 사실 + 코드 판정, RL 학습

v2 대화 14개를 분석해 고친 것:
- [facts.py](facts.py): 챗봇 답마다 사실만 LLM 이 분류 (직접 물음, 안전 확인, 위기 연락처, 의존 표현 등 25개) + 코드가 질문 수·문장 수·반복(앞 답과 유사도 ≥ 0.6) 계산.
  이유: 대화 전체 심판이 질문 2개 턴(4개 대화)·"not ever" 의존 표현을 전부 'ok' 로 판정.
- [flags.py](flags.py): 플래그는 턴 사실 + 모드 + 기한으로 코드가 판정 (Q3 는 뺌).
- 시뮬레이터: 챗봇 쪽 행동은 턴 사실로 검증된 것만 인정 (묻지 않았는데 '직접 물음' 인정 4번), 반복 답에는 감정 상승·좋은 행동 인정 없음.
- 품질 축: A6b·A7 은 턴 사실로, 나머지는 심판 체크리스트. 반복은 코드 (2턴 이상).
- 챗봇 프롬프트: 학습용 짧은 요약(`--prompt short`, run.py `SHORT`). [guardrail] 블록은 마지막 시스템 메시지 (사용자 메시지에 붙이면 8B 가 따라 씀).

RL: [train/gym_rl.py](train/gym_rl.py) (맥에서 반복 실행) + [train/gym_grpo_step.py](train/gym_grpo_step.py) (54번 GPU 4–7).
반복마다 프로필 16명 × 4 표본 롤아웃 → 그룹 표준화 이점 → PPO-clip + 원래 모델 KL(β 0.02), LoRA r16 → 84번 8B vLLM 에 런타임 어댑터로.
결과: `out/gym_rl/<run>/` (log.jsonl, episodes_itXXX.jsonl). sim run1 이 끝난 뒤 자동 시작 (맥 tmux `gym_rl`, out/gym_rl/start_after_run1.sh).

## g1 결과와 종료 (2026-10-08)

| 회차 | 정책 | R | T1 비율 | 위반/대화 | O | Q |
|---|---|---|---|---|---|---|
| 1 | 원래 Qwen3-8B | −0.19 | 34% | 2.47 | +0.12 | 0.67 |
| 2 | 1회 학습 | +0.10 | 14% | 1.48 | +0.13 | 0.64 |
| 3 | 2회 학습 | −0.05 | 19% | 1.84 | +0.04 | 0.56 |

반복마다 인물 16명을 새로 뽑아 회차 비교에 인물 구성 차이가 섞인다 → 고정 평가 [train/gym_eval.py](train/gym_eval.py) (scenes_test 셀당 3명 × 2, 명단 out/gym_rl/g1_eval/eval_ids.txt) 를 만들었지만 돌리지 않음.
16:19 다른 세션이 프롬프트 최적화(chatbot/promptopt)에 자원을 쓰려고 gym·sim run2 를 껐고, 사용자 결정으로 gym 은 여기서 종료 (3회차 학습은 못 끝냄).
남은 것: 어댑터 it001·it002 (54번 ~/yumin_sim/gym/g1, 84번 /data2/yumin/gym_rl/g1), 롤아웃 out/gym_rl/g1/. 다시 하려면 `python chatbot/gym/train/gym_rl.py --run g1` (이어서), 평가는 `gym_eval.py --run g1 --iters 1,2`.
