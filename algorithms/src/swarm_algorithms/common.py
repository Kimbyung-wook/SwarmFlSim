"""MA 공용 부품 (IMP-AGT-011, IMP-AGT-016~017): 작업 추적, 작업 → 비행 구간, PeerStatus.

플러그인은 ctx.ports로만 송수신한다 (DEC-013). 여기 함수들도 ctx 밖의 상태를 보지 않는다.
"""

import math
from collections import deque
from dataclasses import dataclass

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message

from swarm.v1 import c2_pb2, common_pb2, p2p_pb2, vi_pb2
from swarm_api import AgentContext
from swarm_agent.geo import G_MPS2, ned_offset, wrap_pi
from swarm_agent.racetrack import path_error

S = common_pb2
PILOT_TASKS = ("move_to", "hold", "return_to_base", "search_area", "route")


def area_centroid(area) -> tuple[float, float]:
    if area.WhichOneof("shape") == "circle":
        return area.circle.center.lat_deg, area.circle.center.lon_deg
    vs = area.polygon.vertices
    return sum(v.lat_deg for v in vs) / len(vs), sum(v.lon_deg for v in vs) / len(vs)


def area_circle(area) -> tuple[float, float, float]:
    """정찰 원(중심 위도, 경도, 반경 m). 다각형은 중심에서 가장 먼 꼭짓점까지를 반경으로 둔다"""
    if area.WhichOneof("shape") == "circle":
        c = area.circle
        return c.center.lat_deg, c.center.lon_deg, c.radius_m
    lat, lon = area_centroid(area)
    r = 0.0
    for v in area.polygon.vertices:
        n, e = ned_offset(lat, lon, v.lat_deg, v.lon_deg)
        r = max(r, math.hypot(float(n), float(e)))
    return lat, lon, r


@dataclass
class Goal:
    task_id: str
    kind: str                 # move_to | hold | return_to_base | search_area
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0          # 0이면 현재 고도 유지
    speed: float | None = None
    # hold (DEC-033)
    has_center: bool = False  # False면 작업을 시작한 위치에서 선회
    radius: float | None = None
    duration: float | None = None  # None이면 다음 명령까지
    direction: int = vi_pb2.TURN_DIRECTION_UNSPECIFIED
    racetrack: tuple[float, float] | None = None  # (직선 구간 길이 m, 축 방향 deg), DEC-034


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
            self.queue.extend(t for t in plan.tasks
                              if t.WhichOneof("task") in supported and not invalid_reason(t))

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
        if not msg.assignees:  # 대상이 없는 명령은 거부한다. 받은 기체마다 REJECTED를 보낸다 (DEC-038)
            self.status(msg, S.COMMAND_STATE_REJECTED, reason="empty assignees")
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
        reason = invalid_reason(msg)
        if reason:
            self.status(msg, S.COMMAND_STATE_REJECTED, reason=reason)
            return True
        if self.current is not None and self.current.task_id == msg.task_id:
            pass  # 같은 task_id: 내용 교체 (DEC-033). 이전 것을 취소로 보고하지 않는다
        elif self.current is not None:
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
        if kind == "hold":
            h = t.hold
            g = Goal(t.task_id, kind, radius=h.radius_m if h.HasField("radius_m") else None,
                     duration=h.duration_s if h.HasField("duration_s") and h.duration_s > 0 else None,
                     direction=h.direction,
                     racetrack=(h.racetrack.leg_length_m, h.racetrack.axis_heading_deg)
                     if h.HasField("racetrack") else None)
            if h.HasField("center"):
                g.has_center = True
                g.lat, g.lon, g.alt = h.center.lat_deg, h.center.lon_deg, h.center.alt_m
            return g
        return Goal(t.task_id, kind)


# 임무 값 검증 한계 (DEC-038). 지도는 한반도 전역(DEC-016)을 넉넉히 덮는다
MAP_LAT_DEG = (30.0, 45.0)
MAP_LON_DEG = (120.0, 135.0)
ALT_MAX_M = 30000.0            # alt 0은 "현재 고도 유지"
SPEED_MAX_MPS = 1000.0
RADIUS_MAX_M = 100000.0
DURATION_MAX_S = 86400.0 * 7
ROUTE_MAX_POINTS = 200
AREA_MAX_VERTICES = 100


