"""Jev 선택형 (2026-10-30, 질문 정본: 1030)jev_choice.md + 예/아니오 축은 1030)jev.md). 11축의 합친 위험 축을 선택형 4개로.

켜짐: '없음' 이 아닌 선택지 확률 합 ≥ 0.7 (실행 의도는 intent + imminent). 세부 항목: '없음' 아닌 선택지 중 확률 ≥ 0.3.
판정 데이터·state 는 jev11_eval 과 같다. 비교: 같은 발화의 11축 예/아니오 판정 (1030)jev11_*) 과 15축 (1029) 의 옛 세부 축.

    python chatbot/rlver/jev_choice.py --show
    python chatbot/rlver/jev_choice.py --run --source other_check   # 판정 (이미 한 key 는 건너뜀)
    python chatbot/rlver/jev_choice.py --run                        # 개발용 전부
    python chatbot/rlver/jev_choice.py                              # 채점 → chatbot/rlver/1030)jev_choice_dev_eval.md
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "common"))
sys.path.insert(0, HERE)
import jev11  # noqa: E402
import jev11_eval as E11  # noqa: E402
from compare import GROUPS, cradle_group  # noqa: E402
from jev import window_state  # noqa: E402
from jev_client import call_jev, flatten, make_session  # noqa: E402
from jev_dev import data, messages  # noqa: E402
from rules import SPLIT  # noqa: E402

SPEC = os.path.join(HERE, "1030)jev_choice.md")
OUT = E11.OUT
REPORT = os.path.join(HERE, "1030)jev_choice_dev_eval.md")
T, SUB = 0.7, 0.5  # 세부 기준 10-30 0.3 → 0.5 (0.3 은 구체적 계획을 너무 자주 고름)
CHOICES = {"suicidal_thought": ["none", "ideation", "method", "specific_plan"],
           "suicidal_intent": ["no_intent", "ambivalent", "intent", "imminent"],
           "preparatory_acts": ["none", "obtain_means", "suicide_note", "put_affairs_in_order"],
           "self_harm": ["none", "once", "repeated"]}
NOUL = ["means_access", "cannot_stay_safe", "depression"] + jev11.MOD_AXES
SELF = {"suicidal_thought", "suicidal_intent", "preparatory_acts"}  # 자살 관련 공통 지시를 붙이는 선택형


def load_questions():
    md, md11 = open(SPEC).read(), open(jev11.SPEC).read()
    pre, post = jev11._common(md11, "모든 질문 앞"), jev11._common(md11, "모든 질문 뒤")
    self_note = jev11._common(md11, r"1–5, 7번 뒤: 자살 관련 질문")
    qs = {}
    for m in re.finditer(r"^## \d+\. (\w+) — .+?$(.+?)(?=^## |\Z)", md, re.M | re.S):
        key, body = m.group(1), m.group(2)
        q = re.search(r"^> \*\*Q\.\*\* (.+)$", body, re.M).group(1).strip()
        crit = {o: re.search(rf"^> \*\*{o}\*\* (.+)$", body, re.M).group(1).strip() for o in CHOICES[key]}
        tail = post + (" " + self_note if key in SELF else "")
        qs[key] = {"type": "choice", "instructions": f"{pre} {q} {tail}", "criteria": crit}
    assert list(qs) == list(CHOICES), list(qs)
    return {**qs, **{k: jev11.QUESTIONS[k] for k in NOUL}}


QUESTIONS = load_questions()


def judge(session, state):
    """state → ({선택형: {선택지: 확률}, 예/아니오: P(예)}, cost)"""
    raw = call_jev(session, state, QUESTIONS)
    a = flatten(raw.get("answers", {}))
    probs = {k: (a.get(f"{k}_probs") or {}) for k in CHOICES}
    probs.update({k: a.get(k) for k in NOUL})
    return probs, (raw.get("usage") or {}).get("cost") or 0


# ---------- 켜짐·세부 ----------

def none_key(k):
    return CHOICES[k][0]


def on(p, k):
    """선택형: '없음' 아닌 확률 합 ≥ T (실행 의도는 intent + imminent), 예/아니오: P(예) ≥ T"""
    if k == "suicidal_intent":
        d = p[k] or {}
        return (d.get("intent") or 0) + (d.get("imminent") or 0) >= T
    if k in CHOICES:
        d = p[k] or {}
        return bool(d) and 1 - (d.get(none_key(k)) or 0) >= T
    return (p.get(k) or 0) >= T


def subs(p, k, sub=None):
    """세부 항목: 켜졌을 때 '없음' 아닌 선택지 중 확률 ≥ SUB"""
    if not on(p, k):
        return []
    return [o for o in CHOICES[k][1:] if (p[k].get(o) or 0) >= (sub or SUB)]


RISK = list(CHOICES) + ["means_access", "cannot_stay_safe"]


def route(p):
    if any(on(p, k) for k in RISK):
        return "가드레일"
    return "정서 지원" if on(p, "depression") else "일반 대화"


# ---------- 판정 ----------

def path(source):
    return os.path.join(OUT, f"1030)jev_choice_{source}.jsonl")


def run(source, workers, limit):
    done = {json.loads(l)["key"] for l in open(path(source)) if l.strip()} if os.path.exists(path(source)) else set()
    rows = [r for r in data.load(source) if r["key"] not in done][: limit or None]
    print(f"{source}: 이미 {len(done)}, 이번 {len(rows)}", flush=True)
    session = make_session(workers)

    def one(row):
        state = window_state(messages(row))
        probs, cost = judge(session, state)
        assert all(probs[k] for k in CHOICES), "선택형 확률이 비어 있음"
        return {"key": row["key"], "source": source, "gold": row["gold"], "state": state, "probs": probs, "cost": cost}

    cost, n, fail = 0.0, 0, 0
    with open(path(source), "a") as f, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(one, r): r["key"] for r in rows}
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
    print(f"{source}: {n} 완료, 실패 {fail}, ${cost:.2f} → {path(source)}", flush=True)


# ---------- 채점 ----------

def load(source):
    """선택형 판정 + 같은 key 의 11축 (y11) · 15축 옛 축 (p15)"""
    R = [json.loads(l) for l in open(path(source))]
    y11 = {r["key"]: r["probs"] for r in E11.load(source)}
    p15 = {r["key"]: r["probs"] for r in map(json.loads, open(os.path.join(OUT, f"1029)jev13_{source}.jsonl")))}
    for r in R:
        r["y11"] = y11.get(r["key"])
        r["p15"] = p15.get(r["key"])
    return R


def pct(a, n):
    return f"{100 * a / n:.0f}% ({a})" if n else "-"


ROUTES = ["가드레일", "정서 지원", "일반 대화"]
ROUTE_HEAD = ["| 그룹 | n | 가드레일 | 정서 지원 | 일반 대화 | 11축 가드레일 |", "|---|---|---|---|---|---|"]


def route_row(name, R):
    c = Counter(route(r["probs"]) for r in R)
    y = [r for r in R if r["y11"]]
    return (f"| {name} | {len(R)} | " + " | ".join(pct(c[x], len(R)) for x in ROUTES)
            + f" | {pct(sum(E11.route(r['y11']) == '가드레일' for r in y), len(y))} |")


# 선택형 켜짐 ↔ 11축 예/아니오 대응
PAIRS = [("자살 사고 (선택형 켜짐 ↔ 11축 사고 또는 방법·계획)", lambda p: on(p, "suicidal_thought"),
          lambda y: E11.on(y, "suicidal_ideation") or E11.on(y, "suicide_plan")),
         ("방법·계획 (method + specific_plan ≥ 0.7 ↔ 11축 2번)",
          lambda p: (p["suicidal_thought"].get("method") or 0) + (p["suicidal_thought"].get("specific_plan") or 0) >= T,
          lambda y: E11.on(y, "suicide_plan")),
         ("실행 의도 (intent + imminent ↔ 11축 3번)", lambda p: on(p, "suicidal_intent"), lambda y: E11.on(y, "suicidal_intent")),
         ("준비 행동", lambda p: on(p, "preparatory_acts"), lambda y: E11.on(y, "preparatory_acts")),
         ("자해", lambda p: on(p, "self_harm"), lambda y: E11.on(y, "self_harm"))]

# 세부 항목 ↔ 15축 옛 세부 축
SUBPAIRS = [("구체적 계획", "suicidal_thought", "specific_plan", "specific_plan"),
            ("방법 고려", "suicidal_thought", "method", "method"),
            ("수단 마련", "preparatory_acts", "obtain_means", "obtain_means"),
            ("유서", "preparatory_acts", "suicide_note", "suicide_note"),
            ("신변 정리", "preparatory_acts", "put_affairs_in_order", "put_affairs_in_order"),
            ("반복 자해", "self_harm", "repeated", "repeated_self_harm")]


def agree_table(R):
    R = [r for r in R if r["y11"]]
    lines = ["| 축 | 선택형 켜짐 | 11축 예 | 일치 | 선택형만 | 11축만 |", "|---|---|---|---|---|---|"]
    for name, f, g in PAIRS:
        a, b = [f(r["probs"]) for r in R], [g(r["y11"]) for r in R]
        lines.append(f"| {name} | {sum(a)} | {sum(b)} | {100 * sum(x == y for x, y in zip(a, b)) / len(R):.1f}% "
                     f"| {sum(x and not y for x, y in zip(a, b))} | {sum(y and not x for x, y in zip(a, b))} |")
    return lines


def sub_table(R):
    """15축 옛 세부 축이 예인 발화를 선택형 세부가 얼마나 다시 찾는지 (재현), 선택형 세부가 고른 것 중 15축도 예인 비율 (정밀)"""
    R = [r for r in R if r["p15"]]
    lines = ["| 세부 | 15축 예 | 기준 | 선택형 세부 | 둘 다 | 재현 | 정밀 |", "|---|---|---|---|---|---|---|"]
    for name, k, opt, old in SUBPAIRS:
        b = [(r["p15"].get(old) or 0) >= T for r in R]
        for sub in (0.3, SUB):
            a = [opt in subs(r["probs"], k, sub) for r in R]
            both = sum(x and y for x, y in zip(a, b))
            lines.append(f"| {name} | {sum(b)} | {sub} | {sum(a)} | {both} | {pct(both, sum(b))} | {pct(both, sum(a))} |")
    return lines


def dist_table(R):
    """선택형마다 가장 높은 선택지 분포 (켜진 발화만)"""
    lines = ["| 선택형 | 켜짐 | 가장 높은 선택지 (켜진 발화) | 세부 2개 이상 |", "|---|---|---|---|"]
    for k, opts in CHOICES.items():
        rs = [r for r in R if on(r["probs"], k)]
        top = Counter(max(opts[1:], key=lambda o: r["probs"][k].get(o) or 0) for r in rs)
        multi = sum(len(subs(r["probs"], k)) >= 2 for r in rs)
        lines.append(f"| {k} | {len(rs)} | " + ", ".join(f"{o} {c}" for o, c in top.most_common()) + f" | {multi} |")
    amb = sum((r["probs"]["suicidal_intent"].get("ambivalent") or 0) >= 0.5 for r in R)
    lines.append(f"\n실행 의도 ambivalent ≥ 0.5 (켜지지 않음, 결정 11): {amb}개")
    return lines


def examples(R, f, g, k=6):
    out = []
    for r in [r for r in R if r["y11"] and f(r["probs"]) and not g(r["y11"])][:k]:
        cur = r["state"]["current"].split("\n")[-1].split(": ", 1)[-1].replace("|", "/").replace("\n", " ")[:200]
        out.append(f"  - `{r['key']}` — {cur}")
    return out


def report():
    out = ["# Jev 선택형 × 개발용 데이터 채점, 11축 예/아니오와 비교 (2026-10-30)", "",
           "선택형 = `1030)jev_choice.md` (위험 축 1·2·3·4·6 → 선택형 4개, 나머지는 `1030)jev.md` 예/아니오). "
           "켜짐 = '없음' 아닌 확률 합 ≥ 0.7 (실행 의도는 intent + imminent), 세부 = 확률 ≥ 0.5 (표에는 0.3 도 함께). "
           "비교: 같은 발화의 11축 예/아니오 (`1030)jev11_*`), 세부는 15축 옛 축 (`1029)*`).", ""]
    allR, cost = [], 0.0

    R = load("cradle_test")
    allR += R
    cradle_group(R)
    by = defaultdict(list)
    for r in R:
        by[r["group"]].append(r)
    out += ["## CRADLE test (4,527 발화)", ""] + ROUTE_HEAD + [route_row(g, by[g]) for g in GROUPS if by[g]]
    crisis = [r for g in GROUPS[:4] for r in by[g]]
    miss = [r for r in crisis if route(r["probs"]) == "일반 대화"]
    out += ["", f"- 위기 그룹 {len(crisis)} 발화 중 일반 대화로 감 (놓침): 선택형 {pct(len(miss), len(crisis))}, "
            f"11축 {pct(sum(E11.route(r['y11']) == '일반 대화' for r in crisis if r['y11']), len(crisis))}."]
    for r in miss[:10]:
        cur = r["state"]["current"].split("\n")[-1].replace("|", "/")[:180]
        out.append(f"  - `{r['key']}` {r['group']} — {cur}")

    R = load("aegis2")
    allR += R
    out += ["", "## Aegis 2.0 (1,928개)", ""] + ROUTE_HEAD
    out += [route_row("자해 라벨 있음", [r for r in R if r["gold"]["self_harm"]]),
            route_row("자해 라벨 없음", [r for r in R if not r["gold"]["self_harm"]])]

    R = load("kaggle")
    allR += R
    out += ["", "## Kaggle Reddit (15,477개, 참고용)", ""] + ROUTE_HEAD
    out += [route_row("Suicidal", [r for r in R if r["gold"]["orig_label"] == "Suicidal"]),
            route_row("Non-Suicidal", [r for r in R if r["gold"]["orig_label"] != "Suicidal"])]

    R = load("other_check")
    allR += R
    out += ["", "## 남 이야기 확인 10개", "", "| no | 기대 | 선택형 | 11축 | 글 |", "|---|---|---|---|---|"]
    for r in sorted(R, key=lambda r: int(r["gold"]["no"])):
        g = r["gold"]
        exp = g.get("expect") or g.get("expected") or g.get("label") or ""
        out.append(f"| {g['no']} | {exp} | {route(r['probs'])} | {E11.route(r['y11']) if r['y11'] else '-'} | {g['text'][:100].replace('|', '/')} |")

    cost = sum(r["cost"] for r in allR)
    flips = Counter((E11.route(r["y11"]), route(r["probs"])) for r in allR if r["y11"] and E11.route(r["y11"]) != route(r["probs"]))
    out += ["", f"## 전체 {len(allR)}개 (선택형 판정 ${cost:.2f})", "",
            "라우팅이 바뀐 발화 (11축 → 선택형): " + ", ".join(f"{a}→{b} {c}" for (a, b), c in flips.most_common()), "",
            "### 위험 축 켜짐: 선택형 vs 11축 예/아니오", ""] + agree_table(allR)
    out += ["", "### 세부 항목: 선택형 세부 (확률 ≥ 0.3 / 0.5) vs 15축 옛 축 (≥ 0.7)", ""] + sub_table(allR)
    out += ["", "### 선택지 분포", ""] + dist_table(allR)
    out += ["", "### 한쪽만 켜진 예시", ""]
    for name, f, g in PAIRS:
        out += [f"- **{name}** 선택형만:"] + examples(allR, f, g) + [f"- **{name}** 11축만:"] + examples(allR, lambda p, f=f: not f(p), g)
    open(REPORT, "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"→ {REPORT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--source", choices=SPLIT["dev"])
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.show:
        print(json.dumps(QUESTIONS, ensure_ascii=False, indent=1))
    elif args.run:
        for s in [args.source] if args.source else SPLIT["dev"]:
            run(s, args.workers, args.limit)
    else:
        report()


if __name__ == "__main__":
    main()
