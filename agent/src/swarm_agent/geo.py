"""평면 근사 좌표 변환 (IMP-AGT-001). 수십 km 안의 상대 위치 계산용.

모든 함수는 스칼라와 NumPy 배열을 함께 받는다.
"""

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
