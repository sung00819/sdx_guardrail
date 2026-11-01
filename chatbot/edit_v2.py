"""v1 배경 → v2 (PERSONA_V2.md): 다시 생성하지 않고 문제 문장만 고친다 (서버 Qwen3-30B, 무료).

v1 배경에는 숨겨진 욕구가 "듣는 사람에게 무엇을 원하는지" 문장으로 들어가 있다 (핵심 고통의 75%,
예: "He needs one concrete next step for tonight", "wants to be heard without being rushed toward a fix").
공개 규칙도 본문에 들어가 있다 ("will not bring it up until he feels understood (emotion >= 60)").
안전 확인 반응에는 감정 숫자 문턱이 들어가 있다 (573/750).

방식: 코드가 문장을 번호로 나눈다. 문장 조립도 코드가 한다 (시험: 지울 문자열을 모델이 고르게 하면 대소문자가
안 맞거나 핵심 고통 전체를 지웠다).
- W (배경·핵심 고통 문장): 모델이 keep / delete / edit. delete 는 '듣는 사람에게 원하는 것'만으로 된 문장뿐,
  두려움·걱정이 든 문장은 edit 만 (시험: 두려움 문장을 지워 핵심 고통이 공개 규칙 한 줄만 남은 경우).
- T (감정 숫자 문턱이 든 문장, 세 필드 모두): 정규식으로 고르고 모델은 숫자 없이 다시 쓰기만. 지우지 않는다.
- 안전 확인 반응은 T 문장 말고는 손대지 않는다 (시험: 통째로 지운 경우). 숫자 없는 공개 시점 문장은 둔다.
나머지 필드는 그대로. seed 에서 hidden_need, scene 에서 emotion_rises_when/falls_when 을 뺀다.
핵심 고통이 40% 미만으로 줄면 표시한다 (edit.core_short). 결과는 이어 쓴다.

  python edit_v2.py --inp scenes_train.jsonl --out v2_scenes_train.jsonl --urls http://127.0.0.1:18611/v1,... --workers 32
"""

import argparse
import itertools
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507-FP8"
FIELDS = ("background", "core_concern", "safety_check_reaction")

PROMPT = """You are reviewing numbered sentences from a character background for a simulated user who will talk
to a support chatbot.

Part 1 (sentences marked W): for EACH, decide "keep", "delete", or "edit".
 delete ONLY if the whole sentence is about what this person wants, needs, or hopes FROM THE LISTENER / CHATBOT /
   A HELPER in this conversation, or what kind of response would help them. e.g. "He needs one concrete next step
   for tonight, not reassurance." "She wants someone to listen without immediately trying to fix it."
   "She wants reassurance that she can tell the truth without being judged."
 edit if the sentence ALSO contains anything else (a fact, an event, a feeling, a fear, a worry): return the
   sentence with only the wish-about-the-listener part removed. A sentence that contains a fear or worry must
   NEVER be deleted, even if it mentions the chatbot or being judged — keep or edit it.
 keep everything else: facts, events, people, feelings, fears ("she fears people will judge her", "she worries
   the chatbot will judge her too"), the hidden worry itself, wishes about people in their life ("he wants his
   parents to leave him alone tonight"), and statements about when they will open up.

Part 2 (sentences marked T): each mentions an emotion number or threshold. Rewrite it with the number/threshold
 replaced by wording about trust ("before they come to trust the listener", "once they feel understood").
 Change nothing else. Never drop the sentence.

{numbered}

Return JSON only:
{{"decisions": [{{"id": "W.<n>", "action": "keep" | "delete" | "edit", "text": "<edited sentence, only for edit>"}}],
  "rewrites": [{{"id": "T.<n>", "text": "<rewritten sentence>"}}]}}"""

SPLIT = re.compile(r"(?<=[.!?])[\"'”’)]?\s+(?=[A-Z\"'“‘(])")
WANT = re.compile(r"\b(wants?|needs?|hopes?|wishes)\b[^.]*\b(listen\w*|hear\w*|heard|fix\w*|advice|solution|"
                  r"step|reassur\w*|someone|listener|chatbot|help)\b", re.I)
