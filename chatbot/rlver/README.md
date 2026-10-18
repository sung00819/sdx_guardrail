# rlver — 우울한 사용자의 기분을 지키는 챗봇 (RLVER + 성격·태도·공개 정도)

[RLVER](https://arxiv.org/abs/2507.03112) (공식 코드 [Tencent/DigitalHuman/RLVER](https://github.com/Tencent/DigitalHuman/tree/main/RLVER)) 를 그대로 쓰고,
가상 사용자에 다음을 더했다. 목표는 자살 예방이 아니라 **우울한 사용자의 감정이 나빠지지 않게, 암시적인 자살 신호·우울감을 알아채고 감정을 좋게** 만드는 것.
임상 축(셀·가드레일 코드)은 없다. `../sim/`·`../gym/` 과 코드를 공유하지 않는다 (행동 설명 `../sim_text.py` 만 가져다 쓴다).

| RLVER 그대로 | 더한 것 |
|---|---|
| 프로필 = 페르소나 · 배경 · 대화 목적 · 숨겨진 의도 | Big Five 연속 T 점수 (+ N ≥ 60 이면 신경증 하위 특성), 대화 노력 1~5, C 돕는 사람을 대하는 태도, D 털어놓는 정도 |
| 감정 30 에서 시작, 턴마다 −10~+10 (LLM 추정 → 응답 생성, 한 턴 LLM 두 번), 상태 S/A/B/C/F | 사건 `event` (severe: 심한 사건 + 위험 / mild: 약한 사건, 우울감만) × D 털어놓는 정도 `disclosure` (open / hidden), 4칸 같은 수, 둘 다 사용자마다 고정. 말하는 방식일 뿐 대화 중에 바뀌지 않는다 (hidden 은 감정이 올라도 끝까지 흘리기만 함). 챗봇 목표는 감정을 올리는 것 하나 |
| 끝: 감정 ≥ 100 Success · < 10 Failure · 챗봇 8턴 | 고정 감정 규칙 (`prompts.FIXED_RULES`): 암시 신호를 **지나치면 내려감**, 알아채고 부드럽게 짚으면 오름, 공감 뒤 직접 묻는 건 내려가지 않음, 해로운 자기 믿음 동조·무조건 남 탓은 오르지 않음 |
| 보상 r = max(e_T, 0) / 100, think 템플릿 형식 위반이면 0 | 숨겨진 욕구 8개 대신 4개: 내 잘못이 아니라고 동의 · 위로 말고 깊은 공감 · 쏟아내는 걸 들어주기 · 실질적 조언 |
| 챗봇 템플릿 think-then-say / nothink (+ SAGE 평가용 `sage`) | |

## 사용자 = 배경 (고정) + 조합 (나중에)

**배경** ([backgrounds.py](backgrounds.py)): `backgrounds_750.csv` → `out/rlver/backgrounds.csv` (O 셀·비슷한 직장 주제 제외 481 → 4칸 맞춰 336)
- 남기는 열: split, id, name, age, gender, occupation, city, topic, core_concern, risk_fact, background, event, disclosure, slot
- event: risk_fact (의도·계획·방법·최근 시도·자해 등 숨긴 위험 한 문장) 가 있으면 severe, 없으면 mild (자살 신호 없이 우울감만; `--clean` 이 죽음 소망 문장도 지운다). disclosure: 기존 reveal_level 1 → open, 2·3 → hidden
- 직장·가게 주제(389개, 58%) 중 서로 비슷한 절반 194개를 뺀다 (`--drop_work 0.5`)
- 4칸을 같은 수로 남긴다 (split 마다 가장 작은 칸 기준): 학습 66 × 4 = 264, 평가 18 × 4 = 72
  - mild·open 사건·걱정을 그대로 말함 / mild·hidden '그냥 우울해' 만 / severe·open 위험을 직접 말함 / severe·hidden 숨기고 흘리기만
- 지운 열: cell, true_codes, means, stance, reveal_level, effort, hidden_need, opening_message (첫 발화는 시뮬레이터가 연다)
- `--clean`: core_concern·background 에 남은 이전 설정 문장 (공개 문턱, 이전 욕구, 태도) 을 LLM 으로 지운다. 해당 행 학습 212 · 평가 62 (`needs_clean`)

**조합** ([compose.py](compose.py), `run.py --combo k`): 배경 id 와 k 로 고정 시드
- 숨겨진 욕구 4개: (slot + k) mod 4 → event×disclosure 칸 안에서 균등, k = 0~3 이면 배경마다 4개 모두
- C 태도 (비율 ../build_profile.py), Big Five (나이·성별 + 우울 이동 severe 0.8 · mild 0.6 + 태도 보정, N ≥ 60 이면 하위 특성), 대화 노력 (Big Five·태도에서)
- 조합마다 LLM 한 번: 습관·취미·말투·감정별 말투·직접 물을 때 반응·인물별 감정 규칙 → `out/rlver/combos.jsonl` 캐시 (배경을 다시 정리하면 지우고 다시)

```bash
python chatbot/rlver/backgrounds.py --csv backgrounds_750.csv --clean
python chatbot/rlver/run.py --split test --combo 0 --n 8 --out out/rlver/peek
```
RLVER 원래 프로필(중국어 500 · 100, 욕구 8개)로 돌리려면 [profiles.py](profiles.py) 로 번역한 뒤 `run.py --profiles`.

## 대화 · 평가 ([run.py](run.py))

```bash
python chatbot/rlver/run.py --split test --chatbot qwen2.5-7b --template think --out out/rlver/eval_base_think
python chatbot/rlver/run.py --summary out/rlver/eval_base_think   # Score · Success · Failure · event×disclosure·욕구·태도별 Score
```
서버 없이: `--config chatbot/rlver/config_openrouter.json` (시뮬레이터 DeepSeek-V3, 논문과 같음; `.env` 에 `OPENROUTER_API_KEY`).

| 파일 | 하는 일 |
|---|---|
| [config.json](config.json) | 모델 주소, 감정 시작·변화폭·끝 문턱, 턴 수, 보상, 학습 값 (논문 부록 B.3) |
| [prompts.py](prompts.py) | SAGE 감정 추정·응답 프롬프트, 챗봇 템플릿, 욕구 4개·털어놓는 정도 2개·고정 감정 규칙·배경 형식 |
| [simulator.py](simulator.py) | 가상 사용자 (f_emo → f_reply) |
| [episode.py](episode.py) | 한 대화, 형식 검사, 보상 |
| [llm.py](llm.py) | OpenAI 호환 클라이언트 (`<think>` 를 지우지 않음) |

## 남은 것
- 학습 (GRPO, 그룹 4 · 배치 32 · lr 1e-6 · KL 0) 스크립트는 아직 없다
- 실제 모델로는 아직 안 돌렸다 (가짜 LLM 으로 변환 → 대화 → 보상만 확인)
- 주의: 보상이 감정 하나라서 위기 대응을 피하는 쪽으로 배울 수 있다. 고정 규칙(신호를 지나치면 하락, 공감 뒤 직접 확인은 하락 없음)이 이를 막는지 기준 챗봇으로 먼저 확인해야 한다
