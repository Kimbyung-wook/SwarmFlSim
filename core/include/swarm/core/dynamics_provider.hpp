// Core가 쓰는 동역학 공급자. 모델·적분기는 dynamics.hpp 인터페이스로만 받는다 (DEC-006, IMP-API-006)
// WP2 통합 전에는 mock_dynamics.hpp의 목 구현을 쓴다.
#pragma once

#include <functional>
#include <map>
#include <memory>
#include <string>

#include "swarm/api/dynamics.hpp"
#include "swarm/v1/entity.pb.h"

namespace swarm::core {

struct DynamicsProvider {
  // 엔티티 사양(DynamicsKind, airframe)으로 모델을 만든다. 지원하지 않으면 nullptr
  std::function<std::unique_ptr<dyn::DynamicsModel>(const v1::EntitySpec&)> make_model;
  std::function<std::unique_ptr<dyn::Integrator>()> make_integrator;
  // ControlOutput을 받기 전의 입력 u. 비우면 0으로 둔다
  std::function<void(const dyn::DynamicsModel&, std::span<const double> x, std::span<double> u)> init_input;
  dyn::Environment env{};
};

}  // namespace swarm::core
