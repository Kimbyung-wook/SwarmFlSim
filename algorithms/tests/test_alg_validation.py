"""TC-AGT-040~042: 임무 명령 값 검증, 빈 assignees, 중복 task_id (IMP-AGT-024, DEC-038, QA-005)"""

import math

import pytest

from swarm.v1 import c2_pb2, common_pb2
from swarm_agent.geo import offset_geo
from swarm_algorithms.common import ROUTE_MAX_POINTS
from swarm_agent.testing import Harness, make_scenario, send_c2

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)
UAV = "uav-001"
NAN, INF = float("nan"), float("inf")
REJ, ACC, EXE = S.COMMAND_STATE_REJECTED, S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING


def geo(n, e):
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    return float(lat), float(lon)


def pos(p, n=1000.0, e=0.0, alt=1250.0):
    p.lat_deg, p.lon_deg = geo(n, e)
    p.alt_m = alt


def states(h, task_id):
    return [m.state for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id]


def reasons(h, task_id):
    return [m.reason for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id]


def move(task_id="m", **kw):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[UAV])
    pos(t.move_to.destination)
    for k, v in kw.items():
        setattr(t.move_to.destination, k, v)
    return t


def hold(task_id="h"):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[UAV])
    pos(t.hold.center)
    t.hold.radius_m = 300.0
    return t


def route(n, task_id="r"):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[UAV])
    for i in range(n):
        pos(t.route.waypoints.add().position, 500.0 + 10 * i)
    return t


def run_one(t, secs=1.0):
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(secs)
    return h


def bad_cases():
    def edit(t, f):
        f(t)
        return t

    yield "alt_inf", move(alt_m=INF)
    yield "alt_neg", move(alt_m=-100.0)
    yield "alt_100km", move(alt_m=100000.0)
    yield "lat_200", move(lat_deg=200.0)
    yield "lon_nan", move(lon_deg=NAN)
    yield "origin_0_0", move(lat_deg=0.0, lon_deg=0.0)
    yield "out_of_map", move(lat_deg=10.0, lon_deg=100.0)
    yield "speed_nan", edit(move(), lambda t: setattr(t.move_to, "speed_mps", NAN))
    yield "hold_radius_nan", edit(hold(), lambda t: setattr(t.hold, "radius_m", NAN))
    yield "hold_radius_1e9", edit(hold(), lambda t: setattr(t.hold, "radius_m", 1e9))
    yield "hold_duration_nan", edit(hold(), lambda t: setattr(t.hold, "duration_s", NAN))
    yield "hold_center_nan", edit(hold(), lambda t: setattr(t.hold.center, "lat_deg", NAN))
    yield "race_axis_nan", edit(hold(), lambda t: (setattr(t.hold.racetrack, "leg_length_m", 1000.0),
                                                  setattr(t.hold.racetrack, "axis_heading_deg", NAN)))
    yield "race_axis_999", edit(hold(), lambda t: (setattr(t.hold.racetrack, "leg_length_m", 1000.0),
                                                   setattr(t.hold.racetrack, "axis_heading_deg", 999.0)))
    yield "race_leg_inf", edit(hold(), lambda t: setattr(t.hold.racetrack, "leg_length_m", INF))
    yield "route_500", route(500)
    yield "route_nan", edit(route(3), lambda t: setattr(t.route.waypoints[1].position, "lon_deg", NAN))
    yield "route_loiter_radius_nan", edit(route(2), lambda t: (setattr(t.route.waypoints[0].loiter, "duration_s", 10.0),
                                                              setattr(t.route.waypoints[0].loiter, "radius_m", NAN)))
    yield "area_radius_nan", edit(c2_pb2.TaskCommand(task_id="a", assignees=[UAV]),
                                  lambda t: (pos(t.search_area.area.circle.center),
                                             setattr(t.search_area.area.circle, "radius_m", NAN)))
    yield "area_polygon_2", edit(c2_pb2.TaskCommand(task_id="a", assignees=[UAV]),
                                 lambda t: (pos(t.search_area.area.polygon.vertices.add()),
                                            pos(t.search_area.area.polygon.vertices.add(), 2000.0)))


@pytest.mark.parametrize("name,task", list(bad_cases()), ids=[n for n, _ in bad_cases()])
def test_tc_agt_040_bad_values_rejected_with_reason(name, task):
    h = run_one(task)
    assert states(h, task.task_id) == [REJ], name
    assert reasons(h, task.task_id)[0], name


