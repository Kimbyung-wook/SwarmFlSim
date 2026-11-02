"""TC-AGT-026~027: 레이스트랙 기하·FA 유도 수렴 (IMP-AGT-019, DEC-034)"""

import math

import pytest

from swarm.v1 import c2_pb2, common_pb2, vi_pb2
from swarm_agent import racetrack as rt
from swarm_agent.geo import ned_offset, offset_geo
from swarm_agent.testing import Harness, make_scenario, send_c2

S = common_pb2
ORIGIN = (37.5, 128.0, 1500.0)
UAV = "uav-001"
R, L = 300.0, 1500.0


def test_tc_agt_026_path_error_geometry():
    a = math.radians(30.0)
    # 원 중심에서 R 떨어진 점, 직선 위의 점은 오차 0
    cn, ce = 0.5 * L * math.cos(a), 0.5 * L * math.sin(a)
    assert rt.path_error(cn + R * math.cos(a), ce + R * math.sin(a), R, L, a) == pytest.approx(0.0, abs=1e-6)
    rn, re = -math.sin(a) * R, math.cos(a) * R  # 오른쪽 직선 위 중점
    assert rt.path_error(rn, re, R, L, a) == pytest.approx(0.0, abs=1e-6)
    assert rt.path_error(0.0, 0.0, R, L, a) == pytest.approx(R)
    assert rt.path_error(rn * 2, re * 2, R, L, a) == pytest.approx(R)


@pytest.mark.parametrize("fn", [rt.dubins_course, rt.vector_field_course])
def test_tc_agt_026_course_on_path_is_tangent(fn):
    a = 0.0  # 축 = 북
    # CW: 오른쪽(동쪽) 직선은 남쪽, 왼쪽(서쪽) 직선은 북쪽, 북쪽 끝 원 위 동쪽 점은 남쪽
    assert math.cos(fn(0.0, R, R, L, a, 1.0)) == pytest.approx(-1.0, abs=1e-6)
    assert math.cos(fn(0.0, -R, R, L, a, 1.0)) == pytest.approx(1.0, abs=1e-6)
    assert math.cos(fn(0.5 * L, R, R, L, a, 1.0)) < -0.99
    # CCW는 반대
    assert math.cos(fn(0.0, R, R, L, a, -1.0)) == pytest.approx(1.0, abs=1e-6)
    # 안쪽 점은 바깥(가까운 직선) 쪽으로, 바깥 점은 안쪽으로
    assert math.sin(fn(0.0, 0.5 * R, R, L, a, 1.0)) > 0.0
    assert math.sin(fn(0.0, 2.0 * R, R, L, a, 1.0)) < 0.0


def expected_heading(n, e, alpha, lam):
    s, q = rt.locate(n, e, alpha)
    if abs(s) <= 0.5 * L:
        return rt._line(q, R, alpha, lam)[0]
    cs = 0.5 * L if s > 0 else -0.5 * L
    dn, de = n - cs * math.cos(alpha), e - cs * math.sin(alpha)
    return math.atan2(de, dn) + lam * math.pi / 2


CASES = [  # (start course deg, center n, center e, axis deg, direction)
    (0.0, 0.0, 0.0, 0.0, vi_pb2.TURN_DIRECTION_CW),      # 중심에서 출발
    (90.0, 3000.0, -1500.0, 40.0, vi_pb2.TURN_DIRECTION_CCW),  # 멀리서 접근
    (200.0, 600.0, 400.0, 135.0, vi_pb2.TURN_DIRECTION_CW),
    (310.0, -900.0, 100.0, 270.0, vi_pb2.TURN_DIRECTION_CCW),
]


@pytest.mark.parametrize("guidance", ["dubins", "vector_field"])
@pytest.mark.parametrize("course,cn,ce,axis,direction", CASES)
def test_tc_agt_027_converges_to_racetrack(guidance, course, cn, ce, axis, direction):
    sc = make_scenario(1, "waypoint", course_deg=course)
    sc.entities[1].autonomy.fa_params.update({"racetrack_guidance": guidance})
    h = Harness(sc)
    t = c2_pb2.TaskCommand(task_id="rt", assignees=[UAV])
    t.hold.center.lat_deg, t.hold.center.lon_deg = (float(x) for x in offset_geo(ORIGIN[0], ORIGIN[1], cn, ce))
    t.hold.center.alt_m = 1600.0
    t.hold.radius_m, t.hold.direction = R, direction
    t.hold.racetrack.leg_length_m, t.hold.racetrack.axis_heading_deg = L, axis
    send_c2(h.bus, "gcs-01", t, [UAV])
    h.run_s(400.0)
    lam = -1.0 if direction == vi_pb2.TURN_DIRECTION_CCW else 1.0
    alpha = math.radians(axis)
    clat, clon = (float(x) for x in offset_geo(ORIGIN[0], ORIGIN[1], cn, ce))
    worst_err, worst_hdg = 0.0, 0.0
    for _ in range(100):
        h.run_s(1.0)
        b = h.core.bodies[UAV]
        n, e = (float(x) for x in ned_offset(clat, clon, b.lat, b.lon))
        worst_err = max(worst_err, rt.path_error(n, e, R, L, alpha))
        worst_hdg = max(worst_hdg, abs(math.remainder(b.course - expected_heading(n, e, alpha, lam), 2 * math.pi)))
    b = h.core.bodies[UAV]
    assert worst_err < 40.0
    assert math.degrees(worst_hdg) < 30.0
    assert b.alt == pytest.approx(1600.0, abs=3.0)
    # 명령이 레이스트랙으로 수행되었다
    assert h.task_states("rt")[:2] == [S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING]
