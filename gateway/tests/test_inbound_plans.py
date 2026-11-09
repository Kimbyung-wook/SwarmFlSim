"""TC-GW-019~024: 외부 승인 응답(DEC-075), 임무 계획 수신(DEC-076), publisher(DEC-077)

외부 메시지는 Gateway 변환기를 쓰지 않고 공개 XSD 구조대로 직접 만든다.
"""
import copy
import math
import uuid

import pytest
from swarm.v1 import c2_pb2, link_pb2, mp_pb2, options_pb2
from swarm_gateway.gateway import Gateway, GatewayConfig

import samples as S

ROUTE_ID = "11111111-1111-4111-8111-111111111111"
PATH_ID = "22222222-2222-4222-8222-222222222222"


def _u(n: int) -> str:
    return str(uuid.UUID(int=(0xA0 << 120) + n, version=4))


def segment(n: int, lat: float, lon: float, alt: float, next_n: int | None, speed: float | None = None) -> dict:
    seg: dict = {
        "PathSegmentID": {"UUID": _u(n)},
        "Source": "OPERATOR_DEFINED",
        "EndPoint": {"WayPoint": {
            "PointChoice": {"Point2D": {"Latitude": math.radians(lat), "Longitude": math.radians(lon),
                                        "Altitude": alt, "AltitudeReference": "MSL"}},
            "WaypointType": "NAV_ONLY"}},
    }
    if speed is not None:
        seg["Speed"] = {"SpeedChoice": {"SpeedValue": {"Value": speed, "Reference": "TRUE_AIRSPEED"}}}
    if next_n is not None:
        seg["NextPathSegment"] = {"PathSegmentID": {"UUID": _u(next_n)}}
    return seg


def route_data(segments=None, target=S.UAV, route_id=ROUTE_ID, label="route-a") -> dict:
    if segments is None:
        # 배열 순서를 일부러 뒤집는다. 순서는 NextPathSegment가 정한다
        segments = [segment(2, 37.6, 128.1, 900, None), segment(1, 37.5, 128.0, 800, 2, speed=25.0)]
    return {
        "RoutePlanID": {"UUID": route_id, "DescriptiveLabel": label},
        "Plan": {
            "Applicability": {"ApplicableToIDs": {"SystemID": {"UUID": _u(99), "DescriptiveLabel": target}}},
            "Parts": {"RouteType": ["PRIMARY"]},
            "Route": {
                "Detailed": True,
                "FirstInRoutePathID": {"UUID": PATH_ID},
                "RouteProjection": "GREAT_CIRCLE",
                "Path": [{"PathID": {"UUID": PATH_ID}, "PathType": "PRIMARY",
                          "FirstInPathSegmentID": {"UUID": _u(1)}, "PathSegment": segments}],
            },
        },
        "ForPlanningUseOnly": False,
    }


def mission_data(route_ids=(ROUTE_ID,), target=S.UAV) -> dict:
    return {
        "MissionPlanID": {"UUID": _u(50), "DescriptiveLabel": "plan-a"},
        "Applicability": {"ApplicableToIDs": {"SystemID": {"UUID": _u(99), "DescriptiveLabel": target}}},
        "SubPlans": {"RoutePlanID": [{"UUID": r} for r in route_ids]},
        "ForPlanningUseOnly": False,
    }


def approval_data(state="APPROVED", processing="COMPLETED", request="req-1") -> dict:
    return {"RequestID": {"UUID": _u(70), "DescriptiveLabel": request},
            "RequestProcessingState": processing,
            "ApprovalRequestProcessingState": state}


def capture(bus):
    got = []
    bus.subscribe("swarm/gcs-01/tx/**", got.append)
    return got


def envelope_of(sample) -> link_pb2.LinkEnvelope:
    return link_pb2.LinkEnvelope.FromString(sample.payload)


def external(gw, name, data):
    return gw.handle_external(name, gw.envelope(name, data))


# ---------------------------------------------------------------- 승인 응답 (DEC-075)

