// IMP-DYN-006: 동역학 모델·적분기 팩토리 (REQ-DYN-001, REQ-DYN-004)
//
// 모델: "dof2", "dof3". "dof5", "dof6"(Aerosonde)는 자리만 있고 nullptr를 돌려준다.
// 적분기: "rk4", "rk45".
// 파라미터 이름은 각 Params/Config 필드 이름과 같다. 모르는 이름이면 std::invalid_argument.
#pragma once

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/api/dynamics.hpp"
#include "swarm/v1/entity.pb.h"

namespace swarm::dyn {

using Params = std::map<std::string, double, std::less<>>;

std::unique_ptr<DynamicsModel> make_model(std::string_view name, const Params& params = {});
std::unique_ptr<DynamicsModel> make_model(swarm::v1::DynamicsKind kind, const Params& params = {});
std::unique_ptr<Integrator> make_integrator(std::string_view name, const Params& params = {});

// DynamicsKind → 모델 이름. 동역학 모델이 없는 종류(SCRIPTED, STATIC, UNSPECIFIED)는 빈 문자열
std::string_view model_name(swarm::v1::DynamicsKind kind);

std::vector<std::string> model_names();       // 구현된 모델
std::vector<std::string> reserved_model_names();  // 자리만 있는 모델
std::vector<std::string> integrator_names();

}  // namespace swarm::dyn
