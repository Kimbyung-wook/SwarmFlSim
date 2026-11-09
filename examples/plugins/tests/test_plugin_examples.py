"""TC-EXP-001~006: 플러그인 예제 (IMP-EXP-001~004). 가짜 Core·Datalink로 실행한다."""

import math
from importlib.metadata import entry_points

import pytest

from swarm.v1 import c2_pb2, common_pb2, vi_pb2
from swarm_agent.geo import ned_offset, offset_geo
from swarm_agent.testing import Harness, make_scenario, send_c2

ORIGIN = (37.5, 128.0, 1500.0)


def separation(a, b) -> float:
    n, e = ned_offset(a.lat, a.lon, b.lat, b.lon)
    return math.hypot(float(n), float(e))


def test_tc_exp_001_entry_points():
    assert {"example_turn", "example_patrol", "example_rendezvous"} <= {e.name for e in entry_points(group="swarm.ma")}
    assert "example_hsa" in {e.name for e in entry_points(group="swarm.fa")}


def test_tc_exp_002_turn_reaches_heading_and_keeps_altitude():
    h = Harness(make_scenario(1, "example_turn", {"heading_deg": 200.0}, course_deg=45.0))
    h.run_s(60.0)
    b = h.core.bodies["uav-001"]
    assert math.degrees(b.course) % 360.0 == pytest.approx(200.0, abs=1.0)
    assert b.alt == pytest.approx(1500.0, abs=1.0)


def test_tc_exp_003_patrol_runs_move_to():
    h = Harness(make_scenario(1, "example_patrol"))
    h.run_s(1.0)
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], 1500.0, 0.0)
    task = c2_pb2.TaskCommand(task_id="t1", assignees=["uav-001"])
    task.move_to.destination.lat_deg, task.move_to.destination.lon_deg = float(lat), float(lon)
    task.move_to.destination.alt_m = 1500.0
    send_c2(h.bus, "gcs-01", task, ["uav-001"])
    h.run_s(150.0)
    states = h.task_states("t1")
    assert states[0] == common_pb2.COMMAND_STATE_ACCEPTED
    assert states[-1] == common_pb2.COMMAND_STATE_COMPLETED


def test_tc_exp_004_patrol_rejects_unsupported():
    h = Harness(make_scenario(1, "example_patrol"))
    h.run_s(1.0)
    task = c2_pb2.TaskCommand(task_id="t2", assignees=["uav-001"])
    task.track.target_id = "tgt-1"
    send_c2(h.bus, "gcs-01", task, ["uav-001"])
    h.run_s(2.0)
    assert h.task_states("t2") == [common_pb2.COMMAND_STATE_REJECTED]


def test_tc_exp_005_rendezvous_closes_distance():
    h = Harness(make_scenario(4, "example_rendezvous", spacing_m=2000.0))
    bodies = h.core.bodies
    h.run_s(0.1)
    before = separation(bodies["uav-001"], bodies["uav-004"])
    h.run_s(45.0)
    assert separation(bodies["uav-001"], bodies["uav-004"]) < before * 0.7


def test_tc_exp_006_hsa_fa_flies_hsa_command():
    sc = make_scenario(1, "example_turn", {"heading_deg": 120.0}, course_deg=45.0)
    sc.entities[1].autonomy.fa_plugin = "example_hsa"
    h = Harness(sc)
    h.run_s(60.0)
    assert math.degrees(h.core.bodies["uav-001"].course) % 360.0 == pytest.approx(120.0, abs=1.0)


def test_tc_exp_007_hsa_fa_rejects_other_modes():
    from swarm_plugin_examples.hsa_fa import HsaOnlyFlightAutonomy

    fa = HsaOnlyFlightAutonomy()
    cap = fa.on_init("uav-001", {})
    assert cap.supports_hsa and not cap.supports_waypoint
    cmd = vi_pb2.FlightCommand(command_id="c1")
    cmd.curve.orbit.radius_m = 300.0
    assert fa.on_command(cmd).state == common_pb2.COMMAND_STATE_REJECTED
