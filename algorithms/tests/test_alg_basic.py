"""TC-AGT-014~015: hold, waypoint (IMP-AGT-011~013)"""

import math

import pytest

from swarm.v1 import c2_pb2, common_pb2, mp_pb2
from swarm_agent.geo import ned_offset, offset_geo
from swarm_agent.testing import Harness, make_scenario, send_c2

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)


def dest(n, e, alt=1600.0):
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    return float(lat), float(lon), alt


def dist_to(body, lat, lon):
    n, e = ned_offset(body.lat, body.lon, lat, lon)
    return math.hypot(float(n), float(e))


def test_tc_agt_014_hold_keeps_state():
    h = Harness(make_scenario(2, "hold", course_deg=30.0, speed_mps=24.0))
    h.run_s(60.0)
    for b in h.core.bodies.values():
        assert math.degrees(b.course) == pytest.approx(30.0, abs=0.5)
        assert b.speed == pytest.approx(24.0, abs=0.2)
        assert b.alt == pytest.approx(1500.0, abs=0.5)


def test_tc_agt_014_hold_orbit():
    h = Harness(make_scenario(1, "hold", {"orbit_radius_m": 400.0}))
    lat0, lon0 = h.core.bodies["uav-001"].lat, h.core.bodies["uav-001"].lon
    h.run_s(120.0)
    d = []
    for _ in range(100):
        h.run_s(0.5)
        d.append(dist_to(h.core.bodies["uav-001"], lat0, lon0))
    assert max(d) < 400.0 * 1.06 and min(d) > 400.0 * 0.94


def test_tc_agt_015_waypoint_mission_plan_and_status():
    plan = mp_pb2.MissionPlan(plan_id="p")
    t1 = plan.tasks.add(task_id="t1", assignees=["uav-001"])
    t1.move_to.destination.lat_deg, t1.move_to.destination.lon_deg, t1.move_to.destination.alt_m = dest(3000, 0)
    t1.move_to.speed_mps = 28.0
    t2 = plan.tasks.add(task_id="t2", assignees=["uav-001"])
    t2.move_to.destination.lat_deg, t2.move_to.destination.lon_deg, t2.move_to.destination.alt_m = dest(3000, 3000)
    plan.tasks.add(task_id="t3", assignees=["uav-001"]).strike.target_id = "tgt-001"  # 지원 안 함: 건너뜀
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0, mission_plan=plan))
    h.run_s(400.0)
    for t in ("t1", "t2"):
        assert h.task_states(t) == [S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED]
    assert h.task_states("t3") == []
    b = h.core.bodies["uav-001"]
    assert dist_to(b, *dest(3000, 3000)[:2]) < 300.0  # 마지막 점 둘레 선회
    assert b.alt == pytest.approx(1600.0, abs=2.0)


def test_tc_agt_015_c2_preempt_reject_and_rtb():
    plan = mp_pb2.MissionPlan(plan_id="p")
    t1 = plan.tasks.add(task_id="t1", assignees=["uav-001"])
    t1.move_to.destination.lat_deg, t1.move_to.destination.lon_deg, _ = dest(20000, 0)
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0, mission_plan=plan))
    home = (h.core.bodies["uav-001"].lat, h.core.bodies["uav-001"].lon)
    h.run_s(5.0)
    mv = c2_pb2.TaskCommand(task_id="c1", assignees=["uav-001"])
    mv.move_to.destination.lat_deg, mv.move_to.destination.lon_deg, _ = dest(0, 2500)
    send_c2(h.bus, "gcs-01", mv, ["uav-001"])
    strike = c2_pb2.TaskCommand(task_id="c2", assignees=["uav-001"])
    strike.strike.target_id = "tgt-001"
    send_c2(h.bus, "gcs-01", strike, ["uav-001"])
    h.run_s(200.0)
    assert h.task_states("t1")[-1] == S.COMMAND_STATE_CANCELLED
    assert h.task_states("c1")[-1] == S.COMMAND_STATE_COMPLETED
    assert h.task_states("c2") == [S.COMMAND_STATE_REJECTED]
    rtb = c2_pb2.TaskCommand(task_id="c3", assignees=["uav-001"])
    rtb.return_to_base.SetInParent()
    send_c2(h.bus, "gcs-01", rtb, ["uav-001"])
    h.run_s(200.0)
    assert h.task_states("c3")[-1] == S.COMMAND_STATE_COMPLETED
    assert dist_to(h.core.bodies["uav-001"], *home) < 300.0
    # 다른 기체에게 간 작업은 무시한다
    other = c2_pb2.TaskCommand(task_id="c4", assignees=["uav-009"])
    other.hold.SetInParent()
    send_c2(h.bus, "gcs-01", other, ["uav-001"])
    h.run_s(1.0)
    assert h.task_states("c4") == []
