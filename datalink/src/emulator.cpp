// IMP-LNK-008~010, IMP-LNK-012~014: Datalink Emulator
// (PRP-LNK-001, PRP-LNK-002, REQ-LNK-001~004, DEC-009, DEC-005, DEC-028~030)
#include "swarm/lnk/emulator.hpp"

#include <algorithm>
#include <chrono>
#include <span>
#include <string_view>
#include <tuple>

#include <google/protobuf/util/json_util.h>

#include "swarm/api/keys.hpp"

namespace swarm::lnk {
namespace {

template <class M>
bool parse(const Sample& s, M& m) {
  return m.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()));
}

template <class M>
std::string encoding_of() {
  return protobuf_encoding(M::descriptor()->full_name());
}

GeoPoint to_geo(const v1::Geodetic& g) { return {g.lat_deg(), g.lon_deg(), g.alt_m()}; }

// DEC-030: area가 있으면 area, 없으면 폐기 예정 zone(고도 무관 원)
JamArea to_jam_area(const v1::JamZoneEvent& jz) {
  JamArea a;
  if (!jz.has_area()) {
    a.center = to_geo(jz.zone().center());
    a.radius_m = jz.zone().radius_m();
    return a;
  }
  const auto& ar = jz.area();
  if (ar.has_polygon()) {
    for (const auto& v : ar.polygon().vertices()) a.polygon.push_back(to_geo(v));
  } else {
    a.center = to_geo(ar.circle().center());
    a.radius_m = ar.circle().radius_m();
  }
  a.min_alt_m = ar.min_alt_m();
  a.max_alt_m = ar.max_alt_m();
  return a;
}

}  // namespace

Datalink::Datalink(Bus& bus, const dyn::Terrain* terrain, DatalinkConfig cfg)
    : bus_(bus), terrain_(terrain), cfg_(std::move(cfg)) {
  if (!cfg_.participant_id.empty()) keys::check_entity_id(cfg_.participant_id);
  for (const auto& name : builtin_profile_names()) base_profiles_[name] = *find_builtin_profile(name);
  for (const auto& [name, p] : cfg_.profiles) {
    base_profiles_[name] = p;
    base_profiles_[name].name = name;
  }
  profiles_ = base_profiles_;
  seed_ = cfg_.seed;

  subs_.push_back(bus_.subscribe(keys::kTxAll, [this](const Sample& s) { on_tx(s); }));
  subs_.push_back(bus_.subscribe(keys::kTruthState, [this](const Sample& s) { on_truth(s); }));
  subs_.push_back(bus_.subscribe("truth/event/*", [this](const Sample& s) { on_event(s); }));
  subs_.push_back(bus_.subscribe(keys::kSimCtrlCmd, [this](const Sample& s) { on_cmd(s); }));
  subs_.push_back(bus_.subscribe(std::string(keys::kSimCtrlScenario), [this](const Sample& s) { on_scenario(s); }));
  subs_.push_back(bus_.subscribe(keys::kClockTick, [this](const Sample& s) { on_tick(s); }));
  subs_.push_back(bus_.subscribe("sim/clock/done/*", [this](const Sample& s) { on_done(s); }));
}

Datalink::~Datalink() { subs_.clear(); }

void Datalink::log(const std::string& msg) const {
  if (cfg_.log) cfg_.log(msg);
}

void Datalink::load(const v1::Scenario& sc) {
  {
    std::lock_guard lock(mu_);
    load_locked(sc);
  }
  send_ready(sc.run().mode() == v1::RUN_MODE_LOCKSTEP);
}

bool Datalink::wait_shutdown(int timeout_ms) {
  std::unique_lock lock(shutdown_mu_);
  if (timeout_ms < 0) {
    shutdown_cv_.wait(lock, [this] { return shutdown_; });
    return true;
  }
  return shutdown_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms), [this] { return shutdown_; });
}

void Datalink::request_shutdown() {
  {
    std::lock_guard lock(shutdown_mu_);
    shutdown_ = true;
  }
  shutdown_cv_.notify_all();
}

std::uint64_t Datalink::sim_time_us() const {
  std::lock_guard lock(mu_);
  return now_us_;
}

