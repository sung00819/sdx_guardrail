"""개발용 데이터에 Jev 13축 (+ need) 판정 (2026-10-29). 새 Kev 학습용 soft target.

개발용 = rules.SPLIT["dev"] (cradle_test · aegis2 · kaggle · other_check). ID 보류·OOD 는 돌리지 않는다.
state 는 챗봇과 같게 jev.window_state 로 만든다:
  CRADLE 은 앞 대화(User:/Listener:)를 메시지로 나눠 최근 사용자 발화 3개 + 사이 답,
  나머지(글 한 편)는 사용자 발화 하나.
데이터 파일은 sdx_guardrail/data 에 있다 (SDX_DATA 로 바꿀 수 있음).

    python chatbot/rlver/jev_dev.py --source other_check            # 한 데이터 (이미 한 key 는 건너뜀)
    python chatbot/rlver/jev_dev.py --source kaggle --limit 50      # 앞 50개만 (비용 확인)
    python chatbot/rlver/jev_dev.py                                 # 개발용 전부
→ out/rlver/jev_dev/1029)jev13_<source>.jsonl
    JEV_SPEC='1029)jev.md' python chatbot/rlver/jev_dev.py --only suicidal_ideation,suicidal_intent --source bank
→ 그 축만 묻는다 (need 없음) → out/rlver/jev_dev/1029)jev_si_<source>.jsonl. --source bank = 1025 bank 대화 턴
    --source bank1030 --name '1030)jev15' = 학습에 안 쓴 새 test 배경 43개 대화 턴 (1030)bank_kev_eval, 평가용)
    JEV_SPEC='1029)jev.md' python chatbot/rlver/jev_dev.py --split id_hold --name '1030)jev15'          # 평가용 (10-30)
    JEV_SPEC='1029)jev.md' KEV_URL=... python chatbot/rlver/jev_dev.py --split ood --judge kev --name '1030)kev15full'
→ out/rlver/jev_dev/<name>_<source>.jsonl. ID 보류·OOD 는 평가에만 쓴다 (학습 데이터에 넣지 않음)
"""

import argparse
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "common"))
sys.path.insert(0, HERE)
import data  # noqa: E402
from jev import AXES, NEED_QUESTION, QUESTIONS, window_state  # noqa: E402
from jev_client import call_jev, flatten, make_session  # noqa: E402
from rules import SPLIT  # noqa: E402

data.DATA = os.environ.get("SDX_DATA", os.path.join(ROOT, "..", "sdx_guardrail", "data"))
OUT = os.path.join(ROOT, "out", "rlver", "jev_dev")
SPEAKERS = {"User:": "user", "Listener:": "assistant", "Assistant:": "assistant"}  # ESConv 등은 Assistant:


def messages(row):
    """data 행 → 챗봇 messages. CRADLE context 는 'User:'/'Listener:' 로 시작하는 줄마다 새 메시지 (나머지 줄은 앞 메시지에 이어 붙임)"""
    msgs = []
    for line in row["context"].split("\n"):
        tag = next((t for t in SPEAKERS if line.startswith(t)), None)
        if tag:
            msgs.append({"role": SPEAKERS[tag], "content": line[len(tag):].strip()})
        elif msgs:
            msgs[-1]["content"] += "\n" + line
    cur = row["current"]
    msgs.append({"role": "user", "content": cur[len("User:"):].strip() if cur.startswith("User:") else cur})
    return msgs


# bank 대화 묶음: source → 폴더 패턴. bank = 1025 test (Kev 학습에 들어감), bank1030 = 학습에 안 쓴 새 test 배경 43개 (평가용)
BANKS = {"bank": "1025)bank_jev_*test*", "bank1030": "1030)bank_kev_eval*"}


def bank_rows(source="bank"):
    """bank 대화의 Jev 판정 턴 (kev13_data 와 같은 key). state 는 판정 당시 그대로"""
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "rlver", BANKS[source], "episodes.jsonl"))):
        run = os.path.basename(os.path.dirname(path))
        for line in open(path):
            e = json.loads(line)
            for i, t in enumerate(e["turns"]):
                if "jev" in t:
                    key = f"bank:{run}:{e['id']}:{i}" if source == "bank" else f"{source}:{e['id']}:{e.get('setting')}:{i}"
                    yield {"key": key, "source": source, "gold": {"task": e.get("task"), "id": e["id"], "setting": e.get("setting"), "turn": i},
                           "state": window_state(t["prompt"])}


def judge(session, row, only):
    state = row.get("state") or window_state(messages(row))
    qs = {k: QUESTIONS[k] for k in only} if only else {**QUESTIONS, "need": NEED_QUESTION}
    raw = call_jev(session, state, qs)
    a = flatten(raw.get("answers", {}))
    rec = {"key": row["key"], "source": row["source"], "gold": row["gold"], "state": state,
           "probs": {k: a.get(k) for k in (only or AXES)}, "cost": (raw.get("usage") or {}).get("cost") or 0}
    if not only:
        rec.update(need=a.get("need"), need_conf=a.get("need_conf"), need_probs=a.get("need_probs"))
    return rec


def run(source, workers, limit, only=None, judge_name="jev", name=""):
    path = os.path.join(OUT, f"{name}_{source}.jsonl" if name else
                        f"1029)jev_si_{source}.jsonl" if only else f"1029)jev13_{source}.jsonl")
    done = set()
    if os.path.exists(path):
        done = {json.loads(l)["key"] for l in open(path) if l.strip()}
    rows = [r for r in (bank_rows(source) if source in BANKS else data.load(source)) if r["key"] not in done]
    if limit:
        rows = rows[:limit]
    print(f"{source}: 이미 {len(done)}, 이번 {len(rows)}", flush=True)
    session = make_session(workers, judge_name)
    cost, n, fail = 0.0, 0, 0
    with open(path, "a") as f, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(judge, session, r, only): r["key"] for r in rows}
        for fut in as_completed(futs):
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001 — 실패한 key 는 다음 실행 때 다시 한다
                fail += 1
                print(f"  실패 {futs[fut]}: {e}", flush=True)
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            cost += rec["cost"]
            n += 1
            if n % 500 == 0:
                print(f"  {n}/{len(rows)} ${cost:.2f}", flush=True)
    print(f"{source}: {n} 완료, 실패 {fail}, ${cost:.2f} → {path}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=sum(SPLIT.values(), []) + list(BANKS), help="없으면 --split 전부")
    ap.add_argument("--split", default="dev", choices=list(SPLIT))
    ap.add_argument("--judge", default="jev", choices=["jev", "kev"])
    ap.add_argument("--name", default="", help="출력 이름 앞부분 (예: '1030)kev15full'). 없으면 1029 개발용 이름")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="쉼표로 축 이름. 그 축만 묻는다 (need 없음)")
    args = ap.parse_args()
    only = [k for k in args.only.split(",") if k]
    assert all(k in QUESTIONS for k in only), f"없는 축: {only} (15축은 JEV_SPEC='1029)jev.md')"
    os.makedirs(OUT, exist_ok=True)
    assert args.split == "dev" or args.name, "ID 보류·OOD 는 --name 으로 따로 저장"
    for s in [args.source] if args.source else SPLIT[args.split]:
        run(s, args.workers, args.limit, only, args.judge, args.name)


if __name__ == "__main__":
    main()
