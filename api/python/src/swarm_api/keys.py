"""Zenoh 키 체계 (docs/10_contracts.md §3). C++ 쪽은 api/cpp/include/swarm/api/keys.hpp"""

import re
from enum import StrEnum

ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")


class Iface(StrEnum):
    C2 = "c2"
    VI = "vi"
    MS = "ms"
    MP = "mp"
    MD = "md"
    P2P = "p2p"


def check_entity_id(entity_id: str) -> str:
    if len(entity_id) > 32 or not ENTITY_ID_RE.match(entity_id):
        raise ValueError(f"invalid entity id: {entity_id!r}")
    return entity_id


# 시간 분배·시뮬레이션 통제
CLOCK_TICK = "sim/clock/tick"
SIM_CTRL_CMD = "sim/ctrl/cmd"
SIM_CTRL_STATUS = "sim/ctrl/status"


def clock_done(participant: str) -> str:
    return f"sim/clock/done/{check_entity_id(participant)}"


# L1 메시지 (데이터링크 경유)
def tx(src: str, iface: Iface, msg: str) -> str:
    return f"swarm/{check_entity_id(src)}/tx/{iface}/{msg}"


def rx(dst: str, iface: Iface, msg: str) -> str:
    return f"swarm/{check_entity_id(dst)}/rx/{iface}/{msg}"


TX_ALL = "swarm/*/tx/**"


def rx_all(dst: str) -> str:
    return f"swarm/{check_entity_id(dst)}/rx/**"


# 기체 내부 (데이터링크를 거치지 않음)
def onboard(entity_id: str, msg: str) -> str:
    return f"onboard/{check_entity_id(entity_id)}/{msg}"


# 데이터링크 관측
def link_outcome(src: str, dst: str) -> str:
    return f"link/outcome/{check_entity_id(src)}/{check_entity_id(dst)}"


def link_state(a: str, b: str) -> str:
    a, b = sorted((check_entity_id(a), check_entity_id(b)))
    return f"link/state/{a}/{b}"


# Ground truth
TRUTH_STATE = "truth/state"


def truth_event(kind: str) -> str:
    return f"truth/event/{kind}"


def keyexpr_matches(expr: str, key: str) -> bool:
    """Zenoh 키 표현식 일치 판정. `*`는 한 마디, `**`는 0개 이상 마디."""
    e = expr.split("/")
    k = key.split("/")

    def match(i: int, j: int) -> bool:
        if i == len(e):
            return j == len(k)
        if e[i] == "**":
            return any(match(i + 1, jj) for jj in range(j, len(k) + 1))
        if j == len(k):
            return False
        if e[i] == "*" or e[i] == k[j]:
            return match(i + 1, j + 1)
        return False

    return match(0, 0)


# MA 플러그인 런타임이 직접 구독·발행하면 안 되는 접두어 (DEC-013, DEC-014, PRP-SIM-003)
MA_FORBIDDEN_PREFIXES = ("sim/ctrl/", "truth/", "link/")