std::uint64_t Datalink::seed() const {
  std::lock_guard lock(mu_);
  return seed_;
}

std::size_t Datalink::in_flight() const {
  std::lock_guard lock(mu_);
  return in_flight_.size();
}

std::size_t Datalink::pending() const {
  std::lock_guard lock(mu_);
  return pending_.size();
}

PairState Datalink::pair_state(const std::string& a, const std::string& b) const {
  std::lock_guard lock(mu_);
  const auto ia = nodes_.find(a), ib = nodes_.find(b);
  if (ia == nodes_.end() || ib == nodes_.end()) return {};
  return pair_state_locked(ia->second, ib->second);
}

// ---- 구독 콜백 ----

void Datalink::on_tx(const Sample& s) {
  // swarm/<src>/tx/<iface>/<msg>
  constexpr std::string_view kPrefix = "swarm/";
  const std::string_view key = s.key;
  if (key.substr(0, kPrefix.size()) != kPrefix) return;
  const auto slash = key.find('/', kPrefix.size());
  if (slash == std::string_view::npos || key.substr(slash, 4) != "/tx/") return;
  const std::string src(key.substr(kPrefix.size(), slash - kPrefix.size()));
  const std::string suffix(key.substr(slash + 4));
  if (!keys::is_valid_entity_id(src) || suffix.empty()) return;

  v1::LinkEnvelope env;
  if (!parse(s, env)) {
    log("drop unparsable LinkEnvelope on " + s.key);
    return;
  }
  std::lock_guard lock(mu_);
  // 송신 시각은 헤더의 sim_time_us를 쓴다(DEC-039: 받은 시점·도착 순서에 의존하지 않는다). 없으면 마지막 tick 시각
  const std::uint64_t tx_us = env.header().sim_time_us() != 0 ? env.header().sim_time_us() : now_us_;
  Pending p{tx_us, src, s.key, env.header().seq(), arrival_++, suffix, s.payload.size(), std::move(env)};
  if (pending_.size() >= cfg_.max_pending) {
    overflow_locked(std::move(p));
    return;
  }
  pending_.push_back(std::move(p));
}

void Datalink::on_truth(const Sample& s) {
  v1::TruthFrame tf;
  if (!parse(s, tf)) return;
  std::lock_guard lock(mu_);
  for (const auto& e : tf.entities()) {
    if (!keys::is_valid_entity_id(e.id())) continue;
    Node& n = node_locked(e.id());
    if (e.kind() != v1::ENTITY_KIND_UNSPECIFIED) n.kind = e.kind();
    if (e.side() != v1::SIDE_UNSPECIFIED) n.side = e.side();
    if (e.has_kinematics() && e.kinematics().has_position()) {
      n.pos = to_geo(e.kinematics().position());
      n.has_pos = true;
    }
    n.alive = e.alive();
  }
}

void Datalink::on_event(const Sample& s) {
  v1::TruthEvent ev;
  if (!parse(s, ev)) return;
  std::lock_guard lock(mu_);
  if (ev.has_jam_zone()) {
    const auto& jz = ev.jam_zone();
    if (jz.active())
      jam_zones_[jz.owner()] = to_jam_area(jz);
    else
      jam_zones_.erase(jz.owner());
  } else if (ev.has_kill()) {
    if (auto it = nodes_.find(ev.kill().entity_id()); it != nodes_.end()) it->second.alive = false;
  }
}

