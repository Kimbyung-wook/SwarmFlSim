"""MA "waypoint" (IMP-AGT-013, IMP-AGT-016~017, REQ-BHV-002, DEC-033): MissionPlan·TaskCommand의
MoveTo/Hold/RTB/SearchArea/Route를 수행한다 (구간 규칙은 common.TaskPilot).

- MissionPlan 작업(이 기체가 맡은 것)을 순서대로, C2 TaskCommand는 받는 즉시 수행한다.
- RoutePlan은 같은 ID의 계획 작업(Gateway가 route_id를 task_id로 쓴다)이 있으면 그 작업이 수행하므로 따로 비행하지 않는다.
  없으면 단독 항로로 보고 C2 TaskCommand처럼 현재 작업을 CANCELLED(preempted)로 끝내고 바로 비행한다.
  항로 자체의 작업 상태는 보내지 않고, 끝나면 대기 작업을 잇는다 (D-29).
링크 상실 행동은 common.LostLinkGuard를 따른다 (DEC-078).
params: acceptance_m(80), hold_radius_m(300), speed_mps(작업에 속도가 없을 때, 기본 현재 속도), lost_link_timeout_s(5), lost_link_policy
"""

from swarm.v1 import c2_pb2, mp_pb2
from swarm_api import AgentContext, MissionAutonomy, ParamDef, ParamLayer

from .common import LOST_LINK_PARAMS, TaskPilot, invalid_reason


def route_task(ctx: AgentContext, rp: mp_pb2.RoutePlan) -> c2_pb2.TaskCommand:
    t = c2_pb2.TaskCommand(task_id=rp.route_id, assignees=[ctx.entity_id])
    for wp in rp.waypoints:
        out = t.route.waypoints.add()
        out.position.CopyFrom(wp.position)
        if wp.HasField("speed_mps"):
            out.speed_mps = wp.speed_mps
        if wp.acceptance_radius_m > 0:
            out.acceptance_radius_m = wp.acceptance_radius_m
    return t


class WaypointFollower(MissionAutonomy):
    PARAMS = (
        ParamDef("acceptance_m", 80.0, ParamLayer.DECISION, "m", 1.0, 100000.0, "경유점 도달 판정 반경"),
        ParamDef("hold_radius_m", 300.0, ParamLayer.BEHAVIOR, "m", 1.0, 100000.0, "Hold 작업의 기본 선회 반경"),
        ParamDef("speed_mps", 0.0, ParamLayer.BEHAVIOR, "m/s", 0.0, 500.0, "작업에 속도가 없을 때의 속도, 0 = 현재 속도"),
        *LOST_LINK_PARAMS,
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
            tracker = self.pilot.tracker
            if tracker.references(rp.route_id):       # pilot.step()이 같은 틱의 계획까지 반영한 뒤다
                continue
            task = route_task(ctx, rp)
            if invalid_reason(task):
                ctx.ports.md.record("route_plan_invalid", 1.0)
                continue
            tracker.run_quiet(task)
