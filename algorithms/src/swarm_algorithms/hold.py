"""MA "hold" (IMP-AGT-012, REQ-BHV-004): 첫 항법 상태를 유지한다.

params
- orbit_radius_m: 0보다 크면 그 자리에서 선회한다. 기본 0 = 침로·속도·고도 유지(HSA)
"""

import math

from swarm.v1 import vi_pb2
from swarm_api import AgentContext, MissionAutonomy


class Hold(MissionAutonomy):
    def on_init(self, ctx: AgentContext) -> None:
        self.sent = False
        self.orbit_radius_m = float(ctx.params.get("orbit_radius_m", 0.0))

    def on_step(self, ctx: AgentContext) -> None:
        ctx.ports.c2.inbox()
        ctx.ports.vi.command_status()
        nav = ctx.ports.vi.nav()
        if self.sent or nav is None:
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
        self.sent = True
