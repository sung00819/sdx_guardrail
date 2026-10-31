"""가드레일 단독 실행 (2026-10-28): 시뮬레이터 없이 실제 대화 기록 → Jev 13축 판정 → 1025)bank.json 프롬프트 조합 → 챗봇 답.
run_episode (episode.py) 의 bank_jev_plan 한 턴과 같은 처리다: 위험 축 sticky, 원하는 방식 한 번 권하고 다음 답에서 감지,
계획 칸 (위험 턴), 앞 답과 거의 같으면 다시 쓰기.

    from guard import Guardrail
    g = Guardrail(config="config_local.json", chatbot="qwen3-8b")
    state = g.new_state()                       # 대화마다 하나
    out = g.respond([{"role": "user", "content": "요즘 너무 지쳐서 살고 싶은 마음이 없어요"}], state)
    out["reply"], out["route"]                  # 보낼 답, 고른 모듈 (risk · emotional · general)

    python chatbot/rlver/guard.py --chatbot qwen3-8b --show   # 터미널에서 대화

판정기 jev 는 OpenRouter 키 (OPENROUTER_API_KEY, 환경변수나 저장소 맨 위 .env), 챗봇은 config 의 vLLM 서버가 있어야 한다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from episode import REDO_NOTE, REDO_SIMILARITY, jev_route, max_similarity, parse_bot, plan_then_reply  # noqa: E402
from llm import Chat  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class Guardrail:
    def __init__(self, config=os.path.join(HERE, "config_local.json"), chatbot="qwen3-8b", judge="jev", plan=True, bot=None, jev=None):
        """plan: True = bank_jev_plan (계획 칸, 발표 결과 설정), False = bank_jev. bot·jev: 직접 만든 챗봇·판정기를 넣을 때"""
        if bot is None:
            bot = Chat(json.load(open(config))["chatbots"][chatbot])
        if jev is None:
            from jev import Jev
            jev = Jev(judge)
        self.bot, self.jev, self.plan = bot, jev, plan
        self.native = getattr(bot, "native_think", False)

    @staticmethod
    def new_state():
        """대화 하나의 상태: 잡힌 방식, 권했는지, 이번 발화가 권유에 대한 답인지, 켜진 적 있는 위험 축"""
        return {"need": None, "offered": False, "await": False, "risk_seen": []}

    def respond(self, history, state):
        """history: 지금까지 대화 [{"role": "user"|"assistant", "content": ...}], 마지막은 사용자 발화. state 는 제자리에서 바뀐다.
        → {"reply": 사용자에게 보일 답, "jev": 축별 P(예), "route": 고른 모듈, "system": 조합한 시스템 프롬프트, "raw": 생각 포함 원문}"""
        assert history and history[-1]["role"] == "user", "마지막 메시지는 사용자 발화여야 한다"
        messages = [{"role": "system", "content": ""}] + [{"role": m["role"], "content": m["content"]} for m in history]
        messages[0]["content"], probs, route, prefill = jev_route(messages, self.jev, state, self.native, plan=self.plan)
        fmt = "bank_jev_plan" if self.plan else "bank_jev"
        if self.plan and not self.native and not prefill:  # 자체 생각 없는 챗봇의 우울·일반 턴: 계획 칸 없이 답만
            fmt = "reply_only"
        raw = plan_then_reply(self.bot, messages, prefill) if prefill else self.bot(messages)
        reply, _ = parse_bot(raw, fmt)
        prev = [m["content"] for m in history if m["role"] == "assistant"]
        for _ in range(2 if self.plan else 0):  # 앞 답과 거의 같으면 다시 쓰게 한다 (episode.run_episode 와 같다)
            if max_similarity(reply, prev) < REDO_SIMILARITY:
                break
            note = REDO_NOTE.format(prev=max(prev, key=lambda p: max_similarity(reply, [p])))
            retry = [{**messages[0], "content": messages[0]["content"] + "\n\n" + note}] + messages[1:]
            head = (prefill.replace("<think>\n", "<think>\nMy last draft repeated an earlier reply word for word; this time I "
                                    "respond to their newest message with new words.\n", 1) if prefill else None)
            raw = plan_then_reply(self.bot, retry, head, temperature=1.0) if prefill else self.bot(retry, temperature=1.0)
            reply, _ = parse_bot(raw, fmt)
        return {"reply": reply or "...", "jev": {k: round(v, 3) for k, v in probs.items()}, "route": route,
                "system": messages[0]["content"], "raw": raw}


def main():
    ap = argparse.ArgumentParser(description="터미널에서 가드레일 챗봇과 대화 (빈 줄이나 Ctrl-D 로 끝)")
    ap.add_argument("--config", default=os.path.join(HERE, "config_local.json"))
    ap.add_argument("--chatbot", default="qwen3-8b", help="config 의 chatbots 키 (qwen3-8b · qwen30b)")
    ap.add_argument("--judge", default="jev", choices=["jev", "kev", "clm"])
    ap.add_argument("--no_plan", action="store_true", help="계획 칸 없이 (bank_jev)")
    ap.add_argument("--show", action="store_true", help="켜진 축·고른 모듈을 함께 보인다")
    args = ap.parse_args()
    g = Guardrail(args.config, args.chatbot, args.judge, plan=not args.no_plan)
    history, state = [], g.new_state()
    while True:
        try:
            text = input("나> ").strip()
        except EOFError:
            break
        if not text:
            break
        history.append({"role": "user", "content": text})
        out = g.respond(history, state)
        if args.show:
            on = [k for k, p in out["jev"].items() if p >= 0.7]
            r = out["route"]
            print(f"  [Jev 켜짐: {', '.join(on) or '없음'} | 위험 {r['risk'] or '-'} · 우울 {r['emotional']} · 일반 {r['general']}"
                  f" · 방식 {r['need'] or '-'}]")
        print(f"챗봇> {out['reply']}\n")
        history.append({"role": "assistant", "content": out["reply"]})


if __name__ == "__main__":
    main()
