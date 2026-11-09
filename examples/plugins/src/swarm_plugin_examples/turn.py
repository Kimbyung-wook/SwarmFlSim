"""MA "example_turn" (IMP-EXP-001): 가장 작은 MissionAutonomy.

정해진 침로로 돌아 현재 속도·고도를 유지한다. 매개변수 선언과 실행 중 변경을 보여 준다.
"""

import math

from swarm.v1 import vi_pb2
from swarm_api import AgentContext, MissionAutonomy, ParamDef, ParamLayer


class TurnToHeading(MissionAutonomy):
    # 선언한 매개변수만 UI 패널에 나오고 범위 검사를 받는다
    PARAMS = (
        ParamDef("heading_deg", 90.0, ParamLayer.BEHAVIOR, "deg", 0.0, 360.0, "목표 침로"),
    )

    def on_init(self, ctx: AgentContext) -> None:
        self.heading_deg = float(ctx.params.get("heading_deg", 90.0))
        self.sent = False

    def on_params(self, ctx: AgentContext, changed: dict) -> None:
        if "heading_deg" in changed:
            self.heading_deg = float(changed["heading_deg"])
            self.sent = False  # 다음 프레임에 새 값으로 다시 명령한다

    def on_step(self, ctx: AgentContext) -> None:
        # 수신함은 매 프레임 비운다. 이 예제는 내용을 쓰지 않는다
        ctx.ports.c2.inbox()
        ctx.ports.vi.command_status()

        nav = ctx.ports.vi.nav()
        if self.sent or nav is None:
            return
        k = nav.kinematics
        cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-turn")
        cmd.hsa.heading_deg = self.heading_deg
        cmd.hsa.altitude_m = k.position.alt_m
        cmd.hsa.speed_mps = math.hypot(k.velocity_ned_mps.x, k.velocity_ned_mps.y)
        ctx.ports.vi.command(cmd)
        self.sent = True
