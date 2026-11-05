// IMP-PAY-001: 측지 좌표 기하와 DEM 가시선 (DEC-004, DEC-018)
#include "swarm/payload/geometry.hpp"

#include <algorithm>
#include <cmath>

#include "swarm/dyn/geo.hpp"

namespace swarm::payload {

namespace geo = swarm::dyn::geo;

namespace {
double wrap_lon_deg(double d) {
  while (d > 180.0) d -= 360.0;
  while (d < -180.0) d += 360.0;
  return d;
}
}  // namespace

Vec3 ned_between(const Geo& a, const Geo& b) {
  const double lat_mid = 0.5 * (a.lat_deg + b.lat_deg) * geo::kDegToRad;
  const double h_mid = 0.5 * (a.alt_m + b.alt_m);
  const double m = geo::meridian_radius(lat_mid) + h_mid;
  const double n = (geo::prime_vertical_radius(lat_mid) + h_mid) * std::cos(lat_mid);
  return {(b.lat_deg - a.lat_deg) * geo::kDegToRad * m, wrap_lon_deg(b.lon_deg - a.lon_deg) * geo::kDegToRad * n,
          -(b.alt_m - a.alt_m)};
}

Geo offset(const Geo& a, Vec3 d) {
  // 중간점 곡률로 한 번 고쳐 ned_between과 맞춘다
  const double lat0 = a.lat_deg * geo::kDegToRad;
  const double h_mid = a.alt_m - 0.5 * d.z;
  double m = geo::meridian_radius(lat0) + h_mid;
  const double dlat1 = d.x / m;
  const double lat_mid = lat0 + 0.5 * dlat1;
  m = geo::meridian_radius(lat_mid) + h_mid;
  const double n = (geo::prime_vertical_radius(lat_mid) + h_mid) * std::max(std::cos(lat_mid), 1e-9);
  Geo out;
  out.lat_deg = a.lat_deg + d.x / m * geo::kRadToDeg;
  out.lon_deg = wrap_lon_deg(a.lon_deg + d.y / n * geo::kRadToDeg);
  out.alt_m = a.alt_m - d.z;
  return out;
}

Vec3 frd_to_ned(const double q[4], Vec3 v) {
  double yaw = 0.0, pitch = 0.0, roll = 0.0;
  const double n2 = q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3];
  if (n2 > 1e-12) {
    const double s = 1.0 / std::sqrt(n2);
    const double qn[4] = {q[0] * s, q[1] * s, q[2] * s, q[3] * s};
    geo::quat_to_euler(qn, yaw, pitch, roll);
  }
  const double cy = std::cos(yaw), sy = std::sin(yaw);
  const double cp = std::cos(pitch), sp = std::sin(pitch);
  const double cr = std::cos(roll), sr = std::sin(roll);
  // C_b^n (FRD → NED), ZYX
  return {cp * cy * v.x + (sr * sp * cy - cr * sy) * v.y + (cr * sp * cy + sr * sy) * v.z,
          cp * sy * v.x + (sr * sp * sy + cr * cy) * v.y + (cr * sp * sy - sr * cy) * v.z,
          -sp * v.x + sr * cp * v.y + cr * cp * v.z};
}

Vec3 az_el_to_frd(double az_deg, double el_deg) {
  const double az = az_deg * geo::kDegToRad, el = el_deg * geo::kDegToRad;
  return {std::cos(el) * std::cos(az), std::cos(el) * std::sin(az), -std::sin(el)};
}

LosFn make_terrain_los(const dyn::Terrain& terrain, double step_m, double tolerance_m) {
  const dyn::Terrain* t = &terrain;
  return [t, step_m, tolerance_m](const Geo& a, const Geo& b) {
    const double d = distance_m(a, b);
    if (d < 1e-6) return true;
    const int n = std::clamp(static_cast<int>(std::ceil(d / step_m)), 2, 4000);
    const double re = geo::kWgs84A;
    for (int k = 1; k < n; ++k) {
      const double s = static_cast<double>(k) / n;
      const double lat = a.lat_deg + s * (b.lat_deg - a.lat_deg);
      const double lon = a.lon_deg + s * wrap_lon_deg(b.lon_deg - a.lon_deg);
      // 직선(현)은 위경도 보간 고도보다 s(1-s)d²/(2R)만큼 낮다
      const double ray = a.alt_m + s * (b.alt_m - a.alt_m) - s * (1.0 - s) * d * d / (2.0 * re);
      const double ground = t->elevation_m(lat, lon);
      const double near_end = std::min(s, 1.0 - s) * d;
      const double tol = near_end <= step_m ? tolerance_m : 0.0;
      if (ray < ground - tol) return false;
    }
    return true;
  };
}

}  // namespace swarm::payload
