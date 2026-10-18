"""SAGE Sentient Agent: 가상 사용자. 한 턴에 LLM 두 번 (감정 추정 f_emo → 응답 생성 f_reply).

감정은 30 에서 시작 (공식 코드 emo_point), 턴마다 LLM 이 낸 변화(−10~+10, 벗어나면 자른다)를 더하고 0~100 으로 자른다.
상태: S ≥ 100 (고맙다고 하고 끝) · A ≥ 70 · B ≥ 40 · C ≥ 10 · F < 10 (떠난다).
프로필에 reveal_level(D 털어놓는 정도, convert_scenes.py)이 있으면 숨긴 걱정을 말해도 되는지를 감정 점수로 코드가 정해
응답 프롬프트에 넣는다 (config disclosure.reveal_emotion).
"""

import json
import re

from prompts import DISCLOSURE_NOW, EMOTION_STATES, ESTIMATE, OPEN_HISTORY, OPEN_PLANNING, PURPOSE, REPLY

SECTIONS = ("Content", "Reason", "Activity", "Analyze", "Change")


def emotion_state(e):
    for name, low in (("Emotion-S", 100), ("Emotion-A", 70), ("Emotion-B", 40), ("Emotion-C", 10)):
        if e >= low:
            return name
    return "Emotion-F"


def dialog_json(msgs):
    """공식 코드처럼 역할을 you / NPC 로 바꾼 JSON 목록"""
    names = {"user": "you", "assistant": "NPC"}
    return json.dumps([{"role": names[m["role"]], "content": m["content"]} for m in msgs], ensure_ascii=False, indent=2)


def parse_sections(text, names):
    """'Name:' 머리말로 나눈다. 대괄호·별표는 지운다"""
    text = re.sub(r"(?m)^(\s*)Analyse\s*:", r"\1Analyze:", text.replace("*", "").replace("：", ":"))
    out, pat = {}, re.compile(r"^\s*(" + "|".join(names) + r")\s*:\s*", re.M)
    marks = list(pat.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[m.end():end].strip().strip("[]").strip()
    return out


def parse_change(s, lo, hi):
    nums = re.findall(r"[-+]?\d+", s or "")
    if not nums:
        raise ValueError(f"Change 에 숫자 없음: {s!r}")
    return max(lo, min(hi, int(nums[-1])))


class SageUser:
    def __init__(self, profile, llm, cfg):
        self.p, self.llm, self.cfg = profile, llm, cfg
        self.emotion = cfg["start"]
        self.history = []  # [{"role": "user"|"assistant", "content"}], user = 이 시뮬레이터

    def _format(self, template, **kw):
        return template.format(purpose=PURPOSE, persona=self.p["persona"], background=self.p["background"],
                               history=dialog_json(self.history[:-2]) if len(self.history) > 2 else "[]",
                               latest=dialog_json(self.history[-2:]), **kw)

    def _ask(self, prompt, check, tries=3):
        last = None
        for _ in range(tries):
            text = self.llm([{"role": "user", "content": prompt}])
            try:
                return check(text)
            except ValueError as e:
                last = e
        raise last

    def estimate(self):
        """f_emo: 마지막 챗봇 답에 대한 속마음과 변화. self.emotion 을 갱신한다"""
        prompt = self._format(ESTIMATE, emotion=self.emotion)

        def check(text):
            sec = parse_sections(text, SECTIONS)
            return sec, parse_change(sec.get("Change"), self.cfg["change_min"], self.cfg["change_max"])

        sec, change = self._ask(prompt, check)
        self.emotion = max(0, min(100, self.emotion + change))
        return {"change": change, "emotion": self.emotion, "planning": sec}

    def may_reveal(self):
        level = self.p.get("reveal_level")
        return level is None or self.emotion >= self.cfg["reveal_emotion"][str(level)]

    def state_text(self):
        s = emotion_state(self.emotion)
        return s if self.p.get("reveal_level") is None else s + "\n" + DISCLOSURE_NOW[self.may_reveal()]

    def reply(self, planning=None):
        """f_reply: 현재 감정 상태로 다음 발화"""
        if planning is None:
            prompt = REPLY.format(purpose=PURPOSE, states=EMOTION_STATES, persona=self.p["persona"],
                                  background=self.p["background"], history=OPEN_HISTORY, latest="",
                                  planning=OPEN_PLANNING, state=self.state_text())
        else:
            feel = ("Objective analysis of the NPC's reply:\n" + planning.get("Reason", "")
                    + "\nSubjective analysis of the NPC's reply:\n" + planning.get("Analyze", ""))
            prompt = self._format(REPLY, states=EMOTION_STATES, planning=feel, state=self.state_text())

        def check(text):
            sec = parse_sections(text, ("Thinking", "Origin", "Change", "Response"))
            resp = sec.get("Response", "").strip().strip('"“”').strip()
            if not resp:
                raise ValueError("Response 없음")
            return resp, sec.get("Thinking", "")

        text, thinking = self._ask(prompt, check)
        self.history.append({"role": "user", "content": text})
        return text, thinking

    def open(self, first_talk=None):
        """첫 발화. 테스트 프로필의 first_talk 가 있으면 그대로 쓴다 (평가를 같은 시작으로)"""
        if first_talk:
            self.history.append({"role": "user", "content": first_talk})
            return first_talk, ""
        return self.reply()

    def step(self, bot_reply):
        """챗봇 답 → 감정 갱신 → 사용자 답"""
        self.history.append({"role": "assistant", "content": bot_reply})
        est = self.estimate()
        text, thinking = self.reply(est["planning"])
        return {**est, "user": text, "user_thinking": thinking, "state": emotion_state(self.emotion),
                "may_reveal": self.may_reveal()}
