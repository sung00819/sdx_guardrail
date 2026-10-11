"""연구실 서버 주소·계정. 공개 저장소에 남기지 않도록 환경변수나 .env (저장소 맨 위, 그 위) 에서 읽는다 (.env 는 git 에 올리지 않는다).

    SDX_HOST54 / SDX_HOST84 / SDX_HOST27   ssh 로 접속할 주소 (~/.ssh/config 의 이름이어도 된다)
    SDX_USER                               서버 계정 (서버끼리 복사할 때 user@host)
    SDX_ROOT27                             27번 서버 작업 폴더
"""

import os

from jev_client import read_dotenv

_TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV = {**read_dotenv(os.path.join(_TOP, "..", ".env")), **read_dotenv(os.path.join(_TOP, ".env"))}  # 저장소 맨 위가 우선


def get(name, default=""):
    return os.environ.get(name) or _ENV.get(name) or default


H54, H84, H27 = get("SDX_HOST54"), get("SDX_HOST84"), get("SDX_HOST27")
USER = get("SDX_USER")
HOME54 = get("SDX_HOME54", f"/home/{USER}")
ROOT27 = get("SDX_ROOT27")
