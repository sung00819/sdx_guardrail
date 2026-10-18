# data

데이터 원본은 이 저장소에 올리지 않는다 (공개 저장소이고, CRADLE 은 배포 조건이 표기돼 있지 않음). 아래 스크립트로 받는다.

```bash
python3 data/download.py              # 전부
python3 data/download.py cradle       # CRADLE-Dialogue 만
python3 data/download.py guardrail    # 팀 guardrail-dataset 만 (접근 권한 필요)
python3 data/download.py cssrs        # Reddit C-SSRS 2021 만 (받은 뒤 posts.jsonl 로 만듦)
```

| 데이터 | 받는 곳 | 저장 위치 | 쓰임 |
|---|---|---|---|
| CRADLE-Dialogue | [Hugging Face SungJoo/Cradle-Dialogue](https://huggingface.co/datasets/SungJoo/Cradle-Dialogue) | `data/cradle/{test,validation,train}.parquet` | 위기 감지 성능. test = 실제 대화·임상가 라벨 (사용자 발화 4527개), validation·train = GPT-5 합성 |
| guardrail-dataset ID 표본 | 팀 저장소 `yujinoh0103/guardrail-dataset` 의 `data/id-300-windows` 브랜치 (비공개) | `data/guardrail-dataset/id/*.jsonl` | 일반 대화에서 얼마나 보수적인지 (AttuneBench·EmpatheticDialogues·ESConv 각 300창) |
| other_story_check.jsonl | 이 저장소 | `data/` | 다른 사람 이야기 처리 확인용으로 직접 만든 발화 10개 |
| Kaggle Suicidal Ideation Reddit | Kaggle 에서 직접 받기 (로그인 필요, 스크립트 없음) | `data/Suicidal_Reddit.csv` (열: Title, Post, Label) | Reddit 글 15,477개. 라벨은 서브레딧 기준(Suicidal / Non-Suicidal)이라 참고용 |
| Aegis 2.0 test | [Hugging Face nvidia/Aegis-AI-Content-Safety-Dataset-2.0](https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-2.0) | `data/aegis2/test.json` | 챗봇 단일 입력 1,928개 (REDACTED 제외). 양성 = Suicide and Self Harm 38개 |
| Reddit C-SSRS 2021 (time-variant) | [Zenodo 4543776](https://zenodo.org/records/4543776) (CC-BY-4.0) | `data/reddit_cssrs/` → `posts.jsonl` | **OOD.** 임상가가 포스트마다 C-SSRS 단계 라벨을 붙인 Reddit 글. 라벨 있는 2,680개를 포스트 하나씩 판정 |

결과 표(results/)는 2026-10 에 받은 위 파일로 만들었다 (스크립트로 받은 파일과 바이트 단위로 같음을 확인).

## rlver 배경 (`rlver/backgrounds.csv`)

우울한 사용자 시뮬레이터 배경 336개 (학습 264 · 평가 72, mild · severe 반반). 합성 데이터 (gpt-6-sol 생성 → 문장 정리). 다른 데이터와 달리 저장소에 올린다 (사용자 결정 2026-10-18). 열·만든 과정은 [../chatbot/rlver/README.md](../chatbot/rlver/README.md).
