"""TC-AGT-075~081: 실행 중 받은 MissionPlan 반영 (IMP-AGT-034, DEC-076, CR-GW-008)"""

import pytest

from swarm.v1 import c2_pb2, common_pb2, link_pb2, mp_pb2, options_pb2
from swarm_agent.geo import ned_offset, offset_geo
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)
A, B = "uav-001", "uav-002"
ACC, EXE, DONE, CAN, REJ = (S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED,
                            S.COMMAND_STATE_CANCELLED, S.COMMAND_STATE_REJECTED)


def set_pos(p, n, e, alt=0.0):
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    p.lat_deg, p.lon_deg, p.alt_m = float(lat), float(lon), alt


def move(task_id, n, e, *assignees):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=list(assignees) or [A])
    set_pos(t.move_to.destination, n, e)
    return t


def route(task_id, pts):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A])
    for n, e in pts:
        set_pos(t.route.waypoints.add().position, n, e)
    return t


def plan_of(plan_id, *tasks):
    p = mp_pb2.MissionPlan(plan_id=plan_id)
    p.tasks.extend(tasks)
    return p


def send_plan(h, plan, dst=(A,)):
    """Gateway와 같은 경로: swarm/<gcs>/tx/mp/MissionPlan (DEC-076)"""
    env = link_pb2.LinkEnvelope(dst=list(dst), iface=options_pb2.L1_INTERFACE_MP, msg_type="swarm.v1.MissionPlan",
                                payload=plan.SerializeToString())
    env.header.source = "gcs-01"
    env.header.sim_time_us = h.core.frame * h.core.dt_us
    h.bus.put(keys.tx("gcs-01", keys.Iface.MP, "MissionPlan"), env.SerializeToString(),
              protobuf_encoding(env.DESCRIPTOR.full_name))


def dist(h, eid, n, e):
    b = h.core.bodies[eid]
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    dn, de = ned_offset(float(lat), float(lon), b.lat, b.lon)
    return (float(dn) ** 2 + float(de) ** 2) ** 0.5


def reason(h, task_id, state):
    return [m.reason for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id and m.state == state]


def test_tc_agt_075_runtime_plan_move_to():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    assert h.task_states("m1") == []
    send_plan(h, plan_of("p1", move("m1", 3000, 0)))
    h.run_s(200.0)
    assert h.task_states("m1") == [ACC, EXE, DONE]
    assert dist(h, A, 3000, 0) < 500.0        # 도착 뒤 그 점 둘레 선회


def test_tc_agt_076_runtime_plan_route_and_order():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    send_plan(h, plan_of("p1", route("r1", [(2000, 0), (2000, 2000)]), move("m2", 0, 2000)))
    h.run_s(250.0)
    states = h.task_states("r1")              # Route는 진행률과 함께 EXECUTING을 여러 번 보낸다
    assert states[:2] == [ACC, EXE] and states[-1] == DONE and set(states) == {ACC, EXE, DONE}
    assert h.task_states("m2")[0] == ACC      # 계획 안의 순서대로 다음 작업
    h.run_s(200.0)
    assert h.task_states("m2") == [ACC, EXE, DONE]


def test_tc_agt_077_same_plan_id_not_repeated():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    p = plan_of("p1", move("m1", 2000, 0))
    send_plan(h, p)
    h.run_s(5.0)
    send_plan(h, p)                           # 수행 중 재수신
    send_plan(h, plan_of("p1", move("x1", 0, 9000)))   # 같은 plan_id면 내용이 달라도 무시
    h.run_s(150.0)
    assert h.task_states("m1") == [ACC, EXE, DONE]
    assert h.task_states("x1") == []
    send_plan(h, p)                           # 끝난 뒤 재수신
    h.run_s(10.0)
    assert h.task_states("m1") == [ACC, EXE, DONE]


