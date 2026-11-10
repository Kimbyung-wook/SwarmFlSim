"""TC-AGT-095~117: GCS 링크 상실 행동 (IMP-AGT-038, DEC-078, DEC-013, DEC-039)"""

import math

import pytest

from swarm.v1 import c2_pb2, common_pb2, link_pb2, mp_pb2, options_pb2
from swarm_agent.geo import ned_offset, offset_geo
from swarm_agent.plugins import PluginRegistry
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_algorithms.common import LOST_LINK_PARAMS, LinkMonitor, TaskPilot
from swarm_algorithms.flocking import Flocking
from swarm_algorithms.formation import Formation
from swarm_algorithms.hold import Hold
from swarm_algorithms.waypoint import WaypointFollower
from swarm_api import MissionAutonomy, keys, resolve_params
from swarm_api.bus import protobuf_encoding

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)
A, B = "uav-001", "uav-002"
ACC, EXE, DONE, CAN = (S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED,
                       S.COMMAND_STATE_CANCELLED)
UNTIL, RESUME, CONT = (c2_pb2.LOST_LINK_POLICY_HOLD_UNTIL_COMMAND, c2_pb2.LOST_LINK_POLICY_RESUME_ON_RECOVERY,
                       c2_pb2.LOST_LINK_POLICY_CONTINUE)
FAST = {"lost_link_timeout_s": 1.0}


def set_pos(p, n, e, alt=0.0):
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    p.lat_deg, p.lon_deg, p.alt_m = float(lat), float(lon), alt


def move(task_id, n, e, policy=c2_pb2.LOST_LINK_POLICY_UNSPECIFIED, *assignees):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=list(assignees) or [A], lost_link_policy=policy)
    set_pos(t.move_to.destination, n, e)
    return t


def beat(h, *ids):
    """다음 틱에 보이는 Heartbeat (Datalink와 같은 rx 경로)"""
    h.datalink.heartbeat("gcs-01", list(ids) or [A], rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def beating(h, seconds, *ids):
    """1 Hz Heartbeat를 넣으며 진행한다"""
    for _ in range(round(seconds)):
        beat(h, *ids)
        h.core.step(50)


def md(h, name, eid=A):
    return [r[2] for r in h.rt.vehicles[eid].ports.md.records if r[1] == name]


def md_frames(h, name, eid=A):
    return [(r[0], r[2]) for r in h.rt.vehicles[eid].ports.md.records if r[1] == name]


def fa(h, eid=A):
    return h.rt.vehicles[eid].fa


def pos_ne(h, eid=A):
    b = h.core.bodies[eid]
    n, e = ned_offset(ORIGIN[0], ORIGIN[1], b.lat, b.lon)
    return float(n), float(e)


def far_from(h, ref, eid=A):
    n, e = pos_ne(h, eid)
    return ((n - ref[0]) ** 2 + (e - ref[1]) ** 2) ** 0.5


def lost_waypoint(policy=c2_pb2.LOST_LINK_POLICY_UNSPECIFIED, params=None, ma="waypoint", task=True):
    """먼 목표로 비행 중 Heartbeat를 끊어 1 s 뒤 상실시킨 상태까지 진행한다"""
    h = Harness(make_scenario(1, ma, {**FAST, **(params or {})}, course_deg=0.0))
    h.core.step(2)
    if task:
        send_c2(h.bus, "gcs-01", move("far", 20000, 0, policy), [A])
    beating(h, 3)
    h.core.step(60)
    assert md(h, "link_state") == ["lost"]
    return h


def send_plan(h, plan, dst=(A,)):
    env = link_pb2.LinkEnvelope(dst=list(dst), iface=options_pb2.L1_INTERFACE_MP, msg_type="swarm.v1.MissionPlan",
                                payload=plan.SerializeToString())
    env.header.source = "gcs-01"
    h.bus.put(keys.tx("gcs-01", keys.Iface.MP, "MissionPlan"), env.SerializeToString(),
              protobuf_encoding(env.DESCRIPTOR.full_name))


@pytest.mark.parametrize("ma", ["waypoint", "hold", "flocking", "formation"])
def test_tc_agt_095_no_heartbeat_no_monitoring(ma):
    h = Harness(make_scenario(1, ma, FAST, course_deg=0.0))
    h.core.step(2)
    if ma == "waypoint":
        send_c2(h.bus, "gcs-01", move("far", 20000, 0), [A])
    h.run_s(8.0)
    assert md(h, "link_state") == [] and md(h, "lost_link_action") == []
    assert fa(h)._kind != "orbit"


def test_tc_agt_096_timeout_boundary():
    h = Harness(make_scenario(1, "waypoint"))
    h.core.step(50)
    beat(h)                                 # 틱 50에 보인다
    h.core.step(1)
    h.core.step(250)                        # 틱 300 = 수신 + 정확히 5 s: 아직 상실 아님
    assert md(h, "link_state") == []
    h.core.step(1)
    assert md_frames(h, "link_state") == [(301, "lost")]


def test_tc_agt_097_heartbeat_at_boundary_keeps_link_and_custom_timeout():
    h = Harness(make_scenario(1, "waypoint"))
    h.core.step(50)
    beat(h)
    h.core.step(250)                        # 다음 틱(300)이 경계
    beat(h)
    h.core.step(20)
    assert md(h, "link_state") == []
    h2 = Harness(make_scenario(1, "waypoint", {"lost_link_timeout_s": 2.0}))
    h2.core.step(50)
    beat(h2)
    h2.core.step(1 + 100 + 1)
    assert md_frames(h2, "link_state") == [(151, "lost")]


def test_tc_agt_098_hold_until_command():
    h = lost_waypoint(UNTIL)
    ref = pos_ne(h)
    assert fa(h)._kind == "orbit" and fa(h)._cmd_id == f"{A}-lost-link-1"
    assert md(h, "lost_link_policy") == ["hold_until_command"] and md(h, "lost_link_action") == ["hold"]
    h.run_s(30.0)
    assert far_from(h, ref) < 800.0         # 목표(20 km 북쪽)로 가지 않고 그 자리에서 선회
    beating(h, 20)
    assert md(h, "link_state") == ["lost", "recovered"] and md(h, "lost_link_action") == ["hold", "keep_hold"]
    assert fa(h)._kind == "orbit" and far_from(h, ref) < 800.0
    assert CAN not in h.task_states("far")
    beat(h)
    send_c2(h.bus, "gcs-01", move("next", 0, 5000), [A])
    h.core.step(5)
    assert fa(h)._kind == "waypoint" and md(h, "lost_link_action")[-1] == "command"
    assert h.task_states("far")[-1] == CAN and h.task_states("next")[0] == ACC


def route(task_id, pts, policy):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A], lost_link_policy=policy)
    for n, e in pts:
        set_pos(t.route.waypoints.add().position, n, e)
    return t


