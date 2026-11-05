// TC-DYN-001~015: 동역학 모델·적분기·지형 시험. 인자로 TC ID를 받아 해당 시험만 실행한다
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <sstream>
#include <numbers>
#include <stdexcept>
#include <string>
#include <vector>

#include "swarm/dyn/factory.hpp"
#include "swarm/dyn/geo.hpp"
#include "swarm/dyn/integrators.hpp"
#include "swarm/dyn/models.hpp"
#include "swarm/dyn/terrain.hpp"
#include "swarm/v1/fa.pb.h"

using namespace swarm::dyn;
namespace geo = swarm::dyn::geo;

namespace {

int g_failures = 0;

void check(bool cond, const char* what) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}

void check_near(double got, double want, double tol, const char* what) {
  if (!(std::abs(got - want) <= tol)) {
    std::fprintf(stderr, "FAIL: %s: got %.12g want %.12g (tol %.3g)\n", what, got, want, tol);
    ++g_failures;
  }
}

constexpr double kPi = std::numbers::pi;
constexpr double kLat0 = 37.5 * geo::kDegToRad;
constexpr double kLon0 = 127.0 * geo::kDegToRad;

// 시험용 조화 진동자 x'' = −x. 해 x = cos t (x0 = [1, 0])
class Oscillator final : public DynamicsModel {
 public:
  std::string_view name() const override { return "oscillator"; }
  int dof() const override { return 1; }
  std::size_t state_size() const override { return 2; }
  std::size_t input_size() const override { return 0; }
  void derivatives(double, std::span<const double> x, std::span<const double>, const Environment&,
                   std::span<double> dxdt) const override {
    dxdt[0] = x[1];
    dxdt[1] = -x[0];
  }
  bool map_control(const swarm::v1::ControlOutput&, std::span<double>) const override { return false; }
  void to_kinematic(std::span<const double>, const Environment&, KinematicSample&) const override {}
  void from_kinematic(const KinematicSample&, std::span<double>) const override {}
};

// 프레임 dt로 [0, T]를 적분한다. 각 프레임 끝에서 on_frame(t, x) 호출. 이벤트가 나면 그 결과를 돌려준다
struct RunResult {
  double t = 0.0;
  bool event = false;
  int substeps = 0;
  double max_error = 0.0;
};

RunResult run(Integrator& integ, const DynamicsModel& m, std::vector<double>& x, const std::vector<double>& u,
              const Environment& env, double T, double dt, const EventFn* event = nullptr,
              const std::function<void(double, const std::vector<double>&)>& on_frame = {}) {
  RunResult rr;
  double t = 0.0;
  while (T - t > 1e-12) {
    const double h = std::min(dt, T - t);
    const StepResult s = integ.step(m, t, h, x, u, env, event);
    rr.substeps += s.substeps;
    rr.max_error = std::max(rr.max_error, s.max_error);
    t = s.event ? s.t_end : t + h;
    if (on_frame) on_frame(t, x);
    if (s.event) {
      rr.event = true;
      break;
    }
  }
  rr.t = t;
  return rr;
}

// 시작점 기준 국지 북·동 거리(m)
void local_ne(double lat, double lon, double alt, double& n, double& e) {
  n = (lat - kLat0) * (geo::meridian_radius(0.5 * (lat + kLat0)) + alt);
  e = (lon - kLon0) * (geo::prime_vertical_radius(lat) + alt) * std::cos(lat);
}

std::vector<std::unique_ptr<Integrator>> both_integrators() {
  std::vector<std::unique_ptr<Integrator>> v;
  v.push_back(std::make_unique<Rk4Integrator>());
  v.push_back(std::make_unique<Rk45Integrator>(Rk45Integrator::Config{.rtol = 1e-9, .atol = 1e-9}));
  return v;
}

