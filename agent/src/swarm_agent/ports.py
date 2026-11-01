"""L1 포트 구현 (IMP-AGT-003, DEC-013).

MA 플러그인은 이 포트로만 외부와 통신한다. 포트는 버스 객체를 갖지 않고 Vehicle을 거쳐
런타임에 송신을 맡긴다. sim/ctrl·truth·link는 어떤 포트로도 보이지 않는다.

수신 버퍼는 이중 버퍼다. 프레임 사이에 도착한 메시지는 pending에 쌓이고, 프레임 시작 때
current로 넘어간다. inbox()는 current를 돌려주고 비운다 ("지난 프레임 이후 도착한 메시지").
"""

from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING

from google.protobuf.message import Message

from swarm.v1 import c2_pb2, mp_pb2, ms_pb2, vi_pb2

if TYPE_CHECKING:
    from .vehicle import Vehicle

_STATUS_LIMIT = 256
_MS_COMMANDS = ("SensorCommand", "JammerCommand", "StrikeCommand")


class FrameBuffer:
    """프레임 단위 이중 버퍼"""

    def __init__(self, limit: int = 4096) -> None:
        self._pending: deque[Message] = deque(maxlen=limit)
        self._current: list[Message] = []

    def push(self, msg: Message) -> None:
        self._pending.append(msg)

    def flip(self) -> None:
        self._current = list(self._pending)
        self._pending.clear()

    def take(self) -> list[Message]:
        out, self._current = self._current, []
        return out

    def peek(self) -> list[Message]:
        return list(self._current)

    def clear(self) -> None:
        self._pending.clear()
        self._current = []


class C2PortImpl:
    def __init__(self, vehicle: "Vehicle") -> None:
        self._v = vehicle
        self.buffer = FrameBuffer()

    def inbox(self) -> Sequence[Message]:
        return self.buffer.take()

    def send(self, msg: Message) -> None:
        gcs = self._v.spec.controlling_gcs
        if not gcs:
            self._v.warn("c2 send dropped: no controlling_gcs")
            return
        self._v.send_link("c2", msg, [gcs])


class VIPortImpl:
    def __init__(self, vehicle: "Vehicle") -> None:
        self._v = vehicle
        self._status: deque[vi_pb2.FlightCommandStatus] = deque(maxlen=_STATUS_LIMIT)
        self._n = 0

    def nav(self) -> vi_pb2.NavigationReport | None:
        return self._v.nav

    def capability(self) -> vi_pb2.FlightCapability:
        return self._v.capability

    def system_status(self) -> vi_pb2.SystemStatus | None:
        return self._v.system_status

    def command(self, cmd: vi_pb2.FlightCommand) -> None:
        if not cmd.command_id:
            self._n += 1
            cmd.command_id = f"{self._v.entity_id}-fc-{self._n}"
        self._v.stamp(cmd)
        self.push_status(self._v.fa.on_command(cmd))

    def command_status(self) -> Sequence[vi_pb2.FlightCommandStatus]:
        out = list(self._status)
        self._status.clear()
        return out

    def push_status(self, st: vi_pb2.FlightCommandStatus) -> None:
        self._v.stamp(st)
        self._status.append(st)


class MSPortImpl:
    def __init__(self, vehicle: "Vehicle") -> None:
        self._v = vehicle
        self._loadout = ms_pb2.StoreLoadout(stores=list(vehicle.spec.payloads))
        self.detection_buffer = FrameBuffer()
        self.activity_buffer = FrameBuffer()

    def loadout(self) -> ms_pb2.StoreLoadout:
        return self._loadout

    def detections(self) -> Sequence[ms_pb2.Detection]:
        return self.detection_buffer.take()

    def command(self, msg: Message) -> None:
        name = msg.DESCRIPTOR.name
        if name not in _MS_COMMANDS:
            raise TypeError(f"ms.command: unsupported message {name}")
        self._v.send_onboard(msg)

    def activities(self) -> Sequence[Message]:
        return self.activity_buffer.take()

    def on_activity(self, msg: Message) -> None:
        # 발사가 확인되면 잔량을 줄인다
        if isinstance(msg, ms_pb2.StrikeActivity) and msg.state == ms_pb2.STRIKE_STATE_LAUNCHED:
            for store in self._loadout.stores:
                if store.id == msg.payload_id and store.count > 0:
                    store.count -= 1
        self.activity_buffer.push(msg)


