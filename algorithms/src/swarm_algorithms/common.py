"""MA 공용 부품 (IMP-AGT-011): 작업 추적, 작업 → 비행 명령, PeerStatus.

플러그인은 ctx.ports로만 송수신한다 (DEC-013). 여기 함수들도 ctx 밖의 상태를 보지 않는다.
"""

import math
from collections import deque
from dataclasses import dataclass

from google.protobuf.message import Message

from swarm.v1 import c2_pb2, common_pb2, p2p_pb2, vi_pb2
from swarm_api import AgentContext
from swarm_agent.geo import ned_offset

S = common_pb2


def area_centroid(area) -> tuple[float, float]:
    if area.WhichOneof("shape") == "circle":
        return area.circle.center.lat_deg, area.circle.center.lon_deg
    vs = area.polygon.vertices
    return sum(v.lat_deg for v in vs) / len(vs), sum(v.lon_deg for v in vs) / len(vs)


@dataclass
class Goal:
    task_id: str
    kind: str                 # move_to | hold | return_to_base | search_area
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0          # 0이면 현재 고도 유지
    speed: float | None = None


class TaskTracker:
    """MissionPlan 작업을 순서대로, C2 TaskCommand는 받는 즉시(현재 작업을 밀어내고) 처리한다.

    상태는 TaskStatus로 통제 GCS에 보낸다. 지원하지 않는 작업은 C2면 REJECTED, 계획이면 건너뛴다.
    """

    def __init__(self, ctx: AgentContext, supported: tuple[str, ...] = ("move_to", "hold", "return_to_base")):
        self.ctx = ctx
        self.supported = supported
        self.queue: deque[c2_pb2.TaskCommand] = deque()
        self.current: c2_pb2.TaskCommand | None = None
        self.home: tuple[float, float, float] | None = None
        self.changed = False  # 현재 작업이 바뀌었으면 True. 호출자가 지운다
        plan = ctx.ports.mp.mission_plan()
        if plan is not None:
            self.queue.extend(t for t in plan.tasks if t.WhichOneof("task") in supported)

    def status(self, task: c2_pb2.TaskCommand, state: int, progress: float = 0.0, reason: str = "") -> None:
        st = c2_pb2.TaskStatus(task_id=task.task_id, state=state, progress=progress, reason=reason)
        st.header.correlation_id = task.task_id
        self.ctx.ports.c2.send(st)

    def handle(self, msg: Message) -> bool:
        """C2 메시지 하나를 처리한다. TaskCommand가 아니면 False"""
        if not isinstance(msg, c2_pb2.TaskCommand):
            return False
        if msg.assignees and self.ctx.entity_id not in msg.assignees:
            return True
        if msg.cancel:
            if self.current is not None and self.current.task_id == msg.task_id:
                self.status(self.current, S.COMMAND_STATE_CANCELLED)
                self.current = None
                self.changed = True
            else:
                self.queue = deque(t for t in self.queue if t.task_id != msg.task_id)
            return True
        kind = msg.WhichOneof("task")
        if kind not in self.supported:
            self.status(msg, S.COMMAND_STATE_REJECTED, reason=f"unsupported task {kind}")
            return True
        if self.current is not None:
            self.status(self.current, S.COMMAND_STATE_CANCELLED, reason="preempted")
        self.current = msg
        self.changed = True
        self.status(msg, S.COMMAND_STATE_ACCEPTED)
        return True

    def update(self, nav: vi_pb2.NavigationReport | None) -> None:
        if nav is not None and self.home is None:
            p = nav.kinematics.position
            self.home = (p.lat_deg, p.lon_deg, p.alt_m)
        if self.current is None and self.queue:
            self.current = self.queue.popleft()
            self.changed = True
            self.status(self.current, S.COMMAND_STATE_ACCEPTED)

    def finish(self, state: int, reason: str = "") -> None:
        if self.current is not None:
            self.status(self.current, state, 1.0 if state == S.COMMAND_STATE_COMPLETED else 0.0, reason)
            self.current = None
            self.changed = True

    def goal(self) -> Goal | None:
        t = self.current
        if t is None:
            return None
        kind = t.WhichOneof("task")
        if kind == "move_to":
            d = t.move_to.destination
            return Goal(t.task_id, kind, d.lat_deg, d.lon_deg, d.alt_m,
                        t.move_to.speed_mps if t.move_to.HasField("speed_mps") else None)
        if kind == "return_to_base" and self.home is not None:
            return Goal(t.task_id, kind, *self.home)
        if kind == "search_area":
            lat, lon = area_centroid(t.search_area.area)
            return Goal(t.task_id, kind, lat, lon)
        return Goal(t.task_id, kind)


