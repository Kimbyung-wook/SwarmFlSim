// IMP-CORE-002, IMP-CORE-004: 프레임 스케줄러, 실행 모드, onboard 입출력
// IMP-CORE-009: 지면 충돌, IMP-CORE-011: 고장 주입, IMP-CORE-013: 동역학 매개변수
#include "swarm/core/sim_core.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <cstdio>
#include <set>
#include <stdexcept>
#include <thread>

#include "swarm/api/keys.hpp"
#include "swarm/v1/truth.pb.h"

namespace swarm::core {

namespace {

template <class T>
bool parse(const Sample& s, T& msg) {
  return msg.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()));
}

// onboard/<id>/ControlOutput → <id>
std::string onboard_entity(const std::string& key) {
  const auto a = key.find('/');
  const auto b = key.find('/', a + 1);
  return key.substr(a + 1, b - a - 1);
}

std::string state_name(v1::SimRunState s) { return v1::SimRunState_Name(s); }

}  // namespace

SimCore::SimCore(Bus& bus, DynamicsProvider provider, CoreConfig cfg)
    : bus_(bus), provider_(std::move(provider)), cfg_(std::move(cfg)) {
  keys::check_entity_id(cfg_.participant_id);
  subs_.push_back(bus_.subscribe(keys::kSimCtrlCmd, [this](const Sample& s) {
    v1::SimCommand cmd;
    if (!parse(s, cmd)) return;
    submit(cmd);
  }));
  subs_.push_back(bus_.subscribe("onboard/*/ControlOutput", [this](const Sample& s) {
    v1::ControlOutput c;
    if (!parse(s, c)) return;
    {
      std::lock_guard lock(inbox_mu_);
      inbox_.controls[onboard_entity(s.key)] = std::move(c);
    }
  }));
  subs_.push_back(bus_.subscribe("sim/clock/done/*", [this](const Sample& s) {
    v1::FrameDone d;
    if (!parse(s, d)) return;
    {
      std::lock_guard lock(inbox_mu_);
      inbox_.dones.push_back(std::move(d));
    }
    wake();
  }));
}

SimCore::~SimCore() { subs_.clear(); }

void SimCore::submit(const v1::SimCommand& cmd) {
  {
    std::lock_guard lock(inbox_mu_);
    inbox_.commands.push_back(cmd);
  }
  wake();
}

void SimCore::wake() {
  {
    std::lock_guard lock(wake_mu_);
    wake_flag_ = true;
  }
  wake_cv_.notify_one();
}

void SimCore::log(const std::string& msg) const {
  if (cfg_.log)
    cfg_.log(msg);
  else
    std::fprintf(stderr, "[swarm_core] %s\n", msg.c_str());
}

bool SimCore::load(const Scenario& sc) {
  if (state_ == v1::SIM_RUN_STATE_RUNNING || state_ == v1::SIM_RUN_STATE_PAUSED) {
    log("load rejected: reset first");
    return false;
  }
  EntityStore store;
  std::set<std::string> parts(cfg_.participants.begin(), cfg_.participants.end());
  try {
    // IMP-CORE-017: 검증에 실패하면 기존 상태(시나리오·상태)를 그대로 두고 거부한다 (DEC-038)
    validate_scenario(sc);
    if (provider_.known_airframe)
      for (const auto& e : sc.entities)
        if (!e.airframe().empty() && !provider_.known_airframe(e.airframe()))
          throw std::invalid_argument("unknown airframe for " + e.id() + ": " + e.airframe());
    store.build(sc.entities, provider_);
    parts.insert(sc.participants.begin(), sc.participants.end());
    for (const auto& p : parts) keys::check_entity_id(p);
  } catch (const std::exception& e) {
    log(std::string("load rejected: ") + e.what());
    return false;
  }

  scenario_ = sc;
  store_ = std::move(store);
  participants_.assign(parts.begin(), parts.end());
  nav_keys_.clear();
  for (std::size_t i = 0; i < store_.size(); ++i) nav_keys_.push_back(keys::onboard(store_.id(i), "NavigationReport"));

  mode_ = sc.mode == v1::RUN_MODE_UNSPECIFIED ? v1::RUN_MODE_REALTIME : sc.mode;
  frame_hz_ = sc.frame_hz;
  rate_ = mode_ == v1::RUN_MODE_REALTIME ? 1.0 : sc.rate;
  seed_ = sc.seed;
  reset_run_state();
  ready_.clear();

  const auto now = Clock::now();
  publish_truth();
  publish_all_params();
  publish_scenario();
  last_params_wall_ = now;
  set_state(v1::SIM_RUN_STATE_LOADED, now);
  log("loaded scenario '" + sc.name + "', " + std::to_string(store_.size()) + " entities");
  return true;
}