@pytest.mark.parametrize("state,approved", [("APPROVED", True), ("REJECTED", False)])
def test_approval_response_to_requester(gateway, bus, state, approved):
    """TC-GW-019: 외부 승인 응답 → tx/c2/ApprovalResponse. 요청을 낸 기체로 보낸다"""
    S.deliver(bus, S.approval_request())
    got = capture(bus)
    out = external(gateway, "MA_ApprovalRequestStatus", approval_data(state))
    assert out.status == "published", out.reason
    assert [s.key for s in got] == ["swarm/gcs-01/tx/c2/ApprovalResponse"]
    env = envelope_of(got[0])
    assert env.msg_type == "swarm.v1.ApprovalResponse" and env.iface == options_pb2.L1_INTERFACE_C2
    assert list(env.dst) == [S.UAV]
    msg = c2_pb2.ApprovalResponse.FromString(env.payload)
    assert msg.request_id == "req-1" and msg.approved is approved


def test_approval_for_unknown_request_has_empty_dst(gateway, bus):
    got = capture(bus)
    assert external(gateway, "MA_ApprovalRequestStatus", approval_data(request="req-other")).status == "published"
    assert list(envelope_of(got[0]).dst) == []


@pytest.mark.parametrize("state,processing", [("PENDING", "COMPLETED"), ("CANCELED", "COMPLETED"),
                                              ("APPROVED", "QUEUED"), ("APPROVED", "PROCESSING")])
def test_non_final_approval_is_rejected(gateway, bus, state, processing):
    """TC-GW-020: 끝나지 않았거나 approved로 표현할 수 없는 응답은 거부한다"""
    got = capture(bus)
    assert external(gateway, "MA_ApprovalRequestStatus", approval_data(state, processing)).status == "rejected"
    assert got == []


def test_approval_response_on_rx_is_not_echoed(gateway, bus, sent):
    resp = c2_pb2.ApprovalResponse(request_id="req-1", approved=True)
    resp.header.source = "gcs-02"
    S.deliver(bus, resp)
    assert sent == [] and gateway.counters["skipped_inbound_kind"] == 1


# ---------------------------------------------------------------- RoutePlan (DEC-076)

def test_route_plan_to_tx_mp(gateway, bus):
    """TC-GW-021: 외부 경로 계획 → tx/mp/RoutePlan. dst, 연결 순서, 위치, 속력"""
    got = capture(bus)
    out = external(gateway, "MA_RoutePlan", route_data())
    assert out.status == "published", out.reason
    assert [s.key for s in got] == ["swarm/gcs-01/tx/mp/RoutePlan"]
    env = envelope_of(got[0])
    assert env.iface == options_pb2.L1_INTERFACE_MP and list(env.dst) == [S.UAV]
    rp = mp_pb2.RoutePlan.FromString(env.payload)
    assert rp.route_id == "route-a" and rp.entity_id == S.UAV and rp.header.source == S.GCS
    a, b = rp.waypoints
    assert a.position.lat_deg == pytest.approx(37.5) and a.position.lon_deg == pytest.approx(128.0)
    assert a.position.alt_m == 800 and a.speed_mps == 25.0
    assert b.position.lat_deg == pytest.approx(37.6) and b.position.alt_m == 900 and not b.HasField("speed_mps")