class TaskPilot:
    """작업을 FA 명령으로 바꿔 수행한다 (waypoint MA, 편대 리더).

    move_to·return_to_base → Waypoint, hold → 현재 위치 Orbit. FA가 COMPLETED를 보내면 작업 완료.
    """

    def __init__(self, ctx: AgentContext, acceptance_m: float = 80.0, hold_radius_m: float = 300.0,
                 speed_mps: float | None = None):
        self.ctx = ctx
        self.tracker = TaskTracker(ctx)
        self.acceptance_m = acceptance_m
        self.hold_radius_m = hold_radius_m
        self.speed_mps = speed_mps  # 작업에 속도가 없을 때
        self.cmd_task: dict[str, c2_pb2.TaskCommand] = {}
        self._n = 0
        self._started: set[str] = set()

    def step(self, c2_msgs: list[Message] | None = None) -> None:
        ports = self.ctx.ports
        for m in ports.c2.inbox() if c2_msgs is None else c2_msgs:
            self.tracker.handle(m)
        nav = ports.vi.nav()
        self.tracker.update(nav)
        for st in ports.vi.command_status():
            task = self.cmd_task.get(st.command_id)
            if task is None or self.tracker.current is not task:
                continue
            if st.state == S.COMMAND_STATE_EXECUTING and task.task_id not in self._started:
                self._started.add(task.task_id)
                self.tracker.status(task, S.COMMAND_STATE_EXECUTING)
            elif st.state == S.COMMAND_STATE_COMPLETED:
                self.tracker.finish(S.COMMAND_STATE_COMPLETED)
            elif st.state in (S.COMMAND_STATE_REJECTED, S.COMMAND_STATE_FAILED):
                self.tracker.finish(S.COMMAND_STATE_FAILED, st.reason)
        if self.tracker.changed and nav is not None:
            self.tracker.changed = False
            goal = self.tracker.goal()
            if goal is not None:
                self._command(goal, nav)

    def _command(self, goal: Goal, nav: vi_pb2.NavigationReport) -> None:
        self._n += 1
        cmd = vi_pb2.FlightCommand(command_id=f"{self.ctx.entity_id}-task-{self._n}")
        speed = goal.speed if goal.speed is not None else self.speed_mps
        if goal.kind == "hold":
            o = cmd.curve.orbit
            p = nav.kinematics.position
            o.center.lat_deg, o.center.lon_deg, o.center.alt_m = p.lat_deg, p.lon_deg, p.alt_m
            o.radius_m = self.hold_radius_m
            o.direction = vi_pb2.TURN_DIRECTION_CW
            if speed is not None:
                o.speed_mps = speed
        else:
            wp = cmd.waypoint.waypoints.add(acceptance_radius_m=self.acceptance_m)
            wp.position.lat_deg, wp.position.lon_deg, wp.position.alt_m = goal.lat, goal.lon, goal.alt
            if speed is not None:
                wp.speed_mps = speed
        self.cmd_task[cmd.command_id] = self.tracker.current
        self.ctx.ports.vi.command(cmd)


def peer_status(nav: vi_pb2.NavigationReport, group_id: str = "", task_id: str = "") -> p2p_pb2.PeerStatus:
    ps = p2p_pb2.PeerStatus(group_id=group_id, current_task_id=task_id)
    ps.kinematics.CopyFrom(nav.kinematics)
    ps.header.sim_time_us = nav.header.sim_time_us
    return ps


def every(ctx: AgentContext, hz: float) -> bool:
    """대략 hz 주기로 True. 기체마다 위상을 달리해 송신이 한 프레임에 몰리지 않게 한다"""
    if hz <= 0 or ctx.dt_s <= 0:
        return False
    k = max(1, round(1.0 / (hz * ctx.dt_s)))
    return (ctx.frame + sum(ctx.entity_id.encode())) % k == 0


def distance_m(nav: vi_pb2.NavigationReport, lat: float, lon: float) -> float:
    p = nav.kinematics.position
    n, e = ned_offset(p.lat_deg, p.lon_deg, lat, lon)
    return math.hypot(float(n), float(e))
