"""TC-AGT-020~025, 028: 지도 임무 명령 Hold 매개변수·Route·정찰·SearchArea 원·레이스트랙 (IMP-AGT-016~018, 020, DEC-033, DEC-034)"""

import math

import pytest

from swarm.v1 import c2_pb2, common_pb2, mp_pb2, vi_pb2
from swarm_agent.geo import ned_offset, offset_geo
from swarm_agent.testing import Harness, make_scenario, send_c2

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)
UAV = "uav-001"


def geo(n, e):
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    return float(lat), float(lon)


def set_pos(p, n, e, alt=0.0):
    p.lat_deg, p.lon_deg = geo(n, e)
    p.alt_m = alt


def rel(body, n, e):
    """(n, e) 점에서 본 기체 상대 위치 (북, 동)"""
    lat, lon = geo(n, e)
    dn, de = ned_offset(lat, lon, body.lat, body.lon)
    return float(dn), float(de)


def statuses(h, task_id):
    return [m for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id]


def track(h, seconds, fn, dt=0.5):
    """dt마다 fn(시각 s, 기체)를 부른다"""
    out = []
    for _ in range(round(seconds / dt)):
        h.run_s(dt)
        out.append(fn(h.core.frame * h.core.dt_us * 1e-6, h.core.bodies[UAV]))
    return out


def task(task_id="t1", assignee=UAV):
    return c2_pb2.TaskCommand(task_id=task_id, assignees=[assignee])


def route(pts, loop=False, task_id="t1"):
    """pts: (n, e, alt, speed, action) 목록. action은 None | ("loiter", s, r) | ("recon", r, s|None)"""
    t = task(task_id)
    t.route.loop = loop
    for n, e, alt, speed, action in pts:
        w = t.route.waypoints.add()
        set_pos(w.position, n, e, alt)
        if speed is not None:
            w.speed_mps = speed
        if action and action[0] == "loiter":
            w.loiter.duration_s = action[1]
            w.loiter.radius_m = action[2]
        elif action and action[0] == "recon":
            w.recon.radius_m = action[1]
            if action[2] is not None:
                w.recon.duration_s = action[2]
    return t


def cross_sign(dn, de, body):
    """중심 → 기체 × 속도의 부호. CW(위에서 본 시계 방향)면 +"""
    vn, ve = body.speed * math.cos(body.course), body.speed * math.sin(body.course)
    return dn * ve - de * vn


# ---- Hold 매개변수 (IMP-AGT-016) ----

def test_tc_agt_020_hold_center_radius_ccw_alt_duration():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    t = task()
    set_pos(t.hold.center, 2000, 0, 1700.0)
    t.hold.radius_m, t.hold.duration_s, t.hold.direction = 500.0, 90.0, vi_pb2.TURN_DIRECTION_CCW
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(150.0)
    assert [s.state for s in statuses(h, "t1")][:2] == [S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING]
    def f(_, b):
        dn, de = rel(b, 2000, 0)
        return math.hypot(dn, de), cross_sign(dn, de, b)
    for d, cross in track(h, 40.0, f):
        assert d == pytest.approx(500.0, rel=0.08)
        assert cross < 0  # CCW
    assert h.core.bodies[UAV].alt == pytest.approx(1700.0, abs=5.0)
    h.run_s(120.0)
    assert [s.state for s in statuses(h, "t1")] == [
        S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED]


def test_tc_agt_020_hold_defaults_orbit_until_next_command():
    h = Harness(make_scenario(1, "waypoint", {"hold_radius_m": 350.0}, course_deg=0.0))
    start = (h.core.bodies[UAV].lat, h.core.bodies[UAV].lon)
    t = task()
    t.hold.duration_s = 0.0  # 0: 다음 명령까지
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(90.0)

    def f(_, b):
        dn, de = (float(x) for x in ned_offset(start[0], start[1], b.lat, b.lon))
        return math.hypot(dn, de), cross_sign(dn, de, b)
    for d, cross in track(h, 200.0, f, dt=2.0):
        assert d == pytest.approx(350.0, rel=0.08)
        assert cross > 0  # 방향 없음: CW
    assert h.core.bodies[UAV].alt == pytest.approx(1500.0, abs=2.0)
    assert statuses(h, "t1")[-1].state == S.COMMAND_STATE_EXECUTING