void SimCore::reset_run_state() {
  store_.reset();
  integrators_.clear();
  ground_events_.clear();
  for (std::size_t i = 0; i < store_.size(); ++i) {
    const auto* model = store_.model(i);
    integrators_.push_back(model && provider_.make_integrator ? provider_.make_integrator() : nullptr);
    ground_events_.push_back(model && provider_.make_ground_event ? provider_.make_ground_event(*model)
                                                                  : dyn::EventFn{});
  }
  faults_.clear();
  nav_seq_.assign(store_.size(), 0);
  frame_ = 0;
  sim_time_us_ = 0;
  frame_published_ = false;
  step_budget_ = 0;
  done_.clear();
  for (const auto& p : participants_) done_[p] = 0;
  blocked_ = false;
  waiting_.clear();
  overruns_ = 0;
  rng_.seed(seed_);
  std::lock_guard lock(inbox_mu_);
  inbox_.controls.clear();
  inbox_.dones.clear();
}

bool SimCore::paced() const { return mode_ == v1::RUN_MODE_REALTIME || rate_ > 0.0; }

void SimCore::anchor(Clock::time_point now) {
  anchor_wall_ = now;
  anchor_frame_ = frame_;
}

SimCore::Clock::time_point SimCore::next_deadline() const {
  const double wall_s = static_cast<double>(frame_ - anchor_frame_ + 1) * dt_us_ * 1e-6 / rate_;
  return anchor_wall_ + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(wall_s));
}

bool SimCore::barrier_ok() const {
  return std::all_of(done_.begin(), done_.end(), [&](const auto& kv) { return kv.second >= frame_ + 1; });
}

void SimCore::set_state(v1::SimRunState s, Clock::time_point now) {
  if (s != state_) log("state " + state_name(state_) + " -> " + state_name(s));
  state_ = s;
  publish_status(now);
}

void SimCore::handle_start(const v1::Start& s, Clock::time_point now) {
  if (state_ != v1::SIM_RUN_STATE_LOADED) {
    log("start rejected in " + state_name(state_));
    return;
  }
  const std::uint32_t hz = s.frame_hz() ? s.frame_hz() : frame_hz_;
  if (hz < 50 || hz > 100) {  // REQ-DYN-003
    log("start rejected: frame_hz must be 50..100, got " + std::to_string(hz));
    return;
  }
  const auto mode = s.mode() == v1::RUN_MODE_UNSPECIFIED ? mode_ : s.mode();
  if (mode != v1::RUN_MODE_REALTIME && !valid_rate(s.rate())) {  // IMP-CORE-017, DEC-038
    log("start rejected: rate must be finite and within 0.." + std::to_string(static_cast<int>(kMaxRate)) + ", got " +
        std::to_string(s.rate()));
    return;
  }
  mode_ = mode;
  frame_hz_ = hz;
  dt_us_ = 1000000u / hz;
  rate_ = mode_ == v1::RUN_MODE_REALTIME ? 1.0 : s.rate();
  if (s.seed()) seed_ = s.seed();
  rng_.seed(seed_);
  anchor(now);
  rate_wall_ = now;
  rate_sim_us_ = sim_time_us_;
  log("start mode=" + v1::RunMode_Name(mode_) + " hz=" + std::to_string(hz) + " rate=" + std::to_string(rate_) +
      " seed=" + std::to_string(seed_));
  set_state(v1::SIM_RUN_STATE_RUNNING, now);
}

