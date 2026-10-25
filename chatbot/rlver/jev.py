"""Jev 13축 판정 (2026-10-25, 질문 정본: 1025)jev.md). 사용자 최근 발화 3개를 묶어 축마다 P(예)를 받는다.
원하는 대응 방식(need, 선택형)도 같은 호출로 묻는다 (judge).

질문 문구는 1025)jev.md 의 영어 (**Q.** / **Yes** / **No**) 를 그대로 읽어 쓴다. 문구를 바꾸려면 md 만 고친다.
state: current = 사용자 최근 발화 3개 (번호 붙여), context = 그 구간의 대화 (사이 챗봇 답이 무엇에 대한 대답인지 보이게).
판정기: jev (OpenRouter) · kev (54번 서버) · clm, ../../common/jev_client.py.

    python chatbot/rlver/jev.py --show                                   # 묻는 질문 확인
    python chatbot/rlver/jev.py "I wrote a letter to my daughter." "it's in my drawer"   # 한 번 판정
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
from jev_client import call_jev, flatten, make_session  # noqa: E402

SPEC = os.path.join(HERE, "1025)jev.md")
WINDOW = 3  # 판정 단위: 사용자 최근 발화 수 (10-25 사용자 결정)
SELF_AXES = {"obtain_means", "suicide_note", "put_affairs_in_order", "specific_plan", "cannot_stay_safe",
             "means_access", "method"}  # [1–4, 7–9번 뒤] 자살 관련 공통 지시


def _common(md, tag):
    """**[tag]** 다음 첫 인용 줄 (영어)"""
    m = re.search(re.escape(f"**[{tag}]**") + r"\s*\n> (.+)", md)
    assert m, f"1025)jev.md 에 공통 지시 [{tag}] 가 없음"
    return m.group(1).strip()


def load_questions(path=SPEC):
    md = open(path).read()
    pre, post = _common(md, "모든 질문 앞"), _common(md, "모든 질문 뒤")
    self_note = _common(md, "1–4, 7–9번 뒤: 자살 관련 질문")
    qs = {}
    for m in re.finditer(r"^## \d+\. (\w+) — .+?$(.+?)(?=^## |\Z)", md, re.M | re.S):
        key, body = m.group(1), m.group(2)
        grab = {t: re.search(rf"^> \*\*{re.escape(t)}\*\* (.+)$", body, re.M) for t in ("Q.", "Yes", "No")}
        assert all(grab.values()), f"{key}: Q./Yes/No 중 빠진 것이 있음"
        tail = post + (" " + self_note if key in SELF_AXES else "")
        qs[key] = {"type": "noul", "instructions": f"{pre} {grab['Q.'].group(1).strip()} {tail}",
                   "criteria": {"true": grab["Yes"].group(1).strip(), "false": grab["No"].group(1).strip()}}
    return qs


NEED_KEYS = ["listen_vent", "deep_empathy", "practical_advice", "unclear"]
NEED_CONF = 0.9  # 선택형은 신뢰도 0.9 이상일 때만 인정 (docx)


def load_need(path=SPEC):
    """'## 원하는 대응 방식 — need (선택형)' 절 → Jev choice 질문"""
    md = open(path).read()
    body = re.search(r"^## 원하는 대응 방식 — need.+?$(.+?)(?=^## |\Z)", md, re.M | re.S).group(1)
    pre, post = _common(md, "모든 질문 앞"), _common(md, "모든 질문 뒤")
    q = re.search(r"^> \*\*Q\.\*\* (.+)$", body, re.M).group(1).strip()
    crit = {k: re.search(rf"^> \*\*{k}\*\* (.+)$", body, re.M).group(1).strip() for k in NEED_KEYS}
    return {"type": "choice", "instructions": f"{pre} {q} {post}", "criteria": crit}


QUESTIONS = load_questions()
AXES = list(QUESTIONS)
assert len(AXES) == 13, AXES
NEED_QUESTION = load_need()


def window_state(messages, window=WINDOW):
    """챗봇 messages (system/user/assistant) → Jev state. 최근 사용자 발화 window 개와 그 사이 답"""
    talk = [m for m in messages if m["role"] in ("user", "assistant")]
    idx = [i for i, m in enumerate(talk) if m["role"] == "user"][-window:]
    if not idx:
        return {"context": "", "current": ""}
    span = talk[idx[0]:]
    context = "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in span)
    current = "\n".join(f"User message {n}: {talk[i]['content']}" for n, i in enumerate(idx, 1))
    return {"context": context, "current": current}


class Jev:
    def __init__(self, judge="jev", workers=8):
        self.session = make_session(workers, judge)
        self.judge_name = judge
        self.cost = 0.0

    def probs(self, messages, window=WINDOW):
        """→ {축: P(예)}"""
        return self.judge(messages, window, need=False)[0]

    def judge(self, messages, window=WINDOW, need=True):
        """→ ({축: P(예)}, 원하는 방식 또는 None). 방식은 신뢰도 NEED_CONF 이상이고 unclear 가 아닐 때만"""
        qs = {**QUESTIONS, "need": NEED_QUESTION} if need else QUESTIONS
        raw = call_jev(self.session, window_state(messages, window), qs)
        self.cost += (raw.get("usage") or {}).get("cost") or 0
        a = flatten(raw.get("answers", {}))
        probs = {k: float(a.get(k) or 0.0) for k in AXES}
        choice = a.get("need") if need and (a.get("need_conf") or 0) >= NEED_CONF and a.get("need") != "unclear" else None
        return probs, choice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texts", nargs="*", help="사용자 발화 (여러 개면 순서대로, 사이 챗봇 답은 '...')")
    ap.add_argument("--judge", default="jev", choices=["jev", "kev", "clm"])
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show or not args.texts:
        print(json.dumps(QUESTIONS, ensure_ascii=False, indent=1))
        return
    msgs = []
    for t in args.texts:
        msgs += [{"role": "user", "content": t}, {"role": "assistant", "content": "..."}]
    j = Jev(args.judge)
    p = j.probs(msgs[:-1])
    for k, v in p.items():
        print(f"  {k:<24} {v:.2f}{'  ●' if v >= 0.7 else ''}")
    print(f"비용 ${j.cost:.4f}")


if __name__ == "__main__":
    main()
