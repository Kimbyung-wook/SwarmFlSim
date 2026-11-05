// IMP-PAY-001: 측지 좌표 기하와 DEM 가시선 (DEC-004, DEC-018, docs/10_contracts.md §2)
#pragma once

#include <cmath>
#include <functional>

#include "swarm/api/dynamics.hpp"

namespace swarm::payload {

struct Geo {
  double lat_deg = 0.0, lon_deg = 0.0, alt_m = 0.0;  // WGS84, MSL
};

struct Vec3 {
  double x = 0.0, y = 0.0, z = 0.0;
};

inline Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator*(double s, Vec3 a) { return {s * a.x, s * a.y, s * a.z}; }
inline Vec3 operator*(Vec3 a, double s) { return s * a; }
inline double dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline Vec3 cross(Vec3 a, Vec3 b) { return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x}; }
inline double norm(Vec3 a) { return std::sqrt(dot(a, a)); }
// 길이가 0이면 fallback
inline Vec3 unit(Vec3 a, Vec3 fallback = {1.0, 0.0, 0.0}) {
  const double n = norm(a);
  return n > 1e-12 ? (1.0 / n) * a : fallback;
}

// a → b 국지 NED 변위(m). 중간 위도의 곡률 반경을 쓴다. 수십 km 이내용
Vec3 ned_between(const Geo& a, const Geo& b);
// a에서 NED 변위 d만큼 옮긴 점
Geo offset(const Geo& a, Vec3 d_ned);
// 3차원 거리(m)
inline double distance_m(const Geo& a, const Geo& b) { return norm(ned_between(a, b)); }

// 자세 쿼터니언(NED→FRD, w x y z)으로 FRD 벡터를 NED로 옮긴다
Vec3 frd_to_ned(const double quat_wxyz[4], Vec3 v_frd);
// 방위(오른쪽 +)·고각(위 +) → FRD 단위 벡터
Vec3 az_el_to_frd(double az_deg, double el_deg);

// 가시선 판정. true면 a와 b 사이가 지면에 가리지 않는다
using LosFn = std::function<bool(const Geo& a, const Geo& b)>;

// 지면 모델로 가시선을 판정한다. step_m 간격으로 표본을 잡고, 지구 곡률에 따른 처짐을 반영한다.
// 양 끝 tolerance_m 이내의 차폐는 무시한다(지면 위 표적). terrain은 반환된 함수보다 오래 살아야 한다
LosFn make_terrain_los(const dyn::Terrain& terrain, double step_m = 50.0, double tolerance_m = 0.5);

}  // namespace swarm::payload