void SimCore::handle_fault(const v1::InjectFault& f) {
  const auto kind = f.fault();
  // 링크 차단은 Datalink(WP4)가 sim/ctrl/cmd를 직접 구독해 처리한다
  if (kind == v1::FAULT_KIND_LINK_CUT || kind == v1::FAULT_KIND_GCS_LINK_CUT) return;
  const auto idx = store_.find(f.entity_id());
  if (!idx) {
    log("fault: unknown entity " + f.entity_id());
    return;
  }
  const std::string name = v1::FaultKind_Name(kind);
  switch (kind) {
    case v1::FAULT_KIND_KILL:
      if (!f.clear() && store_.alive(*idx)) kill(*idx, "fault", sim_time_us_, frame_);
      return;
    case v1::FAULT_KIND_ENGINE:
    case v1::FAULT_KIND_NAV:
    case v1::FAULT_KIND_SENSOR:
      break;
    default:
      log("fault " + name + " ignored");
      return;
  }
  if (kind == v1::FAULT_KIND_ENGINE && (!store_.model(*idx) || !provider_.engine_out)) {
    log("fault ENGINE not supported for " + f.entity_id());
    return;
  }
  const auto key = std::make_pair(*idx, kind);
  if (f.clear()) {
    faults_.erase(key);
    log("fault " + name + " cleared on " + f.entity_id());
    return;
  }
  faults_[key] = f.duration_s() > 0.0
                     ? sim_time_us_ + static_cast<std::uint64_t>(std::llround(f.duration_s() * 1e6))
                     : std::numeric_limits<std::uint64_t>::max();
  // SENSOR는 기록만 한다. 탐지(Detection)를 Core가 만들게 되면 이 상태로 막는다
  log("fault " + name + " on " + f.entity_id());
}

bool SimCore::fault_active(std::size_t i, v1::FaultKind kind) const {
  const auto it = faults_.find({i, kind});
  return it != faults_.end() && sim_time_us_ < it->second;
}

bool SimCore::fault_active(const std::string& entity_id, v1::FaultKind kind) const {
  const auto idx = store_.find(entity_id);
  return idx && fault_active(*idx, kind);
}

void SimCore::kill(std::size_t i, const char* cause, std::uint64_t sim_time_us, std::uint64_t frame) {
  store_.set_alive(i, false);
  v1::TruthEvent ev;
  auto* h = ev.mutable_header();
  h->set_sim_time_us(sim_time_us);
  h->set_frame(frame);
  h->set_source(cfg_.participant_id);
  h->set_seq(seq_event_++);
  ev.mutable_kill()->set_entity_id(store_.id(i));
  ev.mutable_kill()->set_cause(cause);
  publish(keys::truth_event("kill"), ev);
  log(std::string("kill ") + store_.id(i) + " cause=" + cause);
}

void SimCore::handle_set_params(const v1::SetParams& p) {
  // FA·MA 매개변수는 Agent 런타임이 처리한다
  if (p.owner() != v1::PARAM_OWNER_DYNAMICS) return;
  const auto idx = store_.find(p.entity_id());
  if (!idx || !store_.has_params(*idx)) {
    log("set_params: no dynamics parameters for " + p.entity_id());
    return;
  }
  const auto& rej = store_.apply_params(*idx, p.values(), true);
  for (const auto& r : rej) log("set_params " + p.entity_id() + "." + r.name() + " rejected: " + r.reason());
  publish_params(*idx);
}

void SimCore::publish_params(std::size_t i) {
  if (!store_.has_params(i)) return;
  v1::EntityParams ep;
  store_.fill_params(i, ep);
  ep.set_sim_time_us(sim_time_us_);
  publish(keys::sim_param(store_.id(i), "dynamics"), ep);
}

void SimCore::publish_scenario() { publish(std::string(keys::kSimCtrlScenario), to_proto(scenario_)); }

void SimCore::publish_all_params() {
  for (std::size_t i = 0; i < store_.size(); ++i) publish_params(i);
}

