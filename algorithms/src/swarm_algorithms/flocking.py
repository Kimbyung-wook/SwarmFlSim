"""MA "flocking" (IMP-AGT-015, IMP-AGT-018, PRP-BHV-002, PRP-BHV-003): Reynolds 분리·정렬·응집, 일괄 MA.

- 기체마다 자기 P2P inbox로 받은 PeerStatus로만 이웃 표를 만든다. 다른 기체의 표나 NavBatch의
  다른 행을 이웃 정보로 쓰지 않는다 (PRP-SIM-003). NavBatch는 자기 행만 쓴다.
- 계산은 이웃 표를 (N, M) 배열로 채워 NumPy로 한 번에 한다 (DEC-006).
- 목표 속도 = v_goal + w_align·(v̄ − v) + w_coh·r̄ + w_sep·Σ 분리, 수평만. 고도는 목표(없으면 첫 고도) 유지.
  v_goal: 목표점(MoveTo, SearchArea 중심, RTB)이 있으면 그쪽 방향 × cruise, 없으면 현재 침로 × cruise.
  목표점에 goal_radius_m 안으로 들어오면 작업을 COMPLETED로 보고하고 그 점을 계속 목표로 둔다.
  Hold (DEC-033): 중심(없으면 작업 시작 위치) 둘레 반경(없으면 hold_radius_m) 원의 접선 벡터장
  v_goal = normalize(t − clip((d − R)/R, ±1)·u) × cruise, u = 중심→자기 단위벡터, t = 방향(CW 기본) 접선.
  duration_s가 있으면 원 위(|d − R| < max(0.25R, 50 m))에 처음 든 뒤 그 시간이 지나면 COMPLETED.
  레이스트랙(DEC-034)이면 같은 중심·반경·방향으로 vector_field 레이스트랙 침로를 쓴다(체류 판정은 경로 오차).
  Route는 지원하지 않는다(REJECTED).
- params: group(같은 group_id 이웃만), cruise_mps(22), neighbor_radius_m(600), separation_m(80),
  w_sep(1.5), w_align(0.5), w_coh(0.02), peer_hz(5), stale_s(2), goal_radius_m(300),
  hold_radius_m(300), wander_deg(0, ctx.rng로 침로 흔들기)
"""

import math
from collections.abc import Sequence

import numpy as np

from swarm.v1 import common_pb2, p2p_pb2, vi_pb2
from swarm_api import AgentContext, BatchMissionAutonomy, NavBatch, ParamDef, ParamLayer
from swarm_agent.geo import ned_offset
from swarm_agent.racetrack import path_error, vector_field_course

from .common import Goal, TaskTracker, every, peer_status

S = common_pb2
_B, _D = ParamLayer.BEHAVIOR, ParamLayer.DECISION
PARAMS = (
    ParamDef("cruise_mps", 22.0, _B, "m/s", 1.0, 500.0, "순항 속력(목표 방향 가중)"),
    ParamDef("neighbor_radius_m", 600.0, _B, "m", 1.0, 1e6, "이웃 인식 반경"),
    ParamDef("separation_m", 80.0, _B, "m", 1.0, 1e5, "분리 거리"),
    ParamDef("w_sep", 1.5, _B, "", 0.0, 100.0, "분리 가중"),
    ParamDef("w_align", 0.5, _B, "", 0.0, 100.0, "정렬 가중"),
    ParamDef("w_coh", 0.02, _B, "", 0.0, 100.0, "응집 가중"),
    ParamDef("peer_hz", 5.0, _B, "Hz", 0.1, 100.0, "PeerStatus 송신 주기"),
    ParamDef("stale_s", 2.0, _D, "s", 0.1, 600.0, "이웃 정보 유효 시간"),
    ParamDef("goal_radius_m", 300.0, _D, "m", 1.0, 1e5, "목표점 도달 판정 반경"),
    ParamDef("hold_radius_m", 300.0, _B, "m", 1.0, 1e5, "Hold 기본 선회 반경"),
    ParamDef("wander_deg", 0.0, _B, "deg", 0.0, 180.0, "침로 흔들기 표준편차"),
    ParamDef("group", "", _D, "", description="같은 group_id 이웃만 사용, 빈 값 = 전체", runtime=False),
)
_DEFAULTS = {d.name: d.default for d in PARAMS if isinstance(d.default, float)}
_SUPPORTED = ("move_to", "hold", "return_to_base", "search_area")