THRESH = re.compile(r"\b(60|75)\b|threshold|emotion\s*(>=|≥|>|<|is|reaches|above|below)", re.I)


# 감정 숫자 문턱 → 믿음 표현 (코드로 바꾼다. 시험: 모델에 맡기면 원문을 그대로 돌려주는 경우가 많았다)
_EMO = r"(?:(?:his|her|their|the user's)\s+)?emotion(?:\s+level)?"
_NUM = r"(?:of\s+|is\s+|to\s+|at\s+least\s+|>=\s*|≥\s*)*\d{2}(?:\s+or\s+(?:higher|above|more))?"
DETHRESH = [
    (re.compile(r"\s*\((?:" + _EMO + r")[^)]*\)", re.I), ""),                       # (emotion >= 60)
    (re.compile(r",?\s*and\s+" + _EMO + r"\s+(?:reaches|is)\s+" + _NUM, re.I), ""),   # ... understood and her emotion reaches at least 60
    (re.compile(r"\buntil\s+" + _EMO + r"\s+reaches\s+" + _NUM, re.I), "until trust is established"),
    (re.compile(r"\b(?:only\s+)?(?:when|once)\s+trust\s+reaches\s+" + _NUM, re.I), "only once trust is established"),
    (re.compile(r"\bat\s+or\s+above\s+\d{2}\b", re.I), "once trust is established"),
    (re.compile(r"\bbefore\s+(?:emotion|(?:she|he|they)\s+reach(?:es)?)\s+\d{2}\b", re.I), "before trust is established"),
    (re.compile(r"\bafter\s+\d{2}\b", re.I), "once trust is established"),
    (re.compile(r"\b(?:before|below)\s+\d{2}\b", re.I), "before trust is established"),
    (re.compile(r"\btrust\s+reaches\s+" + _EMO + r"\s+" + _NUM, re.I), "trust is established"),
    (re.compile(r"\b(?:enough\s+)?(?:for\s+(?:her|his|their)\s+emotion\s+)?to\s+reach\s+" + _NUM, re.I), "enough to trust the listener"),
    (re.compile(r"\breaches\s+(?:emotion\s+)?" + _NUM, re.I), "trusts the listener"),
    (re.compile(r",?\s*at\s+" + _EMO + r"\s+" + _NUM, re.I), ""),                   # , at emotion 75 or higher
    (re.compile(r"\bbefore\s+(?:the\s+)?(?:reveal\s+)?threshold\b", re.I), "before trust is established"),
    (re.compile(r"\b(?:after|once|past)\s+(?:the\s+)?(?:reveal\s+)?threshold\b", re.I), "once trust is established"),
    (re.compile(r"\bbefore\s+" + _EMO + r"\s+(?:reaches|is|gets\s+to|rises\s+to)\s+" + _NUM, re.I),
     "before trust is established"),
    (re.compile(r"\b(?:once|when|after|if)\s+" + _EMO + r"\s+(?:reaches|is|gets\s+to|rises\s+to|hits)\s+" + _NUM, re.I),
     "once trust is established"),
    (re.compile(r"\b(?:at|after|above)\s+" + _EMO + r"\s+" + _NUM, re.I), "once trust is established"),
    (re.compile(r"\b(?:meets|reaches|crosses)\s+(?:(?:his|her|their)\s+)?(?:reveal\s+)?threshold\b", re.I),
     "is enough to build trust"),
    (re.compile(r"\bthat\s+crosses\s+the\s+threshold\b", re.I), "that is enough to build trust"),
    (re.compile(r"\b(?:meets|reaches|crosses)\s+the\s+(?:reveal\s+)?threshold\b", re.I), "is enough to build trust"),
    (re.compile(r"\b(?:at|from)\s+(?:60|75)\s+or\s+(?:above|higher|more)\b", re.I), "once trust is established"),
    (re.compile(r"\btrust\s+reaches\s+an?\s+" + _EMO + r"\s+" + _NUM, re.I), "trust is established"),
    (re.compile(r"\b(?:the\s+)?(?:reveal\s+)?threshold\b", re.I), "the point of trust"),  # 남은 것
]


