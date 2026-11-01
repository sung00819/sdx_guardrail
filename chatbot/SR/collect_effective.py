"""gym·sim 대화 기록에서 '효과 있었던 행동'과 '유효한 패널티'를 모은다 (2026-10-13).

행동 효과 (턴 단위):
  y = 그 턴의 상태 변화 (gym: emotion·urge·safety, sim: emotion·위험 감소 칸 수)
  X = 챗봇 답의 턴 사실(gym facts / sim check) + 질문 2개 이상·반복·긴 답 + 셀·출처·턴 위치
  모드(대화 안 최고 response)마다 OLS. 95% CI 는 대화 단위 부트스트랩.
  같은 답에 같이 나오는 행동을 서로 보정한 값이라, 단순 평균 차이(raw)와 같이 낸다.
패널티 유효성 (대화 단위):
  위반 대화 vs 아닌 대화의 결과(gym O, sim 패널티 전 R) 차이, 셀·출처 안에서 비교 (층별 가중 평균).
  플래그 발생률이 RL 반복에 따라 줄었는지 (sim run2·run3, gym g1).

  /data2/yumin/env/bin/python chatbot/SR/collect_effective.py --out out/SR/effective_v0
결과 폴더는 덮어쓰지 않는다.
"""

import argparse
import glob
import json
import os
import re
from collections import Counter, defaultdict

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
RANK = {"normal": 0, "support": 1, "assess": 2, "urgent": 3}
MODES = ["normal", "support", "assess", "urgent", "other"]
B = 200  # 부트스트랩 반복
RNG = np.random.default_rng(0)

GYM_SRC = ["promptopt/*/*.jsonl", "promptopt/*/it*/*.jsonl", "gym_rl/g1/episodes_it*.jsonl"]
SIM_SRC = ["sim_runs/eval_v2", "sim_runs/eval_v3", "sim_runs/eval_v4_rejudge", "sim_runs/eval_v6_base",
           "sim_runs/refcheck_v7", "rl/run2/it*", "rl/run3/it*"]
SIM_LONG = 450  # penalty.py LONG_RISK_REPLY 와 같게


# ---------------------------------------------------------------- 읽기
def src_name(path):
    rel = os.path.relpath(path, OUT)
    if rel.startswith("rl/"):
        return "/".join(rel.split("/")[:2])          # rl/run2
    if rel.startswith("promptopt/"):
        return "po/" + rel.split("/")[1]              # po/p1_turn
    return "/".join(rel.split("/")[:2])


def load_gym():
    eps, seen = [], set()
    for pat in GYM_SRC:
        for f in sorted(glob.glob(os.path.join(OUT, pat))):
            for i, line in enumerate(open(f)):
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(e, dict) or "turns" not in e or "reward" not in e:
                    continue
                e["_src"], e["_uid"] = src_name(f), f"{os.path.relpath(f, os.path.join(OUT, 'promptopt'))}:{i}"
                e["_it"] = _iter_of(f)
                eps.append(e)
                seen.add(e["_uid"])
    return eps


def _iter_of(path):
    m = re.search(r"it(\d{3})", path)
    return int(m.group(1)) if m else None


def load_sim():
    eps = []
    for pat in SIM_SRC:
        for d in sorted(glob.glob(os.path.join(OUT, pat))):
            for f in sorted(glob.glob(os.path.join(d, "*.json"))):
                try:
                    e = json.load(open(f))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if "turns" not in e or "reward" not in e:
                    continue
                e["_src"], e["_it"] = src_name(f), _iter_of(d)
                eps.append(e)
    return eps


def load_sr(path):
    out = {}
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            out[r["uid"]] = r
    return out