def test_tc_agt_040_empty_task_id_and_valid_edges_accepted():
    h = run_one(move(task_id=""))
    assert states(h, "") == [REJ] and "task_id" in reasons(h, "")[0]
    assert states(run_one(move("ok", alt_m=0.0)), "ok")[:1] == [ACC]  # alt 0 = 현재 고도 유지
    assert states(run_one(route(ROUTE_MAX_POINTS, "edge")), "edge")[:1] == [ACC]
    ok = hold("rt")
    ok.hold.racetrack.leg_length_m, ok.hold.racetrack.axis_heading_deg = 1000.0, 359.0
    assert states(run_one(ok), "rt")[:1] == [ACC]


def test_tc_agt_040_nonexistent_entity_and_flocking_share_validation():
    h = Harness(make_scenario(2, "flocking", spacing_m=150.0, course_deg=0.0))
    t = move(alt_m=INF)
    send_c2(h.bus, "gcs-01", t, [UAV])
    ghost = move("ghost")
    ghost.assignees[:] = ["uav-099"]
    send_c2(h.bus, "gcs-01", ghost, [UAV])
    h.run_s(1.0)
    assert states(h, "m") == [REJ]
    assert states(h, "ghost") == []  # 이 기체에게 온 명령이 아니다


def test_tc_agt_040_racetrack_leg0_reports_executing():
    t = hold("race0")
    t.hold.racetrack.leg_length_m, t.hold.racetrack.axis_heading_deg = 0.0, 90.0
    h = run_one(t, 5.0)
    assert states(h, "race0")[:2] == [ACC, EXE]


def test_tc_agt_041_empty_assignees_rejected():
    h = Harness(make_scenario(3, "waypoint", course_deg=0.0))
    t = move("broadcast")
    t.ClearField("assignees")
    send_c2(h.bus, "gcs-01", t, ["uav-001", "uav-002", "uav-003"])
    h.run_s(1.0)
    got = [m for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == "broadcast"]
    assert {m.header.source for m in got} == {"uav-001", "uav-002", "uav-003"}
    assert {m.state for m in got} == {REJ} and all(m.reason == "empty assignees" for m in got)
    assert all(b.speed > 0 for b in h.core.bodies.values())  # 기체는 그대로 비행 중


def test_tc_agt_042_duplicate_task_id_replaces_earlier_mission():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", move("dup"), [UAV])
    h.run_s(2.0)
    second = move("dup")
    pos(second.move_to.destination, 0.0, 5000.0)
    send_c2(h.bus, "gcs-01", second, [UAV])
    h.run_s(60.0)
    sts = states(h, "dup")
    assert CANCELLED not in sts  # 이전 것을 취소로 보고하지 않는다 (같은 task_id 교체)
    assert sts.count(ACC) == 2
    assert h.core.bodies[UAV].course == pytest.approx(math.pi / 2, abs=0.2)  # 새 목적지(동쪽)로 향했다


CANCELLED = S.COMMAND_STATE_CANCELLED


# ---- QA-014: 모든 실수 필드의 유한성을 한 곳에서 검사 ----

def test_tc_agt_043_non_finite_anywhere_rejected_in_every_ma():
    for ma in ("waypoint", "formation", "flocking"):
        for name, t in bad_cases():
            if name not in ("hold_radius_nan", "route_nan"):
                continue
            h = Harness(make_scenario(2, ma, spacing_m=150.0, course_deg=0.0))
            send_c2(h.bus, "gcs-01", t, [UAV])
            h.run_s(1.0)
            assert states(h, t.task_id) == [REJ], (ma, name)
            assert reasons(h, t.task_id)[0], (ma, name)
    # 경로 점 전체가 NaN, 반복·중첩 필드 경로가 사유에 나온다
    t = route(2, "allnan")
    p = t.route.waypoints[0].position
    p.lat_deg = p.lon_deg = p.alt_m = NAN
    h = run_one(t)
    assert reasons(h, "allnan") == ["route.waypoints[0].position.lat_deg not finite"]
    # flocking의 Route 거부 사유(DEC-039 (3))는 그대로 전달된다
    h = Harness(make_scenario(2, "flocking", spacing_m=150.0, course_deg=0.0))
    send_c2(h.bus, "gcs-01", route(2, "rt2"), [UAV])
    h.run_s(1.0)
    assert reasons(h, "rt2") == ["unsupported task route"]
