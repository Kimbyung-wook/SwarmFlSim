"""MA "example_patrol" (IMP-EXP-002): 작업 처리를 공용 부품에 맡기는 MA.

MoveTo·Hold 같은 작업은 TaskPilot이 수행하고 TaskStatus도 대신 보낸다.
이 플러그인은 작업이 없을 때의 행동(그 자리 선회)만 정한다.
MD 포트로 내부 값을 기록하는 방법도 보여 준다.
"""

from swarm.v1 import vi_pb2
from swarm_algorithms.common import TaskPilot
from swarm_api import AgentContext, MissionAutonomy, ParamDef, ParamLayer


class Patrol(MissionAutonomy):
    PARAMS = (
        ParamDef("idle_radius_m", 400.0, ParamLayer.BEHAVIOR, "m", 50.0, 100000.0, "작업이 없을 때 선회 반경"),
    )

    def on_init(self, ctx: AgentContext) -> None:
        self.idle_radius_m = float(ctx.params.get("idle_radius_m", 400.0))
        # 여기 없는 작업(track 등)은 TaskPilot이 REJECTED로 보고한다
        self.pilot = TaskPilot(ctx, supported=("move_to", "hold", "return_to_base"))
        self.idle = False

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        if "idle_radius_m" in changed:
            self.idle_radius_m = float(changed["idle_radius_m"])
            self.idle = False

    def on_step(self, ctx: AgentContext) -> None:
        self.pilot.step()  # C2 수신, 작업 진행, TaskStatus 송신을 모두 맡는다
        busy = self.pilot.tracker.current is not None
        ctx.ports.md.record("patrol.busy", float(busy))
        if busy:
            self.idle = False
            return
        nav = ctx.ports.vi.nav()
        if self.idle or nav is None:
            return
        cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-idle")
        orbit = cmd.curve.orbit
        orbit.center.CopyFrom(nav.kinematics.position)
        orbit.radius_m = self.idle_radius_m
        orbit.direction = vi_pb2.TURN_DIRECTION_CW
        ctx.ports.vi.command(cmd)
        self.idle = True
