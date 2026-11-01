// IMP-DYN-006 (REQ-DYN-001, REQ-DYN-004)
#include "swarm/dyn/factory.hpp"

#include <stdexcept>
#include <utility>

#include "swarm/dyn/integrators.hpp"
#include "swarm/dyn/models.hpp"

namespace swarm::dyn {
namespace {

// 파라미터 이름 → 필드 포인터 표로 Params를 덮어쓴다
template <class T>
using FieldTable = std::vector<std::pair<std::string_view, double T::*>>;

template <class T>
T apply(T value, const FieldTable<T>& fields, const Params& params, std::string_view owner) {
  for (const auto& [key, v] : params) {
    bool known = false;
    for (const auto& [name, member] : fields) {
      if (name == key) {
        value.*member = v;
        known = true;
        break;
      }
    }
    if (!known) throw std::invalid_argument(std::string(owner) + ": unknown parameter '" + key + "'");
  }
  return value;
}

const FieldTable<Dof2Model::Params> kDof2Fields = {
    {"tau_speed_s", &Dof2Model::Params::tau_speed_s},
    {"tau_heading_rate_s", &Dof2Model::Params::tau_heading_rate_s},
    {"tau_climb_s", &Dof2Model::Params::tau_climb_s},
    {"min_speed_mps", &Dof2Model::Params::min_speed_mps},
    {"max_speed_mps", &Dof2Model::Params::max_speed_mps},
    {"max_heading_rate_rps", &Dof2Model::Params::max_heading_rate_rps},
    {"max_climb_rate_mps", &Dof2Model::Params::max_climb_rate_mps},
};

const FieldTable<Dof3Model::Params> kDof3Fields = {
    {"tau_speed_s", &Dof3Model::Params::tau_speed_s},
    {"tau_bank_s", &Dof3Model::Params::tau_bank_s},
    {"tau_gamma_s", &Dof3Model::Params::tau_gamma_s},
    {"min_speed_mps", &Dof3Model::Params::min_speed_mps},
    {"max_speed_mps", &Dof3Model::Params::max_speed_mps},
    {"max_bank_rad", &Dof3Model::Params::max_bank_rad},
    {"max_climb_rate_mps", &Dof3Model::Params::max_climb_rate_mps},
    {"max_gamma_rad", &Dof3Model::Params::max_gamma_rad},
};

const FieldTable<Rk4Integrator::Config> kRk4Fields = {
    {"max_step_s", &Rk4Integrator::Config::max_step_s},
    {"event_time_tol_s", &Rk4Integrator::Config::event_time_tol_s},
};

const FieldTable<Rk45Integrator::Config> kRk45Fields = {
    {"rtol", &Rk45Integrator::Config::rtol},
    {"atol", &Rk45Integrator::Config::atol},
    {"min_step_s", &Rk45Integrator::Config::min_step_s},
    {"max_step_s", &Rk45Integrator::Config::max_step_s},
    {"event_time_tol_s", &Rk45Integrator::Config::event_time_tol_s},
};

}  // namespace

std::unique_ptr<DynamicsModel> make_model(std::string_view name, const Params& params) {
  if (name == "dof2") return std::make_unique<Dof2Model>(apply(Dof2Model::Params{}, kDof2Fields, params, name));
  if (name == "dof3") return std::make_unique<Dof3Model>(apply(Dof3Model::Params{}, kDof3Fields, params, name));
  return nullptr;  // dof5, dof6: 이번 범위 밖
}

std::unique_ptr<DynamicsModel> make_model(swarm::v1::DynamicsKind kind, const Params& params) {
  const auto name = model_name(kind);
  return name.empty() ? nullptr : make_model(name, params);
}

std::unique_ptr<Integrator> make_integrator(std::string_view name, const Params& params) {
  if (name == "rk4") return std::make_unique<Rk4Integrator>(apply(Rk4Integrator::Config{}, kRk4Fields, params, name));
  if (name == "rk45") {
    Params rest = params;
    Rk45Integrator::Config cfg;
    if (auto it = rest.find("max_substeps"); it != rest.end()) {
      cfg.max_substeps = static_cast<int>(it->second);
      rest.erase(it);
    }
    return std::make_unique<Rk45Integrator>(apply(cfg, kRk45Fields, rest, name));
  }
  return nullptr;
}

std::string_view model_name(swarm::v1::DynamicsKind kind) {
  switch (kind) {
    case swarm::v1::DYNAMICS_KIND_DOF2: return "dof2";
    case swarm::v1::DYNAMICS_KIND_DOF3: return "dof3";
    case swarm::v1::DYNAMICS_KIND_DOF5: return "dof5";
    case swarm::v1::DYNAMICS_KIND_DOF6: return "dof6";
    default: return {};
  }
}

std::vector<std::string> model_names() { return {"dof2", "dof3"}; }
std::vector<std::string> reserved_model_names() { return {"dof5", "dof6"}; }
std::vector<std::string> integrator_names() { return {"rk4", "rk45"}; }

}  // namespace swarm::dyn
