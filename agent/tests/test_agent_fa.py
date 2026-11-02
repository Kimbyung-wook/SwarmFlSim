"""TC-AGT-001~005: 기본 FA (IMP-AGT-007)"""

import math

import pytest

from swarm.v1 import common_pb2, vi_pb2
from swarm_agent.fa import DefaultFlightAutonomy
from swarm_agent.geo import G_MPS2, ned_offset, offset_geo, wrap_pi

S = common_pb2
LAT0, LON0 = 37.5, 128.0


class Body:
    """2-DoF 운동학. FA 출력의 heading_rate를 쓴다(use_bank=True면 bank로 3-DoF 협조선회)"""

    def __init__(self, course_deg=0.0, speed=22.0, alt=1500.0, use_bank=False):
        self.lat, self.lon, self.alt = LAT0, LON0, alt
        self.course, self.speed, self.use_bank = math.radians(course_deg), speed, use_bank
        self.frame = 0

    def nav(self):
        n = vi_pb2.NavigationReport()
        n.header.frame = self.frame
        k = n.kinematics
        k.position.lat_deg, k.position.lon_deg, k.position.alt_m = self.lat, self.lon, self.alt
        k.velocity_ned_mps.x = self.speed * math.cos(self.course)
        k.velocity_ned_mps.y = self.speed * math.sin(self.course)
        return n

    def apply(self, out, dt):
        k = out.kinematic
        self.speed += max(-3 * dt, min(3 * dt, k.speed_mps - self.speed))
        rate = G_MPS2 * math.tan(k.bank_rad) / self.speed if self.use_bank else k.heading_rate_rps
        self.course += rate * dt
        n, e = self.speed * math.cos(self.course) * dt, self.speed * math.sin(self.course) * dt
        self.lat, self.lon = (float(x) for x in offset_geo(self.lat, self.lon, n, e))
        self.alt += k.climb_rate_mps * dt
        self.frame += 1


def make_fa(**params):
    fa = DefaultFlightAutonomy()
    cap = fa.on_init("uav-001", params)
    return fa, cap


def fly(fa, body, seconds, dt=0.02, on_status=None):
    statuses = []
    for _ in range(round(seconds / dt)):
        body.apply(fa.step(body.nav(), dt), dt)
        statuses.extend(fa.pending_status())
    return statuses


def test_tc_agt_001_hsa_converges():
    fa, cap = make_fa()
    assert cap.supports_hsa and cap.supports_waypoint and cap.supports_curve
    body = Body(course_deg=0.0, speed=20.0, alt=1500.0)
    cmd = vi_pb2.FlightCommand(command_id="c1")
    cmd.hsa.heading_deg, cmd.hsa.speed_mps, cmd.hsa.altitude_m = 135.0, 28.0, 1700.0
    st = fa.on_command(cmd)
    assert st.state == S.COMMAND_STATE_ACCEPTED
    statuses = fly(fa, body, 90.0)
    assert [s.state for s in statuses] == [S.COMMAND_STATE_EXECUTING]
    assert abs(math.degrees(float(wrap_pi(body.course - math.radians(135.0))))) < 0.5
    assert body.speed == pytest.approx(28.0, abs=0.1)
    assert body.alt == pytest.approx(1700.0, abs=1.0)


def test_tc_agt_001_hold_before_command_and_partial_hsa():
    fa, _ = make_fa()
    body = Body(course_deg=60.0, speed=24.0, alt=1200.0)
    fly(fa, body, 20.0)
    assert math.degrees(body.course) == pytest.approx(60.0, abs=0.5)
    assert body.alt == pytest.approx(1200.0, abs=0.5)
    cmd = vi_pb2.FlightCommand(command_id="c1")
    cmd.hsa.altitude_m = 1300.0  # 침로·속도는 그대로
    fa.on_command(cmd)
    fly(fa, body, 60.0)
    assert math.degrees(body.course) == pytest.approx(60.0, abs=0.5)
    assert body.speed == pytest.approx(24.0, abs=0.1)
    assert body.alt == pytest.approx(1300.0, abs=1.0)