# ---------------------------------------------------------------- 턴 표
def gym_rows(eps, sr):
    rows = []
    for k, e in enumerate(eps):
        s = sr.get(e["_uid"])
        if s and s.get("id") != e.get("id"):
            s = None
        for i, t in enumerate(e["turns"]):
            a, b = t.get("states_before"), t.get("states_after")
            if not a or not b or not t.get("facts"):
                continue
            x = {f"f:{kk}": float(v) for kk, v in t["facts"].items() if isinstance(v, bool)}
            cf = t.get("cf") or {}
            x["c:multi_q"] = float((cf.get("n_questions") or 0) >= 2)
            x["c:no_q"] = float((cf.get("n_questions") or 0) == 0)
            x["c:repeated"] = float(bool(cf.get("repeated")))
            x["c:long"] = float((cf.get("n_sentences") or 0) > 6)
            if s and i < len(s.get("turns", [])):
                st = s["turns"][i]
                for c in st.get("llm_content") or []:
                    x[f"sr:{c}"] = 1.0
                sty = st.get("style") or {}
                for kk in ("directness", "stance", "register"):
                    if sty.get(kk):
                        x[f"st:{kk}={sty[kk]}"] = 1.0
                for emp in sty.get("empathy") or []:
                    x[f"st:empathy={emp}"] = 1.0
            y = {"emotion": b["emotion"] - a["emotion"]}
            if a.get("urge") is not None and b.get("urge") is not None:
                y["urge_down"] = a["urge"] - b["urge"]
            if a.get("safety") is not None and b.get("safety") is not None:
                y["safety"] = b["safety"] - a["safety"]
            rows.append({"ep": k, "mode": t.get("mode") or "normal", "cell": e["cell"], "src": e["_src"],
                         "turn": i, "x": x, "y": y, "has_sr": bool(s),
                         "credited": [z for z in (t.get("state_why") or {}).get("applied") or []]})
    return rows


def sim_rows(eps):
    rows = []
    for k, e in enumerate(eps):
        top = "normal"
        for i, t in enumerate(e["turns"]):
            s, ch = t.get("sim"), t.get("check")
            if not s or not ch:
                continue
            g = (t.get("guardrail") or {}).get("response", "normal")
            if g == "other":
                top = "other"
            elif top != "other" and RANK.get(g, 0) > RANK.get(top, 0):
                top = g
            x = {f"f:{kk}": float(v) for kk, v in ch.items() if isinstance(v, bool)}
            q = ch.get("questions") or 0
            x["c:multi_q"], x["c:no_q"] = float(q >= 2), float(q == 0)
            x["c:repeated"] = float(bool(s.get("repeated")))
            x["c:long"] = float(len(t.get("bot") or "") > SIM_LONG)
            for kk, v in (s.get("actions") or {}).items():
                if isinstance(v, bool):
                    x[f"a:{kk}"] = float(v)
            applied = s.get("risk_applied") or {}
            y = {"emotion": s.get("change") or 0,
                 "risk_down": -sum(v for v in applied.values() if isinstance(v, (int, float)) and v < 0),
                 "risk_up": sum(v for v in applied.values() if isinstance(v, (int, float)) and v > 0)}
            cited = [c.get("id", "") if isinstance(c, dict) else str(c) for c in (s.get("analysis") or {}).get("cited") or []]
            rows.append({"ep": k, "mode": top, "cell": e["cell"], "src": e["_src"], "turn": i, "x": x, "y": y,
                         "cited": cited, "true_response": e.get("true_response")})
    return rows


# ---------------------------------------------------------------- 회귀
def design(rows, keys):
    cells = sorted({r["cell"] for r in rows})[1:]
    srcs = sorted({r["src"] for r in rows})[1:]
    cols = keys + [f"cell={c}" for c in cells] + [f"src={s}" for s in srcs] + ["turn_late", "const"]
    X = np.zeros((len(rows), len(cols)))
    idx = {c: j for j, c in enumerate(cols)}
    for n, r in enumerate(rows):
        for kk in keys:
            X[n, idx[kk]] = r["x"].get(kk, 0.0)
        if f"cell={r['cell']}" in idx:
            X[n, idx[f"cell={r['cell']}"]] = 1
        if f"src={r['src']}" in idx:
            X[n, idx[f"src={r['src']}"]] = 1
        X[n, idx["turn_late"]] = float(r["turn"] >= 4)
        X[n, idx["const"]] = 1
    return X, cols