def test_tc_agt_078_new_plan_id_replaces():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    send_plan(h, plan_of("p1", move("a", 20000, 0), move("b", 0, 20000)))
    h.run_s(5.0)
    send_plan(h, plan_of("p2", move("c", 1500, 1500)))
    h.run_s(150.0)
    assert h.task_states("a") == [ACC, EXE, CAN] and reason(h, "a", CAN) == ["preempted"]
    assert h.task_states("b") == [CAN]        # 시작 전 대기 작업도 교체된다
    assert h.task_states("c") == [ACC, EXE, DONE]


def test_tc_agt_078_same_task_id_is_content_replace():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    send_plan(h, plan_of("p1", move("a", 20000, 0)))
    h.run_s(5.0)
    send_plan(h, plan_of("p2", move("a", 1500, 0)))
    h.run_s(120.0)
    states = h.task_states("a")
    assert CAN not in states and states[-1] == DONE
    assert dist(h, A, 1500, 0) < 500.0


def test_tc_agt_079_other_vehicle_tasks_excluded():
    h = Harness(make_scenario(2, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    send_plan(h, plan_of("p1", move("a", 20000, 0)), [A])
    h.run_s(3.0)
    send_plan(h, plan_of("p2", move("b", 1500, 0, B)), [A, B])   # A에 배정된 작업이 없다
    h.run_s(120.0)
    assert h.task_states("a") == [ACC, EXE]   # A는 수행 중인 작업을 계속한다
    assert [m.header.source for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == "b"] == [B] * 3
    assert h.task_states("b") == [ACC, EXE, DONE]


def test_tc_agt_080_rejected_tasks_do_not_preempt():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(3.0)
    send_plan(h, plan_of("p1", move("a", 20000, 0)))
    h.run_s(3.0)
    bad = c2_pb2.TaskCommand(task_id="s1", assignees=[A])
    bad.strike.target_id = "tgt-001"
    send_plan(h, plan_of("p2", bad, move("off", 0, 0)))
    h.run_s(0.1)
    assert h.task_states("s1") == [REJ]       # 지원하지 않는 작업은 알린다
    assert h.task_states("off")[0] == ACC     # 유효한 작업이 있으면 교체
    send_plan(h, plan_of("p3", bad))
    h.run_s(1.0)
    assert h.task_states("off")[-1] != CAN    # 유효한 작업이 없는 계획은 밀어내지 않는다


def test_tc_agt_080_flocking_and_formation():
    h = Harness(make_scenario(3, "flocking", course_deg=0.0))
    h.run_s(2.0)
    send_plan(h, plan_of("p1", move("m", 3000, 0, A, B, "uav-003")), [A, B, "uav-003"])
    h.run_s(2.0)
    assert h.task_states("m")[:3] == [ACC] * 3

    members = [A, B, "uav-003"]
    h = Harness(make_scenario(3, "formation", course_deg=0.0))
    h.run_s(2.0)
    p = plan_of("p1")
    p.formations.add(group_id="late", members=members, spacing_m=150.0)
    send_plan(h, p, members)
    h.run_s(0.2)
    assert {h.rt.vehicles[m].ma.cmd.group_id for m in members} == {"late"}
    q = plan_of("p1")
    q.formations.add(group_id="other", members=members, spacing_m=150.0)
    send_plan(h, q, members)                  # 같은 plan_id: 편대를 다시 잡지 않는다
    h.run_s(0.2)
    assert {h.rt.vehicles[m].ma.cmd.group_id for m in members} == {"late"}


@pytest.mark.parametrize("ma", ["waypoint", "flocking"])
def test_tc_agt_081_same_input_same_output(ma):
    def run():
        ids = [A, B]
        h = Harness(make_scenario(2, ma, course_deg=0.0))
        h.run_s(1.0)
        send_plan(h, plan_of("p1", move("a", 4000, 0, *ids)), ids)
        h.run_s(3.0)
        send_plan(h, plan_of("p2", move("b", 0, 4000, *ids)), ids)
        h.run_s(5.0)
        return ([m.SerializeToString(deterministic=True) for m in h.gcs_rx],
                [(b.lat, b.lon, b.alt) for b in h.core.bodies.values()])
    a, b = run(), run()
    assert a[0] and a == b