void SimCore::handle(const v1::SimCommand& cmd, Clock::time_point now) {
  using C = v1::SimCommand;
  switch (cmd.cmd_case()) {
    case C::kLoad:
      try {
        load(cmd.load().has_scenario() ? from_proto(cmd.load().scenario())
                                       : parse_scenario_json(cmd.load().scenario_json()));
      } catch (const std::exception& e) {
        log(std::string("load failed: ") + e.what());
      }
      break;
    case C::kStart:
      handle_start(cmd.start(), now);
      break;
    case C::kPause:
      if (state_ == v1::SIM_RUN_STATE_RUNNING) set_state(v1::SIM_RUN_STATE_PAUSED, now);
      break;
    case C::kResume:
      if (state_ == v1::SIM_RUN_STATE_PAUSED) {
        step_budget_ = 0;
        anchor(now);
        set_state(v1::SIM_RUN_STATE_RUNNING, now);
      }
      break;
    case C::kStep:
      if (state_ == v1::SIM_RUN_STATE_PAUSED) step_budget_ += cmd.step().frames();
      else log("step ignored: not paused");
      break;
    case C::kSetRate:
      if (mode_ == v1::RUN_MODE_REALTIME) {
        log("set_rate ignored in REALTIME");
      } else if (!valid_rate(cmd.set_rate().rate())) {  // IMP-CORE-017, DEC-038
        log("set_rate rejected: rate must be finite and within 0.." + std::to_string(static_cast<int>(kMaxRate)) +
            ", got " + std::to_string(cmd.set_rate().rate()));
      } else {
        rate_ = cmd.set_rate().rate();
        anchor(now);
        publish_status(now);
      }
      break;
    case C::kReset:
      if (state_ == v1::SIM_RUN_STATE_IDLE) break;
      reset_run_state();
      publish_truth();
      publish_all_params();
      publish_scenario();
      last_params_wall_ = now;
      set_state(v1::SIM_RUN_STATE_LOADED, now);
      break;
    case C::kShutdown:
      set_state(v1::SIM_RUN_STATE_STOPPED, now);
      break;
    case C::kFault:
      handle_fault(cmd.fault());
      break;
    case C::kSetParams:
      handle_set_params(cmd.set_params());
      break;
    case C::CMD_NOT_SET:
      break;
  }
}

bool SimCore::poll(Clock::time_point now) {
  Inbox in;
  {
    std::lock_guard lock(inbox_mu_);
    in.commands.swap(inbox_.commands);
    in.dones.swap(inbox_.dones);
  }
  for (const auto& d : in.dones) {
    auto it = done_.find(d.participant());
    if (it == done_.end()) continue;
    // 첫 틱 전의 FrameDone{frame=0}은 준비 신호다 (DEC-037)
    if (frame_ == 0 && !frame_published_) ready_.insert(d.participant());
    else it->second = std::max(it->second, d.frame() + 1);
  }
  for (const auto& c : in.commands) handle(c, now);

  if (state_ != v1::SIM_RUN_STATE_RUNNING && state_ != v1::SIM_RUN_STATE_STOPPED &&
      now - last_status_wall_ >= std::chrono::seconds(1))
    publish_status(now);
  if (state_ == v1::SIM_RUN_STATE_LOADED && now - last_params_wall_ >= std::chrono::seconds(1)) {
    publish_all_params();
    publish_scenario();
    last_params_wall_ = now;
  }

  if (state_ != v1::SIM_RUN_STATE_RUNNING && blocked_) {  // 정지·중단하면 대기 표시를 거둔다. status는 1초 안에 나간다
    blocked_ = false;
    waiting_.clear();
  }
  const bool stepping = state_ == v1::SIM_RUN_STATE_PAUSED && step_budget_ > 0;
  if (state_ != v1::SIM_RUN_STATE_RUNNING && !stepping) return false;
  if (!frame_published_) {
    // lockstep은 참여자 전원이 준비되어야 첫 틱을 낸다. 시작 후 동적 참여는 없다 (DEC-037)
    if (mode_ == v1::RUN_MODE_LOCKSTEP && frame_ == 0 && ready_.size() < done_.size()) {
      // 준비 대기 중에도 시나리오를 1초마다 재발행해 늦게 켠 참여자가 받게 한다
      if (now - last_params_wall_ >= std::chrono::seconds(1)) {
        publish_scenario();
        last_params_wall_ = now;
      }
      update_waiting(now, true);
      log_waiting(now, true);
      return false;
    }
    clear_waiting(now);
    publish_frame();
  }
  if (mode_ == v1::RUN_MODE_LOCKSTEP && !barrier_ok()) {
    update_waiting(now, false);
    log_waiting(now, false);
    return false;
  }
  clear_waiting(now);

  if (!stepping && paced()) {
    const auto deadline = next_deadline();
    if (now < deadline) return false;
    // 한 프레임 이상 늦으면 따라잡지 않고 기준점을 다시 잡는다
    if (now - deadline > std::chrono::microseconds(static_cast<std::int64_t>(dt_us_ / rate_))) {
      ++overruns_;
      anchor_wall_ = now;
      anchor_frame_ = frame_ + 1;
    }
  }

  integrate_frame();
  ++frame_;
  sim_time_us_ += dt_us_;
  frame_published_ = false;
  publish_frame();

  if (stepping) {
    --step_budget_;
    anchor(now);
  }
  if (frame_ % frame_hz_ == 0) publish_status(now);
  if (cfg_.stop_after_frames && frame_ >= cfg_.stop_after_frames) set_state(v1::SIM_RUN_STATE_STOPPED, now);
  return true;
}

