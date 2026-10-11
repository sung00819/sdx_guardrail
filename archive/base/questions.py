"""base: v4i 질문 13개 (questions.json). 한 번의 Jev 호출로 모두 묻는다.

자살 점수 0~3, 자해 점수 0~3, C-SSRS 예/아니오 5개(방법·의도·계획·준비·시도), 주체(self/both/other/none),
자살·자해 시점(current/past_only/none), 심한 자해, 도움 요청, 기타 위기(가정폭력·아동학대·성희롱·강간).
"""

import json
import os

VERSION = "v4i"

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions.json")) as f:
    QUESTIONS = json.load(f)

JUDGES = {"all": QUESTIONS}
