# rlver — 우울한 사용자의 기분을 지키는 챗봇 (RLVER + 성격·태도·공개 정도)

[RLVER](https://arxiv.org/abs/2507.03112) (공식 코드 [Tencent/DigitalHuman/RLVER](https://github.com/Tencent/DigitalHuman/tree/main/RLVER)) 를 그대로 쓰고,
가상 사용자에 다음을 더했다. 목표는 자살 예방이 아니라 **우울한 사용자의 감정이 나빠지지 않게, 암시적인 자살 신호·우울감을 알아채고 감정을 좋게** 만드는 것.
임상 축(셀·가드레일 코드)은 없다. `../sim/`·`../gym/` 과 코드를 공유하지 않는다 (행동 설명 `../sim_text.py` 만 가져다 쓴다).

| RLVER 그대로 | 더한 것 |
|---|---|
| 프로필 = 페르소나 · 배경 · 대화 목적 · 숨겨진 의도 | 대화 노력 1~5, C 돕는 사람을 대하는 태도, D 털어놓는 정도 |
| 감정 30 에서 시작, 턴마다 −10~+10 (LLM 추정 → 응답 생성, 한 턴 LLM 두 번), 상태 S/A/B/C/F | 사건 `event` (severe: 심한 사건 + 위험 / mild: 약한 사건, 우울감만, 배경에 고정) × D 털어놓는 정도 `disclosure` (high / low, 조합). 말하는 방식일 뿐 대화 중에 바뀌지 않는다 (hidden 은 감정이 올라도 끝까지 흘리기만 함). 챗봇 목표는 감정을 올리는 것 하나 |
| 끝: 감정 ≥ 100 Success · < 10 Failure · 챗봇 8턴 | 감정이 오르는 경우는 RLVER 그대로 인물별 규칙 + 숨겨진 의도. 고정 규칙은 내리는 경우와 한계만 (신호를 지나치면 내림, 공감 뒤 직접 확인은 내리지 않음, 해로운 동조는 올리지 않음) |
| 보상 r = max(e_T, 0) / 100, think 템플릿 형식 위반이면 0 | 숨겨진 의도 8개 대신 원하는 대응 방식 3개: 위로 말고 깊은 공감 · 쏟아내는 걸 들어주기 · 실질적 조언. 챗봇이 고르게 하면 사용자가 밝힌다 (대화 흐름) |
| 챗봇 템플릿 think-then-say / nothink (+ SAGE 평가용 `sage`) | |

## 사용자 = 배경 (고정) × 설정 6개

**배경** ([`data/rlver/backgrounds.csv`](../../data/rlver/backgrounds.csv), 저장소에 올린 정본, [backgrounds.py](backgrounds.py) 로 만들고 문장 정리까지 끝낸 336개)
- 열 (10개): split, id, name, age, gender, occupation, topic, core_concern, risk_fact, background. 지운 열: city, event, slot, disclosure, needs_clean, opening_message, 임상 축 (cell, true_codes, means), 이전 설정 (stance, reveal_level, effort, hidden_need)
- event 는 열이 아니라 읽을 때 계산한다 (`backgrounds.read`): risk_fact (의도·계획·방법·최근 시도·자해 등) 가 있으면 severe, 없으면 mild (자살 신호 없이 우울감만). 학습 132 · 132, 평가 36 · 36
- Numbers·Excel 에서 내보낸 csv 도 그대로 읽는다 (숫자로 바뀐 id 를 되돌린다, 예 `84964800000000.0` → `849648e8`)
- O 셀과 서로 비슷한 직장 주제 절반은 뺐다. 이전 설정 문장 (공개 문턱·이전 욕구·태도·시작 감정) 과 mild 의 죽음 소망·자해 문장은 지웠다
- 첫 메시지 (`opening_message`) 는 없다: 이전 대화 노력·태도로 쓴 것이라 지웠고, 시뮬레이터가 대화 시작에 쓴다

**설정** ([compose.py](compose.py)): 배경마다 6개 → 배경당 대화 6개. LLM 으로 더 만드는 것은 없다
- 설정 s = 0~5: 원하는 대응 방식 3개 (들어주기 · 깊은 공감 · 조언) × 털어놓는 정도 high/low
- 설정마다 랜덤 (배경 id·s 로 고정 시드): 돕는 사람을 대하는 태도 5개 중 하나, 대화 노력 1~5 중 하나 (둘 다 균등)
- 페르소나 = 이름·나이·성별·직업 + 대화 노력 문장 + 태도 문장 (`../sim_text.py` EFFORT · STANCE)

## 대화 흐름
1. 사용자가 페르소나·배경으로 짧게 연다: "나 기분이 안 좋아", "어제 엄마랑 싸웠어" (어떻게 해 주길 원하는지는 아직 말하지 않는다)
2. 챗봇 (`--template bank`): 공감 ("힘들었겠다") → 어떻게 얘기할지 고르게 한다 ("괜찮았어? 자세히 얘기해도 되고, 그냥 기분만 얘기해도 돼. 들어줄게")
3. 사용자가 원하는 방식을 자기 말로 밝힌다: 그냥 털어놓고 싶다 / 정말 어떤 기분인지 알아줬으면 / "~인데 이건 어떻게 할까?"
4. 챗봇이 그 방식대로 대응한다.
- 감정이 오르는 경우는 RLVER 처럼 고정하지 않는다: 감정 분석기가 숨겨진 의도 (원하는 대응 방식) 를 보고 판단한다
- 고정 규칙 (`prompts.FIXED_RULES`) 은 내리는 경우와 한계만: 밝힌 방식과 다르게 대응, 신호를 지나침, 섣부른 긍정·훈계·축소, 질문 여러 개·반복, 상투적 핫라인 → 내림. 공감 뒤 자살 직접 확인은 내리지 않음, 해로운 자기 믿음 동조·복수·공격 부추김은 올리지 않음
- 털어놓는 정도 high 는 사건·걱정 (severe 는 위험까지) 을 분명히 말하고, low 는 끝까지 '그냥 우울해' (severe 는 흘리기만) 로 말한다. 대화 중에 바뀌지 않는다
- 챗봇 템플릿: `bank` (기본, 대응 전략 뱅크 — [STRATEGY.md](STRATEGY.md)) · `bank_oracle` (원하는 방식·위험을 알려 준 상한) · `guide` (짧은 지침) · `think` · `nothink` (RLVER 원래) · `sage` (평가용)

## 대화 · 평가 ([run.py](run.py))

```bash
python chatbot/rlver/run.py --split test --per_event 1 --out out/rlver/peek   # 맛보기: mild·severe 배경 1개씩 × 설정 6 = 12 대화
python chatbot/rlver/peek.py out/rlver/peek                                       # → out/rlver/peek/dialogues.md
python chatbot/rlver/run.py --split test --chatbot qwen2.5-7b --template bank --out out/rlver/eval_bank
python chatbot/rlver/run.py --summary out/rlver/eval_bank   # Score · Success · Failure · event×disclosure·욕구·태도별 Score
```
84번 서버 안에서: `--config chatbot/rlver/config_84.json --chatbot qwen3-8b` (또는 `qwen30b`). 서버 없이: `--config chatbot/rlver/config_openrouter.json` (시뮬레이터 DeepSeek-V3, 논문과 같음; `.env` 에 `OPENROUTER_API_KEY`).

| 파일 | 하는 일 |
|---|---|
| [config.json](config.json) | 모델 주소, 감정 시작·변화폭·끝 문턱, 턴 수, 보상, 학습 값 (논문 부록 B.3) |
| [prompts.py](prompts.py) | SAGE 감정 추정·응답 프롬프트, 챗봇 템플릿, 대응 방식 3개·털어놓는 정도 2개·고정 감정 규칙·배경 형식 |
| [simulator.py](simulator.py) | 가상 사용자 (f_emo → f_reply) |
| [episode.py](episode.py) | 한 대화, 형식 검사, 보상 |
| [llm.py](llm.py) | OpenAI 호환 클라이언트 (`<think>` 를 지우지 않음) |

## 남은 것
- 학습 (GRPO, 그룹 4 · 배치 32 · lr 1e-6 · KL 0) 스크립트는 아직 없다
- 실제 모델로는 아직 안 돌렸다 (가짜 LLM 으로 변환 → 대화 → 보상만 확인)
- 주의: 보상이 감정 하나라서 위기 대응을 피하는 쪽으로 배울 수 있다. 고정 규칙(신호를 지나치면 하락, 공감 뒤 직접 확인은 하락 없음)이 이를 막는지 기준 챗봇으로 먼저 확인해야 한다
