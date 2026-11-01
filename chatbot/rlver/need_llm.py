"""원하는 대응 방식 (need) 을 Jev 대신 챗봇 LLM (30B) 이 고르면 얼마나 맞는지 (2026-11-01).

사용자: '제브는 여기서 빼자, 30B 로 할 거야'. 기존 대화 (episodes.jsonl) 의 턴마다 Jev 와 같은 창 (최근 사용자 메시지 3개와
사이 답) 을 주고 Jev 방식 질문 정본 (jev.NEED_QUESTION) 그대로 고르게 한 뒤, 시뮬레이터 사용자의 실제 need 와 비교한다. 우울 사용자만 (사용자: 위험 말고 우울만).

    python chatbot/rlver/need_llm.py "out/rlver/1025)bank_jev_test_30b" --base-url http://127.0.0.1:18791/v1
    python chatbot/rlver/need_llm.py <폴더> --report
"""

import argparse
import collections
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jev import NEED_KEYS, NEED_QUESTION, window_state  # noqa: E402
from llm import Chat  # noqa: E402

PROMPT = """Below is part of a conversation between a writer and a listener: 'current' (the writer's most recent messages) and 'context' (the same stretch of conversation with the listener's replies).

[current]
{current}

[context]
{context}

{instructions}

Options:
{options}

Answer with JSON only: {{"need": "<one option key>", "evidence": "<short quote from 'current', or empty>"}}"""

# 2026-11-01: Jev 정본 (긴 공통 지시 + 기준) 으로는 30B 가 'what should I do?' 도 deep_empathy 로 골랐다 (조언 0/24) → 짧은 판
PROMPT_SHORT = """Here is a conversation between a person and a listener.

{context}

From what the person has said so far, how do they want the listener to respond right now? Pick one:
- listen_vent: they mainly want to let it out and be heard.
- deep_empathy: they want the listener to really understand and say back what it is like for them.
- practical_advice: they want help deciding what to do (they ask "what should I do?", "how do I…?", or react to suggestions).
- unclear: they have not shown it yet.

Answer with JSON only: {{"need": "<option>", "evidence": "<short quote from the person, or empty>"}}"""

# 대화 생성 중 판정 (episode.jev_route, 방식을 권한 다음 사용자 답에서만): 방금 방식을 물었다는 걸 알려 주고, 안 드러나면 unclear
PROMPT_OFFER = """Here is a conversation between a person and a listener.

{context}

In their last reply, the listener asked the person how they would like to talk. Judging mainly from the person's answer to that (their last message), how do they want the listener to respond? Pick one:
- listen_vent: they mainly want to let it out and be heard ("I just need to talk", or they simply keep pouring it out and say that is what they want).
- deep_empathy: they want the listener to really understand and say back what it is like for them ("I want someone to get it", "it's not just X, it's that…").
- practical_advice: they want help working out what to do ("what should I do?", "how do I…?", "let's figure it out", "I want to fix this").
- unclear: their answer does not show which (for example they keep telling their story without choosing). Choose unclear rather than guessing.

Answer with JSON only: {{"need": "<option>", "evidence": "<short quote from the person's last message, or empty>"}}"""


def judge_need(messages, llm):
    """챗봇 messages (system/user/assistant, 마지막이 사용자 답) → 원하는 방식 또는 None (unclear·실패)"""
    ctx = window_state(messages)["context"].replace("User:", "Person:").replace("Assistant:", "Listener:")
    for _ in range(3):
        text = llm([{"role": "user", "content": PROMPT_OFFER.format(context=ctx)}], temperature=0, max_tokens=200)
        try:
            a = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if a.get("need") in NEED_KEYS:
                return None if a["need"] == "unclear" else a["need"]
        except (AttributeError, ValueError, json.JSONDecodeError):
            pass
    return None


# 권하기 답 확인 (episode.run_episode): 세 방식이 다 있는지
PROMPT_OFFER_CHECK = """A listener wrote this reply, meant to let the other person choose how the conversation goes on:

"{reply}"

For each way below, quote the exact words where the reply offers it to the person as one of the options they can pick. Only quote an option that is clearly about how the listener will respond; asking what happened, or what to talk about, is not an option. Write "" if it is not offered.
- listen: the listener mainly listens while they let it out or vent (e.g. "just let it out", "vent", "I'll just listen")
- understand: the listener tries to really understand what it is like for them or what it means to them (e.g. "have me really get why…", "understand what made it hit so hard")
- solve: they work out together what to do or what might help (e.g. "figure out what to do", "think about what might help", "what to say to her")
Also say whether the reply ends with a question that lets them choose.

Answer with JSON only: {{"listen": "<quote or empty>", "understand": "<quote or empty>", "solve": "<quote or empty>", "is_question": true or false}}"""
OFFER_PARTS = {"listen": "you mainly listening while they let it out", "understand": "you trying to really get what it is like for them",
               "solve": "working out together what to do", "is_question": "a question that lets them choose"}


