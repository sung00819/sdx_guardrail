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


def assemble(bank, need=None, risk=None, native=False):
    """native: 자체 생각 모드가 있는 챗봇 (Qwen3) 이면 답 형식을 reply_format.native 로"""
    out = [bank["meta"].replace("{REPLY_FORMAT}", bank["reply_format"]["native" if native else "tags"])]
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


def assemble_base(bank, native=False):
    """base (2026-10-19 사용자: bank 와 다 똑같이, 전략 뱅크만 빼고): meta 첫 문단 + 같은 답 형식 (전략 이름만 뺌).
    대화 흐름·전략 3개·위기 지침·신호 없을 때·태도 지침·하지 말 것은 넣지 않는다"""
    intro = bank["meta"].split("\n\nConversation flow")[0]
    fmt = bank["reply_format"]["native" if native else "tags"].replace(" (Listening / Deep empathy / Advice)", "")
    return intro + "\n\n" + fmt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=BANK)
    ap.add_argument("--need")
    ap.add_argument("--risk", choices=["mild", "severe"])
    ap.add_argument("--native", action="store_true", help="자체 생각 모드 챗봇용 답 형식")
    ap.add_argument("--base", action="store_true", help="뱅크 없는 base 프롬프트")
    args = ap.parse_args()
    if args.base:
        print(assemble_base(load(args.bank), args.native))
        return
    print(assemble(load(args.bank), args.need, args.risk, args.native))


if __name__ == "__main__":
    main()