def _bad_geo(g, name: str) -> str:
    for v, lo, hi, what in ((g.lat_deg, *MAP_LAT_DEG, "lat"), (g.lon_deg, *MAP_LON_DEG, "lon")):
        if not math.isfinite(v):
            return f"{name} {what} not finite"
        if not lo <= v <= hi:
            return f"{name} {what} out of map"
    if not math.isfinite(g.alt_m) or not 0.0 <= g.alt_m <= ALT_MAX_M:
        return f"{name} alt out of range"
    return ""


def _bad_num(v: float, lo: float, hi: float, name: str, lo_open: bool = False) -> str:
    if not math.isfinite(v):
        return f"{name} not finite"
    if v < lo or v > hi or (lo_open and v == lo):
        return f"{name} out of range"
    return ""


def _bad_racetrack(r, name: str) -> str:
    return (_bad_num(r.leg_length_m, 0.0, RADIUS_MAX_M, f"{name} leg_length_m")
            or _bad_num(r.axis_heading_deg, -360.0, 360.0, f"{name} axis_heading_deg"))


def _bad_area(a) -> str:
    shape = a.WhichOneof("shape")
    if shape is None:
        return "search area without shape"
    if shape == "circle":
        return (_bad_geo(a.circle.center, "area center")
                or _bad_num(a.circle.radius_m, 0.0, RADIUS_MAX_M, "area radius_m", lo_open=True))
    vs = a.polygon.vertices
    if len(vs) < 3:
        return "area polygon needs 3+ vertices"
    if len(vs) > AREA_MAX_VERTICES:
        return "area polygon too many vertices"
    for v in vs:
        r = _bad_geo(v, "area vertex")
        if r:
            return r
    return ""


_REAL = (FieldDescriptor.TYPE_DOUBLE, FieldDescriptor.TYPE_FLOAT)


def non_finite_field(msg: Message, path: str = "") -> str:
    """메시지의 모든 실수 필드(중첩·반복 포함)에서 NaN·inf를 찾아 경로를 돌려준다. 없으면 빈 문자열.
    필드 종류별 검사보다 먼저 한 곳에서 수행하므로 새 필드가 늘어도 빠지지 않는다 (QA-014)"""
    for fd in msg.DESCRIPTOR.fields:
        if fd.is_repeated:
            vals = getattr(msg, fd.name)
            items = list(enumerate(vals))
            if fd.message_type is not None and fd.message_type.GetOptions().map_entry:
                continue
        elif fd.type == FieldDescriptor.TYPE_MESSAGE:
            if not msg.HasField(fd.name):
                continue
            items = [(None, getattr(msg, fd.name))]
        else:
            items = [(None, getattr(msg, fd.name))]
        for i, v in items:
            name = f"{path}{fd.name}" + (f"[{i}]" if i is not None else "")
            if fd.type == FieldDescriptor.TYPE_MESSAGE:
                r = non_finite_field(v, name + ".")
                if r:
                    return r
            elif fd.type in _REAL and not math.isfinite(v):
                return name
    return ""


