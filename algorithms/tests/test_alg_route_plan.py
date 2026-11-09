"""TC-AGT-082~087: RoutePlan과 MissionPlan의 관계 (IMP-AGT-035, D-29, O-26, DEC-076)"""

import pytest

from swarm.v1 import c2_pb2, link_pb2, mp_pb2, options_pb2, vi_pb2
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding
from test_alg_plan_update import A, ACC, CAN, DONE, EXE, dist, move, plan_of, reason, send_plan, set_pos


def route_plan(route_id, pts):
    r = mp_pb2.RoutePlan(route_id=route_id, entity_id=A)
    for n, e in pts:
        w = r.waypoints.add()
        set_pos(w.position, n, e)
    return r


def send_route(h, r):
    env = link_pb2.LinkEnvelope(dst=[A], iface=options_pb2.L1_INTERFACE_MP, msg_type="swarm.v1.RoutePlan",
                                payload=r.SerializeToString())
    env.header.source = "gcs-01"
    env.header.sim_time_us = h.core.frame * h.core.dt_us
    h.bus.put(keys.tx("gcs-01", keys.Iface.MP, "RoutePlan"), env.SerializeToString(),
              protobuf_encoding(env.DESCRIPTOR.full_name))


def referencing_task(route_id, pts):
    """Gateway가 RoutePlan을 참조한 MissionPlan을 펴는 모양: task_id = route_id, 1점 move_to, 2점 이상 route"""
    if len(pts) == 1:
        return move(route_id, *pts[0])
    t = c2_pb2.TaskCommand(task_id=route_id, assignees=[A])
    for n, e in pts:
        set_pos(t.route.waypoints.add().position, n, e)
    return t


def uniq(states):
    return [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]


PTS = {"one": [(2000, 0)], "two": [(1500, 0), (1500, 1500)]}


def deliver(h, order, r, p):
    if order == "route_first":
        send_route(h, r)
        h.core.step(3)
        send_plan(h, p)
    elif order == "plan_first":
        send_plan(h, p)
        h.core.step(3)
        send_route(h, r)
    elif order == "same_tick_route_plan":
        send_route(h, r)
        send_plan(h, p)
    else:
        send_plan(h, p)
        send_route(h, r)


@pytest.mark.parametrize("pts", ["one", "two"])
@pytest.mark.parametrize("order", ["route_first", "plan_first", "same_tick_route_plan", "same_tick_plan_route"])
def test_tc_agt_082_084_order_independent_completion(order, pts):
    """082: RoutePlan 먼저, 083: MissionPlan 먼저, 084: 같은 틱(양쪽 순서)"""
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(1.0)
    deliver(h, order, route_plan("r1", PTS[pts]), plan_of("p1", referencing_task("r1", PTS[pts])))
    h.run_s(250.0)
    assert uniq(h.task_states("r1")) == [ACC, EXE, DONE], order
    assert dist(h, A, *PTS[pts][-1]) < 500.0


def test_tc_agt_085_standalone_route_preempts_visibly():
    """단독 RoutePlan은 수행 중 작업을 몰래 덮지 않는다: 작업은 CANCELLED로 끝나고(O-26) 항로를 비행한다"""
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(1.0)
    send_plan(h, plan_of("p1", move("a", 20000, 0), move("next", 0, 3000)))
    h.run_s(5.0)
    assert h.task_states("a") == [ACC, EXE]
    send_route(h, route_plan("r1", [(1500, 800), (1500, 2000)]))
    h.run_s(1.0)
    assert h.task_states("a") == [ACC, EXE, CAN] and reason(h, "a", CAN) == ["preempted"]
    assert h.task_states("r1") == []          # 항로 자체의 작업 상태는 없다
    assert h.task_states("next") == []        # 항로가 끝날 때까지 대기
    h.run_s(150.0)
    assert h.task_states("r1") == []
    assert h.task_states("next")[0] == ACC    # 항로를 마치면 대기 작업을 잇는다


def test_tc_agt_086_standalone_route_when_idle_and_late_reference():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    h.run_s(1.0)
    send_route(h, route_plan("solo", [(1500, 0)]))
    h.run_s(90.0)
    assert h.task_states("solo") == []
    assert dist(h, A, 1500, 0) < 500.0
    assert h.rt.vehicles[A].ma.pilot.tracker.current is None
    # 참조 계획이 끝난 뒤 늦게 온 RoutePlan은 다시 비행하지 않는다
    send_plan(h, plan_of("p1", move("r2", 0, 1000)))
    h.run_s(120.0)
    assert h.task_states("r2") == [ACC, EXE, DONE]
    send_route(h, route_plan("r2", [(5000, 5000)]))
    h.run_s(5.0)
    assert h.rt.vehicles[A].ma.pilot.tracker.current is None


@pytest.mark.parametrize("order", ["plan_first", "same_tick_plan_route"])
def test_tc_agt_087_same_input_same_output(order):
    def run():
        h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
        cmds = []

        def on(s):
            env = link_pb2.LinkEnvelope.FromString(s.payload)
            cmds.append(vi_pb2.FlightCommandStatus.FromString(env.payload).SerializeToString(deterministic=True))
        h.bus.subscribe(keys.rx("gcs-01", keys.Iface.VI, "FlightCommandStatus"), on)
        h.run_s(1.0)
        deliver(h, order, route_plan("r1", PTS["one"]), plan_of("p1", referencing_task("r1", PTS["one"])))
        h.run_s(5.0)
        send_route(h, route_plan("r2", [(500, 500)]))
        h.run_s(5.0)
        b = h.core.bodies[A]
        return [m.SerializeToString(deterministic=True) for m in h.gcs_rx], cmds, (b.lat, b.lon, b.alt)
    a, b = run(), run()
    assert a[0] and a == b