def test_tc_agt_099_resume_continues_interrupted_route():
    h = Harness(make_scenario(1, "waypoint", FAST, course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", route("r1", [(400, 0), (1800, 0), (3200, 0)], RESUME), [A])
    beating(h, 20)                           # 첫 항로점 통과
    pilot = h.rt.vehicles[A].ma.pilot
    assert pilot.leg_i == 1
    h.core.step(60)
    assert fa(h)._kind == "orbit" and md(h, "lost_link_action") == ["hold"]
    h.run_s(20.0)
    assert pilot.leg_i == 1 and DONE not in h.task_states("r1")
    beat(h)
    h.core.step(2)
    assert md(h, "lost_link_action") == ["hold", "resume"] and fa(h)._kind == "waypoint" and pilot.leg_i == 1
    beating(h, 200)
    states = h.task_states("r1")
    assert states[-1] == DONE and CAN not in states
    assert md(h, "link_state") == ["lost", "recovered"]


def test_tc_agt_100_resume_keeps_loiter_time_on_station():
    h = Harness(make_scenario(1, "waypoint", FAST, course_deg=0.0))
    h.core.step(2)
    t = c2_pb2.TaskCommand(task_id="h1", assignees=[A], lost_link_policy=RESUME)
    t.hold.radius_m, t.hold.duration_s = 400.0, 60.0
    send_c2(h.bus, "gcs-01", t, [A])
    pilot = None
    for _ in range(240):
        beat(h)
        h.core.step(50)
        pilot = h.rt.vehicles[A].ma.pilot
        if pilot._on_station_since is not None and h.rt.vehicles[A].ctx.sim_time_s - pilot._on_station_since > 15.0:
            break
    h.core.step(60)                        # 상실
    assert pilot._station_s > 15.0
    held = pilot._station_s
    h.run_s(30.0)                           # 선회 시간은 체류로 치지 않는다
    assert pilot._station_s == held and DONE not in h.task_states("h1")
    beat(h)
    h.core.step(2)
    assert pilot._station_s == held and fa(h)._kind == "orbit" and fa(h)._cmd_id != f"{A}-lost-link-1"
    for i in range(1200):
        if i % 10 == 0:
            beat(h)
        h.core.step(5)
        if DONE in h.task_states("h1"):
            break
    assert h.task_states("h1")[-1] == DONE
    remaining = h.rt.vehicles[A].ctx.sim_time_s - pilot._on_station_since
    assert 60.0 - held - 0.5 <= remaining <= 60.0 - held + 0.5   # 처음부터 다시 60 s를 채우지 않는다


def run_continue(link_beats):
    h = Harness(make_scenario(1, "waypoint", FAST, course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("far", 20000, 0, CONT), [A])
    for i in range(30):
        if link_beats and (i < 3 or i > 20):      # 상실 후 복구
            beat(h)
        h.core.step(50)
    return h


def test_tc_agt_101_continue_ignores_loss_and_recovery():
    a, b = run_continue(True), run_continue(False)
    assert md(a, "link_state") == ["lost", "recovered"] and md(a, "lost_link_action") == ["continue"]
    assert md(a, "lost_link_policy") == ["continue"]
    assert md(b, "link_state") == []
    assert (a.core.bodies[A].lat, a.core.bodies[A].lon) == (b.core.bodies[A].lat, b.core.bodies[A].lon)
    assert a.task_states("far") == b.task_states("far") and fa(a)._kind == "waypoint"


def test_tc_agt_102_policy_task_overrides_param():
    h = lost_waypoint(params={"lost_link_policy": "resume_on_recovery"})
    assert md(h, "lost_link_policy") == ["resume_on_recovery"]
    h2 = lost_waypoint(UNTIL, params={"lost_link_policy": "continue"})
    assert md(h2, "lost_link_policy") == ["hold_until_command"]
    h3 = lost_waypoint(CONT, params={"lost_link_policy": "resume_on_recovery"})
    assert md(h3, "lost_link_action") == ["continue"]
    h4 = lost_waypoint()                    # 변수 기본
    assert md(h4, "lost_link_policy") == ["hold_until_command"]
    values, rejected = resolve_params(LOST_LINK_PARAMS, {}, {"lost_link_policy": "nope"})
    assert values["lost_link_timeout_s"] == 5.0 and rejected == {"lost_link_policy": "choice"}
    for cls in (WaypointFollower, Formation, Flocking, Hold):
        names = {d.name for d in cls.PARAMS}
        assert {"lost_link_timeout_s", "lost_link_policy"} <= names


def test_tc_agt_103_recovery_repeats():
    h = lost_waypoint(RESUME)
    for n in (1, 2):
        beat(h)
        h.core.step(2)
        assert fa(h)._kind == "waypoint"
        beat(h)
        h.core.step(110)
        assert fa(h)._kind == "orbit" and fa(h)._cmd_id == f"{A}-lost-link-{n + 1}"
    assert md(h, "link_state") == ["lost", "recovered", "lost", "recovered", "lost"]
    assert md(h, "lost_link_action") == ["hold", "resume", "hold", "resume", "hold"]
    u = lost_waypoint(UNTIL)
    for _ in range(2):
        beat(u)
        u.core.step(120)
    assert md(u, "link_state") == ["lost", "recovered", "lost", "recovered", "lost"]
    assert md(u, "lost_link_action") == ["hold", "keep_hold", "keep_hold"]
    assert fa(u)._cmd_id == f"{A}-lost-link-1"          # 선회 중 재상실은 명령을 다시 내지 않는다


@pytest.mark.parametrize("param,expect", [("hold_until_command", "orbit"), ("resume_on_recovery", "orbit"),
                                          ("continue", "")])
def test_tc_agt_104_idle_vehicle(param, expect):
    h = lost_waypoint(params={"lost_link_policy": param}, task=False)
    assert fa(h)._kind == expect


def test_tc_agt_105_new_commands_release_hold():
    h = lost_waypoint(UNTIL)
    send_c2(h.bus, "gcs-01", move("cmd", 0, 5000), [A])  # 링크가 상실 상태여도 받은 명령이 우선
    h.core.step(3)
    assert fa(h)._kind == "waypoint" and md(h, "lost_link_action") == ["hold", "command"]
    h2 = lost_waypoint(UNTIL)
    plan = mp_pb2.MissionPlan(plan_id="p2")
    plan.tasks.append(move("pm", 0, 5000))
    send_plan(h2, plan)
    h2.core.step(3)
    assert fa(h2)._kind == "waypoint" and h2.task_states("pm")[0] == ACC and md(h2, "lost_link_action")[-1] == "command"
    h3 = lost_waypoint(UNTIL)              # 다른 기체 작업·취소는 새 작업이 아니다
    send_c2(h3.bus, "gcs-01", move("other", 0, 5000, UNTIL, B), [A])
    h3.core.step(3)
    assert fa(h3)._kind == "orbit" and md(h3, "lost_link_action") == ["hold"]


def test_tc_agt_106_command_same_tick_as_loss_wins():
    h = Harness(make_scenario(1, "waypoint", FAST, course_deg=0.0))
    h.core.step(50)
    beat(h)
    h.core.step(51)                       # 다음 틱 101이 상실 틱
    assert md(h, "link_state") == []
    send_c2(h.bus, "gcs-01", move("cmd", 5000, 0), [A])
    h.core.step(1)
    assert md_frames(h, "link_state") == [(101, "lost")] and md(h, "lost_link_action") == ["command"]
    h.core.step(2)
    assert fa(h)._kind == "waypoint"


def test_tc_agt_107_heartbeat_not_a_task_and_queue_paused():
    plan = mp_pb2.MissionPlan(plan_id="p1")
    plan.tasks.extend([move("q1", 20000, 0, RESUME), move("q2", 0, 20000, RESUME)])
    h = Harness(make_scenario(1, "waypoint", FAST, course_deg=0.0, mission_plan=plan))
    beating(h, 3)
    assert not [m for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.reason.startswith("unsupported")]
    h.core.step(60)
    assert fa(h)._kind == "orbit"
    tracker = h.rt.vehicles[A].ma.pilot.tracker
    send_c2(h.bus, "gcs-01", c2_pb2.TaskCommand(task_id="q1", assignees=[A], cancel=True), [A])
    h.run_s(1.0)
    assert h.task_states("q1")[-1] == CAN and tracker.current is None and fa(h)._kind == "orbit"  # 취소는 선회를 끝내지 않고
    assert h.task_states("q2") == []                                                               # 대기 작업도 시작하지 않는다
    beat(h)
    h.core.step(3)
    assert h.task_states("q2")[0] == ACC and fa(h)._kind == "waypoint"


def test_tc_agt_112_task_started_on_loss_tick_waits_for_hold():
    """상실 틱에 취소로 대기 작업이 시작돼도 선회가 먼저다. 취소는 새 작업 명령이 아니다"""
    plan = mp_pb2.MissionPlan(plan_id="p1")
    plan.tasks.extend([move("q1", 20000, 0, RESUME), move("q2", 0, 20000, RESUME)])
    h = Harness(make_scenario(1, "waypoint", FAST, course_deg=0.0, mission_plan=plan))
    h.core.step(50)
    beat(h)
    h.core.step(51)                       # 다음 틱 101이 상실 틱
    send_c2(h.bus, "gcs-01", c2_pb2.TaskCommand(task_id="q1", assignees=[A], cancel=True), [A])
    h.core.step(1)
    assert md_frames(h, "link_state") == [(101, "lost")] and md(h, "lost_link_action") == ["hold"]
    h.core.step(5)
    assert fa(h)._kind == "orbit" and h.rt.vehicles[A].ma.pilot.tracker.current.task_id == "q2"
    beat(h)
    h.core.step(3)
    assert fa(h)._kind == "waypoint" and md(h, "lost_link_action") == ["hold", "resume"]


def test_tc_agt_113_flocking_cancel_during_hold_keeps_hold():
    f = lost_waypoint(RESUME, ma="flocking")
    ag = f.rt._batches["flocking"][0].agents[A]
    hold_goal = ag.goal
    send_c2(f.bus, "gcs-01", c2_pb2.TaskCommand(task_id="far", assignees=[A], cancel=True), [A])
    f.core.step(5)
    assert ag.tracker.current is None and ag.goal is hold_goal and ag.link.held
    beat(f)
    f.core.step(2)
    assert ag.goal is None and not ag.link.held


def test_tc_agt_108_other_mas():
    # hold: 상실 시 선회, 재개하면 원래 명령
    h = lost_waypoint(params={"lost_link_policy": "resume_on_recovery"}, ma="hold", task=False)
    assert fa(h)._kind == "orbit"
    beat(h)
    h.core.step(2)
    assert fa(h)._kind == "hsa" and fa(h)._cmd_id == f"{A}-hold"
    h2 = lost_waypoint(ma="hold", task=False)
    beat(h2)
    h2.core.step(2)
    assert fa(h2)._kind == "orbit"
    send_c2(h2.bus, "gcs-01", move("x", 0, 5000), [A])
    h2.core.step(3)
    assert fa(h2)._kind == "hsa"

    # flocking: 그 자리 Hold 벡터장, 재개하면 이전 목표
    f = lost_waypoint(RESUME, ma="flocking")
    ag = f.rt._batches["flocking"][0].agents[A]
    assert ag.goal.kind == "hold" and ag.link.held
    ref = pos_ne(f)
    f.run_s(30.0)
    assert far_from(f, ref) < 900.0
    beat(f)
    f.core.step(2)
    assert ag.goal.task_id == "far" and not ag.link.held


def formation_harness(params):
    h = Harness(make_scenario(3, "formation", {**FAST, **params}, course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", c2_pb2.FormationCommand(group_id="g1", members=[A, B, "uav-003"], leader=A,
                                                     shape=c2_pb2.FORMATION_SHAPE_WEDGE, spacing_m=120.0),
            [A, B, "uav-003"])
    beating(h, 3, A, B, "uav-003")
    h.core.step(60)
    return h


def test_tc_agt_109_formation_policy_param():
    h = formation_harness({"lost_link_policy": "resume_on_recovery"})
    for e in (A, B):
        assert fa(h, e)._kind == "orbit" and md(h, "lost_link_action", e) == ["hold"]
    ref = pos_ne(h, B)
    h.run_s(20.0)
    assert far_from(h, ref, B) < 900.0
    beat(h, A, B, "uav-003")
    h.core.step(3)
    assert fa(h, B)._kind == "hsa" and md(h, "lost_link_action", B)[-1] == "resume"

    u = formation_harness({})
    beat(u, A, B, "uav-003")
    u.core.step(3)
    assert fa(u, B)._kind == "orbit"       # 새 명령까지 유지
    send_c2(u.bus, "gcs-01", c2_pb2.FormationCommand(group_id="g1", members=[A, B, "uav-003"], leader=A,
                                                     shape=c2_pb2.FORMATION_SHAPE_LINE, spacing_m=150.0),
            [A, B, "uav-003"])
    u.core.step(3)
    assert fa(u, B)._kind == "hsa" and md(u, "lost_link_action", B)[-1] == "command"

    c = formation_harness({"lost_link_policy": "continue"})
    assert fa(c, B)._kind == "hsa" and md(c, "lost_link_action", B) == ["continue"]


def run_det(hb_first):
    h = Harness(make_scenario(2, "waypoint", FAST, course_deg=0.0))
    out = []
    h.bus.subscribe(keys.rx_all("gcs-01"), lambda s: out.append((s.key, link_pb2.LinkEnvelope.FromString(s.payload).payload)))
    h.core.step(2)
    t = move("t", 20000, 0, RESUME, A, B)
    for i in range(12):
        if i == 0 and not hb_first:
            send_c2(h.bus, "gcs-01", t, [A, B])
        if i < 3 or i > 7:
            beat(h, A, B)
        if i == 0 and hb_first:
            send_c2(h.bus, "gcs-01", t, [A, B])
        h.core.step(50)
    records = [list(h.rt.vehicles[e].ports.md.records) for e in (A, B)]
    return out, records, h.core.bodies[A].lat


def test_tc_agt_110_lockstep_deterministic_and_arrival_order():
    a, b, c = run_det(True), run_det(True), run_det(False)
    assert a == b == c
    assert any(r[1] == "link_state" for r in a[1][0])


def course_err_deg(h, deg, eid=A):
    return abs((math.degrees(h.core.bodies[eid].course) - deg + 180.0) % 360.0 - 180.0)


def test_tc_agt_114_resume_idle_never_commanded_returns_to_course():
    """D-32: 명령을 받은 적 없는 기체는 복구하면 상실 전 침로·속도·고도로 돌아간다"""
    h = lost_waypoint(RESUME, params={"lost_link_policy": "resume_on_recovery"}, task=False)
    alt = h.core.bodies[A].alt
    assert fa(h)._kind == "orbit"
    h.run_s(20.0)
    assert course_err_deg(h, 0.0) > 1.0
    beat(h)
    h.core.step(2)
    assert fa(h)._kind == "hsa" and md(h, "lost_link_action") == ["hold", "resume"]
    beating(h, 25)
    assert fa(h)._kind == "hsa" and course_err_deg(h, 0.0) < 1.0 and abs(h.core.bodies[A].alt - alt) < 5.0


def test_tc_agt_115_resume_idle_after_completed_task_returns_to_loiter():
    """끝난 작업의 도착점 둘레 선회로 돌아가고, 끝난 작업을 다시 보고하지 않는다"""
    h = Harness(make_scenario(1, "waypoint", {**FAST, "lost_link_policy": "resume_on_recovery"}, course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("near", 600, 0), [A])
    beating(h, 40)
    assert h.task_states("near")[-1] == DONE and fa(h)._kind == "loiter"
    h.core.step(60)
    assert fa(h)._kind == "orbit"
    h.run_s(15.0)
    beat(h)
    h.core.step(2)
    assert fa(h)._kind == "waypoint" and not fa(h)._cmd_id.startswith(f"{A}-lost-link")
    beating(h, 60)
    assert fa(h)._kind == "loiter" and far_from(h, (600.0, 0.0)) < 400.0
    assert h.task_states("near").count(DONE) == 1


def test_tc_agt_116_resume_after_task_cancelled_in_hold_does_not_fly_to_it():
    """선회 중 취소된 작업의 목표로 가지 않고 상실 순간의 침로로 돌아간다"""
    h = lost_waypoint(RESUME)
    send_c2(h.bus, "gcs-01", c2_pb2.TaskCommand(task_id="far", assignees=[A], cancel=True), [A])
    h.run_s(10.0)
    assert fa(h)._kind == "orbit" and h.task_states("far")[-1] == CAN
    beat(h)
    h.core.step(2)
    assert fa(h)._kind == "hsa" and h.rt.vehicles[A].ma.pilot.tracker.current is None


def test_tc_agt_117_idle_restore_repeats_and_until_command_keeps_orbit():
    h = lost_waypoint(params={"lost_link_policy": "resume_on_recovery"}, task=False)
    for n in (1, 2):
        beat(h)
        h.core.step(2)
        assert fa(h)._kind == "hsa" and abs(math.degrees(fa(h)._hdg)) < 1.0   # 두 번째도 처음 상실 전 침로
        beat(h)
        h.core.step(110)
        assert fa(h)._kind == "orbit" and fa(h)._cmd_id == f"{A}-lost-link-{n + 1}"
    u = lost_waypoint(task=False)          # hold_until_command는 복구해도 선회 유지
    beat(u)
    u.core.step(2)
    assert fa(u)._kind == "orbit" and md(u, "lost_link_action") == ["hold", "keep_hold"]


class MonitorOnly(MissionAutonomy):
    events: list = []

    def on_init(self, ctx):
        self.m = LinkMonitor(ctx)

    def on_step(self, ctx):
        e = self.m.update(ctx.ports.c2.inbox())
        if e:
            MonitorOnly.events.append((ctx.frame, e))


class CustomPilot(MissionAutonomy):
    called: list = []

    def on_init(self, ctx):
        outer = self

        class P(TaskPilot):
            def enter_lost_link_hold(self, nav):
                outer.called.append(ctx.frame)

        self.pilot = P(ctx)

    def on_step(self, ctx):
        self.pilot.step()


def test_tc_agt_111_user_plugin_can_use_or_replace():
    MonitorOnly.events, CustomPilot.called = [], []
    reg = PluginRegistry(extra_ma={"mon": MonitorOnly, "cp": CustomPilot})
    h = Harness(make_scenario(1, "mon", FAST), registry=reg)
    h.core.step(2)
    beat(h)
    h.core.step(1)
    h.core.step(55)
    beat(h)
    h.core.step(1)
    assert [e for _, e in MonitorOnly.events] == ["lost", "recovered"]
    assert fa(h)._kind != "orbit"           # 행동은 플러그인이 정한다
    h2 = Harness(make_scenario(1, "cp", FAST), registry=reg)
    h2.core.step(2)
    beat(h2)
    h2.core.step(60)
    assert len(CustomPilot.called) == 1 and fa(h2)._kind != "orbit"
