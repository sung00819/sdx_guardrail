"""Kev 답을 규칙에 넣기 전에 고치는 방법들. 다시 호출하지 않고 저장된 확률만 바꾼다.

Kev 서버는 보정 온도 T(2.19)로 나눈 확률을 돌려준다 (Jev 는 거의 0/1). 확률을 p^T 로 다시 정규화하면
온도 1(학습한 그대로)의 확률이 된다. score 는 단계별 확률의 가중평균, choice 는 가장 높은 답으로 다시 낸다.

    sharpen(a, t)   발화 하나의 flatten 답 a 를 온도 t 만큼 날카롭게
"""

KEV_TEMPERATURE = 2.193649959389252  # 54번 Kev-9B 서버 /v1/models 의 temperature


def _norm(d):
    s = sum(d.values())
    return {k: v / s for k, v in d.items()} if s else d


def sharpen(a, t=KEV_TEMPERATURE):
    out = dict(a)
    for key, probs in a.items():
        if not key.endswith("_probs") or not isinstance(probs, dict):
            continue
        q = key[:-len("_probs")]
        p = _norm({k: float(v) ** t for k, v in probs.items()})
        out[key] = p
        if all(k.lstrip("-").isdigit() for k in p):  # score: 가중평균
            out[q] = sum(int(k) * v for k, v in p.items())
        else:  # choice: 가장 높은 답
            out[q] = max(p, key=p.get)
        top = max(p.values())
        rest = [v for v in p.values() if v != top] or [0]
        out[f"{q}_conf"] = top - sum(rest) / len(rest)
    for q, v in a.items():  # noul: '예' 확률
        if f"{q}_probs" not in a and isinstance(v, float) and not q.endswith("_conf") and 0 <= v <= 1:
            y, n = v ** t, (1 - v) ** t
            out[q] = y / (y + n) if y + n else v
    return out
