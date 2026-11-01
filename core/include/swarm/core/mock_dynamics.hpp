// IMP-CORE-005: Core 시험용 등속 2-DoF 목 모델과 RK4 목 적분기 (DEC-006)
// WP2 동역학의 대체물이 아니다. 구면 지구(R=6371 km)로 위경도를 적분한다.
#pragma once

#include "swarm/core/dynamics_provider.hpp"

namespace swarm::core::mock {

inline constexpr double kEarthRadiusM = 6371000.0;

// x = [lat_deg, lon_deg, alt_m, speed_mps, heading_rad, climb_mps]
// u = [speed_mps, heading_rate_rps, climb_rate_mps]
// 속도·상승률은 명령값을 1차 지연(kTauS)으로 따르고, 방위각은 heading_rate로 적분한다.
// 명령이 없으면 hold_input으로 현재 값을 유지한다(등속).
class ConstantVelocity2Dof final : public dyn::DynamicsModel {
 public:
  static constexpr double kTauS = 0.5;

  std::string_view name() const override { return "mock_cv2dof"; }
  int dof() const override { return 2; }
  std::size_t state_size() const override { return 6; }
  std::size_t input_size() const override { return 3; }

  void derivatives(double t, std::span<const double> x, std::span<const double> u, const dyn::Environment& env,
                   std::span<double> dxdt) const override;
  bool map_control(const v1::ControlOutput& cmd, std::span<double> u) const override;
  void to_kinematic(std::span<const double> x, dyn::KinematicSample& out) const override;
  void from_kinematic(const dyn::KinematicSample& in, std::span<double> x) const override;

  // 초기 상태에서 입력을 정한다: 현재 속도·상승률 유지, 선회 없음
  static void hold_input(std::span<const double> x, std::span<double> u);
};

class Rk4 final : public dyn::Integrator {
 public:
  explicit Rk4(int substeps = 1) : substeps_(substeps) {}
  std::string_view name() const override { return "mock_rk4"; }
  dyn::StepResult step(const dyn::DynamicsModel& model, double t0, double dt, std::span<double> x,
                       std::span<const double> u, const dyn::Environment& env,
                       const dyn::EventFn* event = nullptr) override;

 private:
  int substeps_;
};

// DOF2, DOF3를 목 모델로 만든다. 그 밖의 DynamicsKind는 nullptr
DynamicsProvider provider();

}  // namespace swarm::core::mock