START_EMO = re.compile(r"(starting\s+emotion|emotion\s+(?:starts|begins)\s+at|at\s+the\s+start[^.]*\bemotion\s+is|\d{2}\s*/\s*100)", re.I)


def dethreshold(text):
    if START_EMO.search(text):
        return ""
    for pat, rep in DETHRESH:
        def sub(m, rep=rep):
            if not rep:
                return rep
            return rep[0].upper() + rep[1:] if m.group(0)[:1].isupper() else rep
        text = pat.sub(sub, text)
    return re.sub(r"\s{2,}", " ", text).strip()


def sentences(text):
    return [s.strip() for s in SPLIT.split(text or "") if s.strip()]


def overlap(new, old):
    a, b = set(re.findall(r"\w+", new.lower())), set(re.findall(r"\w+", old.lower()))
    return len(a & b) / max(1, len(a))


SECOND = """This sentence comes from a hidden character background for a simulated user of a support chatbot:

"{sentence}"

Does it say what the person wants, needs, or hopes FROM A LISTENER / CHATBOT / HELPER, or what kind of response
would help them (e.g. "wants someone to recognize why...", "needs room to admit...", "wants to say it only if the
listener seems to understand")? Fears, feelings, facts, and wishes about people in their life do not count.
If it does, return the sentence with that part removed (keep any fear, feeling or fact word for word), or "" if
nothing else is left. If it does not, return it unchanged.
Return JSON only: {{"text": str}}"""


def call(url, prompt):
    r = requests.post(f"{url}/chat/completions", timeout=300, json={
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0, "max_tokens": 4000, "response_format": {"type": "json_object"}})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def edit(row, url):
    sc = row["scene"]
    sents = {k: [y for y in (dethreshold(x) for x in sentences(sc.get(k, ""))) if y] for k in FIELDS}
    n_dethresh = sum(len(sentences(sc.get(k, ""))) - len(sents[k]) +
                     sum(dethreshold(x) not in ("", x) for x in sentences(sc.get(k, ""))) for k in FIELDS)
    # 규칙으로 못 바꾼 숫자 문턱 문장(T)만 모델이 다시 쓴다. 코드가 정규식으로 고른다. 나머지 배경·핵심 고통 문장(W)만 모델이 판단
    W, T = [], []
    for k, ss in sents.items():
        for i, x in enumerate(ss):
            if THRESH.search(x):
                T.append((k, i, x))
            elif k != "safety_check_reaction":
                W.append((k, i, x))
    numbered = "\n".join(f"[W.{n}] ({k}) {x}" for n, (k, i, x) in enumerate(W))
    if not W and not T:
        out = {}
    if T:
        numbered += "\n\n" + "\n".join(f"[T.{n}] ({k}) {x}" for n, (k, i, x) in enumerate(T))
    out = call(url, PROMPT.format(numbered=numbered)) if (W or T) else {}
    dec = {d.get("id"): d for d in out.get("decisions") or [] if isinstance(d, dict)}
    rew = {d.get("id"): d.get("text") for d in out.get("rewrites") or [] if isinstance(d, dict)}
    final = {k: list(ss) for k, ss in sents.items()}  # None = 삭제
    changes = {"deleted": [], "edited": [], "rewritten": []}
    for n, (k, i, x) in enumerate(W):
        d = dec.get(f"W.{n}") or {"action": "keep"}
        if d.get("action") == "delete":
            final[k][i] = None
            changes["deleted"].append(f"[{k}] {x}")
        elif d.get("action") == "edit" and isinstance(d.get("text"), str) and d["text"].strip() and d["text"].strip() != x \
                and overlap(d["text"], x) >= 0.5:  # 시험: 다른 문장으로 바꿔 쓴 경우가 있었다
            final[k][i] = d["text"].strip()
            changes["edited"].append({"field": k, "from": x, "to": d["text"].strip()})
    for n, (k, i, x) in enumerate(T):
        t = rew.get(f"T.{n}")
        if isinstance(t, str) and t.strip():
            final[k][i] = t.strip()
            changes["rewritten"].append({"field": k, "from": x, "to": t.strip()})
    changes["second"] = []
    for k in ("background", "core_concern"):
        for i, x in enumerate(final[k]):
            if x and WANT.search(x):
                t = call(url, SECOND.format(sentence=x)).get("text")
                if isinstance(t, str) and t.strip() != x and (not t.strip() or overlap(t, x) >= 0.5):
                    final[k][i] = t.strip() or None
                    changes["second"].append({"field": k, "from": x, "to": t.strip()})
    new_sc = {k: v for k, v in sc.items() if k not in ("emotion_rises_when", "emotion_falls_when")}
    for k in FIELDS:
        new_sc[k] = " ".join(x for x in final[k] if x)
    seed = {k: v for k, v in row["seed"].items() if k != "hidden_need"}
    seed["version"] = "v2"
    left = {k: bool(WANT.search(new_sc[k])) for k in ("background", "core_concern")}
    left["threshold"] = any(bool(THRESH.search(new_sc[k])) for k in FIELDS)
    shrink = {k: round(len(new_sc[k]) / max(1, len(sc.get(k, ""))), 3) for k in FIELDS}
    return {**{k: v for k, v in row.items() if k not in ("seed", "scene")}, "seed": seed, "scene": new_sc,
            "version": "v2", "v1_hidden_need": row["seed"].get("hidden_need"),
            "edit": {"model": MODEL, **changes, "dethreshold_rule": n_dethresh, "left": left, "shrink": shrink,
                     "core_short": shrink["core_concern"] < 0.4}}


