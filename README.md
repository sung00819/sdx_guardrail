# sdx_guardrail — 자살·자해 위험 감지 (expert11, 판정기 Jev → Kev)

챗봇 대화의 **사용자 발화 하나**를 보고 자살·자해 위험 신호를 감지해, 위험 수준과 대응 수준을 정한다.
판정은 TypeSafe Jev(`typesafe/jev-1.13`, OpenRouter Decisions API)가 질문별 확률로 답하고, 수준은 코드에서 규칙으로 계산한다.
챗봇 답변의 검사·생성은 범위 밖이다.

설계는 [expert11](expert11/)(전문가 검수 자료의 11개 위험평가 기준 항목 + 시점, 질문 17개를 Jev 1번 호출, 질문 버전 `t11e`)만 쓴다.
비교했던 base(v4i 13문항)와 base-eval(27문항)은 2026-10-07 에 [archive/](archive/)로 옮겼다.

공통
- 입력: `current`(판정할 사용자 발화)와 `context`(앞 대화). 정답 라벨은 Jev 에 보내지 않는다.
- 출력: 급성 위험 수준(고 / 중 / 저 / 신호 없음) + 만성 위험 표지 → 대응 수준 4단계
  (즉시 대응 / 확인과 연계 / 지지와 추적 / 통상 대응). 결합 규칙은 [common/rules.py](common/rules.py).
- 단계 판정: 점수 질문은 Jev 점수(단계별 확률의 가중평균)가 k - 0.5 이상이면 k 단계 이상, 예/아니오는 '예' 확률 ≥ 0.7, 선택형은 신뢰도 ≥ 0.9.
- 판정 원칙: 가장 높은 기준으로 판정(합산하지 않음), 맥락 요인으로 한 단계까지만 상향, 보호요인·부인으로 낮추지 않음,
  시간 창이 지난 정보는 지우지 않고 만성 표지로 옮김.
- 다른 사람 이야기: 질문마다 "작성자 본인의 경험만 센다"고 지시한다.

## 출력 형식

발화마다 한 줄 (`out/combined_expert11_<source>.jsonl`). 값은 영어 코드이고, 한국어 이름은 [common/rules.py](common/rules.py) `LABEL_KO`.

```json
{"level": "moderate", "response": "assess", "reasons": ["indirect_warning"],
 "context": ["acute_context"], "upgraded_by": "acute_context", "chronic": ["psychiatric_history"]}
```

측정값과 규칙 결과를 나눈다 (2026-10-05). `reasons`·`context`·`chronic` 은 Jev 가 본 것, `level`·`response`·`upgraded_by` 는 규칙으로 계산한 것.

| 필드 | 값 |
|---|---|
| `level` (급성 수준) | `high` 급성 고 · `moderate` 급성 중 · `low` 급성 저 · `none` 신호 없음 · `other` 제외(타인) |
| `response` (대응 수준) | `urgent` 즉시 대응 · `assess` 확인과 연계 · `support` 지지와 추적 · `normal` 통상 대응 · `other` 제외(타인) |
| `context` (맥락 요인, 측정) | `means_access` 치명적 수단 접근 · `acute_context` 급성 위험 맥락. Jev 가 '예'면 **상향 여부와 상관없이** 항상 넣는다 |
| `upgraded_by` (상향, 규칙) | 맥락 요인으로 한 단계 올렸으면 `means_access`(중→고) 또는 `acute_context`(저→중), 아니면 `null` |

`reasons`(급성 수준의 근거)와 `chronic`(만성 위험 표지) 코드:

