"""대응 전략 뱅크 → 챗봇 시스템 프롬프트 (설계: STRATEGY.md, 뱅크: strategy_bank.json).

서비스 (원하는 방식·위험을 모름): meta + 전략 3개 모두 + 신호가 보일 때 대응 지침 + 신호가 없을 때 + 태도 지침 + 하면 안 되는 것.
oracle (알 때, 평가 상한): meta + 그 전략 하나 + (severe 면 대응 지침, mild 면 신호 없을 때) + 태도 지침 + 하면 안 되는 것.

    python chatbot/rlver/bank.py                                     # 서비스 프롬프트
    python chatbot/rlver/bank.py --need listen_vent --risk severe    # oracle
"""

import argparse
import json
import os

BANK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_bank.json")


def load(path=BANK):
    return json.load(open(path))


def strategy_text(s):
    return f"{s['name']}: {s['do']}\nAvoid: {s['dont']}"


def assemble(bank, need=None, risk=None):
    out = [bank["meta"]]
    names = [need] if need else list(bank["strategies"])
    out.append("Strategies:\n\n" + "\n\n".join(strategy_text(bank["strategies"][k]) for k in names))
    if risk in (None, "severe"):
        out.append(bank["crisis"]["text"])
    if risk in (None, "mild"):
        out.append(bank["no_signs"]["text"])
    if bank.get("attitudes", {}).get("text"):
        out.append(bank["attitudes"]["text"])
    out.append("Never:\n" + "\n".join(f"- {d}" for d in bank["dont"]))
    text = "\n\n".join(out)
    for k, v in bank.get("fill", {}).items():
        if not k.startswith("_"):
            text = text.replace("{" + k + "}", v)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=BANK)
    ap.add_argument("--need")
    ap.add_argument("--risk", choices=["mild", "severe"])
    args = ap.parse_args()
    print(assemble(load(args.bank), args.need, args.risk))


if __name__ == "__main__":
    main()
