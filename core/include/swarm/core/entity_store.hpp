// IMP-CORE-003: 엔티티 저장소 (SoA). 상태·입력 벡터는 연속 버퍼에 둔다 (DEC-006, REQ-PRF-001)
// IMP-CORE-013: 동역학 매개변수 (DEC-035). 기본값 → airframe 표 → EntitySpec.dynamics_params → SetParams
#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include "swarm/core/dynamics_provider.hpp"
#include "swarm/v1/entity.pb.h"
#include "swarm/v1/sim.pb.h"

namespace swarm::core {

class EntityStore {
 public:
  // 사양 목록으로 저장소를 만든다. ID 형식 오류·중복·지원하지 않는 동역학이면 예외
  void build(const std::vector<v1::EntitySpec>& specs, const DynamicsProvider& provider);
  // 초기 상태로 되돌린다
  void reset();

  std::size_t size() const { return id_.size(); }
  std::optional<std::size_t> find(const std::string& id) const;

  const std::string& id(std::size_t i) const { return id_[i]; }
  v1::EntityKind kind(std::size_t i) const { return kind_[i]; }
  v1::Side side(std::size_t i) const { return side_[i]; }
  bool alive(std::size_t i) const { return alive_[i] != 0; }
  void set_alive(std::size_t i, bool a) { alive_[i] = a ? 1 : 0; }
  double energy(std::size_t i) const { return energy_[i]; }
  bool has_onboard(std::size_t i) const { return onboard_[i] != 0; }
  // 모델이 없으면(STATIC 등) nullptr. 위치는 초기 상태에 고정된다
  const dyn::DynamicsModel* model(std::size_t i) const { return model_[i].get(); }

  std::span<double> x(std::size_t i) { return {x_.data() + x_off_[i], x_len_[i]}; }
  std::span<const double> x(std::size_t i) const { return {x_.data() + x_off_[i], x_len_[i]}; }
  std::span<double> u(std::size_t i) { return {u_.data() + u_off_[i], u_len_[i]}; }
  std::span<const double> u(std::size_t i) const { return {u_.data() + u_off_[i], u_len_[i]}; }

  // 동역학 매개변수 (DEC-035). 모델이 선언한 매개변수가 없으면 has_params가 false
  bool has_params(std::size_t i) const { return model_[i] && !model_[i]->param_descs().empty(); }
  // values의 이름을 모델에 적용하고 거부한 항목을 돌려준다(이름순). runtime_only면 runtime=false 항목은 not_runtime으로 거부한다.
  // 거부 목록은 rejected(i)가 되고, 적용한 항목은 바로 모델에 반영된다
  const std::vector<v1::ParamRejection>& apply_params(std::size_t i, const google::protobuf::Struct& values,
                                                      bool runtime_only);
  const std::vector<v1::ParamRejection>& rejected(std::size_t i) const { return rejected_[i]; }
  // 선언(specs), 적용 중인 값 전체(values), 직전 거부(rejected)를 채운다. sim_time_us는 호출자가 채운다
  void fill_params(std::size_t i, v1::EntityParams& out) const;

  // 현재 상태를 KinematicState(proto)로 꺼낸다
  void kinematics(std::size_t i, v1::KinematicState& out) const;
  void fill_state(std::size_t i, v1::EntityState& out) const;

 private:
  std::vector<std::string> id_;
  std::vector<v1::EntityKind> kind_;
  std::vector<v1::Side> side_;
  std::vector<std::uint8_t> alive_;
  std::vector<std::uint8_t> onboard_;  // 기체 런타임이 붙는 엔티티: NavigationReport 발행 대상
  std::vector<double> energy_;
  std::vector<std::unique_ptr<dyn::DynamicsModel>> model_;
  dyn::Environment env_{};  // to_kinematic의 바람·중력 (DEC-023)
  std::vector<v1::KinematicState> fixed_;  // 모델이 없는 엔티티의 고정 상태
  std::vector<std::size_t> x_off_, x_len_, u_off_, u_len_;
  std::vector<double> x_, u_, x0_, u0_;
  std::vector<std::vector<double>> param0_;            // 적재 시점(시나리오 적용 후) 매개변수 값. Reset이 되돌린다
  std::vector<std::vector<v1::ParamRejection>> rejected_, rejected0_;
  std::unordered_map<std::string, std::size_t> index_;
};

}  // namespace swarm::core