def invalid_reason(t: c2_pb2.TaskCommand) -> str:
    """임무 값 검증. 사유를 돌려주고, 문제가 없으면 빈 문자열 (DEC-038)"""
    if not t.task_id:
        return "empty task_id"
    bad = non_finite_field(t)
    if bad:
        return f"{bad} not finite"
    kind = t.WhichOneof("task")
    if kind == "move_to":
        return (_bad_geo(t.move_to.destination, "destination")
                or (_bad_num(t.move_to.speed_mps, 0.0, SPEED_MAX_MPS, "speed_mps")
                    if t.move_to.HasField("speed_mps") else ""))
    if kind == "route":
        if not t.route.waypoints:
            return "empty route"
        if len(t.route.waypoints) > ROUTE_MAX_POINTS:
            return f"route has more than {ROUTE_MAX_POINTS} waypoints"
        for i, w in enumerate(t.route.waypoints):
            r = _bad_geo(w.position, f"waypoint {i}")
            action = w.WhichOneof("action")
            if not r and action == "loiter":
                a = w.loiter
                r = (_bad_num(a.duration_s, 0.0, DURATION_MAX_S, "loiter duration_s")
                     or (_bad_num(a.radius_m, 0.0, RADIUS_MAX_M, "loiter radius_m", lo_open=True)
                         if a.HasField("radius_m") else "")
                     or (_bad_racetrack(a.racetrack, "loiter racetrack") if a.HasField("racetrack") else ""))
            elif not r and action == "recon":
                r = _bad_num(w.recon.radius_m, 0.0, RADIUS_MAX_M, "recon radius_m", lo_open=True)
            if r:
                return r
        return ""
    if kind == "hold":
        h = t.hold
        if h.HasField("center"):
            r = _bad_geo(h.center, "hold center")
            if r:
                return r
        return ((_bad_num(h.radius_m, 0.0, RADIUS_MAX_M, "hold radius_m", lo_open=True)
                 if h.HasField("radius_m") else "")
                or (_bad_num(h.duration_s, 0.0, DURATION_MAX_S, "hold duration_s")
                    if h.HasField("duration_s") else "")
                or (_bad_racetrack(h.racetrack, "racetrack") if h.HasField("racetrack") else ""))
    if kind == "search_area":
        return _bad_area(t.search_area.area)
    return ""


@dataclass
class Leg:
    """작업을 이루는 비행 구간. goto는 FA Waypoint, orbit은 FA Orbit으로 수행한다"""
    kind: str                       # goto | orbit
    lat: float
    lon: float
    alt: float                      # 0이면 현재 고도 유지
    speed: float | None = None
    acceptance: float = 0.0         # goto
    radius: float = 0.0             # orbit
    direction: int = vi_pb2.TURN_DIRECTION_CW
    duration: float | None = None   # orbit: 원 위에서 보낼 시간
    revs: float = 0.0               # orbit: duration이 없을 때 최소 바퀴 수. 둘 다 없으면 끝나지 않는다
    wp_index: int = -1              # 이 구간을 마치면 항로점 wp_index를 마친 것으로 센다
    racetrack: tuple[float, float] | None = None  # orbit: (직선 구간 길이 m, 축 방향 deg). 중심 = 레이스트랙 중점


def orbit_done(leg: Leg, on_station_s: float, angle_rad: float) -> bool:
    if leg.duration is not None:
        return on_station_s >= leg.duration
    return leg.revs > 0 and angle_rad >= 2.0 * math.pi * leg.revs


def turn_radius(speed_mps: float, bank_max_deg: float = 35.0) -> float:
    return speed_mps * speed_mps / (G_MPS2 * math.tan(math.radians(bank_max_deg)))