void Datalink::on_cmd(const Sample& s) {
  v1::SimCommand cmd;
  if (!parse(s, cmd)) return;
  switch (cmd.cmd_case()) {
    case v1::SimCommand::kLoad: {
      v1::Scenario sc;
      if (cmd.load().has_scenario()) {
        sc = cmd.load().scenario();
      } else if (auto st = google::protobuf::util::JsonStringToMessage(cmd.load().scenario_json(), &sc); !st.ok()) {
        // scenario_json은 폐기 예정(DEC-024). proto JSON 형식만 받는다
        log("LoadScenario.scenario_json: " + std::string(st.message()));
        return;
      }
      {
        std::lock_guard lock(mu_);
        load_locked(sc);
        log("scenario loaded: " + sc.name() + ", " + std::to_string(nodes_.size()) + " entities, seed " +
            std::to_string(seed_));
      }
      send_ready(sc.run().mode() == v1::RUN_MODE_LOCKSTEP);
      break;
    }
    case v1::SimCommand::kStart: {
      std::lock_guard lock(mu_);
      if (cmd.start().seed() != 0) seed_ = cmd.start().seed();
      reset_locked();
      break;
    }
    case v1::SimCommand::kReset: {
      std::lock_guard lock(mu_);
      reset_locked();
      faults_.clear();
      jam_zones_.clear();
      for (auto& [id, n] : nodes_) n.alive = true;
      break;
    }
    case v1::SimCommand::kShutdown:
      request_shutdown();
      break;
    case v1::SimCommand::kFault: {
      // LINK_CUT·GCS_LINK_CUT만 처리한다. 나머지 고장은 Core 담당
      const auto& f = cmd.fault();
      if (f.fault() != v1::FAULT_KIND_LINK_CUT && f.fault() != v1::FAULT_KIND_GCS_LINK_CUT) break;
      std::lock_guard lock(mu_);
      std::erase_if(faults_, [&](const Fault& x) { return x.entity == f.entity_id() && x.kind == f.fault(); });
      if (!f.clear()) {
        const std::uint64_t until =
            f.duration_s() > 0.0 ? now_us_ + static_cast<std::uint64_t>(f.duration_s() * 1e6) : 0;
        faults_.push_back(Fault{f.entity_id(), f.fault(), until});
      }
      break;
    }
    default:
      break;
  }
}

// DEC-037: LoadScenario를 못 받았어도 sim/ctrl/scenario(재발행)에서 시나리오를 얻는다.
// 이름이 이전과 같으면 무시하고(상태·준비 신호 유지), 다르면 다시 적재한다
void Datalink::on_scenario(const Sample& s) {
  v1::Scenario sc;
  if (!parse(s, sc)) {
    log("sim/ctrl/scenario: unparsable Scenario (" + std::to_string(s.payload.size()) + " bytes)");
    return;
  }
  {
    std::lock_guard lock(mu_);
    if (loaded_ && sc.name() == loaded_name_) return;
    load_locked(sc);
    log("scenario received: " + sc.name() + ", " + std::to_string(nodes_.size()) + " entities, seed " +
        std::to_string(seed_));
  }
  send_ready(sc.run().mode() == v1::RUN_MODE_LOCKSTEP);
}

void Datalink::send_ready(bool lockstep) {
  if (!lockstep || cfg_.participant_id.empty()) return;
  v1::FrameDone d;
  d.set_participant(cfg_.participant_id);
  d.set_frame(0);
  const std::string bytes = d.SerializeAsString();
  bus_.put(keys::clock_done(cfg_.participant_id),
           std::span(reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size()),
           encoding_of<v1::FrameDone>());
}

void Datalink::on_tick(const Sample& s) {
  v1::ClockTick tick;
  if (!parse(s, tick)) return;
  {
    std::lock_guard lock(mu_);
    if (tick.sim_time_us() < now_us_ || tick.frame() < frame_) {  // 시각이 되돌아가면(Reset) 큐를 비운다
      reset_locked();
      done_frame_.clear();
      ticks_seen_ = 0;
    }
    waiting_ = tick;
    has_waiting_ = true;
  }
  run_tick();
}

// 다른 참여자의 FrameDone (DEC-039). 참여자는 tx를 보낸 뒤에 FrameDone을 보내므로, 같은 연결의 순서 보장으로
// 이전 프레임의 FrameDone을 받았다면 그 프레임의 tx도 받은 것이다
void Datalink::on_done(const Sample& s) {
  v1::FrameDone d;
  if (!parse(s, d) || d.participant() == cfg_.participant_id) return;
  {
    std::lock_guard lock(mu_);
    if (ticks_seen_ == 0) return;  // 첫 틱 전의 frame 0은 준비 신호다
    auto& f = done_frame_[d.participant()];
    f = std::max(f, d.frame() + 1);
  }
  run_tick();
}

