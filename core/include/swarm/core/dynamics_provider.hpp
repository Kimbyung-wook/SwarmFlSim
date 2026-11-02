// Core가 쓰는 동역학 공급자. 모델·적분기는 dynamics.hpp 인터페이스로만 받는다 (DEC-006, IMP-API-006)
// 실행 파일은 WP2 공급자(wp2_dynamics.hpp), 시험은 목 공급자(mock_dynamics.hpp)도 쓴다.
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
  // IMP-CORE-009: 지면 교차 이벤트. 비우면 이벤트 없이 적분한다. model은 반환된 함수보다 오래 산다
  std::function<dyn::EventFn(const dyn::DynamicsModel&)> make_ground_event;
  // IMP-CORE-011: 엔진 고장(추력 0) 중 입력. 속도 명령을 모델의 최소값으로 바꾼다. 비우면 ENGINE 고장을 처리하지 않는다
  std::function<void(const dyn::DynamicsModel&, std::span<double> u)> engine_out;
  // env.terrain이 가리키는 지형. 공급자를 복사해도 같은 객체를 가리킨다
  std::shared_ptr<const dyn::Terrain> terrain;
  dyn::Environment env{};
};

}  // namespace swarm::core
