// IMP-DYN-001, IMP-DYN-002 (REQ-DYN-001, REQ-DYN-002, PRP-DYN-001)
#include "swarm/dyn/models.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

#include "swarm/dyn/geo.hpp"
#include "swarm/v1/fa.pb.h"

namespace swarm::dyn {
namespace {

using geo::kDegToRad;
using geo::kRadToDeg;

// 위경도는 m 단위 허용치를 rad로 바꾸고, 상대 허용치를 쓰지 않는다. 방위각도 누적되므로 상대 허용치를 쓰지 않는다
void position_heading_scale(std::span<double> abs_scale, std::span<double> rel_scale, std::size_t lat,
                            std::size_t lon, std::size_t heading) {
  std::fill(abs_scale.begin(), abs_scale.end(), 1.0);
  std::fill(rel_scale.begin(), rel_scale.end(), 1.0);
  abs_scale[lat] = abs_scale[lon] = 1.0 / geo::kWgs84A;
  rel_scale[lat] = rel_scale[lon] = rel_scale[heading] = 0.0;
}

bool read_kinematic(const swarm::v1::ControlOutput& cmd, const swarm::v1::KinematicCmd*& k) {
  if (cmd.cmd_case() != swarm::v1::ControlOutput::kKinematic) return false;
  k = &cmd.kinematic();
  return true;
}

void set_position(std::span<const double> x, std::size_t lat, std::size_t lon, std::size_t alt,
                  KinematicSample& out) {
  out.lat_deg = x[lat] * kRadToDeg;
  out.lon_deg = x[lon] * kRadToDeg;
  out.alt_m = x[alt];
}

void get_position(const KinematicSample& in, std::span<double> x, std::size_t lat, std::size_t lon,
                  std::size_t alt) {
  x[lat] = in.lat_deg * kDegToRad;
  x[lon] = in.lon_deg * kDegToRad;
  x[alt] = in.alt_m;
}

// 수평 속도가 거의 0이면 자세의 yaw로 방위각을 정한다
double heading_of(const KinematicSample& in) {
  const double vn = in.vel_ned_mps[0], ve = in.vel_ned_mps[1];
  if (std::hypot(vn, ve) > 1e-6) return std::atan2(ve, vn);
  double yaw, pitch, roll;
  geo::quat_to_euler(in.quat_ned_frd, yaw, pitch, roll);
  return yaw;
}

using L = ParamLayer;

// 선언 표와 필드 표는 같은 순서다
template <class P>
bool set_field(P& p, const std::vector<double P::*>& fields, std::span<const ParamDesc> descs, std::string_view name,
               double value) {
  for (std::size_t i = 0; i < descs.size(); ++i) {
    if (descs[i].name != name) continue;
    if (!(value >= descs[i].min && value <= descs[i].max)) return false;  // NaN 포함
    p.*fields[i] = value;
    return true;
  }
  return false;
}

template <class P>
double get_field(const P& p, const std::vector<double P::*>& fields, std::span<const ParamDesc> descs,
                 std::string_view name) {
  for (std::size_t i = 0; i < descs.size(); ++i)
    if (descs[i].name == name) return p.*fields[i];
  return 0.0;
}

// 시정수 하한 0.05 s는 프레임 스텝(최대 20 ms)의 절반보다 크다 (RK4 안정성)
const ParamDesc kDof2Descs[] = {
    {"tau_speed_s", L::kControl, 1.0, "s", 0.05, 30.0, true, "속도 명령 1차 지연 시정수"},
    {"tau_heading_rate_s", L::kControl, 0.2, "s", 0.05, 10.0, true, "선회율 명령 1차 지연 시정수"},
    {"tau_climb_s", L::kControl, 0.5, "s", 0.05, 20.0, true, "상승률 명령 1차 지연 시정수"},
    {"min_speed_mps", L::kAirframe, 0.0, "m/s", 0.0, 100.0, true, "속도 명령 하한(실속 속도)"},
    {"max_speed_mps", L::kAirframe, 400.0, "m/s", 1.0, 1000.0, true, "속도 명령 상한"},
    {"max_heading_rate_rps", L::kAirframe, 1.0, "rad/s", 0.01, 5.0, true, "선회율 명령 한계"},
    {"max_climb_rate_mps", L::kAirframe, 50.0, "m/s", 0.0, 200.0, true, "상승·하강률 명령 한계"},
};
const std::vector<double Dof2Model::Params::*> kDof2Fields = {
    &Dof2Model::Params::tau_speed_s,   &Dof2Model::Params::tau_heading_rate_s,   &Dof2Model::Params::tau_climb_s,
    &Dof2Model::Params::min_speed_mps, &Dof2Model::Params::max_speed_mps,
    &Dof2Model::Params::max_heading_rate_rps, &Dof2Model::Params::max_climb_rate_mps,
};

const ParamDesc kDof3Descs[] = {
    {"tau_speed_s", L::kControl, 1.0, "s", 0.05, 30.0, true, "속도 명령 1차 지연 시정수"},
    {"tau_bank_s", L::kControl, 0.3, "s", 0.05, 10.0, true, "뱅크 명령 1차 지연 시정수"},
    {"tau_gamma_s", L::kControl, 0.5, "s", 0.05, 20.0, true, "비행경로각 명령 1차 지연 시정수"},
    {"min_speed_mps", L::kAirframe, 1.0, "m/s", 0.1, 100.0, true, "속도 명령 하한, 선회율·비행경로각 계산의 분모 하한"},
    {"max_speed_mps", L::kAirframe, 400.0, "m/s", 1.0, 1000.0, true, "속도 명령 상한"},
    {"max_bank_rad", L::kAirframe, 1.0471975511965976, "rad", 0.05, 1.4, true, "뱅크 명령 한계"},
    {"max_climb_rate_mps", L::kAirframe, 50.0, "m/s", 0.0, 200.0, true, "상승·하강률 명령 한계"},
    {"max_gamma_rad", L::kAirframe, 0.5235987755982988, "rad", 0.05, 1.4, true, "비행경로각 명령 한계"},
};
const std::vector<double Dof3Model::Params::*> kDof3Fields = {
    &Dof3Model::Params::tau_speed_s,   &Dof3Model::Params::tau_bank_s,    &Dof3Model::Params::tau_gamma_s,
    &Dof3Model::Params::min_speed_mps, &Dof3Model::Params::max_speed_mps, &Dof3Model::Params::max_bank_rad,
    &Dof3Model::Params::max_climb_rate_mps, &Dof3Model::Params::max_gamma_rad,
};

}  // namespace

// ---------------------------------------------------------------- 2-DoF

std::span<const ParamDesc> Dof2Model::param_descs() const { return kDof2Descs; }
double Dof2Model::get_param(std::string_view name) const { return get_field(p_, kDof2Fields, kDof2Descs, name); }
bool Dof2Model::set_param(std::string_view name, double value) {
  return set_field(p_, kDof2Fields, kDof2Descs, name, value);
}

void Dof2Model::derivatives(double, std::span<const double> x, std::span<const double> u, const Environment& env,
                            std::span<double> dxdt) const {
  const double v = x[kSpeed], psi = x[kHeading];
  const double* w = env.wind_ned_mps;
  const double vn = v * std::cos(psi) + w[0], ve = v * std::sin(psi) + w[1], vd = -x[kClimbRate] + w[2];
  geo::geodetic_rates(x[kLat], x[kAlt], vn, ve, vd, dxdt[kLat], dxdt[kLon], dxdt[kAlt]);

  const double v_c = std::clamp(u[kSpeedCmd], p_.min_speed_mps, p_.max_speed_mps);
  const double r_c = std::clamp(u[kHeadingRateCmd], -p_.max_heading_rate_rps, p_.max_heading_rate_rps);
  const double h_c = std::clamp(u[kClimbRateCmd], -p_.max_climb_rate_mps, p_.max_climb_rate_mps);
  dxdt[kSpeed] = (v_c - v) / p_.tau_speed_s;
  dxdt[kHeading] = x[kHeadingRate];
  dxdt[kHeadingRate] = (r_c - x[kHeadingRate]) / p_.tau_heading_rate_s;
  dxdt[kClimbRate] = (h_c - x[kClimbRate]) / p_.tau_climb_s;
}

bool Dof2Model::map_control(const swarm::v1::ControlOutput& cmd, std::span<double> u) const {
  const swarm::v1::KinematicCmd* k = nullptr;
  if (!read_kinematic(cmd, k)) return false;
  u[kSpeedCmd] = k->speed_mps();
  u[kHeadingRateCmd] = k->heading_rate_rps();
  u[kClimbRateCmd] = k->climb_rate_mps();
  return true;
}

// 자세: yaw = ψ, pitch = 비행경로각, roll = 선회율에 해당하는 협조선회 뱅크 atan(V·ψ̇/g)
void Dof2Model::to_kinematic(std::span<const double> x, const Environment& env, KinematicSample& out) const {
  set_position(x, kLat, kLon, kAlt, out);
  const double v = x[kSpeed], psi = x[kHeading], hdot = x[kClimbRate], rate = x[kHeadingRate];
  const double* w = env.wind_ned_mps;
  out.vel_ned_mps[0] = v * std::cos(psi) + w[0];
  out.vel_ned_mps[1] = v * std::sin(psi) + w[1];
  out.vel_ned_mps[2] = -hdot + w[2];
  const double pitch = std::atan2(hdot, std::max(v, 1e-9));
  const double roll = std::atan(v * rate / env.gravity_mps2);
  geo::euler_to_quat(psi, pitch, roll, out.quat_ned_frd);
  geo::yaw_rate_to_body_rates(rate, pitch, roll, out.rate_frd_rps);
}

void Dof2Model::from_kinematic(const KinematicSample& in, std::span<double> x) const {
  get_position(in, x, kLat, kLon, kAlt);
  x[kSpeed] = std::hypot(in.vel_ned_mps[0], in.vel_ned_mps[1]);
  x[kHeading] = heading_of(in);
  x[kClimbRate] = -in.vel_ned_mps[2];
  double yaw, pitch, roll;
  geo::quat_to_euler(in.quat_ned_frd, yaw, pitch, roll);
  x[kHeadingRate] = geo::body_rates_to_yaw_rate(in.rate_frd_rps, pitch, roll);
}

void Dof2Model::error_scale(std::span<double> abs_scale, std::span<double> rel_scale) const {
  position_heading_scale(abs_scale, rel_scale, kLat, kLon, kHeading);
}

// ---------------------------------------------------------------- 3-DoF

std::span<const ParamDesc> Dof3Model::param_descs() const { return kDof3Descs; }
double Dof3Model::get_param(std::string_view name) const { return get_field(p_, kDof3Fields, kDof3Descs, name); }
bool Dof3Model::set_param(std::string_view name, double value) {
  return set_field(p_, kDof3Fields, kDof3Descs, name, value);
}

void Dof3Model::derivatives(double, std::span<const double> x, std::span<const double> u, const Environment& env,
                            std::span<double> dxdt) const {
  const double v = x[kSpeed], psi = x[kHeading], gamma = x[kGamma], phi = x[kBank];
  const double vh = v * std::cos(gamma);
  const double* w = env.wind_ned_mps;
  geo::geodetic_rates(x[kLat], x[kAlt], vh * std::cos(psi) + w[0], vh * std::sin(psi) + w[1],
                      -v * std::sin(gamma) + w[2], dxdt[kLat], dxdt[kLon], dxdt[kAlt]);

  const double v_c = std::clamp(u[kSpeedCmd], p_.min_speed_mps, p_.max_speed_mps);
  const double phi_c = std::clamp(u[kBankCmd], -p_.max_bank_rad, p_.max_bank_rad);
  const double h_c = std::clamp(u[kClimbRateCmd], -p_.max_climb_rate_mps, p_.max_climb_rate_mps);
  const double v_den = std::max(v, p_.min_speed_mps);
  const double gamma_c = std::clamp(std::asin(std::clamp(h_c / v_den, -1.0, 1.0)), -p_.max_gamma_rad, p_.max_gamma_rad);

  dxdt[kSpeed] = (v_c - v) / p_.tau_speed_s;
  dxdt[kHeading] = env.gravity_mps2 * std::tan(phi) / std::max(vh, p_.min_speed_mps);
  dxdt[kGamma] = (gamma_c - gamma) / p_.tau_gamma_s;
  dxdt[kBank] = (phi_c - phi) / p_.tau_bank_s;
}

bool Dof3Model::map_control(const swarm::v1::ControlOutput& cmd, std::span<double> u) const {
  const swarm::v1::KinematicCmd* k = nullptr;
  if (!read_kinematic(cmd, k)) return false;
  u[kSpeedCmd] = k->speed_mps();
  u[kBankCmd] = k->bank_rad();
  u[kClimbRateCmd] = k->climb_rate_mps();
  return true;
}

// 각속도는 롤·피치 변화율을 0으로 둔 정상 선회값이다
void Dof3Model::to_kinematic(std::span<const double> x, const Environment& env, KinematicSample& out) const {
  set_position(x, kLat, kLon, kAlt, out);
  const double v = x[kSpeed], psi = x[kHeading], gamma = x[kGamma], phi = x[kBank];
  const double vh = v * std::cos(gamma);
  const double* w = env.wind_ned_mps;
  out.vel_ned_mps[0] = vh * std::cos(psi) + w[0];
  out.vel_ned_mps[1] = vh * std::sin(psi) + w[1];
  out.vel_ned_mps[2] = -v * std::sin(gamma) + w[2];
  geo::euler_to_quat(psi, gamma, phi, out.quat_ned_frd);
  const double rate = env.gravity_mps2 * std::tan(phi) / std::max(vh, p_.min_speed_mps);
  geo::yaw_rate_to_body_rates(rate, gamma, phi, out.rate_frd_rps);
}

void Dof3Model::from_kinematic(const KinematicSample& in, std::span<double> x) const {
  get_position(in, x, kLat, kLon, kAlt);
  const double vn = in.vel_ned_mps[0], ve = in.vel_ned_mps[1], vd = in.vel_ned_mps[2];
  const double vh = std::hypot(vn, ve);
  x[kSpeed] = std::sqrt(vh * vh + vd * vd);
  x[kHeading] = heading_of(in);
  x[kGamma] = std::atan2(-vd, vh);
  double yaw, pitch, roll;
  geo::quat_to_euler(in.quat_ned_frd, yaw, pitch, roll);
  x[kBank] = roll;
}

void Dof3Model::error_scale(std::span<double> abs_scale, std::span<double> rel_scale) const {
  position_heading_scale(abs_scale, rel_scale, kLat, kLon, kHeading);
}

}  // namespace swarm::dyn