// lockstep에서는 프레임 f-1의 FrameDone을 모든 참여자에게서 받은 뒤에 틱 f를 처리한다. 그래야 메시지가
// 틱보다 먼저 도착하느냐에 따라 처리 프레임이 달라지지 않는다. 대기 중에도 콜백을 막지 않는다
void Datalink::run_tick() {
  std::vector<Out> out;
  v1::ClockTick tick;
  {
    std::lock_guard lock(mu_);
    if (!has_waiting_) return;
    if (waiting_.mode() == v1::RUN_MODE_LOCKSTEP && waiting_.frame() > 0 && ticks_seen_ > 0) {
      for (const auto& p : required_)
        if (const auto it = done_frame_.find(p); it == done_frame_.end() || it->second < waiting_.frame()) return;
    }
    tick = waiting_;
    has_waiting_ = false;
    ++ticks_seen_;
    now_us_ = tick.sim_time_us();
    frame_ = tick.frame();
    std::erase_if(faults_, [&](const Fault& f) { return f.until_us != 0 && now_us_ >= f.until_us; });

    // 이전 틱 시각에 송신된 메시지만 처리한다. 도착이 tick보다 앞서든 뒤서든 같은 틱에서 처리해 결정론을 지킨다
    auto by_order = [](const Pending& a, const Pending& b) {
      return std::tie(a.tx_time_us, a.src, a.key, a.seq, a.arrival) <
             std::tie(b.tx_time_us, b.src, b.key, b.seq, b.arrival);
    };
    const std::uint64_t cutoff = now_us_;
    auto held = std::stable_partition(pending_.begin(), pending_.end(),
                                      [&](const Pending& p) { return p.tx_time_us < cutoff || p.tx_time_us == 0; });
    std::vector<Pending> batch(std::make_move_iterator(pending_.begin()), std::make_move_iterator(held));
    pending_.erase(pending_.begin(), held);
    std::sort(batch.begin(), batch.end(), by_order);
    // 틱당 처리량 상한: 남은 것은 다음 틱으로 넘겨 frame_done을 막지 않는다 (DEC-039)
    std::size_t routes = 0, done = 0;
    for (; done < batch.size(); ++done) {
      const std::size_t n = route_count_locked(batch[done]);
      if (done > 0 && routes + n > cfg_.max_routes_per_tick) break;
      routes += n;
      process_locked(batch[done], out);
    }
    if (done < batch.size()) {
      pending_.insert(pending_.end(), std::make_move_iterator(batch.begin() + static_cast<std::ptrdiff_t>(done)),
                      std::make_move_iterator(batch.end()));
      std::sort(pending_.begin(), pending_.end(), by_order);
    }
    // 입력 큐 상한: 가장 늦은 것부터 버린다
    if (pending_.size() > cfg_.max_pending) {
      std::sort(pending_.begin(), pending_.end(), by_order);
      for (std::size_t i = cfg_.max_pending; i < pending_.size(); ++i) overflow_locked(std::move(pending_[i]));
      pending_.resize(cfg_.max_pending);
    }
    deliver_locked(out);
    flush_overflow_locked(out);
    publish_states_locked(out);
  }
  publish(out);

  if (!cfg_.participant_id.empty()) {
    v1::FrameDone d;
    d.set_participant(cfg_.participant_id);
    d.set_frame(tick.frame());
    const std::string bytes = d.SerializeAsString();
    bus_.put(keys::clock_done(cfg_.participant_id),
             std::span(reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size()),
             encoding_of<v1::FrameDone>());
  }
}

// ---- 상태 ----

