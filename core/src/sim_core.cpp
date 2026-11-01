// IMP-CORE-002, IMP-CORE-004: 프레임 스케줄러, 실행 모드, onboard 입출력
#include "swarm/core/sim_core.hpp"

#include <algorithm>
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
  store.build(sc.entities, provider_);  // 오류면 예외. 기존 시나리오는 그대로 둔다

  std::set<std::string> parts(cfg_.participants.begin(), cfg_.participants.end());
  parts.insert(sc.participants.begin(), sc.participants.end());
  for (const auto& p : parts) keys::check_entity_id(p);

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

  const auto now = Clock::now();
  publish_truth();
  set_state(v1::SIM_RUN_STATE_LOADED, now);
  log("loaded scenario '" + sc.name + "', " + std::to_string(store_.size()) + " entities");
  return true;
}

void SimCore::reset_run_state() {
  store_.reset();
  integrators_.clear();
  for (std::size_t i = 0; i < store_.size(); ++i)
    integrators_.push_back(store_.model(i) && provider_.make_integrator ? provider_.make_integrator() : nullptr);
  nav_seq_.assign(store_.size(), 0);
  frame_ = 0;
  sim_time_us_ = 0;
  frame_published_ = false;
  step_budget_ = 0;
  done_.clear();
  for (const auto& p : participants_) done_[p] = 0;
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
  mode_ = s.mode() == v1::RUN_MODE_UNSPECIFIED ? mode_ : s.mode();
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
  if (!frame_published_) publish_frame();
}

void SimCore::handle_fault(const v1::InjectFault& f) {
  const auto idx = store_.find(f.entity_id());
  if (!idx) {
    log("fault: unknown entity " + f.entity_id());
    return;
  }
  if (f.fault() != v1::FAULT_KIND_KILL) {
    // 링크 차단은 Datalink(WP4), 엔진·센서·항법 고장은 해당 WP가 처리한다
    log("fault " + v1::FaultKind_Name(f.fault()) + " not handled by core");
    return;
  }
  if (f.clear() || !store_.alive(*idx)) return;
  store_.set_alive(*idx, false);
  v1::TruthEvent ev;
  auto* h = ev.mutable_header();
  h->set_sim_time_us(sim_time_us_);
  h->set_frame(frame_);
  h->set_source(cfg_.participant_id);
  h->set_seq(seq_event_++);
  ev.mutable_kill()->set_entity_id(f.entity_id());
  ev.mutable_kill()->set_cause("fault");
  publish(keys::truth_event("kill"), ev);
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
      set_state(v1::SIM_RUN_STATE_LOADED, now);
      break;
    case C::kShutdown:
      set_state(v1::SIM_RUN_STATE_STOPPED, now);
      break;
    case C::kFault:
      handle_fault(cmd.fault());
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
    if (it != done_.end()) it->second = std::max(it->second, d.frame() + 1);
  }
  for (const auto& c : in.commands) handle(c, now);

  if (state_ != v1::SIM_RUN_STATE_RUNNING && state_ != v1::SIM_RUN_STATE_STOPPED &&
      now - last_status_wall_ >= std::chrono::seconds(1))
    publish_status(now);

  const bool stepping = state_ == v1::SIM_RUN_STATE_PAUSED && step_budget_ > 0;
  if (state_ != v1::SIM_RUN_STATE_RUNNING && !stepping) return false;
  if (!frame_published_) publish_frame();
  if (mode_ == v1::RUN_MODE_LOCKSTEP && !barrier_ok()) return false;

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
    integrators_[i]->step(*model, t0, dt, store_.x(i), store_.u(i), provider_.env, nullptr);
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
    if (!store_.has_onboard(i) || !store_.alive(i)) continue;
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
