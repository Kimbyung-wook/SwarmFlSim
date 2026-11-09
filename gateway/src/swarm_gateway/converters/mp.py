"""MP 수신 변환기 (IMP-GW-021, DEC-076). 외부 임무 계획을 내부 RoutePlan·MissionPlan으로 바꾼다.

공개 XSD 구조
- 경로 계획은 위치를 직접 담는다: Plan.Route.Path[].PathSegment[].EndPoint.WayPoint.PointChoice.Point2D.
  세그먼트 순서는 배열이 아니라 FirstInPathSegmentID와 NextPathSegment 연결로 정해진다.
- 임무 계획은 내용을 담지 않고 하위 계획을 ID로 참조한다(SubPlans.RoutePlanID, TaskPlanID 등).
  그래서 임무 계획은 먼저 받은 경로 계획을 참조로 찾아 작업으로 편다.
- 대상은 Applicability.ApplicableToIDs(ALL | NON | PackageID | SystemID의 선택)다.

표현할 수 없는 내용은 임시 규칙을 만들지 않고 ConversionError로 거부한다. 허용 목록 밖의 요소가 있으면
의미를 잃지 않도록 전체를 거부한다. 지원 범위는 README "임무 계획 수신"에 적었다.
"""
from __future__ import annotations

import math
from typing import Iterable

from swarm.v1 import c2_pb2, mp_pb2, vi_pb2
from swarm_api.keys import ENTITY_ID_RE

from .base import ConvContext, ConversionError, Converter, register

_TOP_ROUTE = {"RoutePlanID", "PlanCommandID", "Plan", "ForPlanningUseOnly", "PlanInputs"}
_PLAN = {"Applicability", "Parts", "Route"}
_ROUTE = {"Detailed", "FirstInRoutePathID", "RouteProjection", "Path", "Remarks"}
_PATH = {"PathID", "PathType", "FirstInPathSegmentID", "PathSegment", "Remarks"}
_SEGMENT = {"PathSegmentID", "Source", "EndPoint", "Locked", "Modified", "Speed", "CivilPathTerminator",
            "NextPathSegment", "Remarks"}
_WAYPOINT = {"PointChoice", "WaypointType"}
_POINT = {"Latitude", "Longitude", "Altitude", "AltitudeReference", "Timestamp"}
_TOP_MISSION = {"MissionPlanID", "MissionPlanCommandID", "Applicability", "SubPlans", "ForPlanningUseOnly",
                "PlanInputs", "Remarks"}

_TERMINATORS = {"TF_TrackToFix", "DF_DirectToFix", "IF_InitialFix"}   # 고정점으로 곧장 가는 구간만
_SPEED_REFERENCES = {"GROUNDSPEED", "TRUE_AIRSPEED"}                  # CAS·Mach는 대기 모델이 있어야 바꿀 수 있다


def _only(obj: dict, allowed: Iterable[str], where: str) -> None:
    extra = sorted(set(obj) - set(allowed))
    if extra:
        raise ConversionError(f"{where}: unsupported element(s) {extra}")


def _not_planning_only(data: dict, what: str) -> None:
    if data.get("ForPlanningUseOnly"):   # XSD 주석: 이런 계획은 기능을 일으키면 안 된다
        raise ConversionError(f"{what}: ForPlanningUseOnly plans must not be executed")


def _target(applicability: dict, ctx: ConvContext, what: str) -> str:
    """ApplicableToIDs → 대상 엔티티. PlannedForID는 계획의 사용자(상위 C2일 수 있음)라 대상으로 쓰지 않는다"""
    to = applicability.get("ApplicableToIDs") or {}
    if "SystemID" not in to:
        raise ConversionError(f"{what}: only ApplicableToIDs/SystemID is supported, got {sorted(to)}")
    entity = ctx.ids.internal(to["SystemID"])
    if not ENTITY_ID_RE.match(entity):
        raise ConversionError(f"{what}: SystemID {entity!r} does not name an entity")
    return entity


def _key(ref: dict) -> str:
    return str(ref.get("UUID", "")).lower()


def _ordered_segments(path: dict) -> list[dict]:
    """FirstInPathSegmentID부터 NextPathSegment를 따라간다. 끊기거나 순환하거나 남는 세그먼트가 있으면 거부"""
    by_id: dict[str, dict] = {}
    for seg in path["PathSegment"]:
        k = _key(seg["PathSegmentID"])
        if k in by_id:
            raise ConversionError(f"duplicate PathSegmentID {k}")
        by_id[k] = seg
    ordered: list[dict] = []
    seen: set[str] = set()
    current = _key(path["FirstInPathSegmentID"])
    path_id = _key(path["PathID"])
    while True:
        seg = by_id.get(current)
        if seg is None:
            raise ConversionError(f"segment {current} is not in the path")
        if current in seen:
            raise ConversionError(f"segment cycle at {current}")
        seen.add(current)
        ordered.append(seg)
        nxt = seg.get("NextPathSegment")
        if nxt is None:
            break
        if "PathID" in nxt and _key(nxt["PathID"]) != path_id:
            raise ConversionError("NextPathSegment to another path is not supported")
        current = _key(nxt["PathSegmentID"])
    if len(ordered) != len(by_id):
        raise ConversionError(f"{len(by_id) - len(ordered)} segment(s) are not linked from the first segment")
    return ordered


def _speed(seg: dict) -> float | None:
    speed = seg.get("Speed")
    if speed is None:
        return None
    _only(speed, {"SpeedChoice"}, "Speed")
    value = (speed.get("SpeedChoice") or {}).get("SpeedValue")
    if value is None:
        raise ConversionError("only Speed/SpeedChoice/SpeedValue is supported")
    if value["Reference"] not in _SPEED_REFERENCES:
        raise ConversionError(f"speed reference {value['Reference']} is not supported")
    if not math.isfinite(value["Value"]) or value["Value"] <= 0:
        raise ConversionError(f"invalid speed {value['Value']}")
    return float(value["Value"])


