"""MA "formation" (IMP-AGT-014, PRP-BHV-003, REQ-BHV-003): leader-follower 편대.

- 편대 정의: C2 FormationCommand(받는 즉시 교체) 또는 MissionPlan.formations 중 이 기체가 속한 것
  (params.group이 있으면 그 group_id). 리더는 leader, 비어 있으면 members 중 사전순 첫 기체.
- 모든 편대원이 PeerStatus를 편대원에게 P2P로 보낸다(peer_hz). 추종기는 데이터링크로 받은
  리더의 PeerStatus만 쓴다 (PRP-SIM-003). 리더 위치는 받은 시각부터 속도로 외삽한다.
- 리더: 작업(MoveTo/Hold/RTB)을 waypoint MA와 같이 수행한다. 속도는 leader_speed_mps.
- 추종기: 슬롯 = 리더 위치 + R(리더 침로)·오프셋(FRD). 목표 속도 = 리더 속도 + k_p·(슬롯 − 자기),
  보정은 corr_max_mps로 제한한다. HSA로 매 프레임 갱신한다.
  리더 상태가 leader_timeout_s보다 오래되면 현재 침로를 유지한다.

오프셋(FRD, s = spacing_m, k = 추종기 순번 0..): LINE (0, ±s·⌈(k+1)/2⌉), COLUMN (−s(k+1), 0),
WEDGE (−s·r, ±s·r), r = ⌊k/2⌋+1, ECHELON (−s(k+1), s(k+1)), CIRCLE 리더 둘레 반경 s 등간격,
CUSTOM custom_offsets_m[members 순서].
"""

import math
from collections.abc import Sequence

from swarm.v1 import c2_pb2, p2p_pb2, vi_pb2
from swarm_api import AgentContext, MissionAutonomy
from swarm_agent.geo import ned_offset, offset_geo

from .common import TaskPilot, every, peer_status

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
        plan = ctx.ports.mp.mission_plan()
        group = p.get("group")
        if plan is not None:
            for f in plan.formations:
                if ctx.entity_id in f.members and (not group or f.group_id == group):
                    self._set(f)
                    break

    def _set(self, cmd: c2_pb2.FormationCommand) -> None:
        self.cmd = cmd
        self.leader = pick_leader(cmd)
        self.offsets = slot_offsets(cmd, self.leader)
        self._leader_init = False

    @property
    def is_leader(self) -> bool:
        return self.cmd is None or self.leader == self._id

    def on_step(self, ctx: AgentContext) -> None:
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
            if nav is not None:
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
