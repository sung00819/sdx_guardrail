# 페르소나 v2 설계 (초안, 2026-10-13)

목적: **유저 성향 × 발화 전략** 효과를 보기 위한 가상 사용자. 전략은 [SR/STRATEGIES.md](SR/STRATEGIES.md) (ESConv 6개).
**축은 v1([SIMULATOR_PERSONA.md](SIMULATOR_PERSONA.md)) 그대로 쓰고, 전략 선호가 심긴 곳만 고친다** (사용자 결정 2026-10-13: 축을 늘리면 서로 겹쳐 인물이 어색해진다).

---

## 0. 왜 고치나

v1 은 모든 인물에 같은 전략 선호가 들어가 있다.

| 위치 | 내용 |
|---|---|
| 고정 감정 규칙 (sim `COMMON_RULES`, gym `EMOTION_RULES`) | 오름 "묻거나 제안하기 전에 반영", 내림 "이해 전 조언·해결책" |
| 숨겨진 욕구 (`sim_text.py` `HIDDEN_NEED`) | "wants a concrete, doable next step" 등 전략 문장 그대로 |
| 인물별 규칙 (`emotion_rises_when` / `falls_when`) | 위 욕구를 보고 LLM 이 생성 |

기존 대화 3,973개를 6개 전략으로 매핑해 보니, 태도 5개 모두 반영·인정 +, 제안·정보 − 로 **부호가 같았다** (분석: SR 요약 v0, 2026-10-13).

## 1. 축 — v1 그대로

A 임상 상태 · B Big Five(+ 하위 특성, 대화 노력) · C 태도 · D 공개 정도 · E 인구학 · 배경·핵심 고통·위험 사실 · 셀별 시작 상태.
gym·sim 이 읽는 필드가 그대로라 두 시뮬레이터 코드는 거의 안 바뀐다.

Eeyore(증상 18개, 인지 왜곡 5종)는 넣지 않는다 — 증상은 A, 인지 왜곡은 신경증 하위 특성과 겹친다. 시뮬레이터 현실성 비교 대상으로만 쓴다.

## 2. 바꾸는 것

1. **숨겨진 욕구 삭제.** `be_left_alone` 은 C(avoidant), `test_if_safe_to_disclose` 는 D 와 이미 겹치고, 나머지는 전략 이름이다.
2. **고정 규칙은 안전 층만.** 남김: 상태를 절대 좋게 하지 않는 것(의존 약속·치료자 사칭·해로운 믿음 동조·방법 정보), 따뜻한 안전 확인·연결 권유는 나쁘게 하지 않음, 반복 답은 좋게 하지 않음. 뺌: "반영 먼저 → 오름", "이해 전 조언 → 내림" (사용자 결정 2026-10-13), 질문 여러 개·판단·보장 등 나머지 내림 규칙도 인물 반응에 맡김.
3. **인물별 감정 규칙 없음.** 시뮬레이터는 페르소나·배경만 보고 연기한다 (Eeyore 방식).
4. **상태 3개 모두 시뮬레이터가 직접** (사용자 결정 2026-10-13). gym `state_mode: free` — emotion·urge·safety 를 LLM 이 인물 입장에서 −2~+2 단계로 정하고 ×5. 행동별 변화량 표·좋은 행동 한 번만 인정·urge 바닥값·위험 전 한도·감정 하락 시 urge 고정 모두 없음. 한 턴 최대 ±10 은 단계 범위에서 나온다. 행동 목록은 기록만 한다 (심판 A7 체크리스트용).
5. **공개는 숫자 문턱 없이** (사용자 결정 2026-10-13, A안). 핵심 고통·위험 사실과 공개 수준 1~3(D축)은 유지하되, emotion 0/60/75 문턱 대신 성향 설명(쉽게 말함 / 이해받았다고 느껴야 말함 / 직접 물어도 부인)만 주고 언제 털어놓을지는 인물이 정한다 (`REVEAL_FREE`, `REVEAL_V2`). 이제 emotion 숫자가 쓰이는 곳은 대화 종료(100 / ≤10)와 말투 구간뿐이다.
   - 위험: v1 파일럿(2026-10-07)에서 자유 판단이면 공감만으로 urge 60→30 이 나왔다. v2 파일럿에서 셀별 urge 궤적을 먼저 본다.

6. **임상 코드는 시드에 그대로 두고, 분석은 수준(셀)으로만** (사용자 결정 2026-10-13). 근거 코드·만성 표지·위험 사실·수단은 생성 일관성과 oracle 가드레일용으로만 남는다.
7. **대화 끝 심판 없음** (사용자 결정 2026-10-13). `episode.judge = false` → 품질 축 8개·A6a 를 계산하지 않고 Q = 0. 턴 사실(LLM 분류)과 지침 플래그(코드 판정)는 남아 안전 층 위반을 본다. 전략 효과는 R 이 아니라 상태 변화(delta)로 본다.

## 3. 코드 (2026-10-13)

