"""GCS 자동 보고용 키별 변화 추적 (IMP-AGT-029~032, DEC-051, DEC-056, DEC-063, DEC-071).

기체 하나·보고 묶음 하나마다 둔다. 판단은 모두 모의 시간이라 lockstep에서 결정적이다.
"""

from collections.abc import Callable

from google.protobuf.message import Message

from swarm.v1 import common_pb2, ms_pb2

ReportKey = tuple[str, str, str]   # (메시지, 부키1, 부키2). 쓰지 않는 자리는 ""


class ChangeReporter:
    """헤더를 뺀 값이 바뀐 키를 기억했다가 키별 최소 간격을 지켜 최신 값으로 내준다.

    - 미룬 변화는 다음 허용 시점에 그때 최신 값으로 한 번 나간다 (DEC-056)
    - period를 주면 그 값이 바뀔 때 저장된 전체를 내준다(주기 전체 보고, DEC-051)
    - terminal(key, msg)이 참인 값은 한 번 내준 뒤 저장소에서 지운다 (DEC-063).
      송신 시각은 최소 간격이 지나면 버려 저장소가 계속 커지지 않는다
    """

    def __init__(self, terminal: Callable[[ReportKey, Message], bool] | None = None) -> None:
        self._terminal = terminal or (lambda k, m: False)
        self.state: dict[ReportKey, tuple[bytes, Message]] = {}
        self.dirty: set[ReportKey] = set()
        self.sent: dict[ReportKey, int] = {}   # 키 → 마지막으로 내준 모의 시각
        self._period: int | None = None

    def note(self, key: ReportKey, msg: Message) -> None:
        copy = type(msg)()
        copy.CopyFrom(msg)
        body = type(msg)()
        body.CopyFrom(msg)
        body.ClearField("header")
        blob = body.SerializeToString(deterministic=True)
        prev = self.state.get(key)
        self.state[key] = (blob, copy)
        if prev is None or prev[0] != blob:
            self.dirty.add(key)

    def due(self, sim_time_us: int, min_gap_us: int, period: int | None = None) -> list[Message]:
        if period is not None and self._period != period:
            self._period = period
            keys = set(self.state)
        else:
            keys = {k for k in self.dirty if k not in self.sent or sim_time_us - self.sent[k] >= min_gap_us}
        out: list[Message] = []
        for k in sorted(keys):
            msg = self.state[k][1]
            out.append(msg)
            self.sent[k] = sim_time_us
            if self._terminal(k, msg):
                del self.state[k]
        self.dirty -= keys
        for k in [k for k, t in self.sent.items() if k not in self.state and sim_time_us - t >= min_gap_us]:
            del self.sent[k]
        return out


# 종료 상태: 한 번 보낸 키는 저장소에서 지운다
STRIKE_TERMINAL = frozenset({ms_pb2.STRIKE_STATE_IMPACT, ms_pb2.STRIKE_STATE_MISSED, ms_pb2.STRIKE_STATE_REJECTED})  # DEC-063
COMMAND_TERMINAL = frozenset({common_pb2.COMMAND_STATE_REJECTED, common_pb2.COMMAND_STATE_COMPLETED,
                              common_pb2.COMMAND_STATE_FAILED, common_pb2.COMMAND_STATE_CANCELLED})


def activity_key(name: str, msg: Message) -> ReportKey:
    """StrikeActivity는 무장별, 나머지는 (메시지, payload_id)별. weapon_entity가 비면 "" 그대로 (DEC-063)"""
    return (name, msg.payload_id, msg.weapon_entity if name == "StrikeActivity" else "")


def activity_terminal(k: ReportKey, msg: Message) -> bool:
    return k[0] == "StrikeActivity" and msg.state in STRIKE_TERMINAL


def vi_key(name: str, msg: Message) -> ReportKey:
    """SystemStatus는 기체당 하나, FlightCommandStatus는 command_id별 (DEC-071)"""
    return (name, msg.command_id if name == "FlightCommandStatus" else "", "")


def vi_terminal(k: ReportKey, msg: Message) -> bool:
    return k[0] == "FlightCommandStatus" and msg.state in COMMAND_TERMINAL
