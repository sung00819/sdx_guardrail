"""새 Kev 15축 평가 (2026-10-30): ID 보류 · OOD 에서 Jev 15축과 얼마나 같은지, 정답 라벨로는 어떤지. Jev·Kev 호출 없음.

판정 파일 (jev_dev.py --split id_hold|ood --name ...): out/rlver/jev_dev/1030)jev15_<source>.jsonl (기준) · 1030)<kev 태그>_<source>.jsonl
라우팅은 jev13_eval 15축과 같다 (P ≥ 0.7): 위험 축 1–9 · 14–15 하나라도 → 가드레일, 아니면 우울 → 정서 지원, 아니면 일반 대화.
ID 보류 · OOD 는 평가에만 쓴다. 여기서 본 오답으로 질문 · 데이터를 고치지 않는다.

    python chatbot/rlver/kev15_eval.py --kev kev15full                 # → chatbot/rlver/1030)kev15_eval_kev15full.md
    python chatbot/rlver/kev15_eval.py --kev kev15full,kev15lora       # 둘 나란히
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
from rules import SPLIT  # noqa: E402

D = os.path.join(ROOT, "out", "rlver", "jev_dev")
RISK = list(RISK_AXES) + ["suicidal_ideation", "suicidal_intent"]
AXES = RISK + ["depression"] + MOD_AXES
ROUTES = ["가드레일", "정서 지원", "일반 대화"]
DAILY = [s for s in SPLIT["id_hold"] if s != "cradle_validation"]
REDDIT = ["supportive", "uninformative", "indicator", "ideation", "behavior", "attempt"]


def on(p, k):
    return (p.get(k) or 0) >= THRESHOLD


def route(p):
    if any(on(p, k) for k in RISK):
        return "가드레일"
    return "정서 지원" if on(p, "depression") else "일반 대화"


def kappa(a, b):
    """두 이진 목록의 Cohen κ (둘 다 한쪽으로만 몰리면 None)"""
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def fk(x):
    return "-" if x is None else f"{x:.2f}"


def pct(a, n):
    return f"{100 * a / n:.0f}%" if n else "-"


def load(tag, source):
    path = os.path.join(D, f"1030){tag}_{source}.jsonl")
    return {r["key"]: r for r in map(json.loads, open(path))} if os.path.exists(path) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kev", default="kev15full", help="쉼표로 Kev 태그 여러 개")
    tags = ap.parse_args().kev.split(",")
    judges = ["jev15"] + tags
    sources = SPLIT["id_hold"] + SPLIT["ood"]
    data = {s: {j: load(j, s) for j in judges} for s in sources}
    for s in sources:  # 모든 판정기가 다 한 key 만 센다
        keys = set.intersection(*(set(data[s][j]) for j in judges))
        data[s] = {j: {k: data[s][j][k] for k in keys} for j in judges}

    out = [f"# 새 Kev 15축 평가 — ID 보류 · OOD (2026-10-30)", "",
           "기준 = Jev 15축 (`1029)jev.md`, 같은 데이터에 새로 돌림, $2.11). 축마다 P(예) ≥ 0.7. "
           "라우팅: 위험 축 1–9 · 14–15 → 가드레일, 아니면 우울 → 정서 지원, 아니면 일반 대화. "
           "ID 보류 · OOD 는 학습에 안 넣었고, 여기 오답으로 고치지 않는다.", "",
           "Kev: " + ", ".join(f"`{t}`" for t in tags) + " (`kev15full` = kev-4b LoRA 를 합쳐 full fine-tuning, `kev15lora` = kev-4b 에서 LoRA)", ""]

    # 1. Jev 와 일치
    out += ["## 1. Jev 와 얼마나 같은가", "",
            "라우팅 일치 = 세 갈래 라우팅이 같은 비율. 가드레일 κ = 가드레일 여부의 κ. 축 κ 평균 = 15축 κ 평균 (양쪽 다 한쪽으로 몰린 축 제외).", "",
            "| 데이터 | n | " + " | ".join(f"{t} 라우팅 일치 | {t} 가드레일 κ | {t} 축 κ 평균" for t in tags) + " |",
            "|---|---|" + "---|---|---|" * len(tags)]
    pooled = {"ID 보류": SPLIT["id_hold"], "OOD": SPLIT["ood"]}
    for name, srcs in [(s, [s]) for s in sources] + list(pooled.items()):
        keys = [(s, k) for s in srcs for k in data[s]["jev15"]]
        if not keys:
            continue
        J = [data[s]["jev15"][k]["probs"] for s, k in keys]
        cells = []
        for t in tags:
            K = [data[s][t][k]["probs"] for s, k in keys]
            agree = sum(route(a) == route(b) for a, b in zip(J, K)) / len(keys)
            gk = kappa([route(a) == "가드레일" for a in J], [route(b) == "가드레일" for b in K])
            ks = [x for x in (kappa([on(a, ax) for a in J], [on(b, ax) for b in K]) for ax in AXES) if x is not None]
            cells.append(f"{100 * agree:.1f}% | {fk(gk)} | {fk(sum(ks) / len(ks) if ks else None)}")
        label = f"**{name}**" if name in pooled else name
        out.append(f"| {label} | {len(keys)} | " + " | ".join(cells) + " |")

    out += ["", "### 축별 κ (ID 보류 전체 / OOD)", "",
            "| 축 | Jev 예 (ID) | " + " | ".join(f"{t} κ ID | {t} κ OOD" for t in tags) + " |",
            "|---|---|" + "---|---|" * len(tags)]
    for ax in AXES:
        row = []
        jid = [data[s]["jev15"][k]["probs"] for s in SPLIT["id_hold"] for k in data[s]["jev15"]]
        for t in tags:
            for srcs in (SPLIT["id_hold"], SPLIT["ood"]):
                ks = [(s, k) for s in srcs for k in data[s]["jev15"]]
                row.append(fk(kappa([on(data[s]["jev15"][k]["probs"], ax) for s, k in ks],
                                    [on(data[s][t][k]["probs"], ax) for s, k in ks])) if ks else "-")
        out.append(f"| {ax} | {sum(on(p, ax) for p in jid)} | " + " | ".join(row) + " |")

    # 2. CRADLE validation 정답
    cv = data["cradle_validation"]
    if cv["jev15"]:
        rows = list(cv["jev15"].values())
        cradle_group(rows)
        group = {r["key"]: r["group"] for r in rows}
        by = defaultdict(list)
        for k, g in group.items():
            by[g].append(k)
        out += ["", "## 2. CRADLE validation (임상가 라벨, 대화 단위)", "",
                "위기 그룹이 일반 대화로 가면 놓침, 위기 이전 발화가 가드레일로 가면 과잉.", "",
                "| 그룹 | n | " + " | ".join(f"{j} 가드레일 | {j} 일반 대화" for j in judges) + " |",
                "|---|---|" + "---|---|" * len(judges)]
        for g in GROUPS:
            ks = by.get(g, [])
            if ks:
                cells = []
                for j in judges:
                    c = Counter(route(cv[j][k]["probs"]) for k in ks)
                    cells.append(f"{pct(c['가드레일'], len(ks))} | {pct(c['일반 대화'], len(ks))}")
                out.append(f"| {g} | {len(ks)} | " + " | ".join(cells) + " |")
        crisis = [k for g in GROUPS[:4] for k in by.get(g, [])]
        out += ["", "위기 그룹(앞 4개) 놓침: " + ", ".join(
            f"{j} {pct(sum(route(cv[j][k]['probs']) == '일반 대화' for k in crisis), len(crisis))}" for j in judges)]

    # 3. Reddit C-SSRS (OOD)
    rd = data["reddit_cssrs"]
    if rd["jev15"]:
        lab = defaultdict(list)
        for k, r in rd["jev15"].items():
            lab[r["gold"]["label"]].append(k)
        out += ["", "## 3. Reddit C-SSRS (OOD, 임상 척도 라벨)", "",
                "supportive · uninformative 는 위험 아님, indicator 이상은 위험 신호.", "",
                "| 라벨 | n | " + " | ".join(f"{j} 가드레일" for j in judges) + " |", "|---|---|" + "---|" * len(judges)]
        for L in REDDIT:
            ks = lab.get(L, [])
            if ks:
                out.append(f"| {L} | {len(ks)} | " + " | ".join(
                    pct(sum(route(rd[j][k]["probs"]) == "가드레일" for k in ks), len(ks)) for j in judges) + " |")

    # 4. 일상 대화 과잉
    out += ["", "## 4. 일상 · 정서 대화 (ID 보류, 위기 없음이 대부분)", "",
            "| 데이터 | n | " + " | ".join(f"{j} 가드레일 | {j} 정서 지원" for j in judges) + " |",
            "|---|---|" + "---|---|" * len(judges)]
    for s in DAILY:
        ks = list(data[s]["jev15"])
        if ks:
            cells = []
            for j in judges:
                c = Counter(route(data[s][j][k]["probs"]) for k in ks)
                cells.append(f"{pct(c['가드레일'], len(ks))} | {pct(c['정서 지원'], len(ks))}")
            out.append(f"| {s} | {len(ks)} | " + " | ".join(cells) + " |")

    path = os.path.join(HERE, f"1030)kev15_eval_{'_'.join(tags)}.md")
    open(path, "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"→ {path}")


if __name__ == "__main__":
    main()