// ---------------------------------------------------------------- TC-DYN-001 등속(+일정 상승) 해석해
void tc001() {
  const double a = geo::kWgs84A, v = 50.0, c = 5.0, h0 = 100.0, T = 60.0;
  const double lon_exact = (v / c) * std::log((a + h0 + c * T) / (a + h0));
  Dof2Model m;
  for (auto& integ : both_integrators()) {
    std::vector<double> x = {0.0, 0.0, h0, v, kPi / 2, 0.0, c};
    run(*integ, m, x, {v, 0.0, c}, Environment{}, T, 0.02);
    check_near(x[Dof2Model::kLon] * (a + h0 + c * T), lon_exact * (a + h0 + c * T), 1e-4, "tc001 east distance (m)");
    check_near(x[Dof2Model::kAlt], h0 + c * T, 1e-6, "tc001 altitude");
    check_near(x[Dof2Model::kLat] * a, 0.0, 1e-6, "tc001 stays on equator");
  }
}

// 정상 선회: 시작점에서 북쪽으로 출발, 우선회. 중심은 동쪽 R. 한 바퀴 동안 중심까지 거리와 폐합 오차를 본다
void check_circle(Integrator& integ, const DynamicsModel& m, std::vector<double> x, const std::vector<double>& u,
                  double R, double T, std::size_t ilat, std::size_t ilon, std::size_t ialt, const char* tag) {
  double worst = 0.0;
  run(integ, m, x, u, Environment{}, T, 0.02, nullptr, [&](double, const std::vector<double>& s) {
    double n, e;
    local_ne(s[ilat], s[ilon], s[ialt], n, e);
    worst = std::max(worst, std::abs(std::hypot(n, e - R) - R));
  });
  double n, e;
  local_ne(x[ilat], x[ilon], x[ialt], n, e);
  std::string w = std::string(tag) + " radius deviation (m)", c = std::string(tag) + " closure (m)";
  check_near(worst, 0.0, 0.05, w.c_str());
  check_near(std::hypot(n, e), 0.0, 0.05, c.c_str());
}

// ---------------------------------------------------------------- TC-DYN-002 2-DoF 정상 선회 반경 V/ψ̇
void tc002() {
  const double v = 40.0, r = 0.2, R = v / r, T = 2 * kPi / r;
  Dof2Model m;
  for (auto& integ : both_integrators())
    check_circle(*integ, m, {kLat0, kLon0, 500.0, v, 0.0, r, 0.0}, {v, r, 0.0}, R, T, Dof2Model::kLat,
                 Dof2Model::kLon, Dof2Model::kAlt, "tc002");
}

// ---------------------------------------------------------------- TC-DYN-003 3-DoF 협조선회 반경 v²/(g·tanφ)
void tc003() {
  const double v = 30.0, phi = 30.0 * geo::kDegToRad, g = geo::kStdGravity;
  const double R = v * v / (g * std::tan(phi)), T = 2 * kPi * R / v;
  Dof3Model m;
  std::vector<double> x0 = {kLat0, kLon0, 500.0, v, 0.0, 0.0, phi}, d(7);
  m.derivatives(0.0, x0, std::vector<double>{v, phi, 0.0}, Environment{}, d);
  check_near(d[Dof3Model::kHeading], g * std::tan(phi) / v, 1e-12, "tc003 turn rate g·tanφ/V");
  for (auto& integ : both_integrators())
    check_circle(*integ, m, x0, {v, phi, 0.0}, R, T, Dof3Model::kLat, Dof3Model::kLon, Dof3Model::kAlt, "tc003");
}

double oscillator_error(Integrator& integ, double h, double T) {
  Oscillator m;
  std::vector<double> x = {1.0, 0.0};
  run(integ, m, x, {}, Environment{}, T, h);
  return std::hypot(x[0] - std::cos(T), x[1] + std::sin(T));
}

// ---------------------------------------------------------------- TC-DYN-004 RK4 오차 차수 ≈ 4
void tc004() {
  Rk4Integrator integ;
  const double e1 = oscillator_error(integ, 0.1, 10.0), e2 = oscillator_error(integ, 0.05, 10.0);
  const double order = std::log2(e1 / e2);
  std::printf("rk4: e(0.1)=%.3e e(0.05)=%.3e order=%.3f\n", e1, e2, order);
  check(order > 3.8 && order < 4.2, "tc004 rk4 order");
}

