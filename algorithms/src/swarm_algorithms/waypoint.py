"""MA "waypoint" (IMP-AGT-013, IMP-AGT-016~017, REQ-BHV-002, DEC-033): MissionPlan·TaskCommand의
MoveTo/Hold/RTB/SearchArea/Route를 수행한다 (구간 규칙은 common.TaskPilot).

- MissionPlan 작업(이 기체가 맡은 것)을 순서대로, C2 TaskCommand는 받는 즉시 수행한다.
- RoutePlan이 오면 그 경유점 목록을 바로 비행한다(작업 상태 보고 없음).
params: acceptance_m(80), hold_radius_m(300), speed_mps(작업에 속도가 없을 때, 기본 현재 속도)
"""

from swarm.v1 import vi_pb2
from swarm_api import AgentContext, MissionAutonomy, ParamDef, ParamLayer

from .common import TaskPilot


class WaypointFollower(MissionAutonomy):
    PARAMS = (
        ParamDef("acceptance_m", 80.0, ParamLayer.DECISION, "m", 1.0, 100000.0, "경유점 도달 판정 반경"),
        ParamDef("hold_radius_m", 300.0, ParamLayer.BEHAVIOR, "m", 1.0, 100000.0, "Hold 작업의 기본 선회 반경"),
        ParamDef("speed_mps", 0.0, ParamLayer.BEHAVIOR, "m/s", 0.0, 500.0, "작업에 속도가 없을 때의 속도, 0 = 현재 속도"),
    )

    def on_init(self, ctx: AgentContext) -> None:
        p = ctx.params
        self.pilot = TaskPilot(ctx, float(p.get("acceptance_m", 80.0)), float(p.get("hold_radius_m", 300.0)),
                               float(p.get("speed_mps", 0.0)) or None)
        self.routes_seen: set[str] = set()

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        p = self.pilot
        p.acceptance_m = float(ctx.params["acceptance_m"])
        p.hold_radius_m = float(ctx.params["hold_radius_m"])
        p.speed_mps = float(ctx.params["speed_mps"]) or None

    def on_step(self, ctx: AgentContext) -> None:
        self.pilot.step()
        for rp in ctx.ports.mp.route_plans():
            if rp.route_id in self.routes_seen or not rp.waypoints:
                continue
            self.routes_seen.add(rp.route_id)
            cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-route-{rp.route_id}")
            cmd.waypoint.waypoints.extend(rp.waypoints)
            ctx.ports.vi.command(cmd)
