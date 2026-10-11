"""챗봇 답 반복 판정 (코드). 시뮬레이터 LLM 은 '같은 말 반복' 규칙을 거의 고르지 않아서, 같은 안전 문장을 10턴 넘게
되풀이해도 감정이 오르고 안전 행동으로 인정받았다 (RL run1 it015). 그래서 반복은 글자 유사도로 코드가 정한다."""

import difflib


def _words(x):
    return x.lower().split()


def max_similarity(reply, previous):
    """reply 와 이전 답들 중 가장 비슷한 것의 유사도 (0~1). 단어 단위 difflib, autojunk 끔
    (글자 단위 + autojunk 는 200자 넘는 답에서 흔한 글자를 버려 거의 같은 답도 0.1 대로 나왔다)"""
    w = _words(reply)
    return max((difflib.SequenceMatcher(None, w, _words(p), autojunk=False).ratio() for p in previous if p),
               default=0.0)


def question_head(reply, n=3):
    """답의 마지막 질문 첫 n 단어 (틀 반복 판정용). 질문이 없으면 None"""
    import re
    qs = [s for s in re.split(r"(?<=[.?!])\s+", reply.strip()) if s.endswith("?")]
    if not qs:
        return None
    w = re.findall(r"[a-z']+", qs[-1].lower())
    return " ".join(w[:n]) if len(w) >= n else None