// ---------------------------------------------------------------- TC-DYN-005 RK45 고정 스텝 오차 차수 ≈ 5
void tc005() {
  // 허용치를 아주 크게 두면 거부가 없고, 프레임 = 스텝이 된다
  Rk45Integrator integ(Rk45Integrator::Config{.rtol = 1e30, .atol = 1e30});
  const double e1 = oscillator_error(integ, 0.2, 10.0), e2 = oscillator_error(integ, 0.1, 10.0);
  const double order = std::log2(e1 / e2);
  std::printf("rk45: e(0.2)=%.3e e(0.1)=%.3e order=%.3f\n", e1, e2, order);
  check(order > 4.7 && order < 5.3, "tc005 rk45 order");
}

// ---------------------------------------------------------------- TC-DYN-006 RK45 가변 스텝 허용치
void tc006() {
  const double T = 10.0, dt = 0.5;
  double err[2];
  int sub[2];
  const double tols[2] = {1e-6, 1e-9};
  for (int i = 0; i < 2; ++i) {
    Rk45Integrator integ(Rk45Integrator::Config{.rtol = tols[i], .atol = tols[i]});
    Oscillator m;
    std::vector<double> x = {1.0, 0.0};
    const RunResult rr = run(integ, m, x, {}, Environment{}, T, dt);
    err[i] = std::hypot(x[0] - std::cos(T), x[1] + std::sin(T));
    sub[i] = rr.substeps;
    check(rr.max_error <= 1.0, "tc006 accepted error within tolerance");
    std::printf("rk45 tol=%.0e: err=%.3e substeps=%d\n", tols[i], err[i], rr.substeps);
  }
  check(err[0] < 1e-4 && err[1] < 1e-7, "tc006 global error bounded");
  check(err[1] * 100 < err[0], "tc006 tighter tolerance reduces error");
  check(sub[1] > sub[0] && sub[1] > static_cast<int>(T / dt), "tc006 substeps grow inside frames");
}

// ---------------------------------------------------------------- TC-DYN-007 이벤트 시점 (cos t = 0 → π/2)
void tc007() {
  Oscillator m;
  const EventFn ev = [](double, std::span<const double> x) { return x[0]; };
  Rk4Integrator rk4(Rk4Integrator::Config{.max_step_s = 0.01, .event_time_tol_s = 1e-10});
  Rk45Integrator rk45(Rk45Integrator::Config{.rtol = 1e-11, .atol = 1e-11, .event_time_tol_s = 1e-10});
  Integrator* list[] = {&rk4, &rk45};
  for (Integrator* integ : list) {
    std::vector<double> x = {1.0, 0.0};
    const RunResult rr = run(*integ, m, x, {}, Environment{}, 3.0, 0.1, &ev);
    check(rr.event, "tc007 event fired");
    check_near(rr.t, kPi / 2, 1e-8, "tc007 event time");
    check(x[0] <= 0.0 && x[0] > -1e-8, "tc007 state at crossing");
  }
  // 0에서 시작하면 교차로 보지 않는다
  std::vector<double> x = {0.0, -1.0};
  const StepResult s = rk45.step(m, 0.0, 0.1, x, {}, Environment{}, &ev);
  check(!s.event, "tc007 no event when starting on the surface");
}