def test_tc_agt_020_hold_bad_radius_rejected():
    h = Harness(make_scenario(1, "waypoint"))
    t = task()
    t.hold.radius_m = 0.0
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(1.0)
    assert [s.state for s in statuses(h, "t1")] == [S.COMMAND_STATE_REJECTED]


# ---- Route (IMP-AGT-017) ----

def test_tc_agt_021_route_order_altitude_speed_progress():
    pts = [(2500, 0, 1700.0, 30.0, None), (2500, 2500, 1400.0, 18.0, None), (0, 2500, 1600.0, 25.0, None)]
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", route(pts), [UAV])
    closest = [math.inf] * 3
    seen_leg_speed = {1: [], 2: []}

    def f(_, b):
        for i, (n, e, *_r) in enumerate(pts):
            closest[i] = min(closest[i], math.hypot(*rel(b, n, e)))
        p = [s.progress for s in statuses(h, "t1") if s.state == S.COMMAND_STATE_EXECUTING]
        # 다음 항로점으로 가는 도중 항로점에서 1 km 이상 떨어져 있으면 그 구간의 속도·고도를 본다
        k = round(p[-1] * 3) if p else 0
        if k in seen_leg_speed and math.hypot(*rel(b, *pts[k][:2])) > 1000.0:
            seen_leg_speed[k].append((b.speed, b.alt))
        return [s.state for s in statuses(h, "t1")]
    track(h, 500.0, f, dt=1.0)
    st = statuses(h, "t1")
    assert [s.state for s in st] == [S.COMMAND_STATE_ACCEPTED] + [S.COMMAND_STATE_EXECUTING] * 3 + [
        S.COMMAND_STATE_COMPLETED]
    assert [s.progress for s in st[1:4]] == pytest.approx([0.0, 1 / 3, 2 / 3])
    assert all(d < 120.0 for d in closest)
    for k, (v, alt) in ((1, (18.0, 1400.0)), (2, (25.0, 1600.0))):
        tail = seen_leg_speed[k][-10:]
        assert tail and all(s == pytest.approx(v, abs=0.5) for s, _ in tail)
        assert tail[-1][1] == pytest.approx(alt, abs=30.0)


def test_tc_agt_022_route_loiter_time():
    pts = [(2000, 0, 0.0, 22.0, ("loiter", 80.0, 400.0)), (2000, 3000, 0.0, 22.0, None)]
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", route(pts), [UAV])
    log = track(h, 400.0, lambda t, b: (t, math.hypot(*rel(b, 2000, 0)),
                                        [(s.state, s.progress) for s in statuses(h, "t1")]))
    t_half = next(t for t, _, st in log if (S.COMMAND_STATE_EXECUTING, 0.5) in st)
    t_wp = next(t for t, d, _ in log if d < 120.0)  # 항로점 도달 뒤 선회 원에 든다
    t_on = next(t for t, d, _ in log if t > t_wp and abs(d - 400.0) < 100.0)
    assert t_half - t_on >= 80.0
    assert t_half - t_on < 80.0 + 60.0  # 원 위에 든 뒤 오래 끌지 않는다
    ring = [d for t, d, _ in log if t_on + 30.0 < t < t_on + 80.0]
    assert ring and all(d == pytest.approx(400.0, rel=0.1) for d in ring)
    assert log[-1][2][-1][0] == S.COMMAND_STATE_COMPLETED


