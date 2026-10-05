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
"""

import json
import os
import random

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
GUARDRAIL_SETS = ("attunebench", "empathetic_dialogues", "esconv")


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


def load(source, sample=None, seed=0):
    if source.startswith("cradle_"):
        rows = list(cradle(source.split("_", 1)[1]))
    elif source in GUARDRAIL_SETS:
        rows = list(guardrail_set(source))
    elif source == "other_check":
        rows = list(other_check())
    else:
        raise SystemExit(f"없는 데이터: {source}")
    if sample and sample < len(rows):
        rows = random.Random(seed).sample(rows, sample)
    return rows