@pytest.mark.parametrize("mutate,reason", [
    (lambda d: d.update(ForPlanningUseOnly=True), "ForPlanningUseOnly"),
    (lambda d: d["Plan"].update(Window={"Begin": "2026-11-09T00:00:00Z"}), "Window"),
    (lambda d: d["Plan"]["Applicability"].update(ApplicableToIDs={"ALL": ""}), "SystemID"),
    (lambda d: d["Plan"]["Applicability"].update(ApplicableToIDs={"PackageID": {"UUID": _u(5)}}), "SystemID"),
    (lambda d: d["Plan"]["Applicability"]["ApplicableToIDs"]["SystemID"].update(DescriptiveLabel="NOT AN ID"),
     "does not name"),
    (lambda d: d["Plan"]["Route"]["Path"][0].update(PathType="ALTERNATE"), "PathType"),
    (lambda d: d["Plan"]["Parts"].update(RouteType=["PRIMARY", "ALTERNATE"]), "RouteType"),
    (lambda d: d["Plan"]["Route"]["Path"].append(copy.deepcopy(d["Plan"]["Route"]["Path"][0])), "paths"),
    (lambda d: d["Plan"]["Route"]["Path"][0]["PathSegment"][1].update(
        NextPathSegment={"PathSegmentID": {"UUID": _u(1)}}), "cycle"),
    (lambda d: d["Plan"]["Route"]["Path"][0]["PathSegment"][1].pop("NextPathSegment"), "not linked"),
    (lambda d: d["Plan"]["Route"]["Path"][0]["PathSegment"][0].update(Climb={"ClimbRate": 3.0}), "Climb"),
    (lambda d: d["Plan"]["Route"]["Path"][0]["PathSegment"][0]["EndPoint"]["WayPoint"]["PointChoice"]["Point2D"].update(
        AltitudeReference="AGL"), "MSL"),
    (lambda d: d["Plan"]["Route"]["Path"][0]["PathSegment"][0]["EndPoint"]["WayPoint"]["PointChoice"]["Point2D"].pop(
        "Altitude"), "Altitude"),
    (lambda d: d["Plan"]["Route"]["Path"][0]["PathSegment"][1]["Speed"]["SpeedChoice"]["SpeedValue"].update(
        Reference="CALIBRATED_AIRSPEED"), "speed reference"),
])
def test_route_plan_outside_support_is_rejected(gateway, bus, mutate, reason):
    """TC-GW-022: 내부로 표현할 수 없는 경로 계획은 XSD를 통과해도 거부·기록한다. 임시 규칙은 없다"""
    got = capture(bus)
    data = route_data()
    mutate(data)
    out = external(gateway, "MA_RoutePlan", data)
    assert out.status == "rejected", out
    assert reason in out.reason
    assert got == [] and gateway.rejections[-1] is out


# ---------------------------------------------------------------- MissionPlan (DEC-076)

def test_mission_plan_expands_route_to_route_task(gateway, bus):
    """TC-GW-023: 임무 계획의 RoutePlanID 참조 → 내부 항로 작업(TaskCommand.route), dst, 위치"""
    external(gateway, "MA_RoutePlan", route_data())
    got = capture(bus)
    out = external(gateway, "MA_MissionPlan", mission_data())
    assert out.status == "published", out.reason
    assert [s.key for s in got] == ["swarm/gcs-01/tx/mp/MissionPlan"]
    env = envelope_of(got[0])
    assert list(env.dst) == [S.UAV]
    plan = mp_pb2.MissionPlan.FromString(env.payload)
    assert plan.plan_id == "plan-a" and len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.WhichOneof("task") == "route" and list(task.assignees) == [S.UAV] and task.task_id == "route-a"
    assert [round(w.position.lat_deg, 6) for w in task.route.waypoints] == [37.5, 37.6]
    assert task.route.waypoints[0].speed_mps == 25.0


def test_single_waypoint_route_becomes_move_to(gateway, bus):
    only = [segment(1, 37.7, 128.2, 700, None, speed=20.0)]
    external(gateway, "MA_RoutePlan", route_data(segments=only))
    got = capture(bus)
    external(gateway, "MA_MissionPlan", mission_data())
    task = mp_pb2.MissionPlan.FromString(envelope_of(got[0]).payload).tasks[0]
    assert task.WhichOneof("task") == "move_to"
    assert task.move_to.destination.lat_deg == pytest.approx(37.7) and task.move_to.destination.alt_m == 700
    assert task.move_to.speed_mps == 20.0