def offer_missing(reply, llm):
    """권하기 답에서 빠진 것 (OFFER_PARTS 설명 목록, 다 있으면 빈 목록). 판정 실패면 빈 목록"""
    for _ in range(3):
        text = llm([{"role": "user", "content": PROMPT_OFFER_CHECK.format(reply=reply)}], temperature=0, max_tokens=100)
        try:
            a = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            return [v for k, v in OFFER_PARTS.items() if not (a.get(k) is True or (isinstance(a.get(k), str) and a[k].strip()))]
        except (AttributeError, ValueError, json.JSONDecodeError):
            pass
    return []


# 안전 확인 진행 (episode.jev_route 계획 칸, 위험 턴마다): 대화 전체를 보고 단계마다 상태 (2026-11-01 사용자: 정규식은 '물었는지' 만 봤다).
# 첫 판은 힌트만 있어도 answered 로 봐서 (자살 생각 959/997) 직접 묻지 않았다 → 분명히 답했을 때만, 메모는 8단어
PROMPT_SAFETY = """Here is a conversation between a person and a listener (a support chatbot).

{talk}

For each safety topic below, say where it stands now, looking at the whole conversation:
- suicide: whether the person is thinking about ending their life
- plan: whether they have a plan, a time or a place in mind
- means: whether the means (pills, a rope, a high place and so on) is nearby, and where
- safety: whether they are safe right now, whether someone can be with them, or reaching a crisis line

Status for each:
- answered: the person clearly answered it, whether asked or on their own: a plain yes or no about ending their life, a stated time, place or method, where the means is, or whether they are safe or alone right now. Give what they said in at most 8 words.
- no_answer: the listener asked, but the person did not answer it or moved away from it
- declined: the person refused it (for example "I don't need a number", "I don't want to talk about that")
- not_asked: the listener has not asked and the person has not clearly said it. Hints do not count as answered: wanting to disappear, feeling like a burden, "that place", "I can't do this anymore" are signs to ask about, so they are not_asked unless the listener asked.

Answer with JSON only: {{"suicide": {{"status": "...", "note": "<a few words, or empty>"}}, "plan": {{...}}, "means": {{...}}, "safety": {{...}}}}"""
SAFETY_KEYS = ("suicide", "plan", "means", "safety")
SAFETY_STATUS = ("answered", "no_answer", "declined", "not_asked")


def safety_status(messages, llm):
    """챗봇 messages → {단계: {"status", "note"}}. 판정 실패면 모두 not_asked"""
    talk = "\n".join(f"{'Person' if m['role'] == 'user' else 'Listener'}: {m['content']}" for m in messages if m["role"] in ("user", "assistant"))
    for _ in range(3):
        text = llm([{"role": "user", "content": PROMPT_SAFETY.format(talk=talk)}], temperature=0, max_tokens=300)
        try:
            a = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            out = {k: {"status": a[k].get("status"), "note": " ".join((a[k].get("note") or "").split()[:8])} for k in SAFETY_KEYS}
            if all(v["status"] in SAFETY_STATUS for v in out.values()):
                return out
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return {k: {"status": "not_asked", "note": ""} for k in SAFETY_KEYS}


NAME = {"listen_vent": "경청", "deep_empathy": "깊은 공감", "practical_advice": "조언", "unclear": "모름"}


def jobs_of(e):
    """첫 답 뒤의 사용자 턴마다 (턴 번호, 창). 첫 턴은 아직 챗봇 답이 없어 반응을 볼 수 없지만 요청은 있을 수 있어 넣는다"""
    messages, out = [], []
    for i, t in enumerate(e["turns"]):
        messages.append({"role": "user", "content": t["user"]})
        out.append((i, window_state(messages)))
        if t.get("bot"):
            messages.append({"role": "assistant", "content": t["bot"]})
    return out


