"""평가 데이터 로더. 모든 항목은 {"key", "source", "context", "current", "gold"} 형태로 맞춘다.
Jev 에는 context(앞 대화)와 current(판정할 사용자 발화)만 보내고 gold(정답 라벨)는 보내지 않는다.

  cradle_test / cradle_validation / cradle_train
      CRADLE-Dialogue (https://huggingface.co/datasets/SungJoo/Cradle-Dialogue). data/cradle/<split>.parquet 에 받아 둔다.
      test 는 실제 대화 + 임상가 라벨, validation·train 은 GPT-5 합성. 사용자 발화마다 앞 대화 전체가 context.
  attunebench / empathetic_dialogues / esconv
      팀 저장소 guardrail-dataset 의 id/<이름>.jsonl (각 300창, 위험 라벨 없음). data/guardrail-dataset/ 에 clone 해 둔다.
      창의 마지막 사용자 발화가 current, 그 앞 발화가 context. 일반 대화에서 얼마나 보수적인지 보는 용도.
  other_check
      다른 사람 이야기 처리 확인용으로 직접 만든 발화 10개 (data/other_story_check.jsonl).
  kaggle
      Kaggle Suicidal Ideation Reddit (data/Suicidal_Reddit.csv, 15,477개 글). 제목 + 본문을 이어 붙여 current 로 쓴다.
      라벨(Suicidal / Non-Suicidal)은 서브레딧 기준이라 참고용.
  aegis2
      Aegis 2.0 test. 챗봇에 들어온 단일 사용자 입력.
  reddit_cssrs
      Reddit C-SSRS 2021 (data/download.py cssrs 로 받아 data/reddit_cssrs/posts.jsonl 로 만든다). 라벨이 있는 포스트만,
      포스트 하나씩 context 없이 판정한다 (타임스탬프가 없고 순서도 믿을 수 없음). 라벨은 임상가가 붙인 C-SSRS 단계
      supportive / indicator / ideation / behavior / attempt / uninformative. expert11 개발에 쓰지 않은 OOD.
"""

import csv
import json
import os
import random
import sys

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
GUARDRAIL_SETS = ("attunebench", "empathetic_dialogues", "esconv", "sim_vail_turn_scores")


def cradle(split="test", max_chars=20000):
    import pandas as pd
    df = pd.read_parquet(os.path.join(DATA, "cradle", f"{split}.parquet"))
    df["dialogue"] = (df["turn_id"] == 0).cumsum() - 1  # turn_id 가 0 으로 돌아갈 때마다 새 대화
    for d, g in df.groupby("dialogue", sort=True):
        history = []
        for turn_id, text, labels in zip(g["turn_id"], g["text"], g["labels"]):
            if text.startswith("User:"):
                yield {"key": f"cradle_{split}:{d}:{turn_id}", "source": f"cradle_{split}",
                       "context": "\n".join(history)[-max_chars:], "current": text,
                       "gold": {"dialogue": int(d), "turn_id": int(turn_id),
                                "labels": [x.strip() for x in (labels or "").split(";") if x.strip()]}}
            history.append(text)


def guardrail_set(name):
    with open(os.path.join(DATA, "guardrail-dataset", "id", f"{name}.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            msgs = r["context"]
            last = max(i for i, m in enumerate(msgs) if m["role"] == "user")
            who = lambda m: "User" if m["role"] == "user" else "Assistant"  # noqa: E731
            yield {"key": f"{name}:{r['record_id']}", "source": name,
                   "context": "\n".join(f"{who(m)}: {m['text']}" for m in msgs[:last]),
                   "current": f"User: {msgs[last]['text']}",
                   "gold": {"record_id": r["record_id"], "dataset": name}}


def other_check():
    with open(os.path.join(DATA, "other_story_check.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            yield {"key": f"other_check:{r['no']}", "source": "other_check", "context": "", "current": r["text"], "gold": r}


def kaggle(max_chars=20000):
    csv.field_size_limit(sys.maxsize)
    with open(os.path.join(DATA, "Suicidal_Reddit.csv"), newline="", encoding="utf-8", errors="replace") as f:
        for i, row in enumerate(csv.DictReader(f)):
            text = "\n\n".join(p for p in ((row.get("Title") or "").strip(), (row.get("Post") or "").strip()) if p)
            if text:
                yield {"key": f"kaggle:{i}", "source": "kaggle", "context": "", "current": text[:max_chars],
                       "gold": {"orig_label": row.get("Label")}}


def aegis2():
    """Aegis 2.0 test (nvidia/Aegis-AI-Content-Safety-Dataset-2.0, CC-BY-4.0). 챗봇에 들어온 단일 사용자 입력 1,964개.
    양성 = violated_categories 에 'Suicide and Self Harm'. 프롬프트가 REDACTED 인 행은 뺀다."""
    with open(os.path.join(DATA, "aegis2", "test.json")) as f:
        for a in json.load(f):
            text = (a.get("prompt") or "").strip()
            if text and text.upper() != "REDACTED":
                yield {"key": f"aegis2:{a['id']}", "source": "aegis2", "context": "", "current": text,
                       "gold": {"prompt_label": a.get("prompt_label"), "categories": a.get("violated_categories") or "",
                                "self_harm": "Suicide and Self Harm" in (a.get("violated_categories") or "")}}


def reddit_cssrs(max_chars=20000):
    with open(os.path.join(DATA, "reddit_cssrs", "posts.jsonl")) as f:
        for i, line in enumerate(f):
            r = json.loads(line)
            if r["label"] and r["text"].strip():
                yield {"key": f"reddit_cssrs:{i}", "source": "reddit_cssrs", "context": "", "current": r["text"][:max_chars],
                       "gold": {"label": r["label"], "user": r["user"], "text_from_json": r["text_from_json"]}}


def load(source, sample=None, seed=0):
    if source.startswith("cradle_"):
        rows = list(cradle(source.split("_", 1)[1]))
    elif source in GUARDRAIL_SETS:
        rows = list(guardrail_set(source))
    elif source == "other_check":
        rows = list(other_check())
    elif source == "kaggle":
        rows = list(kaggle())
    elif source == "aegis2":
        rows = list(aegis2())
    elif source == "reddit_cssrs":
        rows = list(reddit_cssrs())
    else:
        raise SystemExit(f"없는 데이터: {source}")
    if sample and sample < len(rows):
        rows = random.Random(seed).sample(rows, sample)
    return rows
