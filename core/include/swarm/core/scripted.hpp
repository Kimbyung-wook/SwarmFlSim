// IMP-CORE-010: DYNAMICS_KIND_SCRIPTED 경로 추종 (DEC-017)
//
// 초기 위치에서 출발해 EntitySpec.script_path의 점을 차례로 일정 속도(초기 속도 크기)로 지난다.
// - 구간은 시작점 국소 NED 직선이며, 위경도·고도를 구간 길이 비율로 선형 보간한다
// - 마지막 점에 닿으면 그 자리에 멈춘다(속도 0)
// - 상태 x = [s] (경로를 따라 간 거리, m). ds/dt = 속도. 제어 입력은 받지 않는다(map_control = false)
// - 스크립트 이동은 대지 기준이므로 바람을 더하지 않는다
#pragma once

#include <memory>
#include <vector>

#include "swarm/api/dynamics.hpp"
#include "swarm/v1/entity.pb.h"

namespace swarm::core {

class ScriptedPathModel final : public dyn::DynamicsModel {
 public:
  struct Point {
    double lat_deg, lon_deg, alt_m;
  };

  ScriptedPathModel(std::vector<Point> points, double speed_mps);

  std::string_view name() const override { return "scripted"; }
  int dof() const override { return 0; }
  std::size_t state_size() const override { return 1; }
  std::size_t input_size() const override { return 0; }
  void derivatives(double t, std::span<const double> x, std::span<const double> u, const dyn::Environment& env,
                   std::span<double> dxdt) const override;
  bool map_control(const v1::ControlOutput& cmd, std::span<double> u) const override;
  void to_kinematic(std::span<const double> x, const dyn::Environment& env, dyn::KinematicSample& out) const override;
  void from_kinematic(const dyn::KinematicSample& in, std::span<double> x) const override;

  double length_m() const { return cum_.back(); }
  double speed_mps() const { return speed_; }

 private:
  std::vector<Point> pts_;
  std::vector<double> cum_;          // 점 i까지의 누적 거리
  std::vector<double> dir_ned_;      // 구간 i의 단위 방향 (n, e, d) × 구간 수
  double speed_;
};

// script_path가 비면 nullptr(초기 위치 고정)
std::unique_ptr<dyn::DynamicsModel> make_scripted_model(const v1::EntitySpec& spec);

}  // namespace swarm::core
