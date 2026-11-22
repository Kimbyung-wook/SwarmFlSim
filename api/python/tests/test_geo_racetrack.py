"""TC-AGT-143: 플러그인 API에 공개한 geo·racetrack (IMP-AGT-053, DEC-104, O-48)

함수 이름과 동작은 swarm_agent에 있던 때와 같다. 내장 MA(algorithms)와 Agent 런타임은 swarm_api에서 가져온다.
"""

import ast
import math
import pathlib

import numpy as np

from swarm_api import geo, racetrack

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_geo_scalar_and_array_agree():
    lat0, lon0 = 37.0, 127.0
    lat, lon = geo.offset_geo(lat0, lon0, np.array([1000.0, -250.0]), np.array([500.0, 3000.0]))
    n, e = geo.ned_offset(lat0, lon0, lat, lon)
    assert np.allclose(n, [1000.0, -250.0], atol=1e-6) and np.allclose(e, [500.0, 3000.0], atol=1e-6)
    for i in range(2):
        assert geo.ned_offset_s(lat0, lon0, float(lat[i]), float(lon[i])) == (float(n[i]), float(e[i]))
    for a in (-7.0, -math.pi, 0.3, math.pi, 9.5):
        assert geo.wrap_pi_s(a) == float(geo.wrap_pi(a))
        assert -math.pi <= geo.wrap_pi_s(a) < math.pi
    assert float(geo.course_rad(0.0, 1.0)) == math.pi / 2
    assert geo.G_MPS2 == 9.80665 and geo.EARTH_RADIUS_M == 6378137.0


def test_racetrack_geometry_and_guidance():
    r, leg, alpha = 500.0, 2000.0, math.radians(30.0)
    assert racetrack.GUIDANCE == ("dubins", "vector_field")
    s, q = racetrack.locate(math.cos(alpha) * 100.0, math.sin(alpha) * 100.0, alpha)
    assert math.isclose(s, 100.0) and abs(q) < 1e-9
    # 직선 위(q = R)와 원 위(s = L/2 + R)에서는 경로 오차가 0이다
    n, e = -r * math.sin(alpha), r * math.cos(alpha)
    assert racetrack.path_error(n, e, r, leg, alpha) < 1e-9
    n, e = (leg / 2 + r) * math.cos(alpha), (leg / 2 + r) * math.sin(alpha)
    assert racetrack.path_error(n, e, r, leg, alpha) < 1e-9
    # 오른쪽 직선 위, 시계 방향(lam=+1)이면 경로 방향(축 반대, α+π)을 따른다
    rn, re = -r * math.sin(alpha), r * math.cos(alpha)
    for f in (racetrack.dubins_course, racetrack.vector_field_course):
        c = f(rn, re, r, leg, alpha, 1.0)
        assert abs(geo.wrap_pi_s(c - (alpha + math.pi))) < 1e-6


def test_agent_alias_is_same_module_and_builtin_code_does_not_use_it():
    import swarm_agent.geo
    import swarm_agent.racetrack
    assert swarm_agent.geo is geo and swarm_agent.racetrack is racetrack
    bad = []
    for d in ("algorithms/src", "agent/src"):
        for p in (ROOT / d).rglob("*.py"):
            if p.name in ("geo.py", "racetrack.py") and p.parent.name == "swarm_agent":
                continue
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    names = {a.name for a in node.names}
                    if mod in ("swarm_agent.geo", "swarm_agent.racetrack") or \
                            (mod == "swarm_agent" and names & {"geo", "racetrack"}) or \
                            (node.level and mod in ("geo", "racetrack")) or \
                            (node.level and not mod and names & {"geo", "racetrack"}):
                        bad.append(str(p.relative_to(ROOT)))
                elif isinstance(node, ast.Import):
                    if any(a.name in ("swarm_agent.geo", "swarm_agent.racetrack") for a in node.names):
                        bad.append(str(p.relative_to(ROOT)))
    assert bad == []
