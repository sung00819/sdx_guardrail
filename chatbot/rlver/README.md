# rlver — 우울한 사용자의 기분을 지키는 챗봇 (RLVER + 성격·태도·공개 정도)

[RLVER](https://arxiv.org/abs/2507.03112) (공식 코드 [Tencent/DigitalHuman/RLVER](https://github.com/Tencent/DigitalHuman/tree/main/RLVER)) 를 그대로 쓰고,
가상 사용자에 다음을 더했다. 목표는 자살 예방이 아니라 **우울한 사용자의 감정이 나빠지지 않게, 암시적인 자살 신호·우울감을 알아채고 감정을 좋게** 만드는 것.
임상 축(셀·가드레일 코드)은 없다. `../sim/`·`../gym/` 과 코드를 공유하지 않는다 (행동 설명 `../sim_text.py` 만 가져다 쓴다).

| RLVER 그대로 | 더한 것 |
|---|---|
| 프로필 = 페르소나 · 배경 · 대화 목적 · 숨겨진 의도 | Big Five 연속 T 점수 (+ N ≥ 60 이면 신경증 하위 특성), 대화 노력 1~5, C 돕는 사람을 대하는 태도, D 털어놓는 정도 |
| 감정 30 에서 시작, 턴마다 −10~+10 (LLM 추정 → 응답 생성, 한 턴 LLM 두 번), 상태 S/A/B/C/F | D 는 사용자마다 **고정** 두 가지: `overt` 매우 위험 (배경에 숨긴 위험 사실이 있음, 직접 말함) · `subtle` 은은하게 위험 (끝까지 돌려 말함, 이전 부인·숨김도 여기) |
| 끝: 감정 ≥ 100 Success · < 10 Failure · 챗봇 8턴 | 고정 감정 규칙 (`prompts.FIXED_RULES`): 암시 신호를 **지나치면 내려감**, 알아채고 부드럽게 짚으면 오름, 공감 뒤 직접 묻는 건 내려가지 않음, 해로운 자기 믿음 동조·무조건 남 탓은 오르지 않음 |
| 보상 r = max(e_T, 0) / 100, think 템플릿 형식 위반이면 0 | 숨겨진 욕구 8개 대신 4개: 내 잘못이 아니라고 동의 · 위로 말고 깊은 공감 · 쏟아내는 걸 들어주기 · 실질적 조언 |
| 챗봇 템플릿 think-then-say / nothink (+ SAGE 평가용 `sage`) | |

## 프로필: 기존 배경 재사용 ([convert_scenes.py](convert_scenes.py))

`out/scenes_{train,test}.jsonl` (../gen_scene.py 결과, 600 · 150개) 에서:
- **그대로**: 페르소나, 사건 배경, 핵심 고통, 숨긴 위험 사실(있으면 overt), 감정별 말투, 직접 물을 때의 반응, 첫 메시지 (`first_talk`), Big Five·대화 노력·C·D 시드
- **다시**: 숨겨진 욕구 (같은 뜻은 유지 — be_heard→들어주기, feelings_validated→깊은 공감, practical_help→조언, not_be_judged→내 잘못 아님 — 나머지로 4개 균등), 인물별 감정 규칙 `emotion_rises_when`/`falls_when` (이전 욕구에 맞춰 썼으므로, LLM 한 번)
- **뺌**: O 셀 (다른 사람 이야기). 모든 인물은 우울한 사용자로 그린다
- 출력 `out/rlver/profiles_{split}.jsonl`: `persona`·`background` 는 SAGE 형식 글, 시드 값은 따로 필드로

```bash
python chatbot/rlver/convert_scenes.py --split test --limit 5   # 시험
python chatbot/rlver/convert_scenes.py                          # train, test
```
RLVER 원래 프로필(중국어 500 · 100, 욕구 8개)로 돌리려면 [profiles.py](profiles.py) (영어로 번역).

## 대화 · 평가 ([run.py](run.py))

```bash
python chatbot/rlver/run.py --split test --chatbot qwen2.5-7b --template think --out out/rlver/eval_base_think
python chatbot/rlver/run.py --summary out/rlver/eval_base_think   # Score · Success · Failure · overt/subtle · 욕구별 Score
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
