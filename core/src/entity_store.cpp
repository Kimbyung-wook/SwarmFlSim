// IMP-CORE-003: 엔티티 저장소
#include "swarm/core/entity_store.hpp"

#include <map>
#include <stdexcept>

#include "swarm/api/keys.hpp"
#include "swarm/core/scripted.hpp"

namespace swarm::core {

namespace {

dyn::KinematicSample to_sample(const v1::KinematicState& k) {
  dyn::KinematicSample s;
  s.lat_deg = k.position().lat_deg();
  s.lon_deg = k.position().lon_deg();
  s.alt_m = k.position().alt_m();
  s.vel_ned_mps[0] = k.velocity_ned_mps().x();
  s.vel_ned_mps[1] = k.velocity_ned_mps().y();
  s.vel_ned_mps[2] = k.velocity_ned_mps().z();
  if (k.has_attitude()) {
    s.quat_ned_frd[0] = k.attitude().w();
    s.quat_ned_frd[1] = k.attitude().x();
    s.quat_ned_frd[2] = k.attitude().y();
    s.quat_ned_frd[3] = k.attitude().z();
  }
  s.rate_frd_rps[0] = k.angular_rate_frd_rps().x();
  s.rate_frd_rps[1] = k.angular_rate_frd_rps().y();
  s.rate_frd_rps[2] = k.angular_rate_frd_rps().z();
  return s;
}

void from_sample(const dyn::KinematicSample& s, v1::KinematicState& k) {
  auto* p = k.mutable_position();
  p->set_lat_deg(s.lat_deg);
  p->set_lon_deg(s.lon_deg);
  p->set_alt_m(s.alt_m);
  auto* v = k.mutable_velocity_ned_mps();
  v->set_x(s.vel_ned_mps[0]);
  v->set_y(s.vel_ned_mps[1]);
  v->set_z(s.vel_ned_mps[2]);
  auto* q = k.mutable_attitude();
  q->set_w(s.quat_ned_frd[0]);
  q->set_x(s.quat_ned_frd[1]);
  q->set_y(s.quat_ned_frd[2]);
  q->set_z(s.quat_ned_frd[3]);
  auto* r = k.mutable_angular_rate_frd_rps();
  r->set_x(s.rate_frd_rps[0]);
  r->set_y(s.rate_frd_rps[1]);
  r->set_z(s.rate_frd_rps[2]);
}

bool needs_onboard(const v1::EntitySpec& s) {
  return s.kind() == v1::ENTITY_KIND_UAV || s.kind() == v1::ENTITY_KIND_FPV || !s.autonomy().ma_plugin().empty() ||
         !s.autonomy().fa_plugin().empty();
}

}  // namespace

void EntityStore::build(const std::vector<v1::EntitySpec>& specs, const DynamicsProvider& provider) {
  *this = EntityStore{};
  env_ = provider.env;
  for (const auto& spec : specs) {
    if (!keys::is_valid_entity_id(spec.id())) throw std::invalid_argument("invalid entity id: " + spec.id());
    if (!index_.emplace(spec.id(), id_.size()).second) throw std::invalid_argument("duplicate entity id: " + spec.id());

    std::unique_ptr<dyn::DynamicsModel> model;
    const bool fixed = spec.dynamics() == v1::DYNAMICS_KIND_STATIC || spec.dynamics() == v1::DYNAMICS_KIND_UNSPECIFIED;
    if (!fixed) {
      model = provider.make_model ? provider.make_model(spec) : nullptr;
      // IMP-CORE-010: 공급자가 스크립트 모델을 주지 않으면 Core의 경로 추종 모델을 쓴다. 경로가 없으면 초기 위치 고정
      if (!model && spec.dynamics() == v1::DYNAMICS_KIND_SCRIPTED) model = make_scripted_model(spec);
      if (!model && spec.dynamics() != v1::DYNAMICS_KIND_SCRIPTED)
        throw std::invalid_argument("unsupported dynamics for " + spec.id() + ": " +
                                    v1::DynamicsKind_Name(spec.dynamics()));
    }

    id_.push_back(spec.id());
    kind_.push_back(spec.kind());
    side_.push_back(spec.side());
    alive_.push_back(1);
    onboard_.push_back(needs_onboard(spec) ? 1 : 0);
    energy_.push_back(1.0);
    fixed_.push_back(spec.initial());

    const std::size_t nx = model ? model->state_size() : 0, nu = model ? model->input_size() : 0;
    x_off_.push_back(x_.size());
    x_len_.push_back(nx);
    u_off_.push_back(u_.size());
    u_len_.push_back(nu);
    x_.resize(x_.size() + nx, 0.0);
    u_.resize(u_.size() + nu, 0.0);
    if (model) {
      const std::size_t i = id_.size() - 1;
      model->from_kinematic(to_sample(spec.initial()), x(i));
      if (provider.init_input) provider.init_input(*model, x(i), u(i));
    }
    model_.push_back(std::move(model));
    rejected_.emplace_back();
    // 시나리오 재정의는 airframe 표 위에 덮어쓴다. 거부 항목은 첫 EntityParams에 실린다
    if (spec.has_dynamics_params() && !spec.dynamics_params().fields().empty()) {
      if (has_params(id_.size() - 1)) apply_params(id_.size() - 1, spec.dynamics_params(), false);
      else
        for (const auto& [name, v] : spec.dynamics_params().fields()) {
          (void)v;
          v1::ParamRejection r;
          r.set_name(name);
          r.set_reason("unknown");
          rejected_.back().push_back(std::move(r));
        }
    }
  }
  x0_ = x_;
  u0_ = u_;
  rejected0_ = rejected_;
  param0_.clear();
  for (std::size_t i = 0; i < model_.size(); ++i) {
    auto& v = param0_.emplace_back();
    if (model_[i])
      for (const auto& d : model_[i]->param_descs()) v.push_back(model_[i]->get_param(d.name));
  }
}

void EntityStore::reset() {
  x_ = x0_;
  u_ = u0_;
  std::fill(alive_.begin(), alive_.end(), std::uint8_t{1});
  std::fill(energy_.begin(), energy_.end(), 1.0);
  for (std::size_t i = 0; i < model_.size(); ++i) {
    if (!model_[i]) continue;
    const auto descs = model_[i]->param_descs();
    for (std::size_t k = 0; k < descs.size(); ++k) model_[i]->set_param(descs[k].name, param0_[i][k]);
  }
  rejected_ = rejected0_;
}

const std::vector<v1::ParamRejection>& EntityStore::apply_params(std::size_t i, const google::protobuf::Struct& values,
                                                                 bool runtime_only) {
  auto& rej = rejected_[i];
  rej.clear();
  auto* m = model_[i].get();
  const auto descs = m ? m->param_descs() : std::span<const dyn::ParamDesc>{};
  // protobuf map의 순회 순서는 정해져 있지 않으므로 이름순으로 처리한다 (결정론)
  std::map<std::string, const google::protobuf::Value*> sorted;
  for (const auto& [k, v] : values.fields()) sorted.emplace(k, &v);
  for (const auto& [name, v] : sorted) {
    auto reject = [&](const char* why) {
      v1::ParamRejection r;
      r.set_name(name);
      r.set_reason(why);
      rej.push_back(std::move(r));
    };
    const dyn::ParamDesc* d = nullptr;
    for (const auto& c : descs)
      if (c.name == name) d = &c;
    if (!d) reject("unknown");
    else if (v->kind_case() != google::protobuf::Value::kNumberValue) reject("type");
    else if (runtime_only && !d->runtime) reject("not_runtime");
    else if (!(v->number_value() >= d->min && v->number_value() <= d->max) || !m->set_param(name, v->number_value()))
      reject("range");
  }
  return rej;
}

void EntityStore::fill_params(std::size_t i, v1::EntityParams& out) const {
  out.set_entity_id(id_[i]);
  out.set_owner(v1::PARAM_OWNER_DYNAMICS);
  const auto* m = model_[i].get();
  if (!m) return;
  out.set_plugin(std::string(m->name()));
  auto* values = out.mutable_values()->mutable_fields();
  for (const auto& d : m->param_descs()) {
    auto* s = out.add_specs();
    s->set_name(std::string(d.name));
    s->set_layer(static_cast<v1::ParamLayer>(d.layer));
    s->mutable_default_value()->set_number_value(d.default_value);
    s->set_unit(std::string(d.unit));
    s->set_min(d.min);
    s->set_max(d.max);
    s->set_description(std::string(d.description));
    s->set_runtime(d.runtime);
    (*values)[std::string(d.name)].set_number_value(m->get_param(d.name));
  }
  for (const auto& r : rejected_[i]) *out.add_rejected() = r;
}

std::optional<std::size_t> EntityStore::find(const std::string& id) const {
  const auto it = index_.find(id);
  if (it == index_.end()) return std::nullopt;
  return it->second;
}

void EntityStore::kinematics(std::size_t i, v1::KinematicState& out) const {
  if (!model_[i]) {
    out = fixed_[i];
    return;
  }
  dyn::KinematicSample s;
  model_[i]->to_kinematic(x(i), env_, s);
  from_sample(s, out);
}

void EntityStore::fill_state(std::size_t i, v1::EntityState& out) const {
  out.set_id(id_[i]);
  out.set_kind(kind_[i]);
  out.set_side(side_[i]);
  out.set_alive(alive(i));
  out.set_energy_frac(energy_[i]);
  kinematics(i, *out.mutable_kinematics());
}

}  // namespace swarm::core