| 파일 | 변경 | 예전 동작 |
|---|---|---|
| [build_profile.py](build_profile.py) | `--v2`: `hidden_need` 를 뽑기만 하고 버림 → 나머지 시드는 v1 과 같다 (seed 0, 600개 확인) | 플래그 없으면 그대로 |
| [sim_text.py](sim_text.py) | `SCENE_PROMPT_V2` (욕구 줄·인물별 규칙 7·8번·전략 선호 고정 규칙 제거, 안전 층 규칙 `SAFETY_LAYER_RULES`만) | `scene_prompt(p, persona)` 그대로 |
| [gen_scene.py](gen_scene.py) | `--v2`, 결과에 `version` | 그대로 |
| [gym/simulator.py](gym/simulator.py) | `states.state_mode = "free"` 분기 (`FREE_RULES`, `_apply_free`) | 설정에 없으면 그대로 |
| [gym/config_v2.json](gym/config_v2.json) | config_sr.json + `state_mode: free` + `episode.judge: false` | — |
| [gym/run.py](gym/run.py) | `episode.judge` 가 false 면 심판 호출 없이 플래그·보상만 | 설정에 없으면 그대로 |

생성 예:
```
python chatbot/build_profile.py --v2 --n 600 --seed 0 --split train --out out/v2/seeds_train.jsonl
python chatbot/gen_scene.py --v2 --seeds out/v2/seeds_train.jsonl --model openai/gpt-6-sol --out out/v2/scenes_train.jsonl
python chatbot/gym/run.py --config config_v2.json --profiles out/v2/scenes_train.jsonl ...
```

## 4. 기존 배경 재사용 (2026-10-13, 사용자 결정)

다시 생성하지 않고 v1 750개를 고쳐 쓴다 ([edit_v2.py](edit_v2.py), 서버 Qwen3-30B, 무료). 페르소나 묘사는 그대로 — 페르소나 생성 단계에는 욕구가 안 들어갔다.
v1 배경에 남은 흔적: 핵심 고통의 75% 에 "듣는 사람에게 원하는 것" 문장 ("He needs one concrete next step for tonight", 욕구별로 단어 빈도가 뚜렷이 다름), 안전 확인 반응 741 · 배경 127 · 핵심 고통 79 곳에 감정 숫자 문턱.

- 문장은 코드가 나누고 조립한다. 감정 숫자 문턱은 정규식 규칙으로 '믿음' 표현으로 바꾸고, 시작 감정 문장은 지운다 (750개 중 규칙 뒤 남는 문턱 문장 2개 → 모델이 다시 씀).
- 모델은 배경·핵심 고통 문장마다 keep / delete / edit. delete 는 '듣는 사람에게 원하는 것'만으로 된 문장뿐, 두려움·걱정 문장은 edit 만. 원문과 단어가 50% 미만 겹치는 edit 는 거부. 정규식에 아직 걸리는 문장은 한 문장씩 2차 확인.
- 시험에서 버린 방식: 모델이 고친 글 통째로 받기('지웠다'고 하고 안 지움 4/9), 지울 문자열 고르기(대소문자 불일치, 핵심 고통 전체 삭제).
- 3단계로 돌렸다 (2026-10-13, 750개, 실패 0):
  1. 문장 단위 편집 (`--out`): 삭제 518 · 수정 134 · 2차 175 · 숫자 문턱 규칙. 그런데 핵심 고통이 두려움+원함이 한 문장인 경우가 많아 56개가 비거나 조각이 됐다.
  2. 핵심 고통 다시 쓰기 (`--core-out`): 원함이 있던 463개를 v1 원문에서 '숨은 걱정만' 남게 다시 씀. 445 통과 + 정규식 오탐 18 수용. 빈 칸 0.
  3. 배경 정리 (`--bg-out`): 남은 원함·조각 문장 100개만 한 문장씩.
- 결과 `out/v2/scenes_{train,test}.jsonl` (84 `/data2/yumin/v2edit/v2d_*`). 행마다 `edit` (deleted · edited · second · core_fix · bg_fix · left), `v1_hidden_need` (분석용으로만).
- 페르소나 묘사·id 는 v1 과 같음. 길이: 배경 95% · 핵심 고통 83%. 숫자 문턱 남음 4 (시험 점수 등 오탐 포함).
- 욕구 단어(advice·fix·listen·heard·reassure·concrete 등)가 나온 인물 수, v1 → v2: practical_help 122→47 · be_heard 113→48 · not_be_judged 70→40 · feelings_validated 54→28 · be_left_alone 42→32 · test_if_safe 43→39. 남은 '원함' 정규식 문장 57개 중 혼자 있고 싶음·가족 관련 19, 나머지 중 실제 누출은 십여 개 (예: "She wants one doable next step, but…").

## 남은 것

1. ~~생성 모델~~ → 기존 배경 재사용 (4절). OpenRouter 키 남은 한도 $7.66 (2026-10-13)
2. 상태 숫자에 기준이 없다 (시작값은 '설계', SIMULATOR_EVIDENCE.md). 구간별 기준 문장을 붙일지 — 미정.
3. 남은 선호 흔적: 생성 프롬프트의 "core_concern … Recovery depends on the listener reaching it" — 핵심 고통을 짚는 것이 회복의 열쇠라는 설정. 전략 6개와 직접 겹치지는 않아 두었다.
4. 파일럿 규모: ≈ 100명 × 6전략 × 2회 = 1,200 대화 (gym). 전략 층 프롬프트를 promptopt 뱅크 뒤에 붙이는 실행 옵션은 아직 없음