void Datalink::load_locked(const v1::Scenario& sc) {
  loaded_ = true;
  loaded_name_ = sc.name();
  // DEC-029: base(비우면 같은 이름의 내장·설정 프로파일, 없으면 default)를 복사하고 값이 있는 필드만 덮어쓴다.
  // base는 앞서 정의한 시나리오 항목도 참조할 수 있다
  profiles_ = base_profiles_;
  for (const auto& lp : sc.link_profiles()) {
    if (lp.name().empty()) {
      log("skip link profile without name");
      continue;
    }
    const LinkProfile* base = &profiles_.at("default");
    if (!lp.base().empty()) {
      if (auto it = profiles_.find(lp.base()); it != profiles_.end())
        base = &it->second;
      else
        log("link profile '" + lp.name() + "': unknown base '" + lp.base() + "', using 'default'");
    } else if (auto it = base_profiles_.find(lp.name()); it != base_profiles_.end()) {
      base = &it->second;
    }
    profiles_[lp.name()] = apply_override(*base, lp);
  }
  warned_.clear();

  nodes_.clear();
  for (const auto& e : sc.entities()) {
    if (!keys::is_valid_entity_id(e.id())) {
      log("skip invalid entity id: " + e.id());
      continue;
    }
    Node& n = node_locked(e.id());
    n.kind = e.kind();
    n.side = e.side();
    n.profile_name = e.link_profile();
    if (e.has_initial() && e.initial().has_position()) {
      n.pos = to_geo(e.initial().position());
      n.has_pos = true;
    }
  }
  if (sc.has_run() && sc.run().seed() != 0) seed_ = sc.run().seed();
  required_.clear();
  if (sc.has_run())
    for (const auto& p : sc.run().participants())
      if (p != cfg_.participant_id) required_.push_back(p);
  done_frame_.clear();
  has_waiting_ = false;
  ticks_seen_ = 0;
  faults_.clear();
  jam_zones_.clear();
  reset_locked();
}

void Datalink::reset_locked() {
  channels_.clear();
  pending_.clear();
  overflow_.clear();
  overflow_dropped_ = 0;
  in_flight_.clear();
  next_state_us_ = now_us_;
}

Datalink::Node& Datalink::node_locked(const std::string& id) {
  auto [it, inserted] = nodes_.try_emplace(id);
  if (inserted) it->second.id = id;
  return it->second;
}

const LinkProfile& Datalink::profile_locked(const Node& n) const {
  const std::string name = n.profile_name.empty() ? std::string(default_profile_name(n.kind)) : n.profile_name;
  if (auto it = profiles_.find(name); it != profiles_.end()) return it->second;
  if (!warned_[name]) {
    warned_[name] = true;
    log("unknown link profile '" + name + "', using 'default'");
  }
  return profiles_.at("default");
}

Datalink::Channel& Datalink::channel_locked(const std::string& src, const std::string& dst) {
  auto it = channels_.find({src, dst});
  if (it == channels_.end()) {
    const LinkProfile& p = profile_locked(nodes_.at(src));
    Channel ch{Rng(link_seed(seed_, src, dst)), {}, TokenBucket(p.bandwidth_bps, p.bucket_bytes, p.queue_len)};
    it = channels_.emplace(std::make_pair(src, dst), std::move(ch)).first;
  }
  return it->second;
}

bool Datalink::comm_node(const Node& n) const {
  // 무전기가 있는 엔티티: UAV·GCS·FPV, 또는 시나리오에 링크 프로파일을 지정한 엔티티
  return n.kind == v1::ENTITY_KIND_UAV || n.kind == v1::ENTITY_KIND_GCS || n.kind == v1::ENTITY_KIND_FPV ||
         !n.profile_name.empty();
}

bool Datalink::peers(const Node& a, const Node& b) const {
  return a.side == v1::SIDE_UNSPECIFIED || b.side == v1::SIDE_UNSPECIFIED || a.side == b.side;
}

bool Datalink::jammed_locked(const Node& n) const {
  if (!n.has_pos) return false;
  for (const auto& [owner, z] : jam_zones_)
    if (in_jam_area(n.pos, z)) return true;
  return false;
}

bool Datalink::cut_locked(const std::string& a, const std::string& b) const {
  auto is_gcs = [this](const std::string& id) {
    const auto it = nodes_.find(id);
    return it != nodes_.end() && it->second.kind == v1::ENTITY_KIND_GCS;
  };
  for (const auto& f : faults_) {
    if (f.entity != a && f.entity != b) continue;
    if (f.kind == v1::FAULT_KIND_LINK_CUT) return true;
    // GCS_LINK_CUT: 대상과 GCS 사이 링크. 대상이 GCS면 그 GCS의 모든 링크
    const std::string& other = f.entity == a ? b : a;
    if (is_gcs(other) || is_gcs(f.entity)) return true;
  }
  return false;
}

