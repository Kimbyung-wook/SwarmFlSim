"""레이스트랙 기하·유도 (IMP-AGT-019, DEC-034).

모양: 반경 R인 두 원(중심 = 중점 ± (L/2)·축)과 그 접선 직선 두 개. 축은 진북 기준 시계 방향 α.
좌표는 중점 기준 (n, e) m. s = 축 방향 투영, q = 축의 오른쪽 방향 투영.
방향 lam: +1 시계(CW), −1 반시계(CCW). 모든 침로는 라디안, 진북 기준 시계 방향.

- s > L/2 이면 원 1, s < −L/2 이면 원 2, 그 사이는 가까운 직선(q ≥ 0이면 오른쪽 직선).
- dubins: 원 구간은 벡터장(Beard & McLain) 선회, 직선 구간은 횡방향 오차 기반 진입각
  χ = ψ_path − χ∞·(2/π)·atan(k_cross·e).
- vector_field: 사용자 MATLAB reference/racetrack_vectorfield.m. 원 구간은 수렴 + 접선 합성장
  h = −(r − R)·û_r + γ·r·û_t, 직선 구간은 χ = ψ_path − sign(e)·χ∞·(2/π)·atan(k·√|e|),
  χ∞ = atan2(10R, L).
- e = 경로 진행 방향 오른쪽으로 벗어난 거리(안쪽/바깥쪽 부호 포함). 안쪽이면 시계 방향에서 e > 0.
"""

import math

GUIDANCE = ("dubins", "vector_field")


def locate(n: float, e: float, alpha: float) -> tuple[float, float]:
    """(s, q): 축 방향·축 오른쪽 방향 투영"""
    return (n * math.cos(alpha) + e * math.sin(alpha),
            -n * math.sin(alpha) + e * math.cos(alpha))


def path_error(n: float, e: float, radius: float, leg: float, alpha: float) -> float:
    """경로(스타디움)까지의 거리"""
    s, q = locate(n, e, alpha)
    half = 0.5 * leg
    if abs(s) > half:
        return abs(math.hypot(abs(s) - half, q) - radius)
    return abs(radius - abs(q))


def _circle_center(s: float, leg: float) -> float:
    return 0.5 * leg if s > 0 else -0.5 * leg


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _line(q: float, radius: float, alpha: float, lam: float) -> tuple[float, float]:
    """직선 구간: (경로 침로 ψ, 진행 방향 오른쪽 오차 e)"""
    sgn = 1.0 if q >= 0.0 else -1.0
    t = -lam * sgn  # CW: 오른쪽 직선은 −축 방향, 왼쪽 직선은 +축 방향
    psi = alpha if t > 0 else alpha + math.pi
    return _wrap(psi), lam * (radius - sgn * q)


def _circle_dubins(dn: float, de: float, radius: float, lam: float, k_orbit: float) -> float:
    d = math.hypot(dn, de)
    gamma = math.atan2(de, dn)
    return gamma + lam * (math.pi / 2 + math.atan(k_orbit * (d - radius) / radius))


def _circle_field(dn: float, de: float, radius: float, lam: float, gamma_gain: float) -> float:
    d = max(math.hypot(dn, de), 1e-6)
    un, ue = dn / d, de / d
    tn, te = lam * -ue, lam * un  # lam = +1이면 시계 방향 접선
    hn = -(d - radius) * un + gamma_gain * d * tn
    he = -(d - radius) * ue + gamma_gain * d * te
    return math.atan2(he, hn)


def _split(n: float, e: float, leg: float, alpha: float) -> tuple[float, float, float, float | None]:
    """(s, q, 원 중심까지 (dn, de) 중 dn, de) — 직선 구간이면 마지막 값 None"""
    s, q = locate(n, e, alpha)
    half = 0.5 * leg
    if abs(s) <= half:
        return s, q, 0.0, None
    cs = _circle_center(s, leg)
    dn = n - cs * math.cos(alpha)
    de = e - cs * math.sin(alpha)
    return s, q, dn, de


def dubins_course(n: float, e: float, radius: float, leg: float, alpha: float, lam: float,
                  k_orbit: float = 2.0, k_cross: float = 0.02,
                  course_inf: float = math.radians(60.0)) -> float:
    s, q, dn, de = _split(n, e, leg, alpha)
    if de is not None:
        return _circle_dubins(dn, de, radius, lam, k_orbit)
    psi, err = _line(q, radius, alpha, lam)
    return psi - course_inf * (2.0 / math.pi) * math.atan(k_cross * err)


def vector_field_course(n: float, e: float, radius: float, leg: float, alpha: float, lam: float,
                        k: float = 0.3, gamma_gain: float = 0.2) -> float:
    s, q, dn, de = _split(n, e, leg, alpha)
    if de is not None:
        return _circle_field(dn, de, radius, lam, gamma_gain)
    psi, err = _line(q, radius, alpha, lam)
    chi_inf = math.atan2(10.0 * radius, leg)
    sign = (err > 0) - (err < 0)
    return psi - sign * chi_inf * (2.0 / math.pi) * math.atan(k * math.sqrt(abs(err)))
