// IMP-DYN-001, IMP-DYN-002: 2-DoF 유니사이클, 3-DoF 질점 협조선회 (REQ-DYN-001, REQ-DYN-002, PRP-DYN-001)
//
// 공통
// - 위치 상태는 위도·경도(rad), 고도(m, MSL). to_kinematic이 deg로 바꾼다.
// - 속도 상태는 대기 속도다. 위치 변화와 to_kinematic 출력은 대기 속도 + 바람(대지 속도)이다 (DEC-023).
// - 자세 쿼터니언은 속도 방향(ψ, 비행경로각 γ)과 뱅크각 φ로 만든다. 받음각·옆미끄럼각은 0으로 본다.
// - 명령 추종은 1차 지연이다. 시정수는 RK4 프레임 스텝보다 충분히 커야 한다(τ > dt/2 권장).
#pragma once

#include <span>
#include <string_view>

#include "swarm/api/dynamics.hpp"
#include "swarm/dyn/integrators.hpp"

namespace swarm::dyn {

// 2-DoF: 수평 유니사이클 + 고도 1차 지연. 입력 KinematicCmd(speed, heading_rate, climb_rate)
class Dof2Model final : public DynamicsModel, public ErrorScaleProvider {
 public:
  enum State : std::size_t { kLat, kLon, kAlt, kSpeed, kHeading, kHeadingRate, kClimbRate, kStateSize };
  enum Input : std::size_t { kSpeedCmd, kHeadingRateCmd, kClimbRateCmd, kInputSize };

  struct Params {
    double tau_speed_s = 1.0;
    double tau_heading_rate_s = 0.2;
    double tau_climb_s = 0.5;
    double min_speed_mps = 0.0;
    double max_speed_mps = 400.0;
    double max_heading_rate_rps = 1.0;
    double max_climb_rate_mps = 50.0;
  };

  explicit Dof2Model(Params p = {}) : p_(p) {}
  std::string_view name() const override { return "dof2"; }
  int dof() const override { return 2; }
  std::size_t state_size() const override { return kStateSize; }
  std::size_t input_size() const override { return kInputSize; }
  void derivatives(double t, std::span<const double> x, std::span<const double> u, const Environment& env,
                   std::span<double> dxdt) const override;
  bool map_control(const swarm::v1::ControlOutput& cmd, std::span<double> u) const override;
  void to_kinematic(std::span<const double> x, const Environment& env, KinematicSample& out) const override;
  void from_kinematic(const KinematicSample& in, std::span<double> x) const override;
  void error_scale(std::span<double> abs_scale, std::span<double> rel_scale) const override;
  const Params& params() const { return p_; }

 private:
  Params p_;
};

// 3-DoF 질점 협조선회. 입력 KinematicCmd(speed, bank, climb_rate)
//   V̇ = (V_c − V)/τ_V,  φ̇ = (φ_c − φ)/τ_φ,  γ̇ = (asin(ḣ_c/V) − γ)/τ_γ
//   ψ̇ = g·tanφ / (V·cosγ)  → 정상 선회 반경 R = (V·cosγ)² / (g·tanφ)
class Dof3Model final : public DynamicsModel, public ErrorScaleProvider {
 public:
  enum State : std::size_t { kLat, kLon, kAlt, kSpeed, kHeading, kGamma, kBank, kStateSize };
  enum Input : std::size_t { kSpeedCmd, kBankCmd, kClimbRateCmd, kInputSize };

  struct Params {
    double tau_speed_s = 1.0;
    double tau_bank_s = 0.3;
    double tau_gamma_s = 0.5;
    double min_speed_mps = 1.0;  // 선회율·비행경로각 계산의 분모 하한
    double max_speed_mps = 400.0;
    double max_bank_rad = 1.0471975511965976;  // 60°
    double max_climb_rate_mps = 50.0;
    double max_gamma_rad = 0.5235987755982988;  // 30°
  };

  explicit Dof3Model(Params p = {}) : p_(p) {}
  std::string_view name() const override { return "dof3"; }
  int dof() const override { return 3; }
  std::size_t state_size() const override { return kStateSize; }
  std::size_t input_size() const override { return kInputSize; }
  void derivatives(double t, std::span<const double> x, std::span<const double> u, const Environment& env,
                   std::span<double> dxdt) const override;
  bool map_control(const swarm::v1::ControlOutput& cmd, std::span<double> u) const override;
  void to_kinematic(std::span<const double> x, const Environment& env, KinematicSample& out) const override;
  void from_kinematic(const KinematicSample& in, std::span<double> x) const override;
  void error_scale(std::span<double> abs_scale, std::span<double> rel_scale) const override;
  const Params& params() const { return p_; }

 private:
  Params p_;
};

}  // namespace swarm::dyn
