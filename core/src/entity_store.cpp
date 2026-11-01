// IMP-CORE-003: 엔티티 저장소
#include "swarm/core/entity_store.hpp"

#include <stdexcept>

#include "swarm/api/keys.hpp"

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
  for (const auto& spec : specs) {
    if (!keys::is_valid_entity_id(spec.id())) throw std::invalid_argument("invalid entity id: " + spec.id());
    if (!index_.emplace(spec.id(), id_.size()).second) throw std::invalid_argument("duplicate entity id: " + spec.id());

    std::unique_ptr<dyn::DynamicsModel> model;
    const bool fixed = spec.dynamics() == v1::DYNAMICS_KIND_STATIC || spec.dynamics() == v1::DYNAMICS_KIND_UNSPECIFIED;
    if (!fixed) {
      model = provider.make_model ? provider.make_model(spec) : nullptr;
      // 스크립트 경로 모델이 아직 없으면 초기 위치에 고정한다
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
  }
  x0_ = x_;
  u0_ = u_;
}

void EntityStore::reset() {
  x_ = x0_;
  u_ = u0_;
  std::fill(alive_.begin(), alive_.end(), std::uint8_t{1});
  std::fill(energy_.begin(), energy_.end(), 1.0);
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
  model_[i]->to_kinematic(x(i), s);
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
