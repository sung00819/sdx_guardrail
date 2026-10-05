# data

데이터 원본은 이 저장소에 올리지 않는다 (공개 저장소이고, CRADLE 은 배포 조건이 표기돼 있지 않음). 아래 스크립트로 받는다.

```bash
python3 data/download.py              # 전부
python3 data/download.py cradle       # CRADLE-Dialogue 만
python3 data/download.py guardrail    # 팀 guardrail-dataset 만 (접근 권한 필요)
```

| 데이터 | 받는 곳 | 저장 위치 | 쓰임 |
|---|---|---|---|
| CRADLE-Dialogue | [Hugging Face SungJoo/Cradle-Dialogue](https://huggingface.co/datasets/SungJoo/Cradle-Dialogue) | `data/cradle/{test,validation,train}.parquet` | 위기 감지 성능. test = 실제 대화·임상가 라벨 (사용자 발화 4527개), validation·train = GPT-5 합성 |
| guardrail-dataset ID 표본 | 팀 저장소 `yujinoh0103/guardrail-dataset` 의 `data/id-300-windows` 브랜치 (비공개) | `data/guardrail-dataset/id/*.jsonl` | 일반 대화에서 얼마나 보수적인지 (AttuneBench·EmpatheticDialogues·ESConv 각 300창) |
| other_story_check.jsonl | 이 저장소 | `data/` | 다른 사람 이야기 처리 확인용으로 직접 만든 발화 10개 |

결과 표(results/)는 2026-10 에 받은 위 파일로 만들었다 (스크립트로 받은 파일과 바이트 단위로 같음을 확인).
