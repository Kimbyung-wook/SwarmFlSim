"""호환용 별칭 (IMP-AGT-053, DEC-104): `swarm_api.geo`으로 옮겼다. 새 코드와 플러그인은 `swarm_api.geo`을 쓴다.

이 모듈은 `swarm_api.geo` 자체를 가리킨다(같은 객체). 내장 MA(algorithms)와 Agent 런타임은 쓰지 않는다.
"""

import sys

from swarm_api import geo as _m

sys.modules[__name__] = _m
