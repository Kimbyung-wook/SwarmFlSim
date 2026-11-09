"""FA "example_hsa" (IMP-EXP-004): HSA 모드만 처리하는 가장 작은 FlightAutonomy.

침로 오차에 비례해 선회율을, 고도 오차에 비례해 상승률을 만든다.
Waypoint·Curve 명령은 REJECTED로 답한다. 전체 기능은 기본 FA
agent/src/swarm_agent/fa.py를 본다.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from swarm.v1 import common_pb2, fa_pb2, vi_pb2
from swarm_api import FlightAutonomy, ParamDef, ParamLayer

G_MPS2 = 9.80665


class HsaOnlyFlightAutonomy(FlightAutonomy):
    PARAMS = (
        # 기체 한계는 시작할 때 Core에 알리므로 실행 중 바꿀 수 없다
        ParamDef("max_bank_deg", 30.0, ParamLayer.AIRFRAME, "deg", 1.0, 85.0, "최대 뱅크각", runtime=False),
        ParamDef("k_heading", 0.5, ParamLayer.CONTROL, "1/s", 0.0, 10.0, "침로 오차 → 선회율 이득"),
        ParamDef("k_altitude", 0.2, ParamLayer.CONTROL, "1/s", 0.0, 10.0, "고도 오차 → 상승률 이득"),
    )
    MIN_SPEED, MAX_SPEED, MAX_CLIMB = 12.0, 35.0, 5.0

    def on_init(self, entity_id: str, params: Mapping[str, Any]) -> vi_pb2.FlightCapability:
        self.bank_max = math.radians(float(params.get("max_bank_deg", 30.0)))
        self.k_heading = float(params.get("k_heading", 0.5))
        self.k_altitude = float(params.get("k_altitude", 0.2))
        self.target: vi_pb2.HsaCommand | None = None
        self.pending: list[vi_pb2.FlightCommandStatus] = []
        return vi_pb2.FlightCapability(
            min_speed_mps=self.MIN_SPEED, max_speed_mps=self.MAX_SPEED, max_climb_mps=self.MAX_CLIMB,
            max_bank_deg=math.degrees(self.bank_max), max_altitude_m=6000.0, supports_hsa=True,
        )

    def on_params(self, values: Mapping[str, Any], changed: Mapping[str, Any]) -> None:
        self.k_heading = float(values.get("k_heading", self.k_heading))
        self.k_altitude = float(values.get("k_altitude", self.k_altitude))

    def on_command(self, cmd: vi_pb2.FlightCommand) -> vi_pb2.FlightCommandStatus:
        if cmd.WhichOneof("mode") != "hsa":
            return vi_pb2.FlightCommandStatus(
                command_id=cmd.command_id, state=common_pb2.COMMAND_STATE_REJECTED, reason="hsa only")
        self.target = cmd.hsa
        return vi_pb2.FlightCommandStatus(command_id=cmd.command_id, state=common_pb2.COMMAND_STATE_ACCEPTED)

    def step(self, nav: vi_pb2.NavigationReport, dt_s: float) -> fa_pb2.ControlOutput:
        k = nav.kinematics
        v_n, v_e = k.velocity_ned_mps.x, k.velocity_ned_mps.y
        speed = math.hypot(v_n, v_e)
        out = fa_pb2.ControlOutput()
        c = out.kinematic
        if self.target is None:  # 명령 전: 직진·고도 유지
            c.speed_mps = max(self.MIN_SPEED, speed)
            return out

        course = math.atan2(v_e, v_n)
        error = (math.radians(self.target.heading_deg) - course + math.pi) % (2.0 * math.pi) - math.pi
        v_ref = max(speed, self.MIN_SPEED)
        rate_max = G_MPS2 * math.tan(self.bank_max) / v_ref
        rate = max(-rate_max, min(rate_max, self.k_heading * error))

        c.speed_mps = max(self.MIN_SPEED, min(self.MAX_SPEED, self.target.speed_mps or speed))
        c.heading_rate_rps = rate
        c.bank_rad = math.atan(v_ref * rate / G_MPS2)  # 2-DoF·3-DoF가 같은 궤적을 따르게 함께 채운다
        climb = self.k_altitude * (self.target.altitude_m - k.position.alt_m)
        c.climb_rate_mps = max(-self.MAX_CLIMB, min(self.MAX_CLIMB, climb))
        return out

    def pending_status(self) -> Sequence[vi_pb2.FlightCommandStatus]:
        out, self.pending = self.pending, []
        return out