// ---------------------------------------------------------------- TC-DYN-008 지면 교차
void tc008() {
  // (a) 평지 50 m, 2-DoF 100 m에서 −10 m/s 하강 → t = 5 s
  {
    Dof2Model m;
    FlatTerrain flat(50.0);
    const EventFn ev = make_ground_event(m, flat);
    Rk4Integrator rk4(Rk4Integrator::Config{.event_time_tol_s = 1e-7});
    Rk45Integrator rk45(Rk45Integrator::Config{.event_time_tol_s = 1e-7});
    Integrator* list[] = {&rk4, &rk45};
    for (Integrator* integ : list) {
      std::vector<double> x = {kLat0, kLon0, 100.0, 30.0, 0.0, 0.0, -10.0};
      const RunResult rr = run(*integ, m, x, {30.0, 0.0, -10.0}, Environment{}, 20.0, 0.02, &ev);
      check(rr.event, "tc008a event fired");
      check_near(rr.t, 5.0, 1e-5, "tc008a impact time");
      check(x[Dof2Model::kAlt] - 50.0 <= 0.0 && x[Dof2Model::kAlt] - 50.0 > -1e-5, "tc008a impact altitude");
    }
  }
  // (b) 북쪽으로 오르는 격자 지형(0.1°당 200 m), 3-DoF 150 m 수평 비행 → 위도 +0.075°에서 충돌
  {
    const double lat0 = 37.5, lon0 = 127.0, v = 100.0, alt = 150.0;
    GridTerrain grid({lat0, lon0 - 0.05, 0.05, 0.05, 3, 3}, {0, 0, 0, 100, 100, 100, 200, 200, 200});
    Dof3Model m;
    const EventFn ev = make_ground_event(m, grid);
    Rk45Integrator integ(Rk45Integrator::Config{.event_time_tol_s = 1e-7});
    std::vector<double> x = {lat0 * geo::kDegToRad, lon0 * geo::kDegToRad, alt, v, 0.0, 0.0, 0.0};
    const RunResult rr = run(integ, m, x, {v, 0.0, 0.0}, Environment{}, 200.0, 0.02, &ev);
    const double dlat = 0.075 * geo::kDegToRad;
    const double t_exact = (geo::meridian_radius(lat0 * geo::kDegToRad + 0.5 * dlat) + alt) * dlat / v;
    check(rr.event, "tc008b event fired");
    check_near(rr.t, t_exact, 1e-3, "tc008b impact time");
    const double g = ev(rr.t, x);
    check(g <= 0.0 && g > -1e-4, "tc008b on terrain surface");
  }
}

// ---------------------------------------------------------------- TC-DYN-009 map_control 형식 검사
void tc009() {
  Dof2Model m2;
  Dof3Model m3;
  std::vector<double> u(3, -1.0);
  swarm::v1::ControlOutput empty, att, act, kin;
  att.mutable_attitude()->set_roll_rad(0.1);
  act.mutable_actuator()->set_throttle(0.5);
  auto* k = kin.mutable_kinematic();
  k->set_speed_mps(25.0);
  k->set_bank_rad(0.4);
  k->set_heading_rate_rps(0.1);
  k->set_climb_rate_mps(2.0);

  for (const DynamicsModel* m : {static_cast<const DynamicsModel*>(&m2), static_cast<const DynamicsModel*>(&m3)}) {
    check(!m->map_control(empty, u), "tc009 empty cmd rejected");
    check(!m->map_control(att, u), "tc009 attitude cmd rejected");
    check(!m->map_control(act, u), "tc009 actuator cmd rejected");
  }
  check(m2.map_control(kin, u) && u[0] == 25.0 && u[1] == 0.1 && u[2] == 2.0, "tc009 dof2 uses heading_rate");
  check(m3.map_control(kin, u) && u[0] == 25.0 && u[1] == 0.4 && u[2] == 2.0, "tc009 dof3 uses bank");
}

// ---------------------------------------------------------------- TC-DYN-010 격자 지형 보간
void tc010() {
  // 평면 h = 10 + 300·Δlat + 200·Δlon (deg)은 쌍선형 보간으로 정확히 재현된다
  const GridSpec spec{37.0, 126.0, 0.5, 0.25, 4, 5};
  std::vector<float> h(spec.rows * spec.cols);
  for (std::size_t r = 0; r < spec.rows; ++r)
    for (std::size_t c = 0; c < spec.cols; ++c)
      h[r * spec.cols + c] = static_cast<float>(10.0 + 300.0 * (r * spec.dlat_deg) + 200.0 * (c * spec.dlon_deg));
  GridTerrain grid(spec, h, -1.0);
  const auto plane = [](double lat, double lon) { return 10.0 + 300.0 * (lat - 37.0) + 200.0 * (lon - 126.0); };
  for (double lat : {37.0, 37.13, 37.5, 38.2, 38.5})
    for (double lon : {126.0, 126.07, 126.6, 127.0})
      check_near(grid.elevation_m(lat, lon), plane(lat, lon), 1e-3, "tc010 bilinear on plane");
  check_near(grid.elevation_m(36.9, 126.5), -1.0, 0.0, "tc010 outside south");
  check_near(grid.elevation_m(37.5, 127.1), -1.0, 0.0, "tc010 outside east");
  // 셀 안 비선형 보간
  GridTerrain cell({0.0, 0.0, 1.0, 1.0, 2, 2}, {0, 0, 0, 4});
  check_near(cell.elevation_m(0.5, 0.5), 1.0, 1e-12, "tc010 bilinear saddle");
  FlatTerrain flat(12.5);
  check_near(flat.elevation_m(37.0, 127.0), 12.5, 0.0, "tc010 flat");

  bool threw = false;
  try {
    GridTerrain bad(spec, std::vector<float>(3), 0.0);
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  check(threw, "tc010 size mismatch throws");
}

bool quat_unit(const double q[4]) {
  return std::abs(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3] - 1.0) < 1e-12;
}

