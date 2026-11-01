// Core(WP1) ⇄ 동역학(WP2) 계약. REQ-DYN-001~004, DEC-005
#pragma once

#include <cstddef>
#include <functional>
#include <span>
#include <string_view>

namespace swarm::v1 {
class ControlOutput;
}

namespace swarm::dyn {

// DEM 조회 (DEC-004, DEC-016). WGS84, 고도는 MSL
class Terrain {
 public:
  virtual ~Terrain() = default;
  virtual double elevation_m(double lat_deg, double lon_deg) const = 0;
};

struct Environment {
  double gravity_mps2 = 9.80665;
  double air_density_kgpm3 = 1.225;
  double wind_ned_mps[3] = {0.0, 0.0, 0.0};
  const Terrain* terrain = nullptr;
};

// 동역학 상태를 공통 형식으로 꺼낸 값. KinematicState(proto)로 옮겨 발행한다
struct KinematicSample {
  double lat_deg = 0.0, lon_deg = 0.0, alt_m = 0.0;
  double vel_ned_mps[3] = {0.0, 0.0, 0.0};
  double quat_ned_frd[4] = {1.0, 0.0, 0.0, 0.0};  // w, x, y, z
  double rate_frd_rps[3] = {0.0, 0.0, 0.0};
};

class DynamicsModel {
 public:
  virtual ~DynamicsModel() = default;
  virtual std::string_view name() const = 0;
  virtual int dof() const = 0;  // 2, 3, 5, 6
  virtual std::size_t state_size() const = 0;
  virtual std::size_t input_size() const = 0;

  // dx/dt = f(t, x, u, env)
  virtual void derivatives(double t, std::span<const double> x, std::span<const double> u,
                           const Environment& env, std::span<double> dxdt) const = 0;

  // ControlOutput의 oneof 중 이 모델이 받는 형식을 u로 바꾼다. 받지 않는 형식이면 false
  virtual bool map_control(const swarm::v1::ControlOutput& cmd, std::span<double> u) const = 0;

  virtual void to_kinematic(std::span<const double> x, KinematicSample& out) const = 0;
  virtual void from_kinematic(const KinematicSample& in, std::span<double> x) const = 0;
};

// 영점 교차 이벤트 함수. 예: 고도 - DEM 고도 (탄착, 지면 충돌)
using EventFn = std::function<double(double t, std::span<const double> x)>;

struct StepResult {
  double t_end = 0.0;       // 이벤트가 없으면 t0 + dt
  int substeps = 0;
  double max_error = 0.0;   // 가변 스텝 적분기의 추정 오차
  bool event = false;       // 이벤트가 나면 x는 이벤트 시점 상태
};

// 프레임 한 칸(dt)을 적분한다. RK4는 고정 스텝, RK45는 프레임 안 가변 스텝 (DEC-005)
class Integrator {
 public:
  virtual ~Integrator() = default;
  virtual std::string_view name() const = 0;
  virtual StepResult step(const DynamicsModel& model, double t0, double dt, std::span<double> x,
                          std::span<const double> u, const Environment& env,
                          const EventFn* event = nullptr) = 0;
};

}  // namespace swarm::dyn
