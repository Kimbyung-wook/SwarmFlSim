// IMP-CORE-005: 등속 2-DoF 목 모델, RK4 목 적분기
#include "swarm/core/mock_dynamics.hpp"

#include <algorithm>
#include <cmath>
#include <numbers>
#include <vector>

#include "swarm/v1/fa.pb.h"

namespace swarm::core::mock {

namespace {
constexpr double kDeg = 180.0 / std::numbers::pi;
enum : std::size_t { kLat, kLon, kAlt, kSpeed, kHeading, kClimb };
}  // namespace

void ConstantVelocity2Dof::derivatives(double, std::span<const double> x, std::span<const double> u,
                                       const dyn::Environment&, std::span<double> dxdt) const {
  const double v = x[kSpeed], psi = x[kHeading];
  const double cos_lat = std::max(std::cos(x[kLat] / kDeg), 1e-6);
  dxdt[kLat] = v * std::cos(psi) / kEarthRadiusM * kDeg;
  dxdt[kLon] = v * std::sin(psi) / (kEarthRadiusM * cos_lat) * kDeg;
  dxdt[kAlt] = x[kClimb];
  dxdt[kSpeed] = (u[0] - v) / kTauS;
  dxdt[kHeading] = u[1];
  dxdt[kClimb] = (u[2] - x[kClimb]) / kTauS;
}

bool ConstantVelocity2Dof::map_control(const v1::ControlOutput& cmd, std::span<double> u) const {
  if (!cmd.has_kinematic()) return false;
  const auto& k = cmd.kinematic();
  u[0] = k.speed_mps();
  // 3-DoF 협조선회 명령(bank)도 받아 선회율로 바꾼다
  u[1] = k.heading_rate_rps() + 9.80665 * std::tan(k.bank_rad()) / std::max(k.speed_mps(), 1.0);
  u[2] = k.climb_rate_mps();
  return true;
}

void ConstantVelocity2Dof::to_kinematic(std::span<const double> x, dyn::KinematicSample& out) const {
  const double v = x[kSpeed], psi = x[kHeading], climb = x[kClimb];
  out.lat_deg = x[kLat];
  out.lon_deg = x[kLon];
  out.alt_m = x[kAlt];
  out.vel_ned_mps[0] = v * std::cos(psi);
  out.vel_ned_mps[1] = v * std::sin(psi);
  out.vel_ned_mps[2] = -climb;
  // 요(방위각) → 피치(비행경로각) 순서의 NED→FRD 회전
  const double gamma = std::atan2(climb, std::max(v, 1e-9));
  const double cy = std::cos(psi / 2), sy = std::sin(psi / 2), cp = std::cos(gamma / 2), sp = std::sin(gamma / 2);
  out.quat_ned_frd[0] = cy * cp;
  out.quat_ned_frd[1] = -sy * sp;
  out.quat_ned_frd[2] = cy * sp;
  out.quat_ned_frd[3] = sy * cp;
  out.rate_frd_rps[0] = out.rate_frd_rps[1] = out.rate_frd_rps[2] = 0.0;
}

void ConstantVelocity2Dof::from_kinematic(const dyn::KinematicSample& in, std::span<double> x) const {
  x[kLat] = in.lat_deg;
  x[kLon] = in.lon_deg;
  x[kAlt] = in.alt_m;
  x[kSpeed] = std::hypot(in.vel_ned_mps[0], in.vel_ned_mps[1]);
  x[kHeading] = std::atan2(in.vel_ned_mps[1], in.vel_ned_mps[0]);
  x[kClimb] = -in.vel_ned_mps[2];
}

void ConstantVelocity2Dof::hold_input(std::span<const double> x, std::span<double> u) {
  u[0] = x[kSpeed];
  u[1] = 0.0;
  u[2] = x[kClimb];
}

dyn::StepResult Rk4::step(const dyn::DynamicsModel& model, double t0, double dt, std::span<double> x,
                          std::span<const double> u, const dyn::Environment& env, const dyn::EventFn*) {
  const std::size_t n = x.size();
  std::vector<double> k1(n), k2(n), k3(n), k4(n), tmp(n);
  const double h = dt / substeps_;
  double t = t0;
  for (int s = 0; s < substeps_; ++s) {
    model.derivatives(t, x, u, env, k1);
    for (std::size_t i = 0; i < n; ++i) tmp[i] = x[i] + 0.5 * h * k1[i];
    model.derivatives(t + 0.5 * h, tmp, u, env, k2);
    for (std::size_t i = 0; i < n; ++i) tmp[i] = x[i] + 0.5 * h * k2[i];
    model.derivatives(t + 0.5 * h, tmp, u, env, k3);
    for (std::size_t i = 0; i < n; ++i) tmp[i] = x[i] + h * k3[i];
    model.derivatives(t + h, tmp, u, env, k4);
    for (std::size_t i = 0; i < n; ++i) x[i] += h / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]);
    t += h;
  }
  return {t0 + dt, substeps_, 0.0, false};
}

DynamicsProvider provider() {
  DynamicsProvider p;
  p.make_model = [](const v1::EntitySpec& spec) -> std::unique_ptr<dyn::DynamicsModel> {
    if (spec.dynamics() == v1::DYNAMICS_KIND_DOF2 || spec.dynamics() == v1::DYNAMICS_KIND_DOF3)
      return std::make_unique<ConstantVelocity2Dof>();
    return nullptr;
  };
  p.make_integrator = [] { return std::make_unique<Rk4>(); };
  p.init_input = [](const dyn::DynamicsModel& m, std::span<const double> x, std::span<double> u) {
    if (dynamic_cast<const ConstantVelocity2Dof*>(&m)) ConstantVelocity2Dof::hold_input(x, u);
  };
  return p;
}

}  // namespace swarm::core::mock
