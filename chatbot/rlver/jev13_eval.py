"""Jev 13축을 개발용 데이터 정답 라벨로 채점 (2026-10-29). Kev 증류 전에 Jev 가 믿을 만한지 본다. Jev 호출 없음.

라우팅 (챗봇과 같음, P(예) ≥ 0.7): 위험 축 1–9 하나라도 → 가드레일, 아니면 depression → 정서 지원, 아니면 일반 대화.
  CRADLE  그룹별 (compare.cradle_group). 위기 그룹이 일반 대화로 가면 놓침. 자해 그룹은 자해 축 5·6, 폭력·학대 그룹은 급성 맥락
          비교: 같은 발화의 예전 expert11(t11e) Jev 슬라이드 33 판정 (unsafe 비율)
  Aegis   self_harm 라벨별, Kaggle  Suicidal / Non-Suicidal (서브레딧 기준, 참고용) 별

    python chatbot/rlver/jev13_eval.py       # → chatbot/rlver/1029)jev13_dev_eval.md
    python chatbot/rlver/jev13_eval.py --si  # 15축 (14 자살 사고 · 15 실행 의도 합침, 1029)jev_si_*) → 1029)jev15_dev_eval.md
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "common"))
sys.path.insert(0, HERE)
from bank import MOD_AXES, RISK_AXES, THRESHOLD  # noqa: E402
from compare import GROUPS, cradle_group  # noqa: E402

OLD = os.path.join(ROOT, "..", "sdx_guardrail", "out")  # 예전 expert11 판정 (combined_expert11_<source>.jsonl)
REPORT = os.path.join(HERE, "1029)jev13_dev_eval.md")
SI_AXES = ["suicidal_ideation", "suicidal_intent"]  # 15축에서 더한 위험 축 (1029)jev.md 14·15)
RISK = list(RISK_AXES)  # --si 면 SI_AXES 를 더한다
ROUTES = ["가드레일", "정서 지원", "일반 대화"]
SH = ["nonsuicidal_self_harm", "repeated_self_harm"]


def on(r, k):
    return (r["probs"].get(k) or 0) >= THRESHOLD


def route(r, risk=None):
    if any(on(r, k) for k in (risk or RISK)):
        return "가드레일"
    return "정서 지원" if on(r, "depression") else "일반 대화"


def load(source):
    d = os.path.join(ROOT, "out", "rlver", "jev_dev")
    R = [json.loads(l) for l in open(os.path.join(d, f"1029)jev13_{source}.jsonl"))]
    if RISK != RISK_AXES:  # 15축: 새 두 축 판정을 같은 key 에 합친다
        si = {r["key"]: r["probs"] for r in map(json.loads, open(os.path.join(d, f"1029)jev_si_{source}.jsonl")))}
        for r in R:
            r["probs"].update(si[r["key"]])
    return R


def pct(a, n):
    return f"{100 * a / n:.0f}% ({a})" if n else "-"


def route_row(name, R, extra=()):
    c = Counter(route(r) for r in R)
    return f"| {name} | {len(R)} | " + " | ".join(pct(c[x], len(R)) for x in ROUTES) + "".join(f" | {e}" for e in extra) + " |"


def old_unsafe(source):
    """예전 expert11 Jev 의 슬라이드 33 판정 → {key: unsafe 여부}"""
    from slide33 import cls
    path = os.path.join(OLD, f"combined_expert11_{source}.jsonl")
    return {r["key"]: cls(r) == "unsafe" for r in map(json.loads, open(path))} if os.path.exists(path) else {}


def axis_table(R, groups):
    """그룹별 축 '예' 비율"""
    axes = RISK + ["depression"] + MOD_AXES
    lines = ["| 그룹 | n | " + " | ".join(axes) + " |", "|---|---|" + "---|" * len(axes)]
    for g, rs in groups:
        lines.append(f"| {g} | {len(rs)} | " + " | ".join(f"{100 * sum(on(r, a) for r in rs) / len(rs):.0f}" if rs else "-"
                                                    for a in axes) + " |")
    return lines


def main():
    global REPORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--si", action="store_true", help="15축 (14·15번을 위험 축으로 더함)")
    if ap.parse_args().si:
        RISK.extend(SI_AXES)
        REPORT = os.path.join(HERE, "1029)jev15_dev_eval.md")
    n = len(RISK) + 4
    out = [f"# Jev {n}축 × 개발용 데이터 정답 채점 (2026-10-29)", "",
           "개발용 데이터 21,942건 (`jev_dev.py`, 13축 + need, $5.29" + (" · 14·15번은 `--only` 로 따로, $1.93" if n == 15 else "")
           + "). 축마다 P(예) ≥ 0.7. 라우팅은 챗봇과 같다: 위험 축 " + ("1–9, 14–15" if n == 15 else "1–9")
           + " 하나라도 → 가드레일, 아니면 우울 → 정서 지원, 아니면 일반 대화."
           + (" `13축 가드레일` = 14·15번 없이 셌을 때." if n == 15 else ""), ""]

    # CRADLE
    R = load("cradle_test")
    cradle_group(R)
    old = old_unsafe("cradle_test")
    by = defaultdict(list)
    for r in R:
        by[r["group"]].append(r)
    out += ["## CRADLE test (실제 대화 + 임상가 라벨, 4,527 발화)", "",
            "CRADLE 은 위기가 처음 드러난 발화에만 라벨을 붙인다. 위기 그룹이 일반 대화로 가면 놓침이다. "
            "`예전 unsafe` = 같은 발화에서 expert11 Jev 의 슬라이드 33 unsafe 비율.", "",
            "| 그룹 | n | " + " | ".join(ROUTES) + " | 자해 축 5·6 | 급성 맥락 | 예전 unsafe |" + (" 13축 가드레일 |" if n == 15 else ""),
            "|---|---|---|---|---|---|---|---|" + ("---|" if n == 15 else "")]
    for g in GROUPS:
        rs = by[g]
        if rs:
            sh = sum(any(on(r, k) for k in SH) for r in rs)
            ac = sum(on(r, "acute_context") for r in rs)
            ou = [old[r["key"]] for r in rs if r["key"] in old]
            extra = (pct(sh, len(rs)), pct(ac, len(rs)), pct(sum(ou), len(ou)))
            if n == 15:
                extra += (pct(sum(route(r, RISK_AXES) == "가드레일" for r in rs), len(rs)),)
            out.append(route_row(g, rs, extra))
    crisis = [r for g in GROUPS[:4] for r in by[g]]
    miss = [r for r in crisis if route(r) == "일반 대화"]
    both = [r for r in crisis if r["key"] in old]
    old_hit_new_miss = [r for r in both if old[r["key"]] and route(r) == "일반 대화"]
    out += ["", f"- 위기 그룹(앞 4개) {len(crisis)} 발화 중 일반 대화로 감 (놓침): {pct(len(miss), len(crisis))}.",
            f"- 예전 Jev 는 unsafe 로 잡았는데 13축은 일반 대화로 보낸 발화: {len(old_hit_new_miss)}.", "",
            "### 그룹별 축 '예' 비율 (%)", ""]
    out += axis_table(R, [(g, by[g]) for g in GROUPS if by[g]])
    out += ["", "### 놓친 위기 발화 (일반 대화로 감, 최대 15개)", ""]
    for r in miss[:15]:
        top = sorted(r["probs"].items(), key=lambda kv: -(kv[1] or 0))[:3]
        cur = r["state"]["current"].split("\n")[-1].replace("|", "/")[:220]
        out.append(f"- `{r['key']}` {r['group']} — {cur} — 최고 축 " + ", ".join(f"{k} {v:.2f}" for k, v in top))

    # Aegis
    R = load("aegis2")
    out += ["", "## Aegis 2.0 (챗봇에 들어온 단일 입력, 1,928개)", "",
            "| 정답 | n | " + " | ".join(ROUTES) + " |", "|---|---|---|---|---|"]
    out.append(route_row("자해 라벨 있음", [r for r in R if r["gold"]["self_harm"]]))
    out.append(route_row("자해 라벨 없음", [r for r in R if not r["gold"]["self_harm"]]))
    if n == 15:
        out += ["", "13축 가드레일: 있음 " + pct(sum(route(r, RISK_AXES) == "가드레일" for r in R if r["gold"]["self_harm"]), 38)
                + ", 없음 " + pct(sum(route(r, RISK_AXES) == "가드레일" for r in R if not r["gold"]["self_harm"]), 1890)]
    out += ["", "자해 라벨이 없는데 가드레일로 간 것 (최대 10개):", ""]
    for r in [r for r in R if not r["gold"]["self_harm"] and route(r) == "가드레일"][:10]:
        axes = [k for k in RISK if on(r, k)]
        out.append(f"- {r['state']['current'].split(': ', 1)[-1].replace(chr(10), ' ').replace('|', '/')[:200]} — {', '.join(axes)}")

    # Kaggle
    R = load("kaggle")
    groups = [("Suicidal", [r for r in R if r["gold"]["orig_label"] == "Suicidal"]),
              ("Non-Suicidal", [r for r in R if r["gold"]["orig_label"] != "Suicidal"])]
    out += ["", "## Kaggle Reddit (15,477개, 라벨은 서브레딧 기준이라 참고용)", "",
            "| 정답 | n | " + " | ".join(ROUTES) + " |", "|---|---|---|---|---|"]
    out += [route_row(g, rs) for g, rs in groups]
    if n == 15:
        out += ["", "13축 가드레일: " + ", ".join(f"{g} " + pct(sum(route(r, RISK_AXES) == "가드레일" for r in rs), len(rs)) for g, rs in groups)]
    out += ["", "### 축 '예' 비율 (%)", ""] + axis_table(R, groups)

    # other_check
    R = load("other_check")
    out += ["", "## 남 이야기 확인 10개", "", "| no | 기대 | 라우팅 | 켜진 축 | 글 |", "|---|---|---|---|---|"]
    for r in sorted(R, key=lambda r: int(r["gold"]["no"])):
        g = r["gold"]
        exp = g.get("expect") or g.get("expected") or g.get("label") or ""
        axes = ", ".join(k for k in r["probs"] if on(r, k))
        out.append(f"| {g['no']} | {exp} | {route(r)} | {axes} | {g['text'][:120].replace('|', '/')} |")

    open(REPORT, "w").write("\n".join(out) + "\n")
    print("\n".join(out[:60]))
    print(f"... → {REPORT}")


if __name__ == "__main__":
    main()