def _waypoint(seg: dict) -> vi_pb2.Waypoint:
    _only(seg, _SEGMENT, "PathSegment")
    terminator = seg.get("CivilPathTerminator")
    if terminator is not None and not set(terminator) <= _TERMINATORS:
        raise ConversionError(f"path terminator {sorted(terminator)} is not supported")
    end = seg["EndPoint"]
    if "WayPoint" not in end:
        raise ConversionError(f"EndPoint {sorted(end)} is not supported (only WayPoint)")
    wp = end["WayPoint"]
    _only(wp, _WAYPOINT, "WayPoint")
    if wp["WaypointType"] != "NAV_ONLY":
        raise ConversionError(f"WaypointType {wp['WaypointType']} is not supported")
    if "Point2D" not in wp["PointChoice"]:
        raise ConversionError("only absolute Point2D waypoints are supported")
    p = wp["PointChoice"]["Point2D"]
    _only(p, _POINT, "Point2D")
    if "Altitude" not in p:
        raise ConversionError("waypoint needs Altitude")
    if p.get("AltitudeReference") != "MSL":
        raise ConversionError(f"AltitudeReference must be MSL, got {p.get('AltitudeReference')}")
    out = vi_pb2.Waypoint()
    out.position.lat_deg = math.degrees(p["Latitude"])
    out.position.lon_deg = math.degrees(p["Longitude"])
    out.position.alt_m = float(p["Altitude"])
    speed = _speed(seg)
    if speed is not None:
        out.speed_mps = speed
    return out


def _route_id(ref: dict, ctx: ConvContext) -> str:
    return ctx.ids.internal(ref)


@register
class RoutePlanConverter(Converter):
    proto = "swarm.v1.RoutePlan"

    def from_uci(self, data: dict, ctx: ConvContext) -> tuple[mp_pb2.RoutePlan, list[str]]:
        _only(data, _TOP_ROUTE, "RoutePlan")
        _not_planning_only(data, "RoutePlan")
        plan = data["Plan"]
        _only(plan, _PLAN, "Plan")                                # Window 등 시간 조건은 표현할 수 없다
        if plan["Parts"]["RouteType"] != ["PRIMARY"]:
            raise ConversionError(f"RouteType {plan['Parts']['RouteType']} is not supported (only PRIMARY)")
        route = plan["Route"]
        _only(route, _ROUTE, "Route")
        paths = route["Path"]
        if len(paths) != 1:
            raise ConversionError(f"{len(paths)} paths: only one PRIMARY path is supported")
        path = paths[0]
        _only(path, _PATH, "Path")
        if path["PathType"] != "PRIMARY":
            raise ConversionError(f"PathType {path['PathType']} is not supported (only PRIMARY)")
        if _key(route["FirstInRoutePathID"]) != _key(path["PathID"]):
            raise ConversionError("FirstInRoutePathID does not match the path")
        entity = _target(plan["Applicability"], ctx, "RoutePlan")
        msg = mp_pb2.RoutePlan(route_id=_route_id(data["RoutePlanID"], ctx), entity_id=entity)
        msg.waypoints.extend(_waypoint(seg) for seg in _ordered_segments(path))
        ctx.routes.put(_key(data["RoutePlanID"]), data["RoutePlanID"].get("Version"), msg)
        return msg, [entity]


def _route_to_task(route: mp_pb2.RoutePlan, entity: str) -> c2_pb2.TaskCommand:
    """항로점 하나는 이동(move_to), 둘 이상은 항로(route) 작업이다"""
    task = c2_pb2.TaskCommand(task_id=route.route_id, assignees=[entity])
    if len(route.waypoints) == 1:
        wp = route.waypoints[0]
        task.move_to.destination.CopyFrom(wp.position)
        if wp.HasField("speed_mps"):
            task.move_to.speed_mps = wp.speed_mps
        return task
    for wp in route.waypoints:
        out = task.route.waypoints.add()
        out.position.CopyFrom(wp.position)
        if wp.HasField("speed_mps"):
            out.speed_mps = wp.speed_mps
    return task


@register
class MissionPlanConverter(Converter):
    proto = "swarm.v1.MissionPlan"

    def from_uci(self, data: dict, ctx: ConvContext) -> tuple[mp_pb2.MissionPlan, list[str]]:
        _only(data, _TOP_MISSION, "MissionPlan")
        _not_planning_only(data, "MissionPlan")
        entity = _target(data["Applicability"], ctx, "MissionPlan")
        subplans = data.get("SubPlans") or {}
        _only(subplans, {"RoutePlanID"}, "SubPlans")               # 작업 내용(TaskPlan 등)은 내부 매핑이 없다
        refs = subplans.get("RoutePlanID") or []
        if not refs:
            raise ConversionError("MissionPlan has no RoutePlanID sub-plan")
        msg = mp_pb2.MissionPlan(plan_id=ctx.ids.internal(data["MissionPlanID"]))
        for ref in refs:
            route = ctx.routes.get(_key(ref), ref.get("Version"))
            if route is None:
                raise ConversionError(f"RoutePlan {ctx.ids.internal(ref)} was not received (or version differs)")
            if route.entity_id != entity:
                raise ConversionError(f"RoutePlan {route.route_id} is for {route.entity_id}, not {entity}")
            msg.tasks.append(_route_to_task(route, entity))
        return msg, [entity]