| 코드 | 뜻 |
|---|---|
| `suicidal_ideation_active_intent` | 자살 의도 (C-SSRS ④ 실행 의도 이상) |
| `suicidal_ideation_plan` | 자살 계획 (base-eval·expert11: 의도 없이 계획만. 의도가 있으면 `_active_intent` 로 급성 고) |
| `suicidal_ideation_method` | 방법을 생각하는 사고, 의도 없음 (C-SSRS ③) |
| `suicidal_ideation_passive` | 죽고 싶은 소망·비특이적 능동적 사고 (C-SSRS ①②) |
| `suicidal_ideation` | 자살 사고 (base: v4i 자살 점수 2 이상) |
| `suicidal_ideation_chronic` / `suicidal_ideation_over_1m` | 만성적 자살 사고 / 1개월보다 전의 자살 사고·의도·계획 |
| `preparation`, `attempt` | 준비 행동, 자살 시도 (base) |
| `suicidal_behavior_*`, `preparation_*` | 자살 행동·준비 행동의 시점: `_within_3m` 3개월 안 · `_3_12m_or_unknown` 3~12개월 또는 불명 · `_over_12m` 12개월보다 전 |
| `self_harm_behavior` / `self_harm_urge` | 자해 행동 / 자해 충동만 |
| `self_harm_suicidal_within_3m` | 자살 의도가 있는 자해, 3개월 안 |
| `self_harm_within_12m_or_unknown` / `self_harm_over_12m` | 자해 12개월 안 또는 불명 / 12개월보다 전 |
| `self_harm_severe` | 반복·심한 자해 |
| `self_harm_behavior_fallback`, `self_harm_urge_fallback` | base-eval: 자해 질문이 못 봐서 v4i 자해 점수로 보완 |
| `unable_to_stay_safe` | 혼자 안전을 유지할 수 없다고 표명 |
| `indirect_warning` | 간접 경고신호 |
| `denies_risk` | 부인 진술 (부인으로 수준을 낮추지 않음) |
| `psychiatric_history` | 정신과 병력·위험요인 |
| `past_<코드>` | base: 확실한 과거라 만성 표지로 옮긴 항목 |
| `other_person` | 다른 사람 이야기라 제외 |

결과 요약은 [results/README.md](results/README.md). CRADLE test(실제 대화, 임상가 라벨)에서:

| | 지금 자살·자해 211개 중 놓침 | 과거 42개 중 놓침 | 위기 이전 1814개 중 대응 붙음 | 일반 대화 900개 중 대응 붙음 |
|---|---|---|---|---|
| base | 1 | 13 | 31 | 0 |
| base-eval | 0 | 0 | 144 | 9 |
| expert11 | 0 | 0 | 279 | 17 |

## 구조

```
common/      jev_client.py  Jev 호출(재시도)   data.py  데이터 로더   rules.py  기준값·대응 수준
             run_judge.py   채점              combine.py  수준 계산    compare.py  데이터별 대응 수준 표
             slide33.py     전문가 3분류 채점 (개발용 / ID 보류 / OOD 로 나눠서)
             kev_train_data.py  Jev 답으로 Kev 학습 데이터 만들기   judge_split.py / judge_agree.py  판정기 비교
             kev_adjust.py  Kev 확률 온도 되돌리기 (실험용)
expert11/    questions.py  levels.py
archive/     base, base-eval (2026-10-07 까지 비교한 설계)
data/        download.py  평가 데이터 받기,  other_story_check.jsonl  다른 사람 이야기 확인용 10개
results/     결과 표
```

## 실행

```bash
pip install requests pandas pyarrow
echo "OPENROUTER_API_KEY=..." > .env          # git 에 올라가지 않는다
```

데이터는 저장소에 없고 스크립트로 받는다 ([data/README.md](data/README.md)):

```bash
python3 data/download.py
```

```bash
python3 common/run_judge.py --design expert11 --source cradle_test --dry-run    # 호출 수·글자 수만 확인
python3 common/run_judge.py --design expert11 --source cradle_test              # → out/t11e_cradle_test.jsonl
python3 common/combine.py   --design expert11 --source cradle_test              # → out/combined_expert11_cradle_test.jsonl
python3 common/compare.py   --source cradle_test                                # → out/compare_cradle_test.md
python3 common/slide33.py                                                       # → out/compare_slide33.md (전문가 3분류 채점)
```


## 판정기: Jev → Kev (2026-10-11)