CORE = """This is the hidden core concern of a simulated user of a support chatbot (only the user knows it):

"{core}"

Rewrite it so it contains ONLY the person's underlying worry, fear, or pain, and any hidden facts in it (e.g.
suicidal thoughts, self-harm, a past attempt). Remove everything about:
- what they want, need, or hope from a listener / chatbot / helper, or what response would help them
  (e.g. "wants to be heard without being fixed", "needs a concrete step tonight", "needs to hear that her fear
  makes sense", "wants reassurance she will not be judged")
- when or after what they will open up.
If the worry is only implied by the wish (e.g. "needs to know she will not be judged for struggling"), state the
worry itself ("She is afraid people will judge her for struggling."). Reuse the original wording as much as
possible. Do not add new events or facts. 1-3 full sentences, never empty.
Return JSON only: {{"core_concern": str}}"""

FRAG = re.compile(r"^[a-z]|^\W")


def fix_core(row, v1_core, url):
    """2차: 핵심 고통만 v1 원문에서 다시 (문장 삭제로 두려움까지 지워진 경우 56/750)"""
    t = (call(url, CORE.format(core=v1_core)).get("core_concern") or "").strip()
    ok = bool(t) and not FRAG.search(t) and len(t) >= 40 and not WANT.search(t) and not THRESH.search(t)
    row["edit"]["core_fix"] = {"from_v1": v1_core, "to": t, "ok": ok, "v1_edit": row["scene"]["core_concern"]}
    if ok:
        row["scene"]["core_concern"] = t
        row["edit"]["left"]["core_concern"] = False
        row["edit"]["core_short"] = False
    return row


def needs_core_fix(row, v1_core):
    c = row["scene"]["core_concern"]
    return (bool(WANT.search(v1_core)) or bool(re.search(r"\b(needs?|wants?|hopes?)\b", v1_core, re.I))) and (
        row["edit"]["core_short"] or row["edit"]["left"]["core_concern"] or not c or FRAG.search(c) or len(c) < 40
        or c != v1_core)