class TaskPilot:
    """작업을 비행 구간(Leg) 목록으로 바꿔 차례로 수행한다 (waypoint MA, 편대 리더).

    - move_to·return_to_base: goto 1개. FA가 COMPLETED를 보내면 작업 완료
    - hold: orbit 1개. center가 없으면 작업 시작 위치·고도, radius가 없으면 hold_radius_m, 방향이 없으면 CW.
      duration_s가 있으면 원 위에서 그 시간을 보낸 뒤 완료, 없으면 다음 명령까지
    - search_area: 정찰 원(원 영역, 다각형은 외접 원) orbit 1개, 1바퀴 뒤 완료
    - route: 항로점마다 goto(그 점의 alt_m·speed_mps·acceptance) + 행위 orbit(loiter: duration,
      recon: duration 또는 1바퀴). loop면 끝없이 반복. progress = 이번 바퀴에서 마친 항로점 / 전체
    - orbit 반경은 그 속력의 최소 선회 반경 × 1.3 이상으로 둔다. "원 위"는 |거리 − 반경| < max(0.25·반경, 50 m)
    """

    def __init__(self, ctx: AgentContext, acceptance_m: float = 80.0, hold_radius_m: float = 300.0,
                 speed_mps: float | None = None, supported: tuple[str, ...] = PILOT_TASKS):
        self.ctx = ctx
        self.tracker = TaskTracker(ctx, supported)
        self.acceptance_m = acceptance_m
        self.hold_radius_m = hold_radius_m
        self.speed_mps = speed_mps  # 작업에 속도가 없을 때
        self.cmd_task: dict[str, c2_pb2.TaskCommand] = {}
        self._n = 0
        self._started: set[int] = set()  # EXECUTING을 보낸 작업 (id(task))
        self.legs: list[Leg] = []
        self.leg_i = 0
        self._cmd_id = ""
        self._on_station_since: float | None = None
        self._angle = 0.0
        self._last_bearing: float | None = None

    @property
    def leg(self) -> Leg | None:
        return self.legs[self.leg_i] if self.leg_i < len(self.legs) else None

    def step(self, c2_msgs: list[Message] | None = None) -> None:
        ports = self.ctx.ports
        for m in ports.c2.inbox() if c2_msgs is None else c2_msgs:
            self.tracker.handle(m)
        nav = ports.vi.nav()
        self.tracker.update(nav)
        task = self.tracker.current
        for st in ports.vi.command_status():
            if task is None or st.command_id != self._cmd_id or self.cmd_task.get(st.command_id) is not task:
                continue
            if st.state == S.COMMAND_STATE_EXECUTING and id(task) not in self._started:
                self._started.add(id(task))
                self.tracker.status(task, S.COMMAND_STATE_EXECUTING, self.progress())
            elif st.state == S.COMMAND_STATE_COMPLETED and self.leg is not None and self.leg.kind == "goto":
                self._next_leg(nav)
            elif st.state in (S.COMMAND_STATE_REJECTED, S.COMMAND_STATE_FAILED):
                self.legs, self.leg_i, self._cmd_id = [], 0, ""
                self.tracker.finish(S.COMMAND_STATE_FAILED, st.reason)
                self.tracker.changed = False
        if self.tracker.changed and nav is not None:
            self.tracker.changed = False
            self.legs, self.leg_i, self._cmd_id = [], 0, ""
            if self.tracker.current is not None:
                self.legs = self._plan(self.tracker.current, nav)
                self._command(nav)
        elif nav is not None and self.leg is not None and self.leg.kind == "orbit" and self._cmd_id:
            self._track_orbit(nav)

    # ---- 구간 계획 ----

    def _plan(self, t: c2_pb2.TaskCommand, nav: vi_pb2.NavigationReport) -> list[Leg]:
        kind = t.WhichOneof("task")
        p = nav.kinematics.position
        if kind == "route":
            return self._route_legs(t.route)
        if kind == "search_area":
            lat, lon, r = area_circle(t.search_area.area)
            return [Leg("orbit", lat, lon, 0.0, self.speed_mps, radius=r, revs=1.0)]
        g = self.tracker.goal()
        if kind == "hold":
            lat, lon, alt = (g.lat, g.lon, g.alt) if g.has_center else (p.lat_deg, p.lon_deg, p.alt_m)
            return [Leg("orbit", lat, lon, alt, self.speed_mps, radius=g.radius or self.hold_radius_m,
                        direction=g.direction or vi_pb2.TURN_DIRECTION_CW, duration=g.duration,
                        racetrack=g.racetrack)]
        speed = g.speed if g.speed is not None else self.speed_mps
        return [Leg("goto", g.lat, g.lon, g.alt, speed, self.acceptance_m)]

    def _route_legs(self, route: c2_pb2.RouteTask) -> list[Leg]:
        legs = []
        for i, w in enumerate(route.waypoints):
            pos = w.position
            speed = w.speed_mps if w.HasField("speed_mps") else self.speed_mps
            acc = w.acceptance_radius_m if w.HasField("acceptance_radius_m") else self.acceptance_m
            action = w.WhichOneof("action")
            legs.append(Leg("goto", pos.lat_deg, pos.lon_deg, pos.alt_m, speed, acc,
                            wp_index=-1 if action else i))
            if action == "loiter":
                a = w.loiter
                legs.append(Leg("orbit", pos.lat_deg, pos.lon_deg, pos.alt_m, speed,
                                radius=a.radius_m if a.HasField("radius_m") else self.hold_radius_m,
                                direction=a.direction or vi_pb2.TURN_DIRECTION_CW,
                                duration=a.duration_s, wp_index=i,
                                racetrack=(a.racetrack.leg_length_m, a.racetrack.axis_heading_deg)
                                if a.HasField("racetrack") else None))
            elif action == "recon":
                a = w.recon
                legs.append(Leg("orbit", pos.lat_deg, pos.lon_deg, pos.alt_m, speed, radius=a.radius_m,
                                duration=a.duration_s if a.HasField("duration_s") else None, revs=1.0,
                                wp_index=i))
        return legs

    def progress(self) -> float:
        t = self.tracker.current
        if t is None or t.WhichOneof("task") != "route":
            return 0.0
        done = sum(1 for leg in self.legs[:self.leg_i] if leg.wp_index >= 0)
        return done / len(t.route.waypoints)

    # ---- 구간 진행 ----

    def _next_leg(self, nav: vi_pb2.NavigationReport | None) -> None:
        task = self.tracker.current
        finished = self.leg
        self.leg_i += 1
        if self.leg_i >= len(self.legs):
            if task.WhichOneof("task") == "route" and task.route.loop:
                self.tracker.status(task, S.COMMAND_STATE_EXECUTING, 1.0)
                self.leg_i = 0
            else:
                self.legs, self.leg_i, self._cmd_id = [], 0, ""
                self.tracker.finish(S.COMMAND_STATE_COMPLETED)
                self.tracker.changed = False
                return
        elif finished is not None and finished.wp_index >= 0:
            self.tracker.status(task, S.COMMAND_STATE_EXECUTING, self.progress())
        if nav is not None:
            self._command(nav)
        else:
            self._cmd_id = ""

    def _track_orbit(self, nav: vi_pb2.NavigationReport) -> None:
        leg = self.leg
        p = nav.kinematics.position
        n, e = ned_offset(leg.lat, leg.lon, p.lat_deg, p.lon_deg)
        if leg.racetrack is not None:
            err = path_error(float(n), float(e), leg.radius, leg.racetrack[0],
                             math.radians(leg.racetrack[1]))
        else:
            err = abs(math.hypot(float(n), float(e)) - leg.radius)
        if err < max(0.25 * leg.radius, 50.0):
            if self._on_station_since is None:
                self._on_station_since = self.ctx.sim_time_s
            b = math.atan2(float(e), float(n))
            if self._last_bearing is not None:
                self._angle += abs(float(wrap_pi(b - self._last_bearing)))
            self._last_bearing = b
        if self._on_station_since is not None and orbit_done(
                leg, self.ctx.sim_time_s - self._on_station_since, self._angle):
            self._next_leg(nav)

    def _command(self, nav: vi_pb2.NavigationReport) -> None:
        leg = self.leg
        self._n += 1
        cmd = vi_pb2.FlightCommand(command_id=f"{self.ctx.entity_id}-task-{self._n}")
        speed = leg.speed
        if leg.kind == "orbit":
            v = speed if speed is not None else math.hypot(nav.kinematics.velocity_ned_mps.x,
                                                           nav.kinematics.velocity_ned_mps.y)
            leg.radius = max(leg.radius, 1.3 * turn_radius(max(v, 12.0)))
            o = cmd.curve.racetrack if leg.racetrack is not None else cmd.curve.orbit
            if leg.racetrack is not None:
                o.leg_length_m, o.axis_heading_deg = leg.racetrack
            o.center.lat_deg, o.center.lon_deg, o.center.alt_m = leg.lat, leg.lon, leg.alt
            o.radius_m = leg.radius
            o.direction = leg.direction
            if speed is not None:
                o.speed_mps = speed
            self._on_station_since, self._angle, self._last_bearing = None, 0.0, None
        else:
            wp = cmd.waypoint.waypoints.add(acceptance_radius_m=leg.acceptance)
            wp.position.lat_deg, wp.position.lon_deg, wp.position.alt_m = leg.lat, leg.lon, leg.alt
            if speed is not None:
                wp.speed_mps = speed
        self.cmd_task[cmd.command_id] = self.tracker.current
        self._cmd_id = cmd.command_id
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