OpenRouter 의 Jev 대신 오픈소스 [Kev](https://github.com/jaredpalmer/kev)(TypeSafe 와 같은 `/v1/systemone` API)를 쓴다.
공개 Kev-4B 에 **개발용 데이터의 Jev 답**(질문 17개 확률을 soft target 으로, 4,928발화)을 LoRA 로 더 학습한 어댑터 `kev4b_ft2` 가 판정기다.
질문·규칙·임계값은 expert11 그대로. 학습에 ID 보류·OOD 는 쓰지 않았다. 표 전체는 [results/judges.md](results/judges.md).

| 데이터 (정밀도 / 감지율 / 특이도, unsafe 만 양성) | Jev | 공개 Kev-9B (학습 전) | kev4b_ft2 |
|---|---|---|---|
| CRADLE validation (ID 보류) | 57 / 99 / 91 | 31 / 94 / 74 | 66 / 98 / 94 |
| Reddit C-SSRS 2021 (OOD) | 77 / 63 / 95 | 45 / 74 / 76 | 64 / 63 / 91 |
| 일반 대화 900 + SIM-VAIL 300 (unsafe 비율) | 0.4% / 12.3% | 3.8% / 21.3% | 0.5% / 9.3% |

```bash
# 학습 데이터 (개발용 Jev 답) → out/judges/kev_train_sel2/train.jsonl
python3 common/kev_train_data.py --select --preset v2 --val 0 --out kev_train_sel2
# Kev 저장소에서 학습 (24GB GPU 한 장, 약 9시간; flash-linear-attention 0.5.2 필요)
python -m kev.train --device cuda --data train.jsonl --base Qwen/Qwen3.5-4B-Base --init_from jaredpalmer/kev-4b \
  --lr 5e-5 --epochs 1 --accum 8 --batch 1 --dtype bf16 --weights_dtype bf16 --checkpointing 1 \
  --max_state 4096 --row_budget 1024 --p_none 0 --p_none_distract 0 --p_distract 0 --out runs/sdx_t11e_4b_v2
# 서버 (GPU 한 장 약 14GB). 긴 대화에서 메모리가 모자라지 않게 캐시를 끄고 서버당 동시 요청 2개로
KEV_PREFIX_CACHE=0 KEV_CUDA_GRAPHS=0 python -m kev.serve --run runs/sdx_t11e_4b_v2 --port 18631
# 채점 (여러 서버면 KEV_URL 에 쉼표로) → out/judges/kev4b_ft2_t11e_<source>.jsonl
KEV_URL=http://127.0.0.1:18631/v1/systemone python3 common/run_judge.py --design expert11 --source cradle_validation --judge kev --workers 2
python3 common/judge_split.py --judges kev kev4b_ft2   # → out/judges/split_summary.md
```

어댑터(149MB)와 학습 데이터는 원본 글이 들어 있어 저장소에 올리지 않는다.

### 평가 데이터 구분 (2026-10-07, [common/rules.py](common/rules.py) `SPLIT`)

| 구분 | 데이터 | 이유 |
|---|---|---|
| 개발용 | CRADLE test, Aegis 2.0, Kaggle Reddit, 남 이야기 10개 | 오답을 보고 질문·규칙을 고쳤다 (CRADLE test: 버전마다 비교 기준, Aegis: t11e '자기 자신만' 조건, Kaggle·CRADLE: t11e 병력 좁힘, 남 이야기: '본인 경험만' 지시) |
| ID 보류 | CRADLE validation, 팀 ID 표본(AttuneBench·EmpatheticDialogues·ESConv 각 300), SIM-VAIL 300 | 결과는 봤지만 이걸 보고 고치지 않았다 |
| OOD | Reddit C-SSRS 2021 (임상가 라벨, 2,680포스트) | 개발에 쓰지 않았다 (2026-10-07 추가). Aegis 2.0 도 OOD 로 넣었지만 t11e 수정에 써서 개발용이 됐다 |

개발용 수치는 낙관적일 수 있어 일반화 성능으로 보지 않는다. 질문을 더 고칠 때는 개발용만 보고, ID 보류·OOD 는 마지막 평가에만 쓴다.
OOD 오답을 보고 질문을 고치면 그 데이터는 개발용으로 옮기고 새 OOD 를 구한다.
- 비용: Jev 는 입력 토큰만 과금된다 (약 $0.042 / 100만 토큰). CRADLE test 4527발화 한 번에 약 $1 (expert11 $0.86).
- 결과 파일은 덮어쓰지 않는다. 질문을 바꾸면 `questions.py` 의 `VERSION` 을 올린다.
