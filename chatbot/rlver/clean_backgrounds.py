"""배경 문장 정리 (단독 실행용, 저장소 코드 없이 돌아간다). backgrounds.csv 의 core_concern·background 에서
이전 설정 문장(공개 문턱, 이전 욕구, 태도, 시작 감정)을 지우고, mild 행은 죽음 소망·자해 언급도 지운다.

    pip install requests
    export OPENROUTER_API_KEY=...          # 또는 --base_url 로 로컬 vLLM (키 없이)
    python clean_backgrounds.py backgrounds.csv backgrounds_clean.csv --limit 5   # 먼저 몇 개만
    python clean_backgrounds.py backgrounds.csv backgrounds_clean.csv             # 전부 (끊기면 같은 명령으로 이어감)

needs_clean = 1 인 행만 LLM 에 보낸다 (--all 이면 전부). 결과는 행마다 캐시(<out>.cache.jsonl)에 남긴다.
끝나면 정규식으로 남은 의심 문장 수를 다시 센다.
"""

import argparse
import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

PROMPT = """Below are two fields describing a person's situation. They will be combined later with a personality, an attitude toward helpers and a hidden intention chosen separately, so they must not contain any of those.

Remove every statement about:
- what the person wants or does not want from a listener (to be heard, to be left alone, advice, not to be judged, etc.)
- when or how they will reveal things (emotion thresholds, "after one empathic response", "only after strong trust", "before then they deflect")
- how they react to questions, pressure or the listener in general
- their starting emotion or any emotion score
Keep everything else unchanged: events, dates, numbers, people, what they tried, their feelings about the events, and the real worry itself. Do not add anything. If a sentence mixes both, keep only the situation part. core_concern must still state the real worry in at least one sentence.{extra}

# core_concern
{core_concern}

# background
{background}

# Output (JSON only)
{{"core_concern": str, "background": str}}"""

MILD = """
Also remove every mention of wishing to die, disappear or not wake up, suicide, self-harm, past attempts, or statements that they have no suicidal thoughts; keep the low mood, tiredness and self-blame."""

LEAK = re.compile(r"\b(reveal|emotion (reaches|is at least|>=|≥|of|level)|starting emotion|emotion is \d+|feels? understood|"
                  r"strong trust|only after|wants? (someone|to be|the listener|room)|partly wants|left alone|stop press|"
                  r"without trying to fix|not be judged|safe to (say|tell|disclose)|deflect)", re.I)
DEATH = re.compile(r"\b(die|dying|death|suicid\w*|self-harm|hurt (him|her)self|harm(ing)? (him|her)self|disappear|"
                   r"stop existing|not wake up)", re.I)


def suspicious(row):
    text = row["core_concern"] + " " + row["background"]
    return bool(LEAK.search(text) or (row["event"] == "mild" and DEATH.search(text)))


def call(args, prompt):
    headers = {"Authorization": f"Bearer {args.key}"} if args.key else {}
    body = {"model": args.model, "temperature": 0.2, "max_tokens": 3000,
            "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(5):
        try:
            r = requests.post(args.base_url.rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=300)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"] or ""
            if r.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        except requests.exceptions.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError("retries exhausted")


def clean(args, row):
    prompt = PROMPT.format(core_concern=row["core_concern"], background=row["background"],
                           extra=MILD if row["event"] == "mild" else "")
    for _ in range(3):
        text = re.sub(r"<think>.*?</think>", "", call(args, prompt), flags=re.S)
        try:
            got = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except (AttributeError, json.JSONDecodeError):
            continue
        cc, bg = (got.get("core_concern") or "").strip(), (got.get("background") or "").strip()
        if cc and len(bg) > 0.4 * len(row["background"]):  # 배경을 통째로 날리면 다시
            return {"id": row["id"], "core_concern": cc, "background": bg}
    raise ValueError(f"{row['id']}: 정리 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--base_url", default="https://openrouter.ai/api/v1")
    ap.add_argument("--model", default="deepseek/deepseek-chat-v3-0324")
    ap.add_argument("--key", default=os.environ.get("OPENROUTER_API_KEY"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 n 행만 (시험)")
    ap.add_argument("--all", action="store_true", help="needs_clean 과 상관없이 전부")
    args = ap.parse_args()

    csv.field_size_limit(10 ** 9)
    rows = list(csv.DictReader(open(args.src, encoding="utf-8-sig")))
    fields = list(rows[0].keys())
    cache_path = args.out + ".cache.jsonl"
    done = {}
    if os.path.exists(cache_path):
        for line in open(cache_path, encoding="utf-8"):
            r = json.loads(line)
            done[r["id"]] = r
    target = [r for r in rows if args.all or str(r.get("needs_clean", "1")) == "1"]
    if args.limit:
        target = target[:args.limit]
    todo = [r for r in target if r["id"] not in done]
    print(f"{len(rows)}행 중 정리 대상 {len(target)}, 새로 보낼 것 {len(todo)}")

    fails = []
    with open(cache_path, "a", encoding="utf-8") as cache, ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(clean, args, r): r["id"] for r in todo}
        for i, fu in enumerate(futs, 1):
            try:
                res = fu.result()
            except Exception as e:  # noqa: BLE001
                fails.append(futs[fu])
                print("  실패", futs[fu], e)
                continue
            done[res["id"]] = res
            cache.write(json.dumps(res, ensure_ascii=False) + "\n")
            cache.flush()
            if i % 20 == 0:
                print(f"  {i}/{len(todo)}")

    for r in rows:
        if r["id"] in done:
            r["core_concern"], r["background"] = done[r["id"]]["core_concern"], done[r["id"]]["background"]
            r["needs_clean"] = "0"
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    left = [r["id"] for r in rows if r["id"] in done and suspicious(r)]
    print(f"→ {args.out}  정리 {len(done)} · 실패 {len(fails)} · 정리 뒤에도 의심 문장이 남은 행 {len(left)}")
    if left:
        print("  직접 확인:", ", ".join(left[:30]) + (" ..." if len(left) > 30 else ""))


if __name__ == "__main__":
    main()
