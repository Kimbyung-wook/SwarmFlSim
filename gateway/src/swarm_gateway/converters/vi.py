"""VI 상태 변환기 (IMP-GW-005). 기체 → GCS로 온 VI 상태를 UCI로 내보낸다."""
from __future__ import annotations

from swarm.v1 import common_pb2, vi_pb2

from .base import ConvContext, Converter, label_ok, register

_HEALTH_STATE = {
    vi_pb2.HEALTH_NOMINAL: "OPERATIONAL",
    vi_pb2.HEALTH_DEGRADED: "DEGRADED",
    vi_pb2.HEALTH_FAILED: "FAILED",
}

# CommandState → CommandProcessingStateEnum (RECEIVED, ACCEPTED, REJECTED, CANCELED)
_PROCESSING = {
    common_pb2.COMMAND_STATE_UNSPECIFIED: "RECEIVED",
    common_pb2.COMMAND_STATE_ACCEPTED: "ACCEPTED",
    common_pb2.COMMAND_STATE_EXECUTING: "ACCEPTED",
    common_pb2.COMMAND_STATE_COMPLETED: "ACCEPTED",
    common_pb2.COMMAND_STATE_REJECTED: "REJECTED",
    common_pb2.COMMAND_STATE_FAILED: "REJECTED",
    common_pb2.COMMAND_STATE_CANCELLED: "CANCELED",
}


@register
class NavigationReportConverter(Converter):
    """MA_NavigationReport는 항법 모드·연속 비행 가능 시간 보고다. 공개 XSD에 위치 필드가 없어
    kinematics는 싣지 않는다(위치는 MA_PositionReport 몫, 계약 변경 요청 CR-GW-001)."""
    proto = "swarm.v1.NavigationReport"

    def to_uci(self, msg: vi_pb2.NavigationReport, ctx: ConvContext) -> dict:
        return {
            "SystemID": ctx.system(msg.header.source),
            "Source": "ESTIMATED",            # 잡음이 섞인 항법 해 (PRP-SIM-003)
            "ContingencyLevel": "NORMAL",
            "Endurance": {},
        }


@register
class SystemStatusConverter(Converter):
    proto = "swarm.v1.SystemStatus"

    def to_uci(self, msg: vi_pb2.SystemStatus, ctx: ConvContext) -> dict:
        out = {
            "SystemID": ctx.system(msg.header.source),
            "SystemState": _HEALTH_STATE.get(msg.health, "INACTIVE"),
            "Source": "ACTUAL",
            "Communications": {"MissionCommunicationsState": "ACTIVE"},
        }
        if msg.subsystems:
            out["SubsystemID"] = [ctx.ids.ref("subsystem", f"{msg.header.source}/{s.name}")
                                  for s in msg.subsystems]
        return out


@register
class FlightCommandStatusConverter(Converter):
    proto = "swarm.v1.FlightCommandStatus"

    def to_uci(self, msg: vi_pb2.FlightCommandStatus, ctx: ConvContext) -> dict:
        state = _PROCESSING.get(msg.state, "RECEIVED")
        out: dict = {"CommandID": ctx.ids.ref("command", msg.command_id),
                     "CommandProcessingState": state}
        if state == "REJECTED":
            reason = {"Reason": "CAPABILITY_PERFORMANCE"}
            if msg.reason:
                reason["Description"] = label_ok(msg.reason)
            out["CommandProcessingStateReason"] = reason
        return out


@register
class FlightCapabilityConverter(Converter):
    proto = "swarm.v1.FlightCapability"

    def to_uci(self, msg: vi_pb2.FlightCapability, ctx: ConvContext) -> dict:
        kinds = ["MUST_FLY"]
        if msg.supports_hsa:
            kinds.append("HSA_CSA")
        if msg.supports_waypoint:
            kinds.append("WAYPOINT_FOLLOWING")
        if msg.supports_curve:
            kinds.append("CURVE_FOLLOWING")
        return {"Capability": [{
            "CapabilityID": ctx.ids.ref("capability", f"{msg.header.source}/flight"),
            "AcceptedInterface": ["CAPABILITY_COMMAND"],
            "CapabilityType": kinds,
        }]}
