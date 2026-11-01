// WGS84 곡률 반경과 자세 변환. docs/10_contracts.md §2
#pragma once

#include <algorithm>
#include <cmath>
#include <numbers>

namespace swarm::dyn::geo {

inline constexpr double kWgs84A = 6378137.0;
inline constexpr double kWgs84F = 1.0 / 298.257223563;
inline constexpr double kWgs84E2 = kWgs84F * (2.0 - kWgs84F);
inline constexpr double kStdGravity = 9.80665;
inline constexpr double kDegToRad = std::numbers::pi / 180.0;
inline constexpr double kRadToDeg = 180.0 / std::numbers::pi;

// 자오선 곡률 반경 M
inline double meridian_radius(double lat_rad) {
  const double s = std::sin(lat_rad);
  const double w = 1.0 - kWgs84E2 * s * s;
  return kWgs84A * (1.0 - kWgs84E2) / (w * std::sqrt(w));
}

// 묘유선 곡률 반경 N
inline double prime_vertical_radius(double lat_rad) {
  const double s = std::sin(lat_rad);
  return kWgs84A / std::sqrt(1.0 - kWgs84E2 * s * s);
}

// NED 속도 → 위경도(rad)·고도 변화율
inline void geodetic_rates(double lat_rad, double alt_m, double vn, double ve, double vd, double& dlat,
                           double& dlon, double& dalt) {
  const double cos_lat = std::max(std::cos(lat_rad), 1e-9);
  dlat = vn / (meridian_radius(lat_rad) + alt_m);
  dlon = ve / ((prime_vertical_radius(lat_rad) + alt_m) * cos_lat);
  dalt = -vd;
}

// ZYX 오일러각(yaw ψ, pitch θ, roll φ) → NED→FRD 자세 쿼터니언 (w, x, y, z)
inline void euler_to_quat(double yaw, double pitch, double roll, double q[4]) {
  const double cy = std::cos(0.5 * yaw), sy = std::sin(0.5 * yaw);
  const double cp = std::cos(0.5 * pitch), sp = std::sin(0.5 * pitch);
  const double cr = std::cos(0.5 * roll), sr = std::sin(0.5 * roll);
  q[0] = cr * cp * cy + sr * sp * sy;
  q[1] = sr * cp * cy - cr * sp * sy;
  q[2] = cr * sp * cy + sr * cp * sy;
  q[3] = cr * cp * sy - sr * sp * cy;
}

inline void quat_to_euler(const double q[4], double& yaw, double& pitch, double& roll) {
  const double w = q[0], x = q[1], y = q[2], z = q[3];
  roll = std::atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y));
  pitch = std::asin(std::clamp(2.0 * (w * y - z * x), -1.0, 1.0));
  yaw = std::atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z));
}

// 롤·피치 변화율이 0인 정상 상태에서 선회율 ψ̇ → 기체 FRD 각속도 (p, q, r)
inline void yaw_rate_to_body_rates(double yaw_rate, double pitch, double roll, double rate[3]) {
  rate[0] = -yaw_rate * std::sin(pitch);
  rate[1] = yaw_rate * std::cos(pitch) * std::sin(roll);
  rate[2] = yaw_rate * std::cos(pitch) * std::cos(roll);
}

// yaw_rate_to_body_rates의 역
inline double body_rates_to_yaw_rate(const double rate[3], double pitch, double roll) {
  const double cos_pitch = std::cos(pitch);
  if (std::abs(cos_pitch) < 1e-9) return 0.0;
  return (rate[1] * std::sin(roll) + rate[2] * std::cos(roll)) / cos_pitch;
}

}  // namespace swarm::dyn::geo