// ---------------------------------------------------------------- TC-DYN-011 상태 ⇄ KinematicSample, 자세
void tc011() {
  {
    Dof3Model m;
    const std::vector<double> x = {kLat0, kLon0, 800.0, 50.0, 1.0, 0.1, 0.3};
    KinematicSample k;
    m.to_kinematic(x, Environment{}, k);
    check_near(k.lat_deg, 37.5, 1e-12, "tc011 dof3 lat deg");
    check_near(k.vel_ned_mps[0], 50.0 * std::cos(0.1) * std::cos(1.0), 1e-12, "tc011 dof3 vn");
    check_near(k.vel_ned_mps[1], 50.0 * std::cos(0.1) * std::sin(1.0), 1e-12, "tc011 dof3 ve");
    check_near(k.vel_ned_mps[2], -50.0 * std::sin(0.1), 1e-12, "tc011 dof3 vd");
    double yaw, pitch, roll;
    geo::quat_to_euler(k.quat_ned_frd, yaw, pitch, roll);
    check(quat_unit(k.quat_ned_frd), "tc011 dof3 unit quaternion");
    check_near(yaw, 1.0, 1e-12, "tc011 dof3 yaw = heading");
    check_near(pitch, 0.1, 1e-12, "tc011 dof3 pitch = flight path angle");
    check_near(roll, 0.3, 1e-12, "tc011 dof3 roll = bank");
    std::vector<double> back(7);
    m.from_kinematic(k, back);
    for (std::size_t i = 0; i < 7; ++i) check_near(back[i], x[i], 1e-9, "tc011 dof3 round trip");
  }
  {
    Dof2Model m;
    const std::vector<double> x = {kLat0, kLon0, 300.0, 40.0, -2.0, 0.1, 3.0};
    KinematicSample k;
    m.to_kinematic(x, Environment{}, k);
    double yaw, pitch, roll;
    geo::quat_to_euler(k.quat_ned_frd, yaw, pitch, roll);
    check(quat_unit(k.quat_ned_frd), "tc011 dof2 unit quaternion");
    check_near(yaw, -2.0, 1e-12, "tc011 dof2 yaw = heading");
    check_near(roll, std::atan(40.0 * 0.1 / geo::kStdGravity), 1e-12, "tc011 dof2 coordinated bank");
    check_near(k.vel_ned_mps[2], -3.0, 1e-12, "tc011 dof2 vd");
    std::vector<double> back(7);
    m.from_kinematic(k, back);
    for (std::size_t i = 0; i < 7; ++i) check_near(back[i], x[i], 1e-9, "tc011 dof2 round trip");
  }
}

