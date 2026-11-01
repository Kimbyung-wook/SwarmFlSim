// IMP-DYN-003, IMP-DYN-004: RK4 고정 스텝, RK45(Dormand-Prince) 프레임 안 가변 스텝, 이벤트 이분 탐색
// REQ-DYN-003, REQ-DYN-004, DEC-005
#pragma once

#include <cstddef>
#include <span>
#include <string_view>
#include <vector>

#include "swarm/api/dynamics.hpp"

namespace swarm::dyn {

// 상태 성분별 오차 허용치 가중. 모델이 선택적으로 구현한다 (dynamics/ 내부 확장).
// 성분 i의 허용치 = atol * abs_scale[i] + rtol * rel_scale[i] * max(|x0_i|, |x1_i|).
// 구현하지 않은 모델은 abs_scale = rel_scale = 1.
class ErrorScaleProvider {
 public:
  virtual ~ErrorScaleProvider() = default;
  virtual void error_scale(std::span<double> abs_scale, std::span<double> rel_scale) const = 0;
};

// 영점 교차 판정. g0 = 0에서 시작하면 교차로 보지 않는다
inline bool crossed(double g0, double g1) { return (g0 > 0.0 && g1 <= 0.0) || (g0 < 0.0 && g1 >= 0.0); }

// 인스턴스는 작업 버퍼를 가진다. 한 인스턴스를 여러 스레드에서 동시에 쓰지 않는다.
class Rk4Integrator final : public Integrator {
 public:
  struct Config {
    double max_step_s = 0.0;         // 0이면 프레임당 한 스텝
    double event_time_tol_s = 1e-6;  // 이벤트 시점 이분 탐색 허용치
  };

  explicit Rk4Integrator(Config cfg = {}) : cfg_(cfg) {}
  std::string_view name() const override { return "rk4"; }
  StepResult step(const DynamicsModel& model, double t0, double dt, std::span<double> x,
                  std::span<const double> u, const Environment& env, const EventFn* event = nullptr) override;
  const Config& config() const { return cfg_; }

 private:
  void single(const DynamicsModel& model, double t, double h, std::span<const double> x0, std::span<double> x1,
              std::span<const double> u, const Environment& env);

  Config cfg_;
  std::vector<double> k1_, k2_, k3_, k4_, tmp_, xn_, xb_;
};

// StepResult::max_error는 허용치로 나눈 추정 오차(무차원)의 최댓값이다. 1 이하이면 허용치 안이다.
class Rk45Integrator final : public Integrator {
 public:
  struct Config {
    double rtol = 1e-6;
    double atol = 1e-6;
    double min_step_s = 1e-6;   // 이보다 작아지면 오차와 관계없이 받아들인다
    double max_step_s = 0.0;    // 0이면 프레임 길이
    double event_time_tol_s = 1e-6;
    int max_substeps = 10000;   // 시도(거부 포함) 상한. 넘으면 std::runtime_error
  };

  explicit Rk45Integrator(Config cfg = {}) : cfg_(cfg) {}
  std::string_view name() const override { return "rk45"; }
  StepResult step(const DynamicsModel& model, double t0, double dt, std::span<double> x,
                  std::span<const double> u, const Environment& env, const EventFn* event = nullptr) override;
  const Config& config() const { return cfg_; }

 private:
  // 5차 해를 x1에 쓰고 오차 노름을 돌려준다 (want_error=false면 0)
  double attempt(const DynamicsModel& model, double t, double h, std::span<const double> x0, std::span<double> x1,
                 std::span<const double> u, const Environment& env, bool want_error);

  Config cfg_;
  std::vector<double> k_[7], tmp_, xn_, xb_, abs_scale_, rel_scale_;
};

}  // namespace swarm::dyn