def ols(rows, keys, yname, min_n=30):
    rows = [r for r in rows if yname in r["y"]]
    if len(rows) < 100:
        return {}
    keys = [kk for kk in keys if sum(r["x"].get(kk, 0) for r in rows) >= min_n
            and sum(1 - r["x"].get(kk, 0) for r in rows) >= min_n]
    X, cols = design(rows, keys)
    y = np.array([r["y"][yname] for r in rows], float)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    eps = np.array([r["ep"] for r in rows])
    uniq = np.unique(eps)
    by = {u: np.where(eps == u)[0] for u in uniq}
    boots = []
    for _ in range(B):
        pick = RNG.choice(uniq, len(uniq))
        ii = np.concatenate([by[u] for u in pick])
        boots.append(np.linalg.lstsq(X[ii], y[ii], rcond=None)[0])
    boots = np.array(boots)
    res = {}
    for j, c in enumerate(cols):
        if c not in keys:
            continue
        on = X[:, j] == 1
        res[c] = {"n": int(on.sum()), "rate": round(float(on.mean()), 3),
                  "raw": round(float(y[on].mean() - y[~on].mean()), 2),
                  "adj": round(float(beta[j]), 2),
                  "lo": round(float(np.percentile(boots[:, j], 2.5)), 2),
                  "hi": round(float(np.percentile(boots[:, j], 97.5)), 2)}
    return {"n_rows": len(rows), "n_eps": int(len(uniq)), "y_mean": round(float(y.mean()), 2), "coef": res}


def effects(rows, prefixes, ynames):
    keys = sorted({kk for r in rows for kk in r["x"] if kk.startswith(prefixes)})
    out = {}
    for m in MODES:
        sub = [r for r in rows if r["mode"] == m]
        out[m] = {yn: ols(sub, keys, yn) for yn in ynames}
    return out


# ---------------------------------------------------------------- 패널티
def strat_diff(groups):
    """groups: {층: ([위반 결과], [정상 결과])} → 층별 차이의 위반 수 가중 평균"""
    num = den = 0.0
    for v, ok in groups.values():
        if v and ok:
            num += len(v) * (np.mean(v) - np.mean(ok))
            den += len(v)
    return num / den if den else None


def penalty_validity(items, flag_names):
    """items: [{flags: {name: 'violated'|'ok'|'na'}, outcome, stratum, ep}]"""
    out = {}
    for f in flag_names:
        app = [it for it in items if it["flags"].get(f, "na") != "na"]
        viol = [it for it in app if it["flags"][f] == "violated"]
        if not app:
            out[f] = {"applicable": 0}
            continue
        res = {"applicable": len(app), "violated": len(viol), "rate": round(len(viol) / len(app), 3)}

        def diff(sample):
            g = defaultdict(lambda: ([], []))
            for it in sample:
                g[it["stratum"]][0 if it["flags"][f] == "violated" else 1].append(it["outcome"])
            return strat_diff(g)
        d = diff(app)
        if d is not None and 5 <= len(viol) <= len(app) - 5:
            boots = [diff([app[i] for i in RNG.integers(0, len(app), len(app))]) for _ in range(B)]
            boots = [b for b in boots if b is not None]
            res.update(diff=round(d, 3), lo=round(float(np.percentile(boots, 2.5)), 3),
                       hi=round(float(np.percentile(boots, 97.5)), 3))
        out[f] = res
    return out


SIM_APPLIES = {"U": {"urgent"}, "A": {"assess", "urgent"}, "S": {"support", "assess", "urgent"}, "O": {"other"},
               "M": {"normal", "support", "assess", "urgent"}}


def sim_flag_items(eps, names):
    items = []
    for e in eps:
        top = "normal"
        for t in e["turns"]:
            g = (t.get("guardrail") or {}).get("response", "normal")
            top = "other" if g == "other" or top == "other" else max(top, g, key=lambda z: RANK.get(z, 0))
        fl = e.get("flags") or {}
        st = {}
        for f in names:
            ok_modes = SIM_APPLIES.get(f[0])
            st[f] = "na" if ok_modes and top not in ok_modes else ("violated" if f in fl else "ok")
        r = e["reward"]
        items.append({"flags": st, "outcome": r.get("before_penalty", r.get("total")),
                      "emo": r.get("emotion"), "risk": r.get("risk_drop"),
                      "stratum": (e["cell"], e["_src"]), "src": e["_src"], "it": e["_it"]})
    return items


