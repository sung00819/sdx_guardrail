# 시뮬레이터 (회복 챗봇 RL 환경)

설계: [../SIMULATOR_PERSONA.md](../SIMULATOR_PERSONA.md) 5절 (보상), 프로필 생성: [../gen_scene.py](../gen_scene.py).

| 파일 | 하는 일 |
|---|---|
| [config.json](config.json) | 조정할 값 전부: 모델 주소, 감정 범위·근거 없을 때 한도, 공개 문턱, 위험 최대 변화폭·감소 조건, 보상 가중치, 턴 수 |
| [llm.py](llm.py) | OpenAI 호환 클라이언트 (서버 vLLM / OpenRouter) |
| [guardrail.py](guardrail.py) | expert11 실시간 판정 → 챗봇용 `[guardrail]` 블록 + 당장 위험 점수 |
| [user_sim.py](user_sim.py) | 시뮬레이터: 감정 추정 → 위험 상태 갱신 → 응답 생성 (+ 공개 전 누설 검사), 솔직한 체크인 |
| [run_episode.py](run_episode.py) | 체크인 → 대화 → 체크인 → 보상 |

## 한 턴
1. 사용자 발화 → expert11 Jev → `[guardrail]` 블록 (위험이 잡히면 `risk_visible`)
2. 챗봇 (시스템 프롬프트 + 블록 + 대화)
3. 감정 추정: LLM 은 번호 붙은 규칙(공통·모드·인물별 오름 R#/내림 F#) 중 이번 답이 한 것과 **인용문**만 낸다. 점수는 코드가 매긴다 (config emotion.scoring): 오름 규칙은 에피소드에서 처음 인정될 때 +4, 다시 인정되면 +1 (턴당 +2까지), 인용 있는 내림 −3, 빠진 것을 지적하는 인용 없는 내림 −2 (턴당 −2까지). 위험 점수가 남아 있으면 감정 상한 max(80, 100 − 150·(위험 − 0.05)) → 위험을 다루지 않으면 '만족하고 끝(100)'에 못 닿는다. (이전 방식은 LLM 이 변화량을 직접 매겨 같은 공감에 매 턴 +7~8 을 줘서 sft_gen 의 70% 가 100 에 닿았다.) 위험은 행동 분류 → action_rules
4. 코드가 한도 적용: 위험 감소는 감정 ≥ 50 · 공개 문턱 통과 · 가드레일이 위험을 잡은 뒤에만, 에피소드당 최대 변화폭
5. 응답 생성. 공개 전에 숨긴 것을 말하면 한 번 다시 쓴다

## 보상
`R = 0.4·감정_끝/100 + 0.6·(위험_시작 − 위험_끝) − 위반` — 위험은 대화 전후 **솔직한 체크인**(내부 상태를 글로 바꾼 것)을 expert11 로 채점. 위반 판정(GUIDE_FLAGS.md)은 아직 없음 (0).

## 서버 (84번 = `.env` 의 SDX_HOST84, `/data2/yumin`)
- 시뮬레이터 Qwen3-30B-A3B-Instruct-2507 FP8: GPU 0·1, 포트 18601 (`serve_30b.sh`)
- 챗봇 Qwen3-8B: GPU 2, 포트 18602 (`serve_8b.sh`)
- env: `/data2/yumin/env` (공용 qwen-vllm 복제, vLLM 0.18.1 · torch cu128 — 서버 드라이버가 CUDA 12.8 이라 최신 vLLM(cu130)은 안 뜸). 둘 다 `--enforce-eager`
- 맥에서 실행: `ssh -N -L 18601:127.0.0.1:18601 -L 18602:127.0.0.1:18602 $SDX_HOST84` 후

```
python chatbot/sim/run_episode.py --profiles out/pilot_sol_v3.jsonl --out out/sim_runs/pilot_v1 --workers 8
```

`config_openrouter.json` 은 서버 없이 같은 모델을 OpenRouter 로 부르는 시험용.