def core_pass(a):
    """--core-pass: 1차 결과(--out)의 핵심 고통을 v1(--inp) 원문에서 다시 쓴다. 결과는 --out 에 덮지 않고 --core-out"""
    v1 = {json.loads(l)["id"]: json.loads(l)["scene"]["core_concern"] for l in open(a.inp) if l.strip()}
    rows = [json.loads(l) for l in open(a.out) if l.strip()]
    urls = itertools.cycle(a.urls.split(","))
    todo = [r for r in rows if needs_core_fix(r, v1[r["id"]])]
    print(f"core pass: {len(todo)}/{len(rows)}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(fix_core, r, v1[r["id"]], next(urls)) for r in todo]
        for f in as_completed(futs):
            f.result()
    with open(a.core_out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    bad = sum(1 for r in todo if not r["edit"]["core_fix"]["ok"])
    print(f"core pass done, not ok {bad}", flush=True)


BG = """This sentence comes from the hidden background of a simulated user of a support chatbot:

"{sentence}"

Remove ONLY the part that says what the person wants, needs, or hopes from a listener / chatbot / helper, or what
kind of response would help them (e.g. "wants one doable next step", "needs someone to recognize why it hurts",
"is testing whether they will listen without judging her", "wants someone to hear why it hurt, not give advice").
Keep: facts, events, feelings, fears, hidden risk facts, wishes about people in their life, and mixed feelings
about being alone (e.g. "part of him wants to be left alone"). If the sentence is a broken fragment (starts in
the middle, missing punctuation), repair it into full sentence(s) using only its own words.
Return the result (may be "" if nothing is left). Return JSON only: {{"text": str}}"""


def bg_pass(a):
    """--bg-pass: 배경에 아직 남은 원함 문장·조각 문장만 한 문장씩 다시 (core-pass 결과에서)"""
    rows = [json.loads(l) for l in open(a.core_out) if l.strip()]
    urls = itertools.cycle(a.urls.split(","))
    jobs = []
    for r in rows:
        ss = sentences(r["scene"]["background"])
        r["_ss"] = ss
        for i, x in enumerate(ss):
            if WANT.search(x) or FRAG.search(x):
                jobs.append((r, i, x))
    print(f"bg pass: {len(jobs)} sentences in {len({id(r) for r, _, _ in jobs})} rows", flush=True)

    def one(job):
        r, i, x = job
        t = (call(next(urls), BG.format(sentence=x)).get("text") or "").strip()
        if t == x or (t and overlap(t, x) < 0.5):
            return
        r["_ss"][i] = t or None
        r["edit"].setdefault("bg_fix", []).append({"from": x, "to": t})

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, jobs))
    with open(a.bg_out, "w") as f:
        for r in rows:
            r["scene"]["background"] = " ".join(x for x in r.pop("_ss") if x)
            r["edit"]["left"]["background"] = bool(WANT.search(r["scene"]["background"]))
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("bg pass done", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--urls", required=True)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--core-out", help="주면 --core-pass: --out 결과의 핵심 고통만 v1(--inp)에서 다시 써서 여기에")
    ap.add_argument("--bg-out", help="주면 --bg-pass: --core-out 결과의 배경에 남은 원함·조각 문장만 다시 써서 여기에")
    a = ap.parse_args()
    if a.bg_out:
        return bg_pass(a)
    if a.core_out:
        return core_pass(a)
    rows = [json.loads(l) for l in open(a.inp) if l.strip()][: a.limit]
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["id"] for l in open(a.out) if l.strip()}
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(done)} done, {len(todo)} to edit", flush=True)
    urls = itertools.cycle(a.urls.split(","))
    lock = threading.Lock()
    fails = 0
    with open(a.out, "a") as f, ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(edit, r, next(urls)): r["id"] for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001 — 다시 실행하면 이어서 한다
                fails += 1
                print("fail", futs[fut], str(e)[:200], flush=True)
                continue
            with lock:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print(f"finished, fails {fails}", flush=True)


if __name__ == "__main__":
    main()
