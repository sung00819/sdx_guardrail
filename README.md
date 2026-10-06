# sdx_guardrail — Jev 기반 자살·자해 위험 감지 설계 3안

챗봇 대화의 **사용자 발화 하나**를 보고 자살·자해 위험 신호를 감지해, 위험 수준과 대응 수준을 정한다.
판정은 TypeSafe Jev(`typesafe/jev-1.13`, OpenRouter Decisions API)가 질문별 확률로 답하고, 수준은 코드에서 규칙으로 계산한다.
챗봇 답변의 검사·생성은 범위 밖이다.

| 설계 | 한 줄 요약 | 질문 수 (Jev 1번 호출) |
|---|---|---|
| [base](base/) | 기존 감지 질문(v4i)만으로 단계를 나눔 | 13 |
| [base-eval](base-eval/) | base + 전문가 추가 신호 + 자살 행동·자해의 경험과 시점 | 27 |
| [expert11](expert11/) | 전문가 검수 자료의 11개 위험평가 기준 항목 + 시점 (v4i 없음) | 17 |

공통
- 입력: `current`(판정할 사용자 발화)와 `context`(앞 대화). 정답 라벨은 Jev 에 보내지 않는다.
- 출력: 급성 위험 수준(고 / 중 / 저 / 신호 없음) + 만성 위험 표지 → 대응 수준 4단계
  (즉시 대응 / 확인과 연계 / 지지와 추적 / 통상 대응). 결합 규칙은 [common/rules.py](common/rules.py).
- 판정 원칙: 가장 높은 기준으로 판정(합산하지 않음), 맥락 요인으로 한 단계까지만 상향, 보호요인·부인으로 낮추지 않음,
  시간 창이 지난 정보는 지우지 않고 만성 표지로 옮김.
- 다른 사람 이야기: 질문마다 "작성자 본인의 경험만 센다"고 지시한다. base·base-eval 은 신호가 있는데 v4i 주체가 다른 사람이면 '제외(타인)'로도 표시한다.
- base·base-eval 은 v4i 질문을 포함하므로 기존 발동 규칙([base/guard_rule.py](base/guard_rule.py) `decide_final`) 결과도 함께 나온다. expert11 은 v4i 를 묻지 않아 `v4i_decision` 이 `null`.

## 출력 형식

발화마다 한 줄 (`out/combined_<설계>_<source>.jsonl`). 값은 영어 코드이고, 한국어 이름은 [common/rules.py](common/rules.py) `LABEL_KO`.

```json
{"level": "moderate", "response": "assess", "reasons": ["indirect_warning"],
 "context": ["acute_context"], "upgraded_by": "acute_context", "chronic": ["psychiatric_history"],
 "v4i_decision": "no_alert"}
```

측정값과 규칙 결과를 나눈다 (2026-10-05). `reasons`·`context`·`chronic` 은 Jev 가 본 것, `level`·`response`·`upgraded_by` 는 규칙으로 계산한 것.

| 필드 | 값 |
|---|---|
| `level` (급성 수준) | `high` 급성 고 · `moderate` 급성 중 · `low` 급성 저 · `none` 신호 없음 · `other` 제외(타인) |
| `response` (대응 수준) | `urgent` 즉시 대응 · `assess` 확인과 연계 · `support` 지지와 추적 · `normal` 통상 대응 · `other` 제외(타인) |
| `context` (맥락 요인, 측정) | `means_access` 치명적 수단 접근 · `acute_context` 급성 위험 맥락. Jev 가 '예'면 **상향 여부와 상관없이** 항상 넣는다 |
| `upgraded_by` (상향, 규칙) | 맥락 요인으로 한 단계 올렸으면 `means_access`(중→고) 또는 `acute_context`(저→중), 아니면 `null` |
| `v4i_decision` | 기존 발동 규칙: `alert` 발동 · `past_info_only` 과거(병렬 전달) · `other_person` 제외(타인) · `no_alert` 미발동 (expert11 은 `null`) |

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
| base | 4 | 15 | 26 | 0 |
| base-eval | 1 | 1 | 111 | 7 |
| expert11 | 2 | 0 | 264 | 14 |

## 구조

```
common/      jev_client.py  Jev 호출(재시도)   data.py  데이터 로더   rules.py  기준값·대응 수준
             run_judge.py   채점              combine.py  수준 계산    compare.py  설계 비교표
base/        questions.json / questions.py  질문,  levels.py  수준 규칙,  guard_rule.py  기존 발동 규칙
base-eval/   questions.py  levels.py
expert11/    questions.py  levels.py
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
python3 common/run_judge.py --design base-eval --source cradle_test --dry-run   # 호출 수·글자 수만 확인
python3 common/run_judge.py --design base-eval --source cradle_test             # → out/el3c_cradle_test.jsonl
python3 common/combine.py   --design base-eval --source cradle_test             # → out/combined_base-eval_cradle_test.jsonl
python3 common/compare.py   --source cradle_test                                # → out/compare_cradle_test.md
```

- base 는 base-eval 결과에 들어 있는 v4i 답으로도 계산할 수 있다:
  `python3 common/combine.py --design base --source cradle_test --input out/el3c_cradle_test.jsonl`
- 비용: Jev 는 입력 토큰만 과금된다 (약 $0.042 / 100만 토큰). CRADLE test 4527발화 한 번에 약 $1 (expert11 $0.86).
- 결과 파일은 덮어쓰지 않는다. 질문을 바꾸면 `questions.py` 의 `VERSION` 을 올린다.