PairState Datalink::pair_state_locked(const Node& a, const Node& b) const {
  PairState ps;
  ps.dead = !a.alive || !b.alive;
  ps.cut = cut_locked(a.id, b.id);
  ps.jammed = jammed_locked(a) || jammed_locked(b);
  ps.known = a.has_pos && b.has_pos;
  if (!ps.known) return ps;
  const LinkProfile& pa = profile_locked(a);
  const LinkProfile& pb = profile_locked(b);
  ps.range_m = slant_range_m(a.pos, b.pos);
  ps.snr_db = std::min(snr_db(pa, pb, ps.range_m), snr_db(pb, pa, ps.range_m));
  ps.in_range = in_range(pa, pb, ps.range_m) && in_range(pb, pa, ps.range_m);
  ps.los = line_of_sight(terrain_, a.pos, b.pos, cfg_.los_step_m);
  return ps;
}

v1::DropReason Datalink::static_check_locked(const Node* src, const Node* dst) const {
  if (!src || !dst || !src->alive || !dst->alive) return v1::DROP_REASON_NODE_DEAD;
  if (cut_locked(src->id, dst->id)) return v1::DROP_REASON_FAULT_INJECTED;
  // DEC-009, DEC-028: 수신단이 재밍 영역 안이면 100% 손실. 송신단 위치는 보지 않는다
  if (jammed_locked(*dst)) return v1::DROP_REASON_JAMMED;
  if (!src->has_pos || !dst->has_pos) return v1::DROP_REASON_OUT_OF_RANGE;
  if (!in_range(profile_locked(*src), profile_locked(*dst), slant_range_m(src->pos, dst->pos)))
    return v1::DROP_REASON_OUT_OF_RANGE;
  if (!line_of_sight(terrain_, src->pos, dst->pos, cfg_.los_step_m)) return v1::DROP_REASON_NO_LOS;
  return v1::DROP_REASON_NONE;
}

// ---- 처리 ----

void Datalink::process_locked(Pending& p, std::vector<Out>& out) {
  if (p.env.dst_size() > 0) {
    std::vector<std::string> seen;
    for (const auto& d : p.env.dst()) {
      if (d == p.src || std::find(seen.begin(), seen.end(), d) != seen.end()) continue;
      if (!keys::is_valid_entity_id(d)) {
        log("skip invalid dst '" + d + "' from " + p.src);
        continue;
      }
      seen.push_back(d);
      route_locked(p, d, out);
    }
    return;
  }
  // 브로드캐스트: 같은 편(또는 편 미지정)의 무전기 엔티티 전체
  const auto src = nodes_.find(p.src);
  if (src == nodes_.end()) {
    if (!warned_["src:" + p.src]) {
      warned_["src:" + p.src] = true;
      log("broadcast from unknown entity " + p.src + " ignored");
    }
    return;
  }
  for (const auto& [id, n] : nodes_)
    if (id != p.src && comm_node(n) && peers(src->second, n)) route_locked(p, id, out);
}

std::size_t Datalink::route_count_locked(const Pending& p) const {
  if (p.env.dst_size() > 0) return static_cast<std::size_t>(p.env.dst_size());
  return std::max<std::size_t>(nodes_.size(), 1);
}

// 폭주로 버리는 입력. payload를 지워 메모리를 줄이고 기록 수에도 상한을 둔다
void Datalink::overflow_locked(Pending&& p) {
  if (overflow_.size() >= cfg_.max_overflow_outcomes) {
    ++overflow_dropped_;
    return;
  }
  p.env.clear_payload();
  overflow_.push_back(std::move(p));
}

