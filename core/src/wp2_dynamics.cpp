// IMP-CORE-008, IMP-CORE-009: WP2 동역학 공급자
#include "swarm/core/wp2_dynamics.hpp"

#include <cmath>
#include <stdexcept>

#include "swarm/dyn/models.hpp"
#include "swarm/dyn/terrain.hpp"

namespace swarm::core {

namespace {

struct AirframeRow {
  const char* name;
  double min_speed_mps, max_speed_mps, max_bank_deg;
};

// 공개 일반값(제원 공개 자료 수준). 소형 고정익 UAV
constexpr AirframeRow kAirframes[] = {
    {"skywalker_x8", 12.0, 28.0, 45.0},
    {"aerosonde", 18.0, 32.0, 45.0},
};

}  // namespace

dyn::Params airframe_params(v1::DynamicsKind kind, const std::string& airframe) {
  dyn::Params p;
  for (const auto& row : kAirframes) {
    if (airframe != row.name) continue;
    p["min_speed_mps"] = row.min_speed_mps;
    p["max_speed_mps"] = row.max_speed_mps;
    if (kind == v1::DYNAMICS_KIND_DOF3) p["max_bank_rad"] = row.max_bank_deg * std::acos(-1.0) / 180.0;
  }
  return p;
}

DynamicsProvider wp2_provider(const Wp2DynamicsOptions& opt) {
  if (!dyn::make_integrator(opt.integrator, opt.integrator_params))
    throw std::invalid_argument("unknown integrator: " + opt.integrator);

  DynamicsProvider p;
  p.known_airframe = [](const std::string& name) {
    if (name == "generic") return true;  // 표 없이 기본값을 쓰는 내장 시나리오용 이름
    for (const auto& row : kAirframes)
      if (name == row.name) return true;
    return false;
  };
  p.make_model = [](const v1::EntitySpec& spec) {
    return dyn::make_model(spec.dynamics(), airframe_params(spec.dynamics(), spec.airframe()));
  };
  p.make_integrator = [name = opt.integrator, params = opt.integrator_params] {
    return dyn::make_integrator(name, params);
  };
  // 명령을 받기 전에는 현재 속도·상승률을 유지하고 선회하지 않는다
  p.init_input = [](const dyn::DynamicsModel& m, std::span<const double> x, std::span<double> u) {
    if (dynamic_cast<const dyn::Dof2Model*>(&m)) {
      u[dyn::Dof2Model::kSpeedCmd] = x[dyn::Dof2Model::kSpeed];
      u[dyn::Dof2Model::kHeadingRateCmd] = 0.0;
      u[dyn::Dof2Model::kClimbRateCmd] = x[dyn::Dof2Model::kClimbRate];
    } else if (dynamic_cast<const dyn::Dof3Model*>(&m)) {
      u[dyn::Dof3Model::kSpeedCmd] = x[dyn::Dof3Model::kSpeed];
      u[dyn::Dof3Model::kBankCmd] = 0.0;
      u[dyn::Dof3Model::kClimbRateCmd] = x[dyn::Dof3Model::kSpeed] * std::sin(x[dyn::Dof3Model::kGamma]);
    }
  };
  p.engine_out = [](const dyn::DynamicsModel& m, std::span<double> u) {
    if (const auto* d2 = dynamic_cast<const dyn::Dof2Model*>(&m))
      u[dyn::Dof2Model::kSpeedCmd] = d2->params().min_speed_mps;
    else if (const auto* d3 = dynamic_cast<const dyn::Dof3Model*>(&m))
      u[dyn::Dof3Model::kSpeedCmd] = d3->params().min_speed_mps;
  };

  p.terrain = opt.terrain ? opt.terrain : std::make_shared<dyn::FlatTerrain>(opt.terrain_flat_m);
  p.env.terrain = p.terrain.get();
  if (opt.ground_event) {
    p.make_ground_event = [terrain = p.terrain](const dyn::DynamicsModel& m) {
      // 반환 함수가 지형을 붙잡아 둔다
      auto g = dyn::make_ground_event(m, *terrain);
      return dyn::EventFn([g = std::move(g), terrain](double t, std::span<const double> x) { return g(t, x); });
    };
  }
  return p;
}

}  // namespace swarm::core
