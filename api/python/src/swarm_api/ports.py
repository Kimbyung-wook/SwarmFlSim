"""MA 플러그인이 쓰는 L1 포트 (DEC-013).

MA 플러그인은 이 포트로만 외부와 통신한다. 포트 구현(버스 연결, 데이터링크 경유)은
Agent 런타임(WP3)이 맡는다. 메시지 타입은 swarm.v1 생성 코드(scripts/gen_proto.py)다.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from google.protobuf.message import Message

    from swarm.v1 import mp_pb2, ms_pb2, vi_pb2


class C2Port(Protocol):
    """GCS ⇄ 기체. 수신: TaskCommand, FormationCommand, GroupAssignment, ApprovalResponse"""

    def inbox(self) -> "Sequence[Message]":
        """지난 프레임 이후 도착한 메시지. 호출하면 비워진다."""
        ...

    def send(self, msg: "Message") -> None:
        """통제 GCS로 보낸다. TaskStatus, ApprovalRequest"""
        ...


class VIPort(Protocol):
    """MA ⇄ FA"""

    def nav(self) -> "vi_pb2.NavigationReport | None": ...

    def capability(self) -> "vi_pb2.FlightCapability": ...

    def system_status(self) -> "vi_pb2.SystemStatus | None": ...

    def command(self, cmd: "vi_pb2.FlightCommand") -> None: ...

    def command_status(self) -> "Sequence[vi_pb2.FlightCommandStatus]": ...


class MSPort(Protocol):
    """임무장비·무장"""

    def loadout(self) -> "ms_pb2.StoreLoadout": ...

    def detections(self) -> "Sequence[ms_pb2.Detection]": ...

    def command(self, msg: "Message") -> None:
        """SensorCommand, JammerCommand, StrikeCommand"""
        ...

    def activities(self) -> "Sequence[Message]":
        """SensorActivity, JammerActivity, StrikeActivity"""
        ...


class MPPort(Protocol):
    def mission_plan(self) -> "mp_pb2.MissionPlan | None": ...

    def route_plans(self) -> "Sequence[mp_pb2.RoutePlan]": ...

    def engagement_criteria(self) -> "mp_pb2.EngagementCriteria | None": ...


class P2PPort(Protocol):
    """기체 간. 데이터링크를 거치므로 손실·지연이 있다."""

    def send(self, msg: "Message", to: Sequence[str] | None = None) -> None:
        """to가 None이면 브로드캐스트"""
        ...

    def inbox(self) -> "Sequence[Message]": ...


class MDPort(Protocol):
    """알고리즘 지표를 MCAP에 기록한다."""

    def record(self, name: str, value: float | str) -> None: ...


class Ports(Protocol):
    c2: C2Port
    vi: VIPort
    ms: MSPort
    mp: MPPort
    p2p: P2PPort
    md: MDPort
