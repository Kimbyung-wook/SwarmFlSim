"""MA_PositionReport 변환기 (IMP-GW-014, DEC-072).

`kinematics`(KinematicState)를 가진 내부 메시지의 위치·운동 상태를 InertialState로 싣는다.
어느 내부 메시지에 쓸지는 proto 옵션 (uci_also)가 정한다(지금은 NavigationReport, PeerStatus).
- Position: Point4D (위도·경도 rad, 고도 MSL m, 시각)
- PositionUncertainty: position_sigma_m가 있으면 원형 불확도 타원
- DomainVelocity: NED m/s
- Orientation: NED→FRD 쿼터니언의 ZYX 오일러각(yaw, pitch, roll, rad). 쿼터니언이 비어 있으면 뺀다
"""
from __future__ import annotations

import math

from google.protobuf.message import Message

from .base import AlsoConverter, ConvContext, ConversionError, finite, point, register_also


def euler_zyx(w: float, x: float, y: float, z: float) -> tuple[float, float, float] | None:
    """(yaw, pitch, roll) rad. 정규화할 수 없으면 None"""
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-9:
        return None
    w, x, y, z = w / n, x / n, y / n, z / n
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return yaw, pitch, roll


@register_also
class PositionReportConverter(AlsoConverter):
    uci = "MA_PositionReport"

    def to_uci(self, msg: Message, ctx: ConvContext) -> dict:
        if "kinematics" not in msg.DESCRIPTOR.fields_by_name:
            raise ConversionError(f"{msg.DESCRIPTOR.full_name} has no kinematics")
        if not msg.HasField("kinematics") or not msg.kinematics.HasField("position"):
            raise ConversionError("kinematics.position is missing")
        k = msg.kinematics
        ts = ctx.ts()
        p = k.position
        inertial: dict = {"Position": point(p.lat_deg, p.lon_deg, p.alt_m, ts)}
        sigma = getattr(msg, "position_sigma_m", 0.0)
        if sigma > 0:
            finite(sigma)
            inertial["PositionUncertainty"] = {"UncertaintyEllipse": {
                "SemiMajorAxisLength": sigma, "SemiMinorAxisLength": sigma, "Orientation": 0.0}}
        if k.HasField("velocity_ned_mps"):
            v = k.velocity_ned_mps
            finite(v.x, v.y, v.z)
            inertial["DomainVelocity"] = {"NorthSpeed": v.x, "EastSpeed": v.y, "DownSpeed": v.z, "Timestamp": ts}
        if k.HasField("attitude"):
            q = k.attitude
            finite(q.w, q.x, q.y, q.z)
            ypr = euler_zyx(q.w, q.x, q.y, q.z)
            if ypr is not None:
                inertial["Orientation"] = {"Yaw": ypr[0], "Pitch": ypr[1], "Roll": ypr[2], "Timestamp": ts}
        return {
            "SystemID": ctx.system(msg.header.source),
            "DisplayName": msg.header.source[:256],
            "Source": "ESTIMATED",           # 잡음이 섞인 항법 해 (PRP-SIM-003)
            "CurrentOperatingDomain": "AIR",
            "InertialState": inertial,
        }