// ---------------------------------------------------------------- TC-DYN-012 팩토리
void tc012() {
  for (const auto& n : model_names()) check(make_model(n) != nullptr, "tc012 model created");
  for (const auto& n : reserved_model_names()) check(make_model(n) == nullptr, "tc012 reserved model is null");
  for (const auto& n : integrator_names()) check(make_integrator(n) != nullptr, "tc012 integrator created");
  check(make_model("nope") == nullptr && make_integrator("nope") == nullptr, "tc012 unknown name");
  check(make_model(swarm::v1::DYNAMICS_KIND_DOF3)->dof() == 3, "tc012 kind dof3");
  check(make_model(swarm::v1::DYNAMICS_KIND_DOF2)->dof() == 2, "tc012 kind dof2");
  check(make_model(swarm::v1::DYNAMICS_KIND_STATIC) == nullptr, "tc012 kind static");

  auto m = make_model("dof3", {{"max_bank_rad", 0.5}});
  check(static_cast<Dof3Model&>(*m).params().max_bank_rad == 0.5, "tc012 model param override");
  auto i = make_integrator("rk45", {{"rtol", 1e-8}, {"max_substeps", 50}});
  check(static_cast<Rk45Integrator&>(*i).config().rtol == 1e-8, "tc012 integrator param override");
  check(static_cast<Rk45Integrator&>(*i).config().max_substeps == 50, "tc012 max_substeps override");
  bool threw = false;
  try {
    make_model("dof2", {{"bank", 1.0}});
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  check(threw, "tc012 unknown parameter throws");
}

// ---------------------------------------------------------------- TC-DYN-013 바람: 대지 속도·위치 표류 (DEC-023)
void tc013() {
  Environment env;
  env.wind_ned_mps[1] = 10.0;  // 동풍 성분 10 m/s
  const double v = 50.0, T = 60.0;
  for (auto& integ : both_integrators()) {
    Dof2Model m;
    std::vector<double> x = {kLat0, kLon0, 500.0, v, 0.0, 0.0, 0.0};  // 북쪽 수평 비행
    run(*integ, m, x, {v, 0.0, 0.0}, env, T, 0.02);
    double n, e;
    local_ne(x[Dof2Model::kLat], x[Dof2Model::kLon], x[Dof2Model::kAlt], n, e);
    check_near(n, v * T, 0.5, "tc013 dof2 north distance");
    check_near(e, 10.0 * T, 0.5, "tc013 dof2 east drift by wind");
    KinematicSample k;
    m.to_kinematic(x, env, k);
    check_near(k.vel_ned_mps[0], v, 1e-9, "tc013 dof2 ground vn");
    check_near(k.vel_ned_mps[1], 10.0, 1e-9, "tc013 dof2 ground ve = wind");
  }
  {
    Dof3Model m;
    Environment g;
    g.gravity_mps2 = 9.0;
    const std::vector<double> x = {kLat0, kLon0, 800.0, 50.0, 0.0, 0.0, 0.3};
    KinematicSample k;
    m.to_kinematic(x, g, k);
    double yaw, pitch, roll;
    geo::quat_to_euler(k.quat_ned_frd, yaw, pitch, roll);
    check_near(k.rate_frd_rps[2] / std::cos(roll), 9.0 * std::tan(0.3) / 50.0, 1e-9, "tc013 dof3 turn rate uses env gravity");
  }
}

// TC-DYN-014: 매개변수 노출 (DEC-035). 선언 표 ↔ 기본값, get/set, 범위·이름 거부, 모델 동작 반영, 팩토리 이름과 일치
void tc014() {
  for (const char* name : {"dof2", "dof3"}) {
    auto m = make_model(name);
    const auto descs = m->param_descs();
    check(descs.size() >= 7, "tc014 descs not empty");
    bool control = false, airframe = false;
    for (const auto& d : descs) {
      check_near(m->get_param(d.name), d.default_value, 0.0, "tc014 default equals desc");
      check(d.min <= d.default_value && d.default_value <= d.max && d.runtime, "tc014 desc range/runtime");
      control |= d.layer == ParamLayer::kControl;
      airframe |= d.layer == ParamLayer::kAirframe;
    }
    check(control && airframe, "tc014 control and airframe layers");

    check(m->set_param("tau_speed_s", 2.5) && m->get_param("tau_speed_s") == 2.5, "tc014 set ok");
    check(!m->set_param("tau_speed_s", 0.0) && m->get_param("tau_speed_s") == 2.5, "tc014 below min rejected, unchanged");
    check(!m->set_param("tau_speed_s", 1e9) && m->get_param("tau_speed_s") == 2.5, "tc014 above max rejected");
    check(!m->set_param("tau_speed_s", std::nan("")) && m->get_param("tau_speed_s") == 2.5, "tc014 nan rejected");
    check(!m->set_param("no_such_param", 1.0) && m->get_param("no_such_param") == 0.0, "tc014 unknown name");
  }

  // 선언 이름은 팩토리 파라미터 이름과 같다
  for (const auto& d : make_model("dof3")->param_descs()) {
    Params p{{std::string(d.name), d.max}};
    auto m = make_model("dof3", p);
    check_near(m->get_param(d.name), d.max, 0.0, "tc014 factory name matches desc");
  }

  // 동작 반영: 최대 선회율을 줄이면 선회율 명령이 잘리고, 속도 시정수를 키우면 가속이 느려진다
  auto turn_accel = [](double limit) {
    Dof2Model m;
    check(m.set_param("max_heading_rate_rps", limit), "tc014 set limit");
    Environment env;
    std::vector<double> x(Dof2Model::kStateSize, 0.0), u = {30.0, 0.5, 0.0}, k(x.size());
    x[Dof2Model::kSpeed] = 30.0;
    m.derivatives(0.0, x, u, env, k);
    return k[Dof2Model::kHeadingRate] * m.params().tau_heading_rate_s;  // = 잘린 명령
  };
  check_near(turn_accel(1.0), 0.5, 1e-12, "tc014 rate within limit");
  check_near(turn_accel(0.2), 0.2, 1e-12, "tc014 rate clamped by changed limit");

  Dof3Model slow, fast;
  check(slow.set_param("tau_speed_s", 10.0), "tc014 set tau");
  std::vector<double> x(Dof3Model::kStateSize, 0.0), u = {30.0, 0.0, 0.0}, a(x.size()), b(x.size());
  x[Dof3Model::kSpeed] = 20.0;
  Environment env;
  slow.derivatives(0.0, x, u, env, a);
  fast.derivatives(0.0, x, u, env, b);
  check_near(a[Dof3Model::kSpeed], 1.0, 1e-12, "tc014 slow tau accel");
  check_near(b[Dof3Model::kSpeed], 10.0, 1e-12, "tc014 default tau accel");
}

struct Case {
  const char* id;
  void (*fn)();
};

// TC-DYN-015: 원시 격자 + JSON 머리글 DEM 로더 (IMP-DYN-009, DEC-053). 합성 능선, nodata, 경계, 형식 오류
void tc015() {
  namespace fs = std::filesystem;
  const fs::path data = SWARM_DYN_TEST_DATA;
  const RawDemLoader ld(-1.0, 5.0);
  auto g = ld.load(data / "ridge.json");
  check(g->spec().rows == 101 && g->spec().cols == 101, "tc015 dims");
  check_near(g->elevation_m(37.008, 127.0), 1200.0, 1e-6, "tc015 ridge crest");
  check_near(g->elevation_m(37.006, 127.05), 600.0, 1e-6, "tc015 ridge flank node");
  check_near(g->elevation_m(37.007, 127.0), 900.0, 1e-6, "tc015 bilinear between rows");
  check_near(g->elevation_m(36.95, 127.0), 0.0, 0.0, "tc015 flat south");
  check_near(g->elevation_m(36.9, 126.9), 5.0, 1e-9, "tc015 nodata -> fill (south-west node, row 0 = south)");
  check_near(g->elevation_m(36.9, 126.902), 0.0, 1e-9, "tc015 neighbour of nodata");
  check_near(g->elevation_m(36.899, 127.0), -1.0, 0.0, "tc015 outside south -> outside_m");
  check_near(g->elevation_m(37.0, 127.1001), -1.0, 0.0, "tc015 outside east -> outside_m");
  check(g->contains(37.0999, 127.0999) && !g->contains(37.1001, 127.0), "tc015 contains boundary");

  // 형식 오류: 머리글을 바꿔 임시 디렉터리에 쓴다
  const fs::path tmp = fs::temp_directory_path() / "swarm_tc_dyn_015";
  fs::create_directories(tmp);
  fs::copy_file(data / "ridge.bin", tmp / "ridge.bin", fs::copy_options::overwrite_existing);
  std::string base;
  {
    std::ifstream f(data / "ridge.json", std::ios::binary);
    std::ostringstream s;
    s << f.rdbuf();
    base = s.str();
  }
  auto variant = [&](const std::string& from, const std::string& to) {
    std::string t = base;
    const auto p = t.find(from);
    if (p == std::string::npos) {
      std::fprintf(stderr, "FAIL: tc015 fixture lacks '%s'\n", from.c_str());
      ++g_failures;
      return t;
    }
    return t.replace(p, from.size(), to);
  };
  auto expect_throw = [&](const std::string& json, bool runtime, const char* what) {
    {
      std::ofstream f(tmp / "h.json", std::ios::binary | std::ios::trunc);
      f << json;
    }
    bool ok = false;
    try {
      ld.load(tmp / "h.json");
    } catch (const std::invalid_argument&) {
      ok = !runtime;
    } catch (const std::runtime_error&) {
      ok = runtime;
    }
    if (!ok) {
      std::fprintf(stderr, "FAIL: tc015 expected %s: %s\n", runtime ? "runtime_error" : "invalid_argument", what);
      ++g_failures;
    }
  };
  {
    std::ofstream f(tmp / "h.json", std::ios::binary | std::ios::trunc);
    f << base;
  }
  check(ld.load(tmp / "h.json")->spec().rows == 101, "tc015 copied header loads");
  expect_throw("{ not json", false, "bad json");
  expect_throw(variant("\"swarm-dem-grid\"", "\"other\""), false, "format");
  expect_throw(variant("\"version\": 1", "\"version\": 2"), false, "version");
  expect_throw(variant("\"int16\"", "\"float32\""), false, "sample_type");
  expect_throw(variant("\"little\"", "\"big\""), false, "byte_order");
  expect_throw(variant("\"south_to_north\"", "\"north_to_south\""), false, "row_order");
  expect_throw(variant("\"rows\": 101", "\"rows\": 100"), false, "size mismatch");
  expect_throw(variant("\"rows\": 101", "\"rows\": 1"), false, "rows < 2");
  expect_throw(variant("\"rows\": 101", "\"rows\": 100.5"), false, "fractional rows");
  expect_throw(variant("\"rows\": 101,", ""), false, "missing rows");
  expect_throw(variant("\"dlat_deg\": 0.002", "\"dlat_deg\": 0"), false, "zero spacing");
  expect_throw(variant("\"lat0_deg\": 36.9", "\"lat0_deg\": 89.9"), false, "beyond lat 90");
  expect_throw(variant("\"units\": \"m\"", "\"units\": \"ft\""), false, "units");
  expect_throw(variant("\"nodata\": -32768", "\"nodata\": 40000"), false, "nodata range");
  expect_throw(variant("\"ridge.bin\"", "\"missing.bin\""), true, "missing data file");
  bool rt = false;
  try {
    ld.load(tmp / "no_such.json");
  } catch (const std::runtime_error&) {
    rt = true;
  }
  check(rt, "tc015 missing header -> runtime_error");
  fs::remove_all(tmp);

  // int16 격자 생성자 크기 검사
  bool thrown = false;
  try {
    GridTerrain(kInt16Heights, GridSpec{0, 0, 1, 1, 2, 2}, std::vector<std::int16_t>(3));
  } catch (const std::invalid_argument&) {
    thrown = true;
  }
  check(thrown, "tc015 int16 size mismatch");
  check_near(GridTerrain(kInt16Heights, GridSpec{0, 0, 1, 1, 2, 2}, std::vector<std::int16_t>{0, 10, 20, 30})
                 .elevation_m(0.5, 0.5),
             15.0, 1e-12, "tc015 int16 bilinear");
}

const Case kCases[] = {
    {"TC-DYN-001", tc001}, {"TC-DYN-002", tc002}, {"TC-DYN-003", tc003}, {"TC-DYN-004", tc004},
    {"TC-DYN-005", tc005}, {"TC-DYN-006", tc006}, {"TC-DYN-007", tc007}, {"TC-DYN-008", tc008},
    {"TC-DYN-009", tc009}, {"TC-DYN-010", tc010}, {"TC-DYN-011", tc011}, {"TC-DYN-012", tc012}, {"TC-DYN-013", tc013},
    {"TC-DYN-014", tc014}, {"TC-DYN-015", tc015},
};

}  // namespace

int main(int argc, char** argv) {
  int ran = 0;
  for (const auto& c : kCases) {
    if (argc > 1 && std::strcmp(argv[1], c.id) != 0) continue;
    c.fn();
    ++ran;
  }
  if (ran == 0) {
    std::fprintf(stderr, "unknown test id\n");
    return EXIT_FAILURE;
  }
  if (g_failures == 0) std::puts("swarm_dynamics_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