void Datalink::flush_overflow_locked(std::vector<Out>& out) {
  for (const auto& p : overflow_) {
    if (p.env.dst_size() > 0) {
      for (const auto& d : p.env.dst())
        if (d != p.src && keys::is_valid_entity_id(d))
          outcome_locked(p.src, d, p.env, p.size, v1::DROP_REASON_QUEUE_OVERFLOW, p.tx_time_us, 0, out);
    } else {
      // 브로드캐스트는 수신자별로 펼치지 않고 송신자 한 건으로 기록한다
      outcome_locked(p.src, p.src, p.env, p.size, v1::DROP_REASON_QUEUE_OVERFLOW, p.tx_time_us, 0, out);
    }
  }
  if (!overflow_.empty() || overflow_dropped_ != 0) {
    log("input overflow: " + std::to_string(overflow_.size() + overflow_dropped_) + " messages dropped (" +
        std::to_string(overflow_dropped_) + " without outcome)");
  }
  overflow_.clear();
  overflow_dropped_ = 0;
}

void Datalink::route_locked(const Pending& p, const std::string& dst, std::vector<Out>& out) {
  const auto is = nodes_.find(p.src), id = nodes_.find(dst);
  const Node* s = is == nodes_.end() ? nullptr : &is->second;
  const Node* d = id == nodes_.end() ? nullptr : &id->second;
  v1::DropReason reason = static_check_locked(s, d);
  if (!s || !d) {
    outcome_locked(p.src, dst, p.env, p.size, reason, p.tx_time_us, 0, out);
    return;
  }

  Channel& ch = channel_locked(p.src, dst);
  const LinkProfile& prof = profile_locked(*s);
  ++ch.sent;
  std::uint64_t depart = p.tx_time_us;
  if (reason == v1::DROP_REASON_NONE && !ch.bucket.admit(p.tx_time_us, p.size, depart))
    reason = v1::DROP_REASON_QUEUE_OVERFLOW;
  if (reason == v1::DROP_REASON_NONE && ch.ge.lost(prof.ge, ch.rng)) reason = v1::DROP_REASON_BURST_LOSS;
  if (reason == v1::DROP_REASON_NONE && in_flight_.size() >= cfg_.max_in_flight) reason = v1::DROP_REASON_QUEUE_OVERFLOW;
  if (reason == v1::DROP_REASON_NONE) {
    const std::uint64_t arrive = depart + sample_delay_us(prof, ch.rng);
    in_flight_.push_back(InFlight{arrive, p.tx_time_us, p.src, dst, p.suffix, p.size,
                                  std::make_shared<const v1::LinkEnvelope>(p.env)});
    return;
  }
  ++ch.lost;
  outcome_locked(p.src, dst, p.env, p.size, reason, p.tx_time_us, 0, out);
}

void Datalink::deliver_locked(std::vector<Out>& out) {
  auto due_end = std::stable_partition(in_flight_.begin(), in_flight_.end(),
                                       [this](const InFlight& f) { return f.arrive_us <= now_us_; });
  std::vector<InFlight> due(std::make_move_iterator(in_flight_.begin()), std::make_move_iterator(due_end));
  in_flight_.erase(in_flight_.begin(), due_end);
  std::stable_sort(due.begin(), due.end(), [](const InFlight& a, const InFlight& b) {
    return std::tie(a.arrive_us, a.src, a.dst) < std::tie(b.arrive_us, b.src, b.dst);
  });

  for (const auto& f : due) {
    // 전송 중에 수신자가 죽거나 링크 고장이 들어오면 버린다
    const auto id = nodes_.find(f.dst);
    v1::DropReason reason = v1::DROP_REASON_NONE;
    if (id == nodes_.end() || !id->second.alive)
      reason = v1::DROP_REASON_NODE_DEAD;
    else if (cut_locked(f.src, f.dst))
      reason = v1::DROP_REASON_FAULT_INJECTED;
    if (reason != v1::DROP_REASON_NONE) {
      if (auto it = channels_.find({f.src, f.dst}); it != channels_.end()) ++it->second.lost;
      outcome_locked(f.src, f.dst, *f.env, f.size, reason, f.tx_time_us, 0, out);
      continue;
    }
    v1::LinkEnvelope env = *f.env;
    env.set_rx_time_us(f.arrive_us);
    out.push_back(Out{"swarm/" + f.dst + "/rx/" + f.suffix, env.SerializeAsString(), encoding_of<v1::LinkEnvelope>()});
    outcome_locked(f.src, f.dst, *f.env, f.size, v1::DROP_REASON_NONE, f.tx_time_us, f.arrive_us, out);
  }
}