class MPPortImpl:
    def __init__(self, vehicle: "Vehicle", plan: mp_pb2.MissionPlan | None,
                 criteria: mp_pb2.EngagementCriteria | None) -> None:
        self._v = vehicle
        self._plan = self._own(plan) if plan is not None else None
        self._criteria = criteria
        self._routes: dict[str, mp_pb2.RoutePlan] = {}

    def _own(self, plan: mp_pb2.MissionPlan) -> mp_pb2.MissionPlan:
        """이 기체가 맡은 작업과 속한 편대만 남긴다"""
        eid = self._v.entity_id
        out = mp_pb2.MissionPlan()
        out.header.CopyFrom(plan.header)
        out.plan_id = plan.plan_id
        out.tasks.extend(t for t in plan.tasks if eid in t.assignees)
        out.formations.extend(f for f in plan.formations if eid in f.members)
        return out

    def mission_plan(self) -> mp_pb2.MissionPlan | None:
        return self._plan

    def route_plans(self) -> Sequence[mp_pb2.RoutePlan]:
        return [self._routes[k] for k in sorted(self._routes)]

    def engagement_criteria(self) -> mp_pb2.EngagementCriteria | None:
        return self._criteria

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, mp_pb2.MissionPlan):
            self._plan = self._own(msg)
        elif isinstance(msg, mp_pb2.RoutePlan):
            if not msg.entity_id or msg.entity_id == self._v.entity_id:
                self._routes[msg.route_id] = msg
        elif isinstance(msg, mp_pb2.EngagementCriteria):
            self._criteria = msg


class P2PPortImpl:
    def __init__(self, vehicle: "Vehicle") -> None:
        self._v = vehicle
        self.buffer = FrameBuffer()

    def send(self, msg: Message, to: Sequence[str] | None = None) -> None:
        self._v.send_link("p2p", msg, list(to) if to else [])

    def inbox(self) -> Sequence[Message]:
        return self.buffer.take()


class MDPortImpl:
    """지표 기록. 계약에 MD 메시지·키가 없어 런타임 메모리에만 남긴다 (계약 변경 요청)"""

    def __init__(self, vehicle: "Vehicle", limit: int = 10000) -> None:
        self._v = vehicle
        self.records: deque[tuple[int, str, float | str]] = deque(maxlen=limit)

    def record(self, name: str, value: float | str) -> None:
        self.records.append((self._v.frame, name, value))


class PortsImpl:
    def __init__(self, vehicle: "Vehicle", plan: mp_pb2.MissionPlan | None,
                 criteria: mp_pb2.EngagementCriteria | None) -> None:
        self.c2 = C2PortImpl(vehicle)
        self.vi = VIPortImpl(vehicle)
        self.ms = MSPortImpl(vehicle)
        self.mp = MPPortImpl(vehicle, plan, criteria)
        self.p2p = P2PPortImpl(vehicle)
        self.md = MDPortImpl(vehicle)

    def flip(self) -> None:
        self.c2.buffer.flip()
        self.p2p.buffer.flip()
        self.ms.detection_buffer.flip()
        self.ms.activity_buffer.flip()


# c2 수신으로 받는 메시지 (그 밖의 것은 버린다)
C2_INBOUND = (c2_pb2.TaskCommand, c2_pb2.FormationCommand, c2_pb2.GroupAssignment, c2_pb2.ApprovalResponse)
