"""P2P 변환기 (IMP-GW-007). GCS도 받는 기체 간 공유(브로드캐스트) 메시지를 UCI로 내보낸다."""
from __future__ import annotations

import math

from swarm.v1 import entity_pb2, p2p_pb2

from .base import ConvContext, Converter, finite, lon_rad, rad, register

_IDENTITY = {
    entity_pb2.SIDE_BLUE: "FRIEND",
    entity_pb2.SIDE_RED: "HOSTILE",
    entity_pb2.SIDE_NEUTRAL: "NEUTRAL",
}

_ENVIRONMENT = {
    entity_pb2.ENTITY_KIND_UAV: "AIR",
    entity_pb2.ENTITY_KIND_AIR_TARGET: "AIR",
    entity_pb2.ENTITY_KIND_MISSILE: "AIR",
    entity_pb2.ENTITY_KIND_FPV: "AIR",
    entity_pb2.ENTITY_KIND_GCS: "GROUND",
    entity_pb2.ENTITY_KIND_GROUND_TARGET: "GROUND",
    entity_pb2.ENTITY_KIND_JAMMER_SITE: "GROUND",
}


@register
class PeerStatusConverter(Converter):
    """패키지(그룹) 동료 상태. 공개 XSD의 MA_PackagePartnerStatusReport에는 운동 상태 필드가 없어
    그룹·참여 상태만 싣는다. 위치·운동 상태는 uci_also의 MA_PositionReport로 따로 나간다 (DEC-072)."""
    proto = "swarm.v1.PeerStatus"

    def to_uci(self, msg: p2p_pb2.PeerStatus, ctx: ConvContext) -> dict:
        group = msg.group_id or msg.header.source
        return {
            "CommandID": ctx.ids.ref("command", f"{group}/partner-status"),
            "PackageID": ctx.ids.ref("package", group),
            "PackageStatus": "PROCESSING",
            "SystemStatus": [{"SystemID": ctx.system(msg.header.source),
                              "PackagePartnerStatus": "PROCESSING"}],
        }


@register
class LeaderUpdateConverter(Converter):
    proto = "swarm.v1.LeaderUpdate"

    def to_uci(self, msg: p2p_pb2.LeaderUpdate, ctx: ConvContext) -> dict:
        request: dict = {"RequestingSystemID": ctx.system(msg.header.source),
                         "Applicability": {"ApplicablePackageID": ctx.ids.ref("package", msg.group_id)}}
        if msg.leader:
            request["ProposedLeaderID"] = ctx.system(msg.leader)
        return {
            "RequestID": ctx.ids.ref("request", f"{msg.group_id}/leader/{msg.term}"),
            "RequestState": "NEW",
            "Status": "ASSIGN",
            "Request": request,
        }


@register
class TrackShareConverter(Converter):
    proto = "swarm.v1.TrackShare"

    def to_uci(self, msg: p2p_pb2.TrackShare, ctx: ConvContext) -> dict:
        ts = ctx.ts()
        p = msg.position
        finite(p.lat_deg, p.lon_deg, p.alt_m)
        v = msg.velocity_ned_mps
        identity: dict = {
            "Standard": [{"StandardIdentity": "UNKNOWN", "Confidence": 50.0}],
            "IdentityTimestamp": ts,
        }
        env = _ENVIRONMENT.get(msg.kind)
        if env:
            identity["Environment"] = [{"Environment": env, "Confidence": 100.0}]
        out: dict = {
            "EntityID": ctx.ids.ref("entity", msg.track_id),
            "CreationTimestamp": {"DateTime": ts},
            "Source": {"SystemID": ctx.system(msg.header.source), "SourceType": "FUSION_SYSTEM"},
            "EntityStatus": "CONFIRMED",
            "Identity": identity,
            "Mobility": "MOVER" if math.hypot(v.x, v.y, v.z) > 0.5 else "UNDETERMINED",
            "Kinematics": {
                "KinematicsTimeStamp": ts,
                "Position": {"FixedPositionType": {"FixedPoint": {
                    "Latitude": rad(p.lat_deg), "Longitude": lon_rad(p.lon_deg), "Altitude": p.alt_m,
                    "AltitudeReference": "MSL"}}},
                "Velocity": {"NorthSpeed": v.x, "EastSpeed": v.y, "DownSpeed": v.z},
            },
        }
        if msg.target_id:
            out["AssociatedID"] = [ctx.ids.ref("entity", msg.target_id)]
        return out
