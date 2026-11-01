"""TC-AGT-016~019: formation, flocking (IMP-AGT-014~015)"""

import itertools
import math

import numpy as np
import pytest

from swarm.v1 import c2_pb2, common_pb2, mp_pb2
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_algorithms.formation import slot_offsets

S = common_pb2
F = c2_pb2
MEMBERS = [f"uav-{i:03d}" for i in range(1, 6)]


def slot_errors(h: Harness, cmd: c2_pb2.FormationCommand) -> list[float]:
    """truth(가짜 Core)로 잰 추종기 슬롯 오차(수평, m)"""
    leader = cmd.leader or sorted(cmd.members)[0]
    offs = slot_offsets(cmd, leader)
    psi = h.core.bodies[leader].course
    out = []
    for m in cmd.members:
        if m == leader:
            continue
        x, y, _ = offs[m]
        dn, de = x * math.cos(psi) - y * math.sin(psi), x * math.sin(psi) + y * math.cos(psi)
        n, e, _ = h.core.offset_m(leader, m)
        out.append(math.hypot(n - dn, e - de))
    return out


def test_tc_agt_016_slot_geometry():
    def offs(shape, n=5, s=100.0, **kw):
        c = c2_pb2.FormationCommand(members=MEMBERS[:n], leader="uav-001", shape=shape, spacing_m=s, **kw)
        return [slot_offsets(c, "uav-001")[m] for m in MEMBERS[:n]]

    assert offs(F.FORMATION_SHAPE_LINE) == [(0, 0, 0), (0, 100, 0), (0, -100, 0), (0, 200, 0), (0, -200, 0)]
    assert offs(F.FORMATION_SHAPE_COLUMN) == [(0, 0, 0), (-100, 0, 0), (-200, 0, 0), (-300, 0, 0), (-400, 0, 0)]
    assert offs(F.FORMATION_SHAPE_WEDGE) == [(0, 0, 0), (-100, 100, 0), (-100, -100, 0), (-200, 200, 0),
                                             (-200, -200, 0)]
    assert offs(F.FORMATION_SHAPE_ECHELON) == [(0, 0, 0), (-100, 100, 0), (-200, 200, 0), (-300, 300, 0),
                                               (-400, 400, 0)]
    circ = offs(F.FORMATION_SHAPE_CIRCLE)
    assert circ[0] == (0, 0, 0) and all(math.hypot(x, y) == pytest.approx(100.0) for x, y, _ in circ[1:])
    custom = c2_pb2.FormationCommand(members=MEMBERS[:3], leader="uav-002", shape=F.FORMATION_SHAPE_CUSTOM)
    for v in [(-50, -50, 0), (0, 0, 0), (-50, 50, -20)]:
        custom.custom_offsets_m.add(x=v[0], y=v[1], z=v[2])
    co = slot_offsets(custom, "uav-002")
    assert co["uav-001"] == (-50, -50, 0) and co["uav-003"] == (-50, 50, -20) and co["uav-002"] == (0, 0, 0)
    # leader가 비면 사전순 첫 기체
    from swarm_algorithms.formation import pick_leader
    assert pick_leader(c2_pb2.FormationCommand(members=["uav-004", "uav-002"])) == "uav-002"


def formation_plan(shape=F.FORMATION_SHAPE_WEDGE, spacing=120.0) -> tuple[mp_pb2.MissionPlan, c2_pb2.FormationCommand]:
    plan = mp_pb2.MissionPlan(plan_id="p")
    f = plan.formations.add(group_id="alpha", members=MEMBERS, leader="uav-001", shape=shape, spacing_m=spacing)
    t = plan.tasks.add(task_id="t1", assignees=MEMBERS)
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg, t.move_to.destination.alt_m = 37.65, 128.1, 1600
    return plan, f