class _Agent:
    def __init__(self, ctx: AgentContext) -> None:
        self.p = {k: float(ctx.params.get(k, v)) for k, v in _DEFAULTS.items()}
        self.group = str(ctx.params.get("group", ""))
        self.tracker = TaskTracker(ctx, _SUPPORTED)
        self.table: dict[str, p2p_pb2.PeerStatus] = {}
        self.alt0: float | None = None
        self.goal: Goal | None = None
        self.hold_since: float | None = None  # hold 원 위에 처음 든 모의 시각


class Flocking(BatchMissionAutonomy):
    PARAMS = PARAMS

    def on_init(self, ctxs: Sequence[AgentContext]) -> None:
        self.agents = {c.entity_id: _Agent(c) for c in ctxs}

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        a = self.agents[ctx.entity_id]
        for k in _DEFAULTS:
            if k in changed:
                a.p[k] = float(changed[k])

    def on_step_batch(self, ctxs: Sequence[AgentContext], nav: NavBatch) -> None:
        n = len(ctxs)
        agents = [self.agents[c.entity_id] for c in ctxs]
        now_us = np.array([c.sim_time_s * 1e6 for c in ctxs])

        # 1. 기체별 수신 처리 (자기 포트만)
        for c, a in zip(ctxs, agents):
            for m in c.ports.c2.inbox():
                a.tracker.handle(m)
            for m in c.ports.p2p.inbox():
                if isinstance(m, p2p_pb2.PeerStatus) and (not a.group or m.group_id == a.group):
                    a.table[m.header.source] = m
            c.ports.vi.command_status()
            a.tracker.update(c.ports.vi.nav())
            if a.tracker.changed:
                a.tracker.changed = False
                a.goal = a.tracker.goal()
                a.hold_since = None
            stale_us = a.p["stale_s"] * 1e6
            for k in [k for k, m in a.table.items() if c.sim_time_s * 1e6 - m.header.sim_time_us > stale_us]:
                del a.table[k]

        # 2. 이웃 표 → (N, M) 배열
        m_max = max((len(a.table) for a in agents), default=0)
        lat = np.zeros((n, max(m_max, 1)))
        lon = np.zeros_like(lat)
        vn = np.zeros_like(lat)
        ve = np.zeros_like(lat)
        age = np.zeros_like(lat)
        mask = np.zeros(lat.shape, dtype=bool)
        for i, a in enumerate(agents):
            for j, ps in enumerate(a.table.values()):
                k = ps.kinematics
                lat[i, j], lon[i, j] = k.position.lat_deg, k.position.lon_deg
                vn[i, j], ve[i, j] = k.velocity_ned_mps.x, k.velocity_ned_mps.y
                age[i, j] = (now_us[i] - ps.header.sim_time_us) * 1e-6
                mask[i, j] = True

        own_lat, own_lon = nav.lat_lon_alt[:, 0:1], nav.lat_lon_alt[:, 1:2]
        own_v = nav.velocity_ned[:, :2]
        rn, re = ned_offset(own_lat, own_lon, lat, lon)
        rn = rn + vn * age  # 받은 뒤 지난 시간만큼 외삽
        re = re + ve * age
        dist = np.hypot(rn, re)

        p = np.array([[a.p[k] for k in ("neighbor_radius_m", "separation_m", "w_sep", "w_align", "w_coh",
                                        "cruise_mps")] for a in agents])
        r_nb, d_sep, w_sep, w_al, w_coh, cruise = (p[:, i:i + 1] for i in range(6))
        nb = mask & (dist < r_nb) & (dist > 1e-3)
        cnt = nb.sum(axis=1, keepdims=True)
        safe = np.maximum(cnt, 1)
        # 응집: 이웃 상대 위치 평균, 정렬: 이웃 속도 평균 − 자기 속도
        coh = np.stack([np.where(nb, rn, 0).sum(1), np.where(nb, re, 0).sum(1)], axis=1) / safe
        mean_v = np.stack([np.where(nb, vn, 0).sum(1), np.where(nb, ve, 0).sum(1)], axis=1) / safe
        align = np.where(cnt > 0, mean_v - own_v, 0.0)
        # 분리: 가까울수록 크게, 이웃 반대 방향
        close = nb & (dist < d_sep)
        push = np.where(close, (d_sep - dist) / d_sep / np.maximum(dist, 1e-3), 0.0)
        sep = -np.stack([(push * rn).sum(1), (push * re).sum(1)], axis=1) * cruise

        # 목표 방향
        goal_v = np.zeros((n, 2))
        for i, (c, a) in enumerate(zip(ctxs, agents)):
            g = a.goal
            if g is not None and g.kind == "hold":
                goal_v[i] = self._hold_dir(c, a, g, nav.lat_lon_alt[i, 0], nav.lat_lon_alt[i, 1])
            elif g is not None:
                gn, ge = ned_offset(nav.lat_lon_alt[i, 0], nav.lat_lon_alt[i, 1], g.lat, g.lon)
                d = math.hypot(float(gn), float(ge))
                if d < a.p["goal_radius_m"] and a.tracker.current is not None:
                    a.tracker.finish(S.COMMAND_STATE_COMPLETED)
                    a.tracker.changed = False
                if d > 1.0:
                    goal_v[i] = (float(gn) / d, float(ge) / d)
            else:
                h = math.atan2(own_v[i, 1], own_v[i, 0])
                goal_v[i] = (math.cos(h), math.sin(h))
        goal_v *= cruise

        want = goal_v + w_al * align + w_coh * coh + w_sep * sep

        # 3. 기체별 명령
        for i, (c, a) in enumerate(zip(ctxs, agents)):
            if not nav.valid[i]:
                continue
            if a.alt0 is None:
                a.alt0 = float(nav.lat_lon_alt[i, 2])
            heading = math.degrees(math.atan2(want[i, 1], want[i, 0]))
            if a.p["wander_deg"] > 0:
                heading += float(c.rng.normal(0.0, a.p["wander_deg"]))
            cmd = vi_pb2.FlightCommand(command_id=f"{c.entity_id}-flock")
            cmd.hsa.heading_deg = heading
            cmd.hsa.speed_mps = float(np.hypot(*want[i]))
            g = a.goal
            cmd.hsa.altitude_m = g.alt if g is not None and g.alt > 0 else a.alt0
            c.ports.vi.command(cmd)
            if every(c, a.p["peer_hz"]):
                task = a.tracker.current
                ps = peer_status(c.ports.vi.nav(), a.group, task.task_id if task is not None else "")
                c.ports.p2p.send(ps)
            if every(c, 1.0):
                c.ports.md.record("neighbors", float(cnt[i, 0]))

    @staticmethod
    def _hold_dir(c: AgentContext, a: _Agent, g: Goal, lat: float, lon: float) -> tuple[float, float]:
        if not g.has_center:
            g.lat, g.lon, g.has_center = float(lat), float(lon), True
        r = g.radius or a.p["hold_radius_m"]
        n, e = ned_offset(g.lat, g.lon, lat, lon)
        n, e = float(n), float(e)
        d = math.hypot(n, e)
        if g.racetrack is not None:
            leg, alpha = g.racetrack[0], math.radians(g.racetrack[1])
            lam = -1.0 if g.direction == vi_pb2.TURN_DIRECTION_CCW else 1.0
            if path_error(n, e, r, leg, alpha) < max(0.25 * r, 50.0) and a.hold_since is None:
                a.hold_since = c.sim_time_s
            Flocking._maybe_finish(c, a, g)
            h = vector_field_course(n, e, r, leg, alpha, lam)
            return math.cos(h), math.sin(h)
        if d < 1.0:
            return 1.0, 0.0  # 중심 위: 북쪽으로 벗어난다
        un, ue = n / d, e / d
        tn, te = (-ue, un) if g.direction != vi_pb2.TURN_DIRECTION_CCW else (ue, -un)
        err = max(-1.0, min(1.0, (d - r) / r))
        vn, ve = tn - err * un, te - err * ue
        norm = math.hypot(vn, ve)
        if abs(d - r) < max(0.25 * r, 50.0) and a.hold_since is None:
            a.hold_since = c.sim_time_s
        Flocking._maybe_finish(c, a, g)
        return vn / norm, ve / norm

    @staticmethod
    def _maybe_finish(c: AgentContext, a: _Agent, g: Goal) -> None:
        if (g.duration is not None and a.hold_since is not None and a.tracker.current is not None
                and c.sim_time_s - a.hold_since >= g.duration):
            a.tracker.finish(S.COMMAND_STATE_COMPLETED)
            a.tracker.changed = False


__all__ = ["Flocking"]
