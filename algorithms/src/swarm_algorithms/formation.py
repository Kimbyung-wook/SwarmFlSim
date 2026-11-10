"""MA "formation" (IMP-AGT-014, IMP-AGT-016~017, PRP-BHV-003, REQ-BHV-003): leader-follower 편대.

- 편대 정의: C2 FormationCommand(받는 즉시 교체) 또는 MissionPlan.formations 중 이 기체가 속한 것
  (params.group이 있으면 그 group_id). 리더는 leader, 비어 있으면 members 중 사전순 첫 기체.
- 모든 편대원이 PeerStatus를 편대원에게 P2P로 보낸다(peer_hz). 추종기는 데이터링크로 받은
  리더의 PeerStatus만 쓴다 (PRP-SIM-003). 리더 위치는 받은 시각부터 속도로 외삽한다.
- 리더: 작업(MoveTo/Hold/RTB/SearchArea/Route, DEC-033)을 waypoint MA와 같이 수행한다.
  속도는 작업에 없으면 leader_speed_mps.
- 추종기: 슬롯 = 리더 위치 + R(리더 침로)·오프셋(FRD). 목표 속도 = 리더 속도 + k_p·(슬롯 − 자기),
  보정은 corr_max_mps로 제한한다. HSA로 매 프레임 갱신한다.
  리더 상태가 leader_timeout_s보다 오래되면 현재 침로를 유지한다.
- 링크 상실(DEC-078): 리더는 수행 중 작업의 정책, 추종기와 작업 없는 리더는 MA 변수 lost_link_policy를 따른다(FormationCommand에 정책이 없다).
  선회 중 새 편대 명령이나 자기에게 온 작업 명령을 받으면 선회를 끝낸다.

오프셋(FRD, s = spacing_m, k = 추종기 순번 0..): LINE (0, ±s·⌈(k+1)/2⌉), COLUMN (−s(k+1), 0),
WEDGE (−s·r, ±s·r), r = ⌊k/2⌋+1, ECHELON (−s(k+1), s(k+1)), CIRCLE 리더 둘레 반경 s 등간격,
CUSTOM custom_offsets_m[members 순서].
"""

import math
from collections.abc import Sequence

from swarm.v1 import c2_pb2, mp_pb2, p2p_pb2, vi_pb2
from swarm_api import AgentContext, MissionAutonomy, ParamDef, ParamLayer
from swarm_agent.geo import ned_offset, offset_geo

from .common import LOST_LINK_PARAMS, PlanWatcher, TaskPilot, assigned_task, every, peer_status

F = c2_pb2


def slot_offsets(cmd: c2_pb2.FormationCommand, leader: str) -> dict[str, tuple[float, float, float]]:
    """편대원별 리더 기준 FRD 오프셋(m). 리더는 (0, 0, 0)"""
    s = cmd.spacing_m or 100.0
    members = list(cmd.members)
    if cmd.shape == F.FORMATION_SHAPE_CUSTOM:
        out = {}
        for i, m in enumerate(members):
            o = cmd.custom_offsets_m[i] if i < len(cmd.custom_offsets_m) else None
            out[m] = (o.x, o.y, o.z) if o is not None else (0.0, 0.0, 0.0)
        out[leader] = (0.0, 0.0, 0.0)
        return out
    followers = [m for m in members if m != leader]
    out = {leader: (0.0, 0.0, 0.0)}
    n = len(followers)
    for k, m in enumerate(followers):
        side = 1.0 if k % 2 == 0 else -1.0
        rank = k // 2 + 1
        if cmd.shape == F.FORMATION_SHAPE_LINE:
            out[m] = (0.0, side * rank * s, 0.0)
        elif cmd.shape == F.FORMATION_SHAPE_COLUMN:
            out[m] = (-(k + 1) * s, 0.0, 0.0)
        elif cmd.shape == F.FORMATION_SHAPE_ECHELON:
            out[m] = (-(k + 1) * s, (k + 1) * s, 0.0)
        elif cmd.shape == F.FORMATION_SHAPE_CIRCLE:
            th = 2.0 * math.pi * k / n
            out[m] = (s * math.cos(th), s * math.sin(th), 0.0)
        else:  # WEDGE, UNSPECIFIED
            out[m] = (-rank * s, side * rank * s, 0.0)
    return out


