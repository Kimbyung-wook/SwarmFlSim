"""평면 근사 좌표 변환 (IMP-AGT-001, 플러그인 API 공개 IMP-AGT-053·DEC-104). 수십 km 안의 상대 위치 계산용.

버스·truth·Core에 접근하지 않는 순수 계산이다. 내장 MA·사용자 플러그인·Agent 런타임이 함께 쓴다.

모든 함수는 스칼라와 NumPy 배열을 함께 받는다.
"""

import math

import numpy as np

EARTH_RADIUS_M = 6378137.0
G_MPS2 = 9.80665


def ned_offset(lat0_deg, lon0_deg, lat_deg, lon_deg):
    """(lat0, lon0) 기준 (lat, lon)의 북·동 오프셋(m)"""
    n = np.radians(np.asarray(lat_deg) - lat0_deg) * EARTH_RADIUS_M
    e = np.radians(np.asarray(lon_deg) - lon0_deg) * EARTH_RADIUS_M * np.cos(np.radians(lat0_deg))
    return n, e


def offset_geo(lat0_deg, lon0_deg, north_m, east_m):
    """(lat0, lon0)에서 북·동으로 옮긴 위경도(deg)"""
    lat = lat0_deg + np.degrees(np.asarray(north_m) / EARTH_RADIUS_M)
    lon = lon0_deg + np.degrees(np.asarray(east_m) / (EARTH_RADIUS_M * np.cos(np.radians(lat0_deg))))
    return lat, lon


def wrap_pi(a):
    return (np.asarray(a) + np.pi) % (2.0 * np.pi) - np.pi


def course_rad(vn, ve):
    """대지 침로(북 기준 시계 방향, rad)"""
    return np.arctan2(ve, vn)


# 스칼라 전용 (IMP-AGT-044, DEC-086). 기본 FA가 기체마다 매 프레임 부르는 곳에 쓴다. NumPy 스칼라 연산은 호출마다
# µs 단위 오버헤드가 있다. 연산 순서가 위 함수와 같아 결과가 비트 단위로 같다(TC-AGT-129)
_TWO_PI = 2.0 * math.pi


def ned_offset_s(lat0_deg: float, lon0_deg: float, lat_deg: float, lon_deg: float) -> tuple[float, float]:
    return (math.radians(lat_deg - lat0_deg) * EARTH_RADIUS_M,
            math.radians(lon_deg - lon0_deg) * EARTH_RADIUS_M * math.cos(math.radians(lat0_deg)))


def wrap_pi_s(a: float) -> float:
    return (a + math.pi) % _TWO_PI - math.pi
