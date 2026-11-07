"""agra_lacal CAL Server를 이 uv 환경에서 띄운다 (IMP-GW-013, 서브모듈 수정 없음).

uv run python -m swarm_gateway.lacal_server --config config/lacal_server.yaml
설정 파일의 schema.path는 agra_lacal 루트 기준이다. 백엔드는 local만 쓴다(cyclonedds 미설치).
"""
from __future__ import annotations

import sys

from . import lacal  # noqa: F401  서브모듈을 sys.path에 넣는다

from server.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.argv[0] = "python -m swarm_gateway.lacal_server"
    main()
