// IMP-CORE-010: 스크립트 경로 추종
#include "swarm/core/scripted.hpp"

#include <algorithm>
#include <cmath>

#include "swarm/dyn/geo.hpp"

namespace swarm::core {

namespace geo = dyn::geo;

ScriptedPathModel::ScriptedPathModel(std::vector<Point> points, double speed_mps)
    : pts_(std::move(points)), speed_(std::max(speed_mps, 0.0)) {
  cum_.push_back(0.0);
  for (std::size_t i = 0; i + 1 < pts_.size(); ++i) {
    const auto& a = pts_[i];
    const auto& b = pts_[i + 1];
    const double lat = a.lat_deg * geo::kDegToRad;
    const double dn = (b.lat_deg - a.lat_deg) * geo::kDegToRad * (geo::meridian_radius(lat) + a.alt_m);
    const double de = (b.lon_deg - a.lon_deg) * geo::kDegToRad * (geo::prime_vertical_radius(lat) + a.alt_m) *
                      std::cos(lat);
    const double dd = -(b.alt_m - a.alt_m);
    const double len = std::sqrt(dn * dn + de * de + dd * dd);
    cum_.push_back(cum_.back() + len);
    const double inv = len > 0.0 ? 1.0 / len : 0.0;
    dir_ned_.insert(dir_ned_.end(), {dn * inv, de * inv, dd * inv});
  }
}

void ScriptedPathModel::derivatives(double, std::span<const double>, std::span<const double>,
                                    const dyn::Environment&, std::span<double> dxdt) const {
  // 끝을 넘어도 거리는 계속 늘리고 to_kinematic에서 끝점에 묶는다(도함수 불연속을 피한다)
  dxdt[0] = speed_;
}

bool ScriptedPathModel::map_control(const v1::ControlOutput&, std::span<double>) const { return false; }

void ScriptedPathModel::to_kinematic(std::span<const double> x, const dyn::Environment&,
                                     dyn::KinematicSample& out) const {
  const double s = std::clamp(x[0], 0.0, length_m());
  const bool moving = x[0] < length_m() && speed_ > 0.0;
  // s가 속한 구간 i: cum_[i] <= s < cum_[i+1]. 끝점이면 마지막 구간
  std::size_t i = static_cast<std::size_t>(std::upper_bound(cum_.begin(), cum_.end(), s) - cum_.begin());
  i = std::min(i == 0 ? 0 : i - 1, cum_.size() >= 2 ? cum_.size() - 2 : 0);

  out = dyn::KinematicSample{};
  if (pts_.size() < 2) {
    out.lat_deg = pts_[0].lat_deg;
    out.lon_deg = pts_[0].lon_deg;
    out.alt_m = pts_[0].alt_m;
    return;
  }
  const auto& a = pts_[i];
  const auto& b = pts_[i + 1];
  const double seg = cum_[i + 1] - cum_[i];
  const double f = seg > 0.0 ? (s - cum_[i]) / seg : 1.0;
  out.lat_deg = a.lat_deg + f * (b.lat_deg - a.lat_deg);
  out.lon_deg = a.lon_deg + f * (b.lon_deg - a.lon_deg);
  out.alt_m = a.alt_m + f * (b.alt_m - a.alt_m);

  const double* d = &dir_ned_[3 * i];
  const double v = moving ? speed_ : 0.0;
  for (int k = 0; k < 3; ++k) out.vel_ned_mps[k] = v * d[k];
  // 자세는 진행 방향(멈춰도 마지막 구간 방향). 뱅크 0
  const double yaw = std::atan2(d[1], d[0]);
  const double pitch = std::atan2(-d[2], std::hypot(d[0], d[1]));
  geo::euler_to_quat(yaw, pitch, 0.0, out.quat_ned_frd);
}

void ScriptedPathModel::from_kinematic(const dyn::KinematicSample&, std::span<double> x) const { x[0] = 0.0; }

std::unique_ptr<dyn::DynamicsModel> make_scripted_model(const v1::EntitySpec& spec) {
  if (spec.script_path_size() == 0) return nullptr;
  const auto& init = spec.initial();
  std::vector<ScriptedPathModel::Point> pts{
      {init.position().lat_deg(), init.position().lon_deg(), init.position().alt_m()}};
  for (const auto& g : spec.script_path()) {
    const ScriptedPathModel::Point p{g.lat_deg(), g.lon_deg(), g.alt_m()};
    const auto& q = pts.back();
    if (p.lat_deg == q.lat_deg && p.lon_deg == q.lon_deg && p.alt_m == q.alt_m) continue;  // 길이 0 구간
    pts.push_back(p);
  }
  const auto& v = init.velocity_ned_mps();
  const double speed = std::sqrt(v.x() * v.x() + v.y() * v.y() + v.z() * v.z());
  return std::make_unique<ScriptedPathModel>(std::move(pts), speed);
}

}  // namespace swarm::core