def gym_flag_items(eps):
    items = []
    for e in eps:
        fl = {k: v.get("status", "na") for k, v in (e.get("flags") or {}).items()}
        r = e["reward"]
        items.append({"flags": fl, "outcome": r.get("O"), "stratum": (e["cell"], e["_src"]),
                      "src": e["_src"], "it": e["_it"]})
    return [it for it in items if it["outcome"] is not None]


def trend(items, names, src_prefix):
    """RL 반복별 위반률 (적용 대화 중)"""
    byit = defaultdict(list)
    for it in items:
        if it["src"].startswith(src_prefix) and it["it"] is not None:
            byit[it["it"]].append(it)
    out = {}
    for f in names:
        row = {}
        for k in sorted(byit):
            app = [it for it in byit[k] if it["flags"].get(f, "na") != "na"]
            if app:
                row[k] = round(sum(it["flags"][f] == "violated" for it in app) / len(app), 3)
        out[f] = row
    return out


# ---------------------------------------------------------------- 주
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sr", default=os.path.join(OUT, "SR/summaries/v0.jsonl"))
    a = ap.parse_args()
    od = os.path.join(ROOT, a.out)
    if os.path.exists(od):
        raise SystemExit(f"{od} 가 이미 있다 (덮어쓰지 않음)")
    os.makedirs(od)

    gym, sim, sr = load_gym(), load_sim(), load_sr(a.sr)
    print("gym", len(gym), Counter(e["_src"] for e in gym))
    print("sim", len(sim), Counter(e["_src"] for e in sim))
    print("sr", len(sr))

    gr, sm = gym_rows(gym, sr), sim_rows(sim)
    res = {"counts": {"gym_eps": len(gym), "sim_eps": len(sim), "gym_turns": len(gr), "sim_turns": len(sm),
                      "gym_src": Counter(e["_src"] for e in gym), "sim_src": Counter(e["_src"] for e in sim),
                      "sr_joined_turns": sum(r["has_sr"] for r in gr)}}

    res["gym_effects"] = effects(gr, ("f:", "c:"), ["emotion", "urge_down", "safety"])
    res["gym_sr_effects"] = effects([r for r in gr if r["has_sr"]], ("f:", "c:", "sr:", "st:"), ["emotion"])
    res["sim_effects"] = effects(sm, ("f:", "c:"), ["emotion", "risk_down"])

    # 시뮬레이터가 인정한 좋아지는 행동 (gym applied): 어떤 턴 사실 뒤에 인정됐나
    cred = defaultdict(Counter)
    tot = Counter()
    for r in gr:
        for kk, v in r["x"].items():
            if kk.startswith("f:") and v:
                tot[kk] += 1
                for c in r["credited"]:
                    cred[kk][c if isinstance(c, str) else json.dumps(c)] += 1
    res["gym_credit"] = {kk: {"n": tot[kk], "top": cred[kk].most_common(6)} for kk in tot}

    # sim 감정 규칙 인용 (공통 규칙만 번호가 고정: R1~R3, F1~F11)
    cites = defaultdict(Counter)
    for r in sm:
        for c in r["cited"]:
            cites[r["true_response"]][c] += 1
    res["sim_cited"] = {m: c.most_common(15) for m, c in cites.items()}

    # 패널티
    gi = gym_flag_items(gym)
    gnames = sorted({f for it in gi for f in it["flags"]})
    res["gym_penalty"] = penalty_validity(gi, gnames)
    res["gym_penalty_trend_g1"] = trend(gi, gnames, "gym_rl")
    snames = sorted({f for e in sim for f in (e.get("flags") or {})})
    si = sim_flag_items(sim, snames)
    res["sim_penalty"] = penalty_validity(si, snames)
    for name, key in (("sim_penalty_emotion", "emo"), ("sim_penalty_risk", "risk")):
        res[name] = penalty_validity([{**it, "outcome": it[key]} for it in si if it[key] is not None], snames)
    res["sim_penalty_trend_run2"] = trend(si, snames, "rl/run2")
    res["sim_penalty_trend_run3"] = trend(si, snames, "rl/run3")

    json.dump(res, open(os.path.join(od, "effective.json"), "w"), ensure_ascii=False, indent=1, default=str)
    print("saved", od)


if __name__ == "__main__":
    main()
