"""대응 전략 뱅크 → 챗봇 시스템 프롬프트 (설계: STRATEGY.md, 뱅크: strategy_bank.json).

조립 = meta + needs.<원하는 방식> + risk.<event> + dos + penalties.
원하는 방식·위험을 모르면 (서비스) meta 의 분기 지시만으로 챗봇이 판단하고,
알면 (oracle 평가, 나중에 감지기) 해당 조각을 넣는다.

    python chatbot/rlver/bank.py --need listen_vent --risk severe   # 조립 결과 보기
"""

import argparse
import json
import os

BANK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_bank.json")


def load(path=BANK):
    return json.load(open(path))


def penalties(bank, risk=None):
    """이 위험 수준에 해당하는 금지 목록 (when 이 없거나 같은 것)"""
    return [p for p in bank["penalties"] if p.get("when") in (None, risk) or risk is None]


def assemble(bank, need=None, risk=None):
    out = [bank["meta"]]
    if need:
        n = bank["needs"][need]
        out.append(f"What they want: {n['do']}\nAvoid: {n['dont']}")
    if risk:
        r = bank["risk"][risk]
        out.append(f"Their situation: {r['do']}\nAvoid: {r['dont']}")
    out.append(bank["dos"])
    out.append("Never:\n" + "\n".join(f"- {p['text']}" for p in penalties(bank, risk)))
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
