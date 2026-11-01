// IMP-CORE-008: WP2 동역학(swarm_dynamics 팩토리) 공급자 (DEC-005, DEC-006, REQ-DYN-001, REQ-DYN-004)
// IMP-CORE-009: 지형과 지면 교차 이벤트 (DEC-004, DEC-016, REQ-SIM-003)
//
// - DynamicsKind → dyn::make_model. airframe은 모델 파라미터(공개 일반값 표)로 바꾼다. 표에 없으면 기본값
// - 적분기는 dyn::make_integrator(integrator). 기본 rk45
// - 지형은 평지(terrain_flat_m). terrain을 주면 그것을 쓴다(DEM 로더 연결 자리, DEC-016)
#pragma once

#include <memory>
#include <string>

#include "swarm/core/dynamics_provider.hpp"
#include "swarm/dyn/factory.hpp"

namespace swarm::core {

struct Wp2DynamicsOptions {
  std::string integrator = "rk45";  // rk4 | rk45
  dyn::Params integrator_params;
  double terrain_flat_m = 0.0;
  std::shared_ptr<const dyn::Terrain> terrain;  // 주면 terrain_flat_m 대신 쓴다
  bool ground_event = true;
};

// airframe 이름 → 모델 파라미터. 모르는 이름이면 빈 표(기본값)
dyn::Params airframe_params(v1::DynamicsKind kind, const std::string& airframe);

// 모르는 적분기 이름이면 std::invalid_argument
DynamicsProvider wp2_provider(const Wp2DynamicsOptions& opt = {});

}  // namespace swarm::core
