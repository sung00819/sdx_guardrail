"""영어 프롬프트뱅크 docx → 1025)bank.json (2026-10-25, 라우팅 설계: 1025)jev.md).

docx 절 → JSON 칸:
  4      meta           항상 (역할·우선순위 몇 줄 + 4절 안전·대화 규칙)
  1.0·1.2.2 style       정서 지원 모듈과 함께 (말투 대응 중 공통·지나가는 위험 언급만)
  2.0    strategy_intro 정서 지원 모듈, 원하는 방식을 모를 때
  2.1–2.3 strategies    listen_vent / deep_empathy / practical_advice
  1.3    general        일반 대화 모드
  3.1–3.12 crisis       Jev 축 키별 (3.10–3.12 는 보정)
reply_format 과 fill 은 strategy_bank.json (이전 뱅크) 에서 가져온다.

    python chatbot/rlver/build_bank.py "/Users/seong-yumin/SDX/유민) 프롬프트 뱅크_EN.docx"
"""

import argparse
import json
import os
import re
import zipfile
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(HERE, "strategy_bank.json")
OUT = os.path.join(HERE, "1025)bank.json")

CRISIS_KEYS = ["obtain_means", "suicide_note", "put_affairs_in_order", "specific_plan", "nonsuicidal_self_harm",
               "repeated_self_harm", "cannot_stay_safe", "means_access", "method",
               "acute_context", "psych_history", "substance_use_disorder"]  # 3.1 … 3.12 순서
STRATEGY_KEYS = {"2.1": "listen_vent", "2.2": "deep_empathy", "2.3": "practical_advice"}
FIXES = {"helf harm": "self-harm"}  # docx 오타
# docx 문단 → 바꿀 문단들 (2026-10-25, bank_jev 대화 12개에서 8B·30B 둘 다 약병 위치를 안 묻고, 30B 가 작별·'쉬고 싶다' 에 동의했다).
# docx 원본에는 아직 반영 안 함 → 확정되면 docx 에 옮기고 여기서 지운다
PATCHES = {
    # 3.8 수단 접근: 위치 묻기를 다음 답에서 반드시, 수단을 감정의 상징으로만 다루지 않기
    "Notice the means they mentioned and ask, calmly, where it is right now.": [
        "In your very next reply after they mention the means, name it and ask, calmly, where it is right now "
        "(\"You mentioned the pills in your bag. Where are they right now?\"). Do this even if you also respond to their feelings."],
    "Do not avoid talking about the means.": [
        "Do not avoid talking about the means, and do not treat it only as a symbol of their feelings "
        "(\"the bottle is a reminder of how much you're carrying\") without asking where it is."],
    # 4절 메타: 동조 금지에 죽음·포기·작별을 받아 주는 말의 예시
    "Never agree with harmful beliefs (“they’d be better off without you”, “you’re worthless”) or justify or encourage suicide or self-harm; acknowledge the feeling without agreeing with the belief.": [
        "Never agree with harmful beliefs (“they’d be better off without you”, “you’re worthless”) or justify or encourage suicide or self-harm; acknowledge the feeling without agreeing with the belief.",
        "Never affirm, praise or normalize a wish to die, to rest for good, to give up, or to say a final goodbye. Not: \"You're not failing anyone by wanting to rest\", \"That's honesty — it takes strength to walk away\", \"It makes sense that you're done\". Instead, name the pain and ask about it directly (\"When you say you're done, are you thinking about ending your life?\")."],
    # 3.10 급성 맥락: 1025)jev.md 11번 축 v5 (2026-10-26) 와 같은 범위의 예시
    "Acknowledge the specific event and how hard it has been (a loss, a breakup, a job loss, debt, violence).": [
        "Acknowledge the specific situation and how hard it has been (a death or serious loss, including losing something they "
        "deeply hoped for or long worked toward; a divorce or breakup; losing a job; money they cannot cover or have fallen "
        "behind on; bullying or a serious family conflict; a worsening illness or caring for someone who is ill; violence or "
        "a legal problem)."],
}

# 4절 앞에 붙이는 역할·모듈 우선순위 (발표 자료 Safety Meta-Prompt: 역할 설정, 대응 우선순위)
ROLE = ("You are a supportive conversation partner. Respond to what the person brings, keep them safe, and help them "
        "feel a little better.\n"
        "The guidance below is assembled for this conversation. If it includes crisis guidance, safety comes first, "
        "then emotional support, then ordinary conversation.")

HEAD = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$")


def paragraphs(path):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode()
    out, used = [], set()
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = unescape(re.sub(r"<[^>]+>", "", p)).strip()
        for a, b in FIXES.items():
            t = t.replace(a, b)
        if t:
            out += PATCHES.get(t, [t])
            used.add(t)
    missing = [k for k in PATCHES if k not in used]
    assert not missing, f"docx 에서 덧쓸 문단을 못 찾음: {missing}"
    return out


def sections(paras):
    """번호 제목마다 (번호, 제목, 본문 줄들)"""
    secs, cur = [], None
    for t in paras:
        m = HEAD.match(t)
        if m:
            cur = [m.group(1), m.group(2), []]
            secs.append(cur)
        elif cur:
            cur[2].append(t)
    return {n: (title, lines) for n, title, lines in secs}


def render(lines, subheads=()):
    out = []
    for t in lines:
        if t in ("Do", "Do not"):
            out.append(t + ":")
        elif t in subheads:
            out.append("\n" + t + ":")
        elif t.startswith("Cues:"):
            out.append(t)
        else:
            out.append("- " + t)
    return "\n".join(out).strip()


def block(secs, n):
    title, lines = secs[n]
    return f"{title}\n{render(lines)}"


def build(docx):
    secs = sections(paragraphs(docx))
    v1 = json.load(open(V1))
    meta_title, meta_lines = secs["4"]
    bank = {
        "_doc": "대응 전략 뱅크 1025 (2026-10-25, 영어 프롬프트뱅크 docx 에서 build_bank.py 로 만듦). "
                "라우팅은 bank.assemble_route, 설계는 1025)jev.md",
        "meta": ROLE + "\n\n" + render(meta_lines, ("Suicide and self-harm", "Conversation style")) + "\n\n{REPLY_FORMAT}",
        "reply_format": v1["reply_format"],
        # 2026-10-25: 8B 가 긴 프롬프트에서 위기 지침을 놓쳐서 1.x 중 공통(1.0)과 지나가는 위험 언급(1.2.2)만 둔다
        "style": "How to respond to the way they talk:\n\n" + "\n\n".join(block(secs, n) for n in ("1.0", "1.2.2")),
        "strategy_intro": block(secs, "2.0"),
        "strategies": {k: {"label": secs[n][0], "text": block(secs, n)} for n, k in STRATEGY_KEYS.items()},
        "general": block(secs, "1.3"),
        "crisis": {k: {"label": secs[f"3.{i}"][0], "text": block(secs, f"3.{i}")}
                   for i, k in enumerate(CRISIS_KEYS, 1)},
        "fill": v1["fill"],
    }
    return bank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    bank = build(args.docx)
    json.dump(bank, open(args.out, "w"), ensure_ascii=False, indent=2)
    print(f"→ {args.out}")
    for k, v in bank["crisis"].items():
        print(f"  {k:<24} {v['label']}")


if __name__ == "__main__":
    main()