void Datalink::publish_states_locked(std::vector<Out>& out) {
  if (cfg_.state_period_s <= 0.0 || now_us_ < next_state_us_) return;
  next_state_us_ = now_us_ + static_cast<std::uint64_t>(cfg_.state_period_s * 1e6);

  std::vector<const Node*> comm;
  for (const auto& [id, n] : nodes_)
    if (comm_node(n)) comm.push_back(&n);
  for (std::size_t i = 0; i < comm.size(); ++i) {
    for (std::size_t j = i + 1; j < comm.size(); ++j) {
      const Node& a = *comm[i];
      const Node& b = *comm[j];
      if (!peers(a, b)) continue;
      const PairState ps = pair_state_locked(a, b);

      std::uint64_t sent = 0, lost = 0;
      for (const auto& k : {std::make_pair(a.id, b.id), std::make_pair(b.id, a.id)}) {
        if (auto it = channels_.find(k); it != channels_.end()) {
          sent += it->second.sent;
          lost += it->second.lost;
          it->second.sent = it->second.lost = 0;
        }
      }
      const double loss = sent ? static_cast<double>(lost) / static_cast<double>(sent) : 0.0;

      v1::LinkState st;
      auto* h = st.mutable_header();
      h->set_sim_time_us(now_us_);
      h->set_frame(frame_);
      h->set_source(cfg_.participant_id);
      h->set_seq(state_seq_++);
      st.set_a(a.id);
      st.set_b(b.id);
      st.set_snr_db(ps.snr_db);
      st.set_loss_rate(loss);
      st.set_los(ps.known && ps.los);
      st.set_jammed(ps.jammed);
      const LinkProfile& pa = profile_locked(a);
      const LinkProfile& pb = profile_locked(b);
      const bool unlimited = pa.unlimited_range || pb.unlimited_range;
      if (!ps.known || ps.dead || ps.cut || ps.jammed || !ps.in_range || !ps.los)
        st.set_state(v1::LINK_STATE_KIND_DOWN);
      else if ((!unlimited && ps.snr_db < std::max(pa.snr_min_db, pb.snr_min_db) + cfg_.degraded_margin_db) ||
               loss >= cfg_.degraded_loss_rate)
        st.set_state(v1::LINK_STATE_KIND_DEGRADED);
      else
        st.set_state(v1::LINK_STATE_KIND_UP);
      out.push_back(Out{keys::link_state(a.id, b.id), st.SerializeAsString(), encoding_of<v1::LinkState>()});
    }
  }
}

void Datalink::outcome_locked(const std::string& src, const std::string& dst, const v1::LinkEnvelope& env,
                              std::size_t size, v1::DropReason reason, std::uint64_t tx_us, std::uint64_t rx_us,
                              std::vector<Out>& out) {
  v1::LinkOutcome o;
  o.set_src(src);
  o.set_dst(dst);
  o.set_seq(env.header().seq());
  o.set_iface(env.iface());
  o.set_msg_type(env.msg_type());
  o.set_size_bytes(static_cast<std::uint32_t>(size));
  o.set_outcome(reason == v1::DROP_REASON_NONE ? v1::LINK_OUTCOME_KIND_DELIVERED : v1::LINK_OUTCOME_KIND_DROPPED);
  o.set_reason(reason);
  o.set_tx_time_us(tx_us);
  o.set_rx_time_us(rx_us);
  out.push_back(Out{keys::link_outcome(src, dst), o.SerializeAsString(), encoding_of<v1::LinkOutcome>()});
}

void Datalink::publish(std::vector<Out>& out) {
  for (const auto& o : out)
    bus_.put(o.key, std::span(reinterpret_cast<const std::uint8_t*>(o.bytes.data()), o.bytes.size()), o.encoding);
}

}  // namespace swarm::lnk