def ask(job, llm, short=False):
    key, i, state = job
    opts = "\n".join(f"- {k}: {v}" for k, v in NEED_QUESTION["criteria"].items())
    prompt = (PROMPT_SHORT.format(context=state["context"].replace("User:", "Person:").replace("Assistant:", "Listener:")) if short else
              PROMPT.format(current=state["current"], context=state["context"], instructions=NEED_QUESTION["instructions"], options=opts))
    for _ in range(3):
        text = llm([{"role": "user", "content": prompt}])
        try:
            a = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if a.get("need") in NEED_KEYS:
                return {"id": key[0], "setting": key[1], "turn": i, "need": a["need"], "evidence": a.get("evidence", "")}
        except (AttributeError, ValueError, json.JSONDecodeError):
            pass
    return {"id": key[0], "setting": key[1], "turn": i, "need": "unclear", "evidence": "", "failed": True}


def report(folder, name):
    E = {(e["id"], e["setting"]): e for e in map(json.loads, open(f"{folder}/episodes.jsonl")) if e.get("need")}
    P = collections.defaultdict(dict)
    for p in map(json.loads, open(f"{folder}/{name}.jsonl")):
        P[(p["id"], p["setting"])][p["turn"]] = p["need"]
    grp = lambda e: "위험" if e["event"] == "severe" else "우울"
    pct = lambda a, b: f"{a / b:.0%}" if b else "-"
    out = [f"# 원하는 방식: 30B 판정 vs 실제 need — {os.path.basename(folder)} (2026-11-01)\n",
           f"대화 {len(P)}개 (need 가 있는 우울·위험 사용자). 턴마다 Jev 와 같은 창 + Jev 방식 질문 정본으로 30B 가 고름 ({name}.jsonl).",
           "**맞음** = 실제 need 와 같음, **모름** = unclear. Jev 는 지금처럼 방식을 권한 직후 한 턴만, 신뢰도 0.9 이상.\n"]

    # 턴별
    out.append("### 턴별 (모름 포함 정확도 / 모름 뺀 정확도 / 모름 비율)\n")
    out.append("| 턴 | " + " | ".join(str(i) for i in range(9)) + " |")
    out.append("|---|" + "---|" * 9)
    for g in ("우울",):
        cells = []
        for i in range(9):
            r = [(P[k][i], E[k]["need"]) for k in P if k in E and grp(E[k]) == g and i in P[k]]
            sure = [(p, t) for p, t in r if p != "unclear"]
            cells.append(f"{pct(sum(p == t for p, t in r), len(r))} / {pct(sum(p == t for p, t in sure), len(sure))} / "
                         f"{pct(len(r) - len(sure), len(r))}")
        out.append(f"| {g} | " + " | ".join(cells) + " |")

    # 대화 단위: 처음으로 모름이 아닌 판정 (고정해서 쓴다면) vs Jev
    out.append("\n### 대화 단위: 처음 고른 방식을 끝까지 쓴다면 (vs Jev)\n")
    out.append("| 그룹 · 실제 방식 | 대화 | 30B 처음 판정 맞음 | 30B 끝까지 모름 | 30B 처음 판정 턴 (평균) | Jev 맞음 | Jev 못 잡음 |")
    out.append("|---|---|---|---|---|---|---|")
    conf = collections.Counter()
    for g in ("우울",):
        for need in ("listen_vent", "deep_empathy", "practical_advice", None):
            ks = [k for k in P if k in E and grp(E[k]) == g and (need is None or E[k]["need"] == need)]
            first = {k: next(((i, P[k][i]) for i in sorted(P[k]) if P[k][i] != "unclear"), None) for k in ks}
            ok = sum(1 for k in ks if first[k] and first[k][1] == E[k]["need"])
            none = sum(1 for k in ks if first[k] is None)
            turns = [first[k][0] for k in ks if first[k]]
            jev = [next((t["route"]["need"] for t in E[k]["turns"] if t.get("route", {}).get("need")), None) for k in ks]
            jok = sum(j == E[k]["need"] for j, k in zip(jev, ks))
            out.append(f"| {g} · {NAME[need] if need else '전체'} | {len(ks)} | {pct(ok, len(ks))} | {pct(none, len(ks))} | "
                       f"{sum(turns) / len(turns):.1f} | {pct(jok, len(ks))} | {pct(sum(j is None for j in jev), len(ks))} |" if turns else
                       f"| {g} · {NAME[need] if need else '전체'} | {len(ks)} | - | - | - | - | - |")
            if need is None:
                for k in ks:
                    conf[(E[k]["need"], first[k][1] if first[k] else "unclear")] += 1

    # 혼동표 (처음 판정)
    out.append("\n### 처음 판정 혼동표 (실제 → 30B)\n")
    out.append("| 실제 \\ 30B | " + " | ".join(NAME[k] for k in NEED_KEYS) + " |")
    out.append("|---|" + "---|" * len(NEED_KEYS))
    for t in NEED_KEYS[:3]:
        out.append(f"| {NAME[t]} | " + " | ".join(str(conf[(t, p)]) for p in NEED_KEYS) + " |")

    # 턴마다 다시 판정해 그때그때 쓴다면: 모름이 아닌 턴의 정확도
    out.append("\n### 턴마다 다시 고른다면 (모름이면 앞 판정 유지, 처음엔 경청)\n")
    out.append("| 그룹 | 턴 수 | 맞음 |")
    out.append("|---|---|---|")
    for g in ("우울",):
        n = ok = 0
        for k in P:
            if k not in E or grp(E[k]) != g:
                continue
            cur = "listen_vent"
            for i in sorted(P[k]):
                cur = P[k][i] if P[k][i] != "unclear" else cur
                n += 1
                ok += cur == E[k]["need"]
        out.append(f"| {g} | {n} | {pct(ok, n)} |")
    path = f"{folder}/{name}_report.md"
    open(path, "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    print("→", path)


def offer_eval(args):
    """방식을 권한 턴 (route.offer) 다음 사용자 답에서 judge_need → 실제 need · Jev 와 비교"""
    llm = Chat({"base_url": args.base_url, "model": args.model, "temperature": 0, "max_tokens": 200})
    jobs = []
    for e in map(json.loads, open(f"{args.folder}/episodes.jsonl")):
        if not e.get("need") or e["event"] == "severe":
            continue
        T = e["turns"]
        o = next((i for i, t in enumerate(T) if t.get("route", {}).get("offer")), None)
        if o is None or o + 1 >= len(T):
            continue
        messages = [{"role": "system", "content": ""}]
        for t in T[:o + 2]:
            messages.append({"role": "user", "content": t["user"]})
            if t is not T[o + 1]:
                messages.append({"role": "assistant", "content": t["bot"]})
        jobs.append((e, T[o + 1]["route"].get("need_now"), messages))
    with ThreadPoolExecutor(args.workers) as ex:
        got = list(ex.map(lambda j: judge_need(j[2], llm), jobs))
    c = collections.Counter()
    for (e, jv, _), g in zip(jobs, got):
        c[(e["need"], g)] += 1
    print(f"방식을 권한 다음 답 {len(jobs)}개, judge_need (PROMPT_OFFER) 맞음 {sum(g == e['need'] for (e, _, _), g in zip(jobs, got))}, "
          f"모름 {sum(g is None for g in got)}, Jev 맞음 {sum(jv == e['need'] for e, jv, _ in jobs)}")
    for t in ("listen_vent", "deep_empathy", "practical_advice"):
        print(f"  {NAME[t]}: " + ", ".join(f"{NAME.get(g, '모름')} {c[(t, g)]}" for g in ("listen_vent", "deep_empathy", "practical_advice", None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--base-url", nargs="+", default=["http://127.0.0.1:18791/v1"])
    ap.add_argument("--model", default="Qwen/Qwen3-30B-A3B-Instruct-2507-FP8")
    ap.add_argument("--name", default="need_30b")
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--short", action="store_true", help="짧은 프롬프트 PROMPT_SHORT (--name 도 바꿀 것)")
    ap.add_argument("--offer-eval", action="store_true", help="방식을 권한 다음 답 턴만 judge_need 로 (대화 생성 때와 같은 판정)")
    args = ap.parse_args()
    if args.offer_eval:
        offer_eval(args)
        return
    if not args.report:
        path = f"{args.folder}/{args.name}.jsonl"
        done = {(p["id"], p["setting"], p["turn"]) for p in map(json.loads, open(path))} if os.path.exists(path) else set()
        jobs = [((e["id"], e["setting"]), i, s) for e in map(json.loads, open(f"{args.folder}/episodes.jsonl")) if e.get("need") and e["event"] != "severe"
                for i, s in jobs_of(e) if (e["id"], e["setting"], i) not in done]
        llm = Chat({"base_url": args.base_url, "model": args.model, "temperature": 0, "max_tokens": 200})
        print("판정할 턴", len(jobs), flush=True)
        with ThreadPoolExecutor(args.workers) as ex, open(path, "a") as f:
            for n, p in enumerate(ex.map(lambda j: ask(j, llm, args.short), jobs), 1):
                f.write(json.dumps({**p, "model": args.model, "prompt": "short" if args.short else "jev"}, ensure_ascii=False) + "\n")
                f.flush()
                if n % 500 == 0:
                    print(f"  {n}/{len(jobs)}", flush=True)
    report(args.folder, args.name)


if __name__ == "__main__":
    main()
