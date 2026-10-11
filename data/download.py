"""평가 데이터를 data/ 아래로 받는다. 데이터 원본은 이 저장소에 올리지 않는다 (공개 저장소, 원 데이터의 배포 조건).

    python3 data/download.py              # 전부
    python3 data/download.py cradle       # CRADLE-Dialogue 만
    python3 data/download.py guardrail    # 팀 guardrail-dataset 만
    python3 data/download.py cssrs        # Reddit C-SSRS 2021 만 (OOD)

  cradle     https://huggingface.co/datasets/SungJoo/Cradle-Dialogue → data/cradle/{test,validation,train}.parquet
             test 는 실제 대화 + 임상가 라벨, validation·train 은 GPT-5 합성.
  guardrail  https://github.com/yujinoh0103/guardrail-dataset (비공개 팀 저장소, 접근 권한 필요)의
             data/id-300-windows 브랜치 → data/guardrail-dataset/ (id/attunebench.jsonl 등, 데이터별 300창)
  cssrs      https://zenodo.org/records/4543776 (Reddit C-SSRS 2021 time-variant, CC-BY-4.0) → data/reddit_cssrs/
             받은 뒤 posts.jsonl 로 만든다: 라벨은 xlsx(포스트 단위), 텍스트는 Unlabeled_Dataset.json 의 원문.
             xlsx 텍스트는 단어가 의학 용어로 바뀌어 있어서("hurt"→"Pain") 같은 사용자의 json 포스트와 단어 유사도로 맞춘다.
             매칭 방법과 라벨 오타 정리는 팀 guardrail-dataset 의 scripts/labeling_pipeline/build/reddit_cssrs.py 와 같다.
"""

import difflib
import json
import math
import warnings

import os
import subprocess
import sys

import requests

DATA = os.path.dirname(os.path.abspath(__file__))
CRADLE_URL = "https://huggingface.co/datasets/SungJoo/Cradle-Dialogue/resolve/main/data/{split}-00000-of-00001.parquet"
GUARDRAIL_REPO = "https://github.com/yujinoh0103/guardrail-dataset.git"
GUARDRAIL_BRANCH = "data/id-300-windows"
CSSRS_URL = "https://zenodo.org/records/4543776/files/{name}?download=1"
CSSRS_BATCHES = [f"Redditors_and_posts_batch_{i}.xlsx" for i in range(1, 6)]
CSSRS_JSON = "Unlabeled_Dataset.json"
CSSRS_MATCH = 0.6
CSSRS_LABELS = {  # 라벨 표기(오타 포함) → 6개. 모르는 표기는 에러
    "supportive": "supportive", "supporitve": "supportive", "suppr": "supportive",
    "indicator": "indicator", "indiccator": "indicator",
    "ideation": "ideation", "ideations": "ideation", "suicidal ideations": "ideation",
    "behavior": "behavior", "attempt": "attempt",
    "uninformative": "uninformative", "noninformative": "uninformative",
    "uniformative": "uninformative", "noninformtative": "uninformative",
}


def cradle():
    os.makedirs(os.path.join(DATA, "cradle"), exist_ok=True)
    for split in ("test", "validation", "train"):
        dst = os.path.join(DATA, "cradle", f"{split}.parquet")
        if os.path.exists(dst):
            print(f"있음: {dst}")
            continue
        print(f"받는 중: {split}")
        r = requests.get(CRADLE_URL.format(split=split), timeout=120)
        r.raise_for_status()
        with open(dst, "wb") as f:
            f.write(r.content)
    print("CRADLE 완료")


def guardrail():
    dst = os.path.join(DATA, "guardrail-dataset")
    if os.path.exists(dst):
        print(f"있음: {dst}")
        return
    subprocess.run(["git", "clone", "--depth", "1", "--branch", GUARDRAIL_BRANCH, GUARDRAIL_REPO, dst], check=True)
    print("guardrail-dataset 완료")


def _cssrs_label(raw):
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    key = str(raw).strip().lower()
    if key not in CSSRS_LABELS:
        raise ValueError(f"모르는 C-SSRS 라벨 표기: {raw!r}")
    return CSSRS_LABELS[key]


def _cssrs_clean(text):
    text = str(text).strip()
    return (text[1:] if text.startswith("'") else text).strip()  # xlsx 의 리스트 repr 잔재


def _cssrs_match(text, posts, index):
    key = " ".join(text.split())
    if key in index:
        return posts[index[key]], True
    words, best, best_score = text.split(), None, 0.0
    for p in posts:
        m = difflib.SequenceMatcher(None, words, p.split(), autojunk=False)
        if m.quick_ratio() < CSSRS_MATCH:
            continue
        if m.ratio() > best_score:
            best, best_score = p, m.ratio()
    return (best, True) if best_score >= CSSRS_MATCH else (text, False)


def cssrs():
    import pandas as pd
    d = os.path.join(DATA, "reddit_cssrs")
    os.makedirs(d, exist_ok=True)
    for name in CSSRS_BATCHES + [CSSRS_JSON]:
        dst = os.path.join(d, name)
        if os.path.exists(dst):
            print(f"있음: {dst}")
            continue
        print(f"받는 중: {name}")
        r = requests.get(CSSRS_URL.format(name=name), timeout=600)
        r.raise_for_status()
        with open(dst, "wb") as f:
            f.write(r.content)
    originals = json.load(open(os.path.join(d, CSSRS_JSON), encoding="utf-8"))
    n = n_fallback = 0
    with open(os.path.join(d, "posts.jsonl"), "w") as out:
        for batch in CSSRS_BATCHES:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # openpyxl 데이터 검증 확장 경고
                sheets = pd.read_excel(os.path.join(d, batch), sheet_name=None)
            for user, sheet in sheets.items():
                if "Suicide Risk" not in sheet.columns:  # batch 2 의 빈 Sheet1
                    continue
                posts = [_cssrs_clean(p) for p in originals[user]]
                index = {" ".join(p.split()): i for i, p in enumerate(posts)}
                for row_no, row in sheet.dropna(subset=["Reddit Post"]).iterrows():
                    text, ok = _cssrs_match(_cssrs_clean(row["Reddit Post"]), posts, index)
                    out.write(json.dumps({"user": user, "batch": batch, "xlsx_row": int(row_no) + 2, "text": text,
                                          "label": _cssrs_label(row["Suicide Risk"]), "text_from_json": ok},
                                         ensure_ascii=False) + "\n")
                    n += 1
                    n_fallback += not ok
    print(f"C-SSRS 완료: 포스트 {n}개 (원문을 못 찾아 xlsx 텍스트를 쓴 것 {n_fallback}개) → {d}/posts.jsonl")


if __name__ == "__main__":
    which = sys.argv[1:] or ["cradle", "guardrail", "cssrs"]
    for name in which:
        {"cradle": cradle, "guardrail": guardrail, "cssrs": cssrs}[name]()
