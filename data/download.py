"""평가 데이터를 data/ 아래로 받는다. 데이터 원본은 이 저장소에 올리지 않는다 (공개 저장소, 원 데이터의 배포 조건).

    python3 data/download.py              # 전부
    python3 data/download.py cradle       # CRADLE-Dialogue 만
    python3 data/download.py guardrail    # 팀 guardrail-dataset 만

  cradle     https://huggingface.co/datasets/SungJoo/Cradle-Dialogue → data/cradle/{test,validation,train}.parquet
             test 는 실제 대화 + 임상가 라벨, validation·train 은 GPT-5 합성.
  guardrail  https://github.com/yujinoh0103/guardrail-dataset (비공개 팀 저장소, 접근 권한 필요)의
             data/id-300-windows 브랜치 → data/guardrail-dataset/ (id/attunebench.jsonl 등, 데이터별 300창)
"""

import os
import subprocess
import sys

import requests

DATA = os.path.dirname(os.path.abspath(__file__))
CRADLE_URL = "https://huggingface.co/datasets/SungJoo/Cradle-Dialogue/resolve/main/data/{split}-00000-of-00001.parquet"
GUARDRAIL_REPO = "https://github.com/yujinoh0103/guardrail-dataset.git"
GUARDRAIL_BRANCH = "data/id-300-windows"


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


if __name__ == "__main__":
    which = sys.argv[1:] or ["cradle", "guardrail"]
    for name in which:
        {"cradle": cradle, "guardrail": guardrail}[name]()