// IMP-CORE-018, IMP-CORE-021: 같은 대기가 5초 넘게 이어질 때만, 이후 5초마다 누구를 기다리는지 로그로 남긴다 (QA-004, D-14).
// 프레임마다 생기는 짧은 장벽 대기는 기록하지 않는다. update_waiting이 먼저 불려 wait_since_가 잡혀 있어야 한다
void SimCore::log_waiting(Clock::time_point now, bool ready_phase) {
  if (!blocked_) return;
  const auto ref = std::max(wait_since_, last_wait_log_);
  if (now - ref < std::chrono::seconds(5)) return;
  last_wait_log_ = now;
  std::string names;
  for (const auto& [p, next] : done_) {
    const bool waiting = ready_phase ? !ready_.count(p) : next < frame_ + 1;
    if (waiting) names += (names.empty() ? "" : ", ") + p;
  }
  log(std::string(ready_phase ? "waiting for ready: " : "waiting for frame done: ") + names + " (frame " +
      std::to_string(frame_) + ")");
}

// IMP-CORE-020: lockstep 장벽에서 5 s(벽시계) 넘게 기다리면 응답 없는 참여자를 SimStatus.waiting_participants에
// 싣고 status를 계속 발행한다. 참여자는 기다리는 동안에도 기다린 채 남는다 (재합류 미지원, DEC-038, DEC-041)
void SimCore::update_waiting(Clock::time_point now, bool ready_phase) {
  if (!blocked_) {
    blocked_ = true;
    wait_since_ = now;
    return;
  }
  if (now - wait_since_ < std::chrono::seconds(5)) return;
  std::vector<std::string> names;
  for (const auto& [p, next] : done_)
    if (ready_phase ? !ready_.count(p) : next < frame_ + 1) names.push_back(p);
  const bool changed = names != waiting_;
  waiting_ = std::move(names);
  if (changed || now - last_status_wall_ >= std::chrono::seconds(1)) publish_status(now);
}

void SimCore::clear_waiting(Clock::time_point now) {
  blocked_ = false;
  if (waiting_.empty()) return;
  waiting_.clear();
  publish_status(now);
}

void SimCore::integrate_frame() {
  std::map<std::string, v1::ControlOutput> controls;
  {
    std::lock_guard lock(inbox_mu_);
    controls.swap(inbox_.controls);
  }
  for (const auto& [id, c] : controls) {
    const auto idx = store_.find(id);
    if (!idx || !store_.model(*idx)) continue;
    // 형식이 맞지 않는 입력은 버리고 이전 입력을 유지한다
    if (!store_.model(*idx)->map_control(c, store_.u(*idx))) ++control_mismatches_;
  }

  const double t0 = static_cast<double>(sim_time_us_) * 1e-6, dt = dt_us_ * 1e-6;
  for (std::size_t i = 0; i < store_.size(); ++i) {
    const auto* model = store_.model(i);
    if (!model || !store_.alive(i)) continue;
    std::span<const double> u = store_.u(i);
    if (fault_active(i, v1::FAULT_KIND_ENGINE)) {
      // 명령은 그대로 두고 적분 입력만 바꾼다. 고장이 풀리면 마지막 명령으로 돌아간다
      u_scratch_.assign(u.begin(), u.end());
      provider_.engine_out(*model, u_scratch_);
      u = u_scratch_;
    }
    // 프레임 시작에 지면 위에 있을 때만 이벤트를 건다(지상 엔티티, 지면 아래 시작은 제외)
    const auto& ground = ground_events_[i];
    const dyn::EventFn* event = ground && ground(t0, store_.x(i)) > 0.0 ? &ground : nullptr;
    const auto r = integrators_[i]->step(*model, t0, dt, store_.x(i), u, provider_.env, event);
    // 교차 시점 상태에서 멈춘다. 이벤트 프레임은 엔티티가 죽은 채 처음 발행되는 프레임(N+1)이다
    if (r.event) kill(i, "ground", static_cast<std::uint64_t>(std::llround(r.t_end * 1e6)), frame_ + 1);
  }
}

