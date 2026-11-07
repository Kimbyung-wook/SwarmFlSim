"""MS 활동 변환기 (IMP-GW-008). Agent 런타임이 GCS로 보내는 임무장비 상태(DEC-051)를 UCI로 내보낸다."""
from __future__ import annotations

import math

from swarm.v1 import ms_pb2

from .base import ConvContext, Converter, finite, rad, register

_STRIKE_STATE = {
    ms_pb2.STRIKE_STATE_UNSPECIFIED: "ENABLED",
    ms_pb2.STRIKE_STATE_LAUNCHED: "ACTIVE_UNCONSTRAINED",
    ms_pb2.STRIKE_STATE_IMPACT: "COMPLETED",   # 유도 객체 도달 (DEC-067)
    ms_pb2.STRIKE_STATE_MISSED: "FAILED",
    ms_pb2.STRIKE_STATE_REJECTED: "FAILED",
}


def _activity(ctx: ConvContext, msg, active: bool, capability: str) -> dict:
    src = msg.header.source
    return {
        "ActivityID": ctx.ids.ref("activity", f"{src}/{msg.payload_id}/{capability}"),
        "CapabilityID": [ctx.ids.ref("capability", f"{src}/{msg.payload_id}")],
        "Interactive": False,
        "ActivityState": "ACTIVE_UNCONSTRAINED" if active else "DISABLED",
        "Basis": "ACTUAL",
    }


def _subsystem(ctx: ConvContext, msg) -> dict:
    return ctx.ids.ref("subsystem", f"{msg.header.source}/{msg.payload_id}")


@register
class SensorActivityConverter(Converter):
    proto = "swarm.v1.SensorActivity"

    def to_uci(self, msg: ms_pb2.SensorActivity, ctx: ConvContext) -> dict:
        act = _activity(ctx, msg, msg.active, "po")
        b = msg.boresight_ned
        finite(b.x, b.y, b.z, msg.hfov_deg, msg.vfov_deg, msg.max_range_m)
        if (b.x, b.y, b.z) != (0.0, 0.0, 0.0) and msg.hfov_deg > 0 and msg.vfov_deg > 0:
            az = math.atan2(b.y, b.x) % (2 * math.pi)
            el = math.atan2(-b.z, math.hypot(b.x, b.y))
            fov: dict = {"LOS": {"Azimuth": az, "Elevation": el},
                         "AzimuthWidth": rad(msg.hfov_deg), "ElevationWidth": rad(msg.vfov_deg),
                         "FOV_Timestamp": ctx.ts()}
            if msg.max_range_m > 0:
                fov["MaximumEffectiveRange"] = msg.max_range_m
            act["FOV"] = fov
        return {"SubsystemID": _subsystem(ctx, msg), "Activity": [act]}


@register
class JammerActivityConverter(Converter):
    """재밍 구역(Circle)은 EA_Activity의 공개 필드로 옮길 곳이 정해지지 않아 활동 상태만 싣는다."""
    proto = "swarm.v1.JammerActivity"

    def to_uci(self, msg: ms_pb2.JammerActivity, ctx: ConvContext) -> dict:
        act = _activity(ctx, msg, msg.active, "ea")
        act["EA_Details"] = {"Unassigned": {"Emission": [{}], "Activation": "PREEMPTIVE"}}
        return {"SubsystemID": _subsystem(ctx, msg), "Activity": [act]}


@register
class StrikeActivityConverter(Converter):
    proto = "swarm.v1.StrikeActivity"

    def to_uci(self, msg: ms_pb2.StrikeActivity, ctx: ConvContext) -> dict:
        src = msg.header.source
        weapon = msg.weapon_entity or "none"
        state = _STRIKE_STATE.get(msg.state, "ENABLED")
        released = msg.state != ms_pb2.STRIKE_STATE_UNSPECIFIED and msg.state != ms_pb2.STRIKE_STATE_REJECTED
        act = {
            "ActivityID": ctx.ids.ref("activity", f"{src}/{msg.payload_id}/{weapon}"),
            "CapabilityID": [ctx.ids.ref("capability", f"{src}/{msg.payload_id}")],
            "Interactive": False,
            "ActivityState": state,
            "Basis": "ACTUAL",
            "SelectedForKeyLoad": False,
            "WeaponArmed": released,
            "ReadyForRelease": False,
            "SelectedForRelease": released,
            "SelectedForJettison": False,
        }
        if msg.state in (ms_pb2.STRIKE_STATE_REJECTED, ms_pb2.STRIKE_STATE_MISSED):
            reason = {"Reason": "CONSTRAINT_OP"}
            if msg.reason:
                reason["Description"] = msg.reason[:1024]
            act["ActivityReason"] = reason
        return {"SubsystemID": _subsystem(ctx, msg), "Activity": [act]}


@register
class StoreLoadoutConverter(Converter):
    proto = "swarm.v1.StoreLoadout"

    def to_uci(self, msg: ms_pb2.StoreLoadout, ctx: ConvContext) -> dict:
        out: dict = {"StoreLoadoutConfigurationID": ctx.ids.ref("loadout", msg.header.source)}
        if msg.stores:
            out["Loadout"] = [{"Mnemonic": f"{s.id}:{s.type}x{s.count}"[:256]} for s in msg.stores]
        return out