def test_tc_agt_017_formation_converges_from_plan():
    plan, f = formation_plan()
    h = Harness(make_scenario(5, "formation", mission_plan=plan, spacing_m=200.0))
    e0 = slot_errors(h, f)
    h.run_s(120.0)
    e1 = slot_errors(h, f)
    assert max(e0) > 200.0 and max(e1) < 5.0, (e0, e1)
    # 고도도 리더를 따른다 (리더는 MoveTo 고도 1600)
    assert all(abs(h.core.bodies[m].alt - h.core.bodies["uav-001"].alt) < 2.0 for m in MEMBERS)
    # 리더만 작업 상태를 보고한다
    assert h.task_states("t1")[:2] == [S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING]
    assert {m.header.source for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus"} == {"uav-001"}
    # 슬롯 오차 지표(MD)
    recs = [r for r in h.rt.vehicles["uav-002"].ports.md.records if r[1] == "slot_error_m"]
    assert recs and recs[-1][2] < 10.0


@pytest.mark.parametrize("shape", [F.FORMATION_SHAPE_COLUMN, F.FORMATION_SHAPE_CIRCLE])
def test_tc_agt_017_formation_from_c2(shape):
    h = Harness(make_scenario(5, "formation", spacing_m=200.0))
    h.run_s(2.0)
    cmd = c2_pb2.FormationCommand(group_id="bravo", members=MEMBERS, shape=shape, spacing_m=150.0)
    send_c2(h.bus, "gcs-01", cmd, MEMBERS)
    h.run_s(150.0)
    assert max(slot_errors(h, cmd)) < 10.0


def test_tc_agt_018_formation_needs_datalink():
    """P2P가 모두 손실되면 추종기는 리더 위치를 모르므로 편대를 이루지 못한다 (truth를 쓰지 않음)"""
    plan, f = formation_plan()
    h = Harness(make_scenario(5, "formation", mission_plan=plan, spacing_m=200.0),
                drop=lambda iface, src, dst: iface == "p2p")
    h.run_s(120.0)
    assert min(slot_errors(h, f)) > 100.0
    assert h.datalink.dropped > 0


def swarm_metrics(h: Harness):
    ids = sorted(h.core.bodies)
    d = [math.hypot(*h.core.offset_m(a, b)[:2]) for a, b in itertools.combinations(ids, 2)]
    v = np.array([[b.speed * math.cos(b.course), b.speed * math.sin(b.course)] for b in h.core.bodies.values()])
    polar = float(np.linalg.norm(v.mean(0)) / np.linalg.norm(v, axis=1).mean())
    return min(d), max(d), polar


def test_tc_agt_019_flocking_cohesion_separation_alignment():
    plan = mp_pb2.MissionPlan(plan_id="p")
    t = plan.tasks.add(task_id="t1", assignees=[f"uav-{i:03d}" for i in range(1, 21)])
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg = 37.58, 128.12
    # 침로가 제각각인 20대
    sc = make_scenario(20, "flocking", {"group": "a"}, spacing_m=250.0, mission_plan=plan)
    for i, e in enumerate(sc.entities[1:]):
        c = math.radians(20.0 * i)
        e.initial.velocity_ned_mps.x, e.initial.velocity_ned_mps.y = 22 * math.cos(c), 22 * math.sin(c)
    h = Harness(sc)
    _, dmax0, pol0 = swarm_metrics(h)
    h.run_s(150.0)
    dmin, dmax, pol = swarm_metrics(h)
    assert pol0 < 0.5 and pol > 0.95, (pol0, pol)
    assert dmin > 40.0, dmin
    assert dmax < dmax0, (dmax0, dmax)
    # 목표 쪽으로 움직였다
    from swarm_agent.geo import ned_offset
    b = h.core.bodies["uav-010"]
    n, e = ned_offset(b.lat, b.lon, 37.58, 128.12)
    assert math.hypot(float(n), float(e)) < 13000.0
    # 이웃 수 지표: 데이터링크로 받은 PeerStatus만 센다
    recs = [r for r in h.rt.vehicles["uav-001"].ports.md.records if r[1] == "neighbors"]
    assert recs[-1][2] >= 3


def test_tc_agt_019_flocking_without_p2p_has_no_neighbors():
    sc = make_scenario(6, "flocking", spacing_m=100.0)
    h = Harness(sc, drop=lambda iface, src, dst: iface == "p2p")
    h.run_s(10.0)
    for v in h.rt.vehicles.values():
        assert all(r[2] == 0.0 for r in v.ports.md.records if r[1] == "neighbors")


def test_tc_agt_019_flocking_search_area_goal_and_group_filter():
    plan = mp_pb2.MissionPlan(plan_id="p")
    t = plan.tasks.add(task_id="s1", assignees=["uav-001", "uav-002"])
    for lat, lon in [(37.52, 128.02), (37.53, 128.02), (37.53, 128.03), (37.52, 128.03)]:
        t.search_area.area.polygon.vertices.add(lat_deg=lat, lon_deg=lon)
    sc = make_scenario(4, "flocking", mission_plan=plan, spacing_m=150.0)
    for i, e in enumerate(sc.entities[1:]):
        from google.protobuf import struct_pb2
        s = struct_pb2.Struct()
        s.update({"group": "a" if i < 2 else "b"})
        e.autonomy.ma_params.CopyFrom(s)
    h = Harness(sc)
    h.run_s(200.0)
    assert h.task_states("s1").count(S.COMMAND_STATE_COMPLETED) == 2
    # 그룹 b(uav-003, 004)는 그룹 a의 PeerStatus를 이웃으로 세지 않는다
    agents = h.rt._batches["flocking"][0].agents
    assert set(agents["uav-003"].table) <= {"uav-004"}
