# sdx_guardrail — Jev 기반 자살·자해 위험 감지 설계 3안

챗봇 대화의 **사용자 발화 하나**를 보고 자살·자해 위험 신호를 감지해, 위험 수준과 대응 수준을 정한다.
판정은 TypeSafe Jev(`typesafe/jev-1.13`, OpenRouter Decisions API)가 질문별 확률로 답하고, 수준은 코드에서 규칙으로 계산한다.
챗봇 답변의 검사·생성은 범위 밖이다.

| 설계 | 한 줄 요약 | 질문 수 (Jev 1번 호출) |
|---|---|---|
| [base](base/) | 기존 감지 질문(v4i)만으로 단계를 나눔 | 13 |
| [base-eval](base-eval/) | base + 전문가 추가 신호 + 자살 행동·자해의 경험과 시점 | 27 |
| [expert11](expert11/) | 전문가 검수 자료의 11개 위험평가 기준 항목 + 시점 | 30 |

공통
- 입력: `current`(판정할 사용자 발화)와 `context`(앞 대화). 정답 라벨은 Jev 에 보내지 않는다.
- 출력: 급성 위험 수준(고 / 중 / 저 / 신호 없음) + 만성 위험 표지 → 대응 수준 4단계
  (즉시 대응 / 확인과 연계 / 지지와 추적 / 통상 대응). 결합 규칙은 [common/rules.py](common/rules.py).
- 판정 원칙: 가장 높은 기준으로 판정(합산하지 않음), 맥락 요인으로 한 단계까지만 상향, 보호요인·부인으로 낮추지 않음,
  시간 창이 지난 정보는 지우지 않고 만성 표지로 옮김.
- 다른 사람 이야기: 질문마다 "작성자 본인의 경험만 센다"고 지시하고, 신호가 있는데 주체가 다른 사람이면 '제외(타인)'.
- 세 설계 모두 v4i 질문을 포함하므로 기존 발동 규칙([base/guard_rule.py](base/guard_rule.py) `decide_final`) 결과도 함께 나온다.

결과 요약은 [results/README.md](results/README.md). CRADLE test(실제 대화, 임상가 라벨)에서:

| | 지금 자살·자해 211개 중 놓침 | 과거 42개 중 놓침 | 위기 이전 1814개 중 대응 붙음 | 일반 대화 900개 중 대응 붙음 |
|---|---|---|---|---|
| base | 4 | 15 | 26 | 0 |
| base-eval | 1 | 1 | 111 | 7 |
| expert11 | 1 | 0 | 268 | 18 |

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

- base 는 base-eval·expert11 결과에 들어 있는 v4i 답으로도 계산할 수 있다:
  `python3 common/combine.py --design base --source cradle_test --input out/el3c_cradle_test.jsonl`
- 비용: Jev 는 입력 토큰만 과금된다 (약 $0.042 / 100만 토큰). CRADLE test 4527발화 한 번에 약 $1.
- 결과 파일은 덮어쓰지 않는다. 질문을 바꾸면 `questions.py` 의 `VERSION` 을 올린다.