void SimCore::publish_truth() {
  v1::TruthFrame tf;
  auto* h = tf.mutable_header();
  h->set_sim_time_us(sim_time_us_);
  h->set_frame(frame_);
  h->set_source(cfg_.participant_id);
  h->set_seq(seq_truth_++);
  for (std::size_t i = 0; i < store_.size(); ++i) store_.fill_state(i, *tf.add_entities());
  publish(std::string(keys::kTruthState), tf);
}

void SimCore::publish_frame() {
  publish_truth();

  for (std::size_t i = 0; i < store_.size(); ++i) {
    if (!store_.has_onboard(i) || !store_.alive(i) || fault_active(i, v1::FAULT_KIND_NAV)) continue;
    v1::NavigationReport nav;
    auto* h = nav.mutable_header();
    h->set_sim_time_us(sim_time_us_);
    h->set_frame(frame_);
    h->set_source(store_.id(i));
    h->set_seq(nav_seq_[i]++);
    store_.kinematics(i, *nav.mutable_kinematics());
    if (cfg_.nav_noise) cfg_.nav_noise(store_.id(i), nav, rng_);
    publish(nav_keys_[i], nav);
  }

  v1::ClockTick tick;
  tick.set_frame(frame_);
  tick.set_sim_time_us(sim_time_us_);
  tick.set_dt_us(dt_us_);
  tick.set_mode(mode_);
  publish(std::string(keys::kClockTick), tick);
  frame_published_ = true;
}

v1::SimStatus SimCore::status() const {
  v1::SimStatus st;
  st.set_state(state_);
  st.set_mode(mode_);
  st.set_sim_time_us(sim_time_us_);
  st.set_frame(frame_);
  st.set_frame_hz(frame_hz_);
  st.set_rate_target(rate_);
  st.set_rate_actual(state_ == v1::SIM_RUN_STATE_RUNNING ? rate_actual_ : 0.0);
  st.set_entity_count(static_cast<std::uint32_t>(store_.size()));
  st.set_frame_overruns(overruns_);
  st.set_scenario_name(scenario_.name);
  for (const auto& p : waiting_) st.add_waiting_participants(p);
  return st;
}

void SimCore::publish_status(Clock::time_point now) {
  const double wall_s = std::chrono::duration<double>(now - rate_wall_).count();
  if (state_ == v1::SIM_RUN_STATE_RUNNING && wall_s > 0.0) {
    rate_actual_ = static_cast<double>(sim_time_us_ - rate_sim_us_) * 1e-6 / wall_s;
  }
  rate_wall_ = now;
  rate_sim_us_ = sim_time_us_;
  last_status_wall_ = now;
  publish(std::string(keys::kSimCtrlStatus), status());
}

void SimCore::publish(const std::string& key, const google::protobuf::Message& msg) {
  const std::string bytes = msg.SerializeAsString();
  bus_.put(key, {reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size()},
           protobuf_encoding(msg.GetDescriptor()->full_name()));
}

void SimCore::run() {
  using namespace std::chrono_literals;
  while (state_ != v1::SIM_RUN_STATE_STOPPED) {
    const auto now = Clock::now();
    if (poll(now)) continue;

    auto until = now + 100ms;
    const bool waiting_deadline = state_ == v1::SIM_RUN_STATE_RUNNING && paced() &&
                                  (mode_ != v1::RUN_MODE_LOCKSTEP || barrier_ok());
    if (waiting_deadline) {
      const auto deadline = next_deadline();
      // 대기 정밀도가 낮은 플랫폼(Windows 기본 타이머)을 위해 마지막 2 ms는 양보하며 기다린다
      if (deadline - now < 2ms) {
        std::this_thread::yield();
        continue;
      }
      until = std::min(until, deadline - 2ms);
    }
    std::unique_lock lock(wake_mu_);
    wake_cv_.wait_until(lock, until, [this] { return wake_flag_; });
    wake_flag_ = false;
  }
}

}  // namespace swarm::core