def test_tc_agt_023_route_recon_one_revolution():
    pts = [(2000, 0, 1500.0, 22.0, ("recon", 600.0, None))]
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", route(pts), [UAV])
    angle, last = 0.0, None
    done_at = None
    for t, dn, de, st in track(h, 600.0, lambda t, b: (t, *rel(b, 2000, 0), statuses(h, "t1")[-1].state)):
        d = math.hypot(dn, de)
        if done_at is None and abs(d - 600.0) < 150.0:
            b = math.atan2(de, dn)
            if last is not None:
                angle += abs(math.remainder(b - last, 2 * math.pi))
            last = b
            assert d == pytest.approx(600.0, rel=0.25)
        if done_at is None and st == S.COMMAND_STATE_COMPLETED:
            done_at = t
    assert done_at is not None
    assert angle >= 2 * math.pi * 0.95


def test_tc_agt_023_search_area_circle_in_waypoint():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    t = task()
    c = t.search_area.area.circle
    set_pos(c.center, 0, 2500)
    c.radius_m = 700.0
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(150.0)
    ds = track(h, 60.0, lambda _, b: math.hypot(*rel(b, 0, 2500)))
    assert all(d == pytest.approx(700.0, rel=0.1) for d in ds)
    h.run_s(400.0)
    assert [s.state for s in statuses(h, "t1")] == [
        S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED]


def test_tc_agt_024_route_replaced_by_same_task_id():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", route([(8000, 0, 0.0, None, None)]), [UAV])
    h.run_s(20.0)
    send_c2(h.bus, "gcs-01", route([(0, 2500, 0.0, 25.0, None)]), [UAV])
    h.run_s(250.0)
    assert [s.state for s in statuses(h, "t1")] == [
        S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING,
        S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED]
    assert math.hypot(*rel(h.core.bodies[UAV], 0, 2500)) < 400.0


def test_tc_agt_024_route_loop_and_empty_rejected():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", route([(1500, 0, 0.0, 25.0, None), (1500, 1500, 0.0, 25.0, None)], loop=True), [UAV])
    send_c2(h.bus, "gcs-01", c2_pb2.TaskCommand(task_id="t2", assignees=[UAV], route=c2_pb2.RouteTask()), [UAV])
    h.run_s(500.0)
    st = statuses(h, "t1")
    assert all(s.state != S.COMMAND_STATE_COMPLETED for s in st)
    prog = [s.progress for s in st if s.state == S.COMMAND_STATE_EXECUTING]
    assert prog.count(1.0) >= 2  # 두 바퀴 이상
    assert prog[:4] == pytest.approx([0.0, 0.5, 1.0, 0.5])
    assert [s.state for s in statuses(h, "t2")] == [S.COMMAND_STATE_REJECTED]


# ---- 편대 리더·flocking (IMP-AGT-016~018) ----

def test_tc_agt_025_formation_leader_route_followers_keep_slot():
    plan = mp_pb2.MissionPlan(plan_id="p")
    plan.formations.add(group_id="g", members=["uav-001", "uav-002", "uav-003"], leader="uav-001",
                        shape=c2_pb2.FORMATION_SHAPE_LINE, spacing_m=200.0)
    h = Harness(make_scenario(3, "formation", course_deg=0.0, mission_plan=plan))
    send_c2(h.bus, "gcs-01", route([(3000, 0, 1600.0, 24.0, None), (3000, 3000, 1600.0, 24.0, None)]), [UAV])
    h.run_s(500.0)
    assert [s.state for s in statuses(h, "t1")][-1] == S.COMMAND_STATE_COMPLETED
    assert [s.progress for s in statuses(h, "t1") if s.state == S.COMMAND_STATE_EXECUTING] == [0.0, 0.5]
    for other in ("uav-002", "uav-003"):
        dn, de, _ = h.core.offset_m(UAV, other)
        assert math.hypot(dn, de) < 800.0