def pick_leader(cmd: c2_pb2.FormationCommand) -> str:
    return cmd.leader or (sorted(cmd.members)[0] if cmd.members else "")


class Formation(MissionAutonomy):
    PARAMS = (
        ParamDef("peer_hz", 5.0, ParamLayer.BEHAVIOR, "Hz", 0.1, 100.0, "PeerStatus 송신 주기"),
        ParamDef("leader_speed_mps", 20.0, ParamLayer.BEHAVIOR, "m/s", 1.0, 500.0, "작업에 속도가 없을 때 리더 속도"),
        ParamDef("k_p", 0.08, ParamLayer.BEHAVIOR, "1/s", 0.0, 10.0, "슬롯 오차 비례 이득"),
        ParamDef("corr_max_mps", 12.0, ParamLayer.BEHAVIOR, "m/s", 0.0, 200.0, "슬롯 보정 속도 상한"),
        ParamDef("leader_timeout_s", 3.0, ParamLayer.DECISION, "s", 0.1, 600.0, "리더 상태 유효 시간"),
        ParamDef("acceptance_m", 80.0, ParamLayer.DECISION, "m", 1.0, 100000.0, "리더 경유점 도달 판정 반경"),
        ParamDef("hold_radius_m", 400.0, ParamLayer.BEHAVIOR, "m", 1.0, 100000.0, "리더 Hold 기본 선회 반경"),
        ParamDef("group", "", ParamLayer.DECISION, "", description="따를 편대 group_id, 빈 값 = 소속 첫 편대", runtime=False),
        *LOST_LINK_PARAMS,
    )

    def on_init(self, ctx: AgentContext) -> None:
        p = ctx.params
        self._id = ctx.entity_id
        self.peer_hz = float(p.get("peer_hz", 5.0))
        self.leader_speed = float(p.get("leader_speed_mps", 20.0))
        self.k_p = float(p.get("k_p", 0.08))
        self.corr_max = float(p.get("corr_max_mps", 12.0))
        self.timeout_s = float(p.get("leader_timeout_s", 3.0))
        self.pilot = TaskPilot(ctx, float(p.get("acceptance_m", 80.0)), float(p.get("hold_radius_m", 400.0)),
                               self.leader_speed)
        self.cmd: c2_pb2.FormationCommand | None = None
        self.leader = ""
        self.offsets: dict[str, tuple[float, float, float]] = {}
        self.peers: dict[str, p2p_pb2.PeerStatus] = {}
        self._leader_init = False
        self._psi = 0.0
        self.group = p.get("group")
        self.plans = PlanWatcher(ctx)
        self._apply_plan(ctx, self.plans.initial)

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        p = ctx.params
        self.peer_hz = float(p["peer_hz"])
        self.leader_speed = float(p["leader_speed_mps"])
        self.k_p = float(p["k_p"])
        self.corr_max = float(p["corr_max_mps"])
        self.timeout_s = float(p["leader_timeout_s"])
        self.pilot.acceptance_m = float(p["acceptance_m"])
        self.pilot.hold_radius_m = float(p["hold_radius_m"])
        self.pilot.speed_mps = self.leader_speed

    def _apply_plan(self, ctx: AgentContext, plan: mp_pb2.MissionPlan | None) -> None:
        """계획의 편대 편성을 적용한다. 이 기체의 편대가 없는 계획은 지금 편대를 건드리지 않는다"""
        if plan is None:
            return
        for f in plan.formations:
            if ctx.entity_id in f.members and (not self.group or f.group_id == self.group):
                self._set(f)
                break

    def _set(self, cmd: c2_pb2.FormationCommand) -> None:
        self.cmd = cmd
        self.leader = pick_leader(cmd)
        self.offsets = slot_offsets(cmd, self.leader)
        self._leader_init = False
        self.pilot.link.release()

    @property
    def is_leader(self) -> bool:
        return self.cmd is None or self.leader == self._id

    def on_step(self, ctx: AgentContext) -> None:
        self._apply_plan(ctx, self.plans.poll())    # 실행 중 받은 새 계획 (DEC-076)
        other = []
        for m in ctx.ports.c2.inbox():
            if isinstance(m, c2_pb2.FormationCommand):
                if ctx.entity_id in m.members:
                    self._set(m)
                elif self.cmd is not None and m.group_id == self.cmd.group_id:
                    self.cmd = None  # 이 편대에서 빠졌다
            else:
                other.append(m)
        for m in ctx.ports.p2p.inbox():
            if isinstance(m, p2p_pb2.PeerStatus):
                self.peers[m.header.source] = m
        nav = ctx.ports.vi.nav()

        if self.is_leader:
            if not self._leader_init and nav is not None:
                self._leader_init = True
                cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-fmn-lead")
                cmd.hsa.speed_mps = self.leader_speed
                ctx.ports.vi.command(cmd)
            self.pilot.step(other)
        else:
            ctx.ports.vi.command_status()
            link = self.pilot.link
            if any(assigned_task(ctx, m) for m in other):
                link.release()
            if link.update(other, nav is not None) == "hold":
                link.orbit_here(nav, self.pilot.hold_radius_m)
            if nav is not None and not link.held:
                self._follow(ctx, nav)

        if nav is not None and self.cmd is not None and every(ctx, self.peer_hz):
            task = self.pilot.tracker.current
            ps = peer_status(nav, self.cmd.group_id, task.task_id if task is not None else "")
            ctx.ports.p2p.send(ps, [m for m in self.cmd.members if m != ctx.entity_id])

    def _follow(self, ctx: AgentContext, nav: vi_pb2.NavigationReport) -> None:
        ls = self.peers.get(self.leader)
        age = ctx.sim_time_s - ls.header.sim_time_us * 1e-6 if ls is not None else math.inf
        cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-fmn-{self.cmd.group_id}")
        if age > self.timeout_s:
            ctx.ports.vi.command(cmd)  # 빈 HSA: 현재 목표 유지
            return
        k = ls.kinematics
        vn, ve = k.velocity_ned_mps.x, k.velocity_ned_mps.y
        if math.hypot(vn, ve) > 1.0:
            self._psi = math.atan2(ve, vn)
        psi = self._psi
        lat_l, lon_l = offset_geo(k.position.lat_deg, k.position.lon_deg, vn * age, ve * age)
        x, y, z = self.offsets.get(ctx.entity_id, (0.0, 0.0, 0.0))
        dn, de = x * math.cos(psi) - y * math.sin(psi), x * math.sin(psi) + y * math.cos(psi)
        me = nav.kinematics.position
        rn, re = ned_offset(me.lat_deg, me.lon_deg, lat_l, lon_l)
        en, ee = float(rn) + dn, float(re) + de
        cn, ce = self.k_p * en, self.k_p * ee
        c = math.hypot(cn, ce)
        if c > self.corr_max:
            cn, ce = cn * self.corr_max / c, ce * self.corr_max / c
        wn, we = vn + cn, ve + ce
        cmd.hsa.heading_deg = math.degrees(math.atan2(we, wn))
        cmd.hsa.speed_mps = math.hypot(wn, we)
        cmd.hsa.altitude_m = k.position.alt_m - z
        ctx.ports.vi.command(cmd)
        if every(ctx, 1.0):
            ctx.ports.md.record("slot_error_m", math.hypot(en, ee))


def formation_slots(cmd: c2_pb2.FormationCommand) -> Sequence[tuple[str, tuple[float, float, float]]]:
    leader = pick_leader(cmd)
    offs = slot_offsets(cmd, leader)
    return [(m, offs[m]) for m in cmd.members]