def test_tc_agt_002_waypoints_complete_then_loiter():
    fa, _ = make_fa()
    body = Body(course_deg=0.0, speed=22.0)
    cmd = vi_pb2.FlightCommand(command_id="w1")
    pts = [(2000.0, 0.0), (2000.0, 2000.0), (0.0, 2000.0)]
    for n, e in pts:
        wp = cmd.waypoint.waypoints.add(acceptance_radius_m=60.0, speed_mps=25.0)
        wp.position.lat_deg, wp.position.lon_deg = (float(x) for x in offset_geo(LAT0, LON0, n, e))
        wp.position.alt_m = 1600.0
    assert fa.on_command(cmd).state == S.COMMAND_STATE_ACCEPTED
    closest = [math.inf] * 3
    statuses = []
    for _ in range(round(400 / 0.02)):
        body.apply(fa.step(body.nav(), 0.02), 0.02)
        statuses.extend(fa.pending_status())
        for i, (n, e) in enumerate(pts):
            dn, de = ned_offset(LAT0, LON0, body.lat, body.lon)
            closest[i] = min(closest[i], math.hypot(float(dn) - n, float(de) - e))
    assert [s.state for s in statuses] == [S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED]
    r_turn = 25.0 ** 2 / (G_MPS2 * math.tan(math.radians(35.0)))
    assert all(c < max(60.0, r_turn) for c in closest)
    # 마지막 점 둘레 선회: 반경 2·R_min 근처
    dn, de = ned_offset(LAT0, LON0, body.lat, body.lon)
    d = math.hypot(float(dn) - pts[-1][0], float(de) - pts[-1][1])
    assert d == pytest.approx(2.0 * r_turn, rel=0.1)
    assert body.alt == pytest.approx(1600.0, abs=1.0)


@pytest.mark.parametrize("direction,sign", [(vi_pb2.TURN_DIRECTION_CW, 1.0), (vi_pb2.TURN_DIRECTION_CCW, -1.0)])
def test_tc_agt_003_orbit_converges(direction, sign):
    fa, _ = make_fa()
    body = Body(course_deg=0.0, speed=22.0)
    cmd = vi_pb2.FlightCommand(command_id="o1")
    o = cmd.curve.orbit
    o.center.lat_deg, o.center.lon_deg = (float(x) for x in offset_geo(LAT0, LON0, 1500.0, 800.0))
    o.radius_m, o.direction = 400.0, direction
    fa.on_command(cmd)
    fly(fa, body, 200.0)
    radii, turn = [], 0.0
    for _ in range(round(60 / 0.02)):
        c0 = body.course
        body.apply(fa.step(body.nav(), 0.02), 0.02)
        turn += body.course - c0
        dn, de = ned_offset(o.center.lat_deg, o.center.lon_deg, body.lat, body.lon)
        radii.append(math.hypot(float(dn), float(de)))
    assert max(abs(r - 400.0) for r in radii) < 0.05 * 400.0
    assert math.copysign(1.0, turn) == sign


def test_tc_agt_004_reject_supersede_and_update():
    fa, _ = make_fa()
    assert fa.on_command(vi_pb2.FlightCommand(command_id="x")).state == S.COMMAND_STATE_REJECTED
    empty_wp = vi_pb2.FlightCommand(command_id="x")
    empty_wp.waypoint.loop = True
    assert fa.on_command(empty_wp).state == S.COMMAND_STATE_REJECTED
    bad_orbit = vi_pb2.FlightCommand(command_id="x")
    bad_orbit.curve.orbit.radius_m = 0.0
    assert fa.on_command(bad_orbit).state == S.COMMAND_STATE_REJECTED

    body = Body()
    a = vi_pb2.FlightCommand(command_id="a")
    a.hsa.heading_deg = 10.0
    fa.on_command(a)
    fly(fa, body, 1.0)
    # 같은 command_id 갱신: 상태를 다시 내지 않는다
    a.hsa.heading_deg = 20.0
    fa.on_command(a)
    assert fly(fa, body, 1.0) == []
    b = vi_pb2.FlightCommand(command_id="b")
    b.hsa.heading_deg = 90.0
    fa.on_command(b)
    st = fly(fa, body, 1.0)
    assert [(s.command_id, s.state) for s in st] == [("a", S.COMMAND_STATE_CANCELLED), ("b", S.COMMAND_STATE_EXECUTING)]


def test_tc_agt_005_bank_consistent_and_limited():
    fa, _ = make_fa(max_bank_deg=30.0, min_speed_mps=15.0, max_speed_mps=30.0)
    body = Body(course_deg=0.0, speed=22.0)
    cmd = vi_pb2.FlightCommand(command_id="c")
    cmd.hsa.heading_deg, cmd.hsa.speed_mps = 180.0, 50.0
    fa.on_command(cmd)
    out = fa.step(body.nav(), 0.02)
    k = out.kinematic
    assert k.speed_mps == 30.0  # 최대 속도로 제한
    assert abs(k.bank_rad) == pytest.approx(math.radians(30.0), abs=1e-9)
    assert k.bank_rad == pytest.approx(math.atan(22.0 * k.heading_rate_rps / G_MPS2))
    # 3-DoF(bank) 해석으로도 같은 침로에 수렴
    body3 = Body(course_deg=0.0, speed=22.0, use_bank=True)
    fa3, _ = make_fa()
    fa3.on_command(cmd)
    fly(fa3, body3, 60.0)
    assert abs(math.degrees(float(wrap_pi(body3.course - math.pi)))) < 0.5