def test_tc_agt_025_flocking_route_rejected_hold_orbit():
    h = Harness(make_scenario(3, "flocking", {"cruise_mps": 22.0}, spacing_m=150.0, course_deg=0.0))
    send_c2(h.bus, "gcs-01", route([(2000, 0, 0.0, None, None)]), [UAV])
    t = c2_pb2.TaskCommand(task_id="h1")  # 수신 기체 모두
    set_pos(t.hold.center, 1500, 1500)
    t.hold.radius_m, t.hold.duration_s = 600.0, 60.0
    for uav in ("uav-001", "uav-002", "uav-003"):
        send_c2(h.bus, "gcs-01", t, [uav])
    h.run_s(1.0)
    assert [s.state for s in statuses(h, "t1")] == [S.COMMAND_STATE_REJECTED]
    h.run_s(200.0)
    ds = track(h, 30.0, lambda _, b: math.hypot(*rel(b, 1500, 1500)))
    assert all(d == pytest.approx(600.0, rel=0.25) for d in ds)
    assert statuses(h, "h1")[-1].state == S.COMMAND_STATE_COMPLETED


# ---- 레이스트랙 (IMP-AGT-020, DEC-034) ----

def fa_of(h, uav=UAV):
    return h.rt.vehicles[uav].fa


def test_tc_agt_028_hold_racetrack_goes_to_fa_and_completes():
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    t = task()
    set_pos(t.hold.center, 2000, 0, 1600.0)
    t.hold.radius_m, t.hold.duration_s = 300.0, 100.0
    t.hold.racetrack.leg_length_m, t.hold.racetrack.axis_heading_deg = 1200.0, 90.0
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(30.0)
    race = fa_of(h)._race
    assert race is not None and race[2:5] == pytest.approx((300.0, 1200.0, math.pi / 2))
    h.run_s(300.0)
    assert [s.state for s in statuses(h, "t1")] == [
        S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED]


def test_tc_agt_028_loiter_racetrack_in_route():
    pts = [(2000, 0, 1500.0, 22.0, ("loiter", 60.0, 300.0)), (2000, 3000, 1500.0, 22.0, None)]
    t = route(pts)
    w = t.route.waypoints[0]
    w.loiter.racetrack.leg_length_m, w.loiter.racetrack.axis_heading_deg = 1000.0, 0.0
    h = Harness(make_scenario(1, "waypoint", course_deg=0.0))
    send_c2(h.bus, "gcs-01", t, [UAV])
    seen = False
    for _ in range(300):
        h.run_s(1.0)
        seen = seen or fa_of(h)._race is not None
    assert seen
    assert fa_of(h)._race is None or statuses(h, "t1")[-1].state == S.COMMAND_STATE_COMPLETED
    assert statuses(h, "t1")[-1].state == S.COMMAND_STATE_COMPLETED


def test_tc_agt_028_negative_leg_rejected_flocking_racetrack_hold():
    h = Harness(make_scenario(2, "flocking", spacing_m=150.0, course_deg=0.0))
    bad = task("bad", "")
    bad.ClearField("assignees")
    bad.hold.racetrack.leg_length_m = -1.0
    send_c2(h.bus, "gcs-01", bad, [UAV])
    h.run_s(1.0)
    assert [s.state for s in statuses(h, "bad")] == [S.COMMAND_STATE_REJECTED]
    t = c2_pb2.TaskCommand(task_id="rk")
    set_pos(t.hold.center, 1500, 1500)
    t.hold.radius_m, t.hold.duration_s = 400.0, 40.0
    t.hold.racetrack.leg_length_m, t.hold.racetrack.axis_heading_deg = 1200.0, 45.0
    for uav in ("uav-001", "uav-002"):
        send_c2(h.bus, "gcs-01", t, [uav])
    h.run_s(300.0)
    assert statuses(h, "rk")[-1].state == S.COMMAND_STATE_COMPLETED
    dn, de = rel(h.core.bodies[UAV], 1500, 1500)
    assert math.hypot(dn, de) < 400.0 + 600.0 + 300.0  # 레이스트랙 둘레 안