def test_mission_plan_outside_support_is_rejected(gateway, bus):
    """TC-GW-024: 받지 못한 경로, 다른 기체의 경로, 경로 밖 하위 계획, 판 불일치, 빈 계획은 거부한다"""
    got = capture(bus)
    assert "was not received" in external(gateway, "MA_MissionPlan", mission_data()).reason

    external(gateway, "MA_RoutePlan", route_data())
    got.clear()
    assert "is for" in external(gateway, "MA_MissionPlan", mission_data(target="uav-002")).reason

    task_plan = mission_data()
    task_plan["SubPlans"]["TaskPlanID"] = [{"UUID": _u(60)}]
    assert "TaskPlanID" in external(gateway, "MA_MissionPlan", task_plan).reason

    empty = mission_data()
    del empty["SubPlans"]
    assert "no RoutePlanID" in external(gateway, "MA_MissionPlan", empty).reason

    planning = mission_data()
    planning["ForPlanningUseOnly"] = True
    assert "ForPlanningUseOnly" in external(gateway, "MA_MissionPlan", planning).reason

    versioned = mission_data()
    versioned["SubPlans"]["RoutePlanID"][0]["Version"] = 7
    assert "version differs" in external(gateway, "MA_MissionPlan", versioned).reason
    assert got == []


@pytest.mark.parametrize("name,data", [
    ("MA_RoutePlan", {"RoutePlanID": {"UUID": ROUTE_ID}}),                         # 필수 요소 누락
    ("MA_MissionPlan", {"MissionPlanID": {"UUID": "not-a-uuid"}, "ForPlanningUseOnly": False}),
    ("MA_ApprovalRequestStatus", {"RequestID": {"UUID": _u(1)}, "RequestProcessingState": "DONE",
                                  "ApprovalRequestProcessingState": "APPROVED"}),
])
def test_invalid_xml_is_rejected(gateway, bus, name, data):
    got = capture(bus)
    out = external(gateway, name, data)
    assert out.status == "rejected" and gateway.counters["ext_invalid"] == 1
    assert got == []


# ---------------------------------------------------------------- publisher·발행 범위 (DEC-077, DEC-076)

def test_publisher_and_seq_per_key(bus, codec):
    """TC-GW-025: 모든 발행에 publisher를 채우고 seq는 키별로 매긴다"""
    gw = Gateway(bus, GatewayConfig(S.GCS, participant="gateway-7"), codec=codec, sink=lambda t, o: None)
    got = capture(bus)
    external(gw, "MA_ApprovalRequestStatus", approval_data())
    external(gw, "MA_ApprovalRequestStatus", approval_data())
    external(gw, "MA_RoutePlan", route_data())
    envs = [envelope_of(s) for s in got]
    assert [e.publisher for e in envs] == ["gateway-7"] * 3
    assert [e.header.seq for e in envs] == [0, 1, 0]


def test_default_participant(gateway, bus):
    got = capture(bus)
    external(gateway, "MA_RoutePlan", route_data())
    assert envelope_of(got[0]).publisher == "gateway-0"


def test_invalid_participant():
    with pytest.raises(ValueError):
        GatewayConfig(S.GCS, participant="Gateway 0")


def test_publish_scope_is_c2_and_mp(gateway, bus):
    """TC-GW-026: 2단계 전 종류를 보내도 발행 키는 tx/c2/**, tx/mp/**뿐이다"""
    from test_import import _task_command

    for make in S.EXPORT_SAMPLES.values():
        S.deliver(bus, make())
    gateway.handle_external("MA_TaskCommand", _task_command(gateway))
    external(gateway, "MA_ApprovalRequestStatus", approval_data())
    external(gateway, "MA_RoutePlan", route_data())
    external(gateway, "MA_MissionPlan", mission_data())
    own = {k for k in bus.published if not k.startswith("swarm/gcs-01/rx/")}
    assert own == {"swarm/gcs-01/tx/c2/TaskCommand", "swarm/gcs-01/tx/c2/ApprovalResponse",
                   "swarm/gcs-01/tx/mp/RoutePlan", "swarm/gcs-01/tx/mp/MissionPlan"}
    assert bus.subscribed == ["swarm/gcs-01/rx/**"]
    with pytest.raises(ValueError):
        gateway.publish_inbound(gateway.table.by_full_name("swarm.v1.NavigationReport"), S.nav(), [])
