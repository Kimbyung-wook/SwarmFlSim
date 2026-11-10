"""MA "hold" (IMP-AGT-012, REQ-BHV-004): 첫 항법 상태를 유지한다.

params
- orbit_radius_m: 0보다 크면 그 자리에서 선회한다. 기본 0 = 침로·속도·고도 유지(HSA)
- lost_link_timeout_s(5), lost_link_policy: 링크 상실 행동 (DEC-078). 작업을 수행하지 않으므로 MA 변수만 쓴다.
  선회 중 자기에게 온 작업 명령을 받거나 재개하면 원래 비행 명령을 다시 낸다
"""

import math

from swarm.v1 import vi_pb2
from swarm_api import AgentContext, MissionAutonomy, ParamDef, ParamLayer

from .common import LOST_LINK_PARAMS, LostLinkGuard, assigned_task

LOST_LINK_ORBIT_M = 300.0     # orbit_radius_m이 0일 때 링크 상실 선회 반경


class Hold(MissionAutonomy):
    PARAMS = (
        ParamDef("orbit_radius_m", 0.0, ParamLayer.BEHAVIOR, "m", 0.0, 100000.0,
                 "0보다 크면 그 자리에서 이 반경으로 선회, 0이면 침로·속도·고도 유지"),
        *LOST_LINK_PARAMS,
    )

    def on_init(self, ctx: AgentContext) -> None:
        self.sent = False
        self.orbit_radius_m = float(ctx.params.get("orbit_radius_m", 0.0))
        self.link = LostLinkGuard(ctx)
        self.cmd: vi_pb2.FlightCommand | None = None

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        if "orbit_radius_m" in changed:
            self.orbit_radius_m = float(changed["orbit_radius_m"])
            self.sent = False  # 다음 프레임에 새 값으로 다시 명령한다
            self.cmd = None

    def on_step(self, ctx: AgentContext) -> None:
        msgs = list(ctx.ports.c2.inbox())
        ctx.ports.vi.command_status()
        nav = ctx.ports.vi.nav()
        if any(assigned_task(ctx, m) for m in msgs):
            self.link.release()
        action = self.link.update(msgs, nav is not None)
        if action == "hold":
            self.link.orbit_here(nav, self.orbit_radius_m or LOST_LINK_ORBIT_M)
        elif action == "resume" and self.cmd is not None:
            ctx.ports.vi.command(self.cmd)
        if self.link.held or self.sent or nav is None:
            return
        k = nav.kinematics
        cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-hold")
        speed = math.hypot(k.velocity_ned_mps.x, k.velocity_ned_mps.y)
        if self.orbit_radius_m > 0:
            o = cmd.curve.orbit
            o.center.CopyFrom(k.position)
            o.radius_m = self.orbit_radius_m
            o.direction = vi_pb2.TURN_DIRECTION_CW
        else:
            cmd.hsa.heading_deg = math.degrees(math.atan2(k.velocity_ned_mps.y, k.velocity_ned_mps.x))
            cmd.hsa.altitude_m = k.position.alt_m
        if speed > 1.0:
            if cmd.HasField("hsa"):
                cmd.hsa.speed_mps = speed
            else:
                cmd.curve.orbit.speed_mps = speed
        ctx.ports.vi.command(cmd)
        self.sent, self.cmd = True, cmd
