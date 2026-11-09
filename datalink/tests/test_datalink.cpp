// TC-LNK-001~026: 데이터링크 시험. InMemoryBus에 Datalink를 붙이고 tick·truth·tx를 직접 발행한다.
// 인자로 TC ID를 받아 해당 시험만 실행한다
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <span>
#include <string>
#include <tuple>
#include <mutex>
#include <optional>
#include <thread>
#include <vector>

#include "swarm/api/bus.hpp"
#include "swarm/api/keys.hpp"
#include "swarm/dyn/terrain.hpp"
#include "swarm/lnk/channel.hpp"
#include "swarm/lnk/emulator.hpp"
#include "swarm/lnk/profile.hpp"

using namespace swarm;
using namespace swarm::lnk;

namespace {

int g_failures = 0;

void check(bool cond, const char* what) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}

void check_near(double got, double want, double tol, const char* what) {
  if (!(std::abs(got - want) <= tol)) {
    std::fprintf(stderr, "FAIL: %s: got %.12g want %.12g (tol %.3g)\n", what, got, want, tol);
    ++g_failures;
  }
}

template <class M>
void put(Bus& bus, const std::string& key, const M& m) {
  const std::string b = m.SerializeAsString();
  bus.put(key, std::span(reinterpret_cast<const std::uint8_t*>(b.data()), b.size()),
          protobuf_encoding(M::descriptor()->full_name()));
}

template <class M>
M parse(const Sample& s) {
  M m;
  check(m.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size())), "payload parses");
  return m;
}

constexpr double kLat0 = 37.0, kLon0 = 127.5;
constexpr double kMPerDegLat = 110996.0;  // 위도 37° 부근

// 손실·지터 없는 시험 프로파일. 거리 판정은 uav_default와 같다
LinkProfile clean_profile() {
  LinkProfile p = *find_builtin_profile("uav_default");
  p.ge = {0.0, 1.0, 0.0, 0.0};
  p.jitter_ms = 0.0;
  p.latency_ms = 0.0;
  p.bandwidth_bps = 0.0;
  return p;
}

struct Ent {
  std::string id;
  v1::EntityKind kind = v1::ENTITY_KIND_UAV;
  v1::Side side = v1::SIDE_BLUE;
  double north_m = 0.0;
  double alt_m = 1000.0;
  std::string profile = "clean";
  bool alive = true;
};

struct Rig {
  InMemoryBus bus;
  std::vector<v1::LinkOutcome> outcomes;
  std::vector<std::pair<std::string, v1::LinkEnvelope>> rx;
  std::vector<v1::LinkState> states;
  std::vector<v1::FrameDone> dones;
  std::vector<std::unique_ptr<Subscription>> subs;
  std::vector<Ent> ents;
  std::unique_ptr<Datalink> dl;
  std::uint64_t frame = 0;
  std::uint32_t dt_us = 20000;
  std::map<std::string, std::uint32_t> seq;

  explicit Rig(std::vector<Ent> e, DatalinkConfig cfg = {}, const dyn::Terrain* terrain = nullptr, std::uint64_t seed = 7,
               bool via_cmd = false, const std::vector<v1::LinkProfile>& link_profiles = {})
      : ents(std::move(e)) {
    subs.push_back(bus.subscribe("link/outcome/**", [this](const Sample& s) {
      outcomes.push_back(parse<v1::LinkOutcome>(s));
    }));
    subs.push_back(bus.subscribe("swarm/*/rx/**", [this](const Sample& s) {
      rx.emplace_back(s.key, parse<v1::LinkEnvelope>(s));
    }));
    subs.push_back(bus.subscribe("link/state/**", [this](const Sample& s) {
      auto st = parse<v1::LinkState>(s);
      check(s.key == keys::link_state(st.a(), st.b()), "link/state key sorted a<b");
      states.push_back(std::move(st));
    }));
    subs.push_back(bus.subscribe("sim/clock/done/*", [this](const Sample& s) {
      dones.push_back(parse<v1::FrameDone>(s));
    }));
    if (!cfg.profiles.count("clean")) cfg.profiles["clean"] = clean_profile();
    if (cfg.state_period_s == 1.0) cfg.state_period_s = 0.0;
    dl = std::make_unique<Datalink>(bus, terrain, cfg);

    v1::Scenario sc;
    sc.set_name("test");
    sc.mutable_run()->set_seed(seed);
    for (const auto& lp : link_profiles) *sc.add_link_profiles() = lp;
    for (const auto& x : ents) {
      auto* s = sc.add_entities();
      s->set_id(x.id);
      s->set_kind(x.kind);
      s->set_side(x.side);
      s->set_link_profile(x.profile);
      auto* p = s->mutable_initial()->mutable_position();
      p->set_lat_deg(kLat0 + x.north_m / kMPerDegLat);
      p->set_lon_deg(kLon0);
      p->set_alt_m(x.alt_m);
    }
    if (via_cmd) {
      v1::SimCommand cmd;
      *cmd.mutable_load()->mutable_scenario() = sc;
      put(bus, std::string(keys::kSimCtrlCmd), cmd);
    } else {
      dl->load(sc);
    }
  }

  Ent& ent(const std::string& id) {
    for (auto& e : ents)
      if (e.id == id) return e;
    throw std::runtime_error("no entity " + id);
  }

  void truth() {
    v1::TruthFrame tf;
    tf.mutable_header()->set_frame(frame);
    tf.mutable_header()->set_sim_time_us(frame * dt_us);
    for (const auto& x : ents) {
      auto* e = tf.add_entities();
      e->set_id(x.id);
      e->set_kind(x.kind);
      e->set_side(x.side);
      e->set_alive(x.alive);
      auto* p = e->mutable_kinematics()->mutable_position();
      p->set_lat_deg(kLat0 + x.north_m / kMPerDegLat);
      p->set_lon_deg(kLon0);
      p->set_alt_m(x.alt_m);
    }
    put(bus, std::string(keys::kTruthState), tf);
  }

  void tx(const std::string& src, std::vector<std::string> dst, std::size_t payload = 32,
          keys::Iface iface = keys::Iface::P2P, const std::string& msg = "PeerStatus",
          std::optional<std::uint64_t> sim_time_us = std::nullopt) {
    v1::LinkEnvelope env;
    auto* h = env.mutable_header();
    h->set_source(src);
    h->set_frame(frame);
    // 시각을 주면 기체 런타임처럼 찍는다. 안 주면 시각을 비운 지상 발행자다 (DEC-077)
    if (sim_time_us)
      h->set_sim_time_us(*sim_time_us);
    else
      env.set_publisher("rig-ground");
    const std::string key = keys::tx(src, iface, msg);
    h->set_seq(seq[key]++);
    for (auto& d : dst) env.add_dst(d);
    env.set_iface(static_cast<v1::L1Interface>(static_cast<int>(iface) + 1));
    env.set_msg_type("swarm.v1." + msg);
    env.set_payload(std::string(payload, 'x'));
    put(bus, key, env);
  }

  // Core 순서와 같게 truth를 먼저, tick을 나중에 보낸다
  void tick(v1::RunMode mode = v1::RUN_MODE_LOCKSTEP) {
    truth();
    v1::ClockTick t;
    t.set_frame(frame);
    t.set_sim_time_us(frame * dt_us);
    t.set_dt_us(dt_us);
    t.set_mode(mode);
    put(bus, std::string(keys::kClockTick), t);
    ++frame;
  }

  void cmd(const v1::SimCommand& c) { put(bus, std::string(keys::kSimCtrlCmd), c); }

  void fault(const std::string& id, v1::FaultKind k, double duration_s = 0.0, bool clear = false) {
    v1::SimCommand c;
    auto* f = c.mutable_fault();
    f->set_entity_id(id);
    f->set_fault(k);
    f->set_duration_s(duration_s);
    f->set_clear(clear);
    cmd(c);
  }

  void jam(const std::string& owner, double north_m, double radius_m, bool active) {
    v1::TruthEvent ev;
    auto* j = ev.mutable_jam_zone();
    j->set_owner(owner);
    j->set_active(active);
    j->mutable_zone()->mutable_center()->set_lat_deg(kLat0 + north_m / kMPerDegLat);
    j->mutable_zone()->mutable_center()->set_lon_deg(kLon0);
    j->mutable_zone()->set_radius_m(radius_m);
    put(bus, keys::truth_event("jam_zone"), ev);
  }

  // DEC-030: area 재밍 영역(다각형). 꼭짓점은 (북쪽 m, 동쪽 m)
  void jam_area(const std::string& owner, const std::vector<std::pair<double, double>>& ne, double min_alt_m,
                double max_alt_m) {
    v1::TruthEvent ev;
    auto* j = ev.mutable_jam_zone();
    j->set_owner(owner);
    j->set_active(true);
    auto* a = j->mutable_area();
    for (const auto& [n, e] : ne) {
      auto* v = a->mutable_polygon()->add_vertices();
      v->set_lat_deg(kLat0 + n / kMPerDegLat);
      v->set_lon_deg(kLon0 + e / (kMPerDegLat * std::cos(kLat0 * 3.14159265358979 / 180.0)));
    }
    a->set_min_alt_m(min_alt_m);
    a->set_max_alt_m(max_alt_m);
    put(bus, keys::truth_event("jam_zone"), ev);
  }

  // 한 쌍(src→dst) 메시지를 보내고 다음 tick 뒤의 결과
  v1::DropReason send_one(const std::string& src, const std::string& dst) {
    outcomes.clear();
    tx(src, {dst});
    tick();
    for (const auto& o : outcomes)
      if (o.src() == src && o.dst() == dst) return o.reason();
    return static_cast<v1::DropReason>(-1);
  }

  std::size_t count(v1::DropReason r) const {
    return static_cast<std::size_t>(
        std::count_if(outcomes.begin(), outcomes.end(), [r](const v1::LinkOutcome& o) { return o.reason() == r; }));
  }
};

// ---- TC-LNK-001: 자유공간 경로손실·SNR·최대 거리 ----
void tc001() {
  check_near(fspl_db(1000.0, 2400.0), 100.05, 0.02, "FSPL 1 km 2.4 GHz");
  check_near(fspl_db(2000.0, 2400.0) - fspl_db(1000.0, 2400.0), 6.0206, 1e-3, "FSPL +6 dB per doubling");
  const LinkProfile& u = *find_builtin_profile("uav_default");
  // SNR = 30 + 3 + 3 − FSPL + 100
  check_near(snr_db(u, u, 1000.0), 136.0 - 100.05, 0.02, "SNR at 1 km");
  // SNR 10 dB 경계: FSPL 126 dB → d = 10^((126 − 20log10(4πf/c))/20)
  const double d_max = std::pow(10.0, (126.0 - 20.0 * std::log10(4.0 * 3.14159265358979 * 2.4e9 / 299792458.0)) / 20.0);
  check(in_range(u, u, d_max * 0.99), "in range just inside");
  check(!in_range(u, u, d_max * 1.01), "out of range just outside");
  LinkProfile capped = u;
  capped.max_range_m = 5000.0;
  check(!in_range(capped, u, 6000.0), "max_range_m cap");
  check(in_range(*find_builtin_profile("ideal"), u, 1e7), "ideal unlimited");
  check_near(slant_range_m({37.0, 127.0, 0.0}, {37.0, 127.0, 1000.0}), 1000.0, 1e-6, "slant vertical");

  // 버스: 10 km 전달, 30 km OUT_OF_RANGE
  Rig r({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 10000.0}, {"uav-003", v1::ENTITY_KIND_UAV,
                                                                                    v1::SIDE_BLUE, 30000.0}});
  r.tick();
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NONE, "10 km delivered");
  check(r.send_one("uav-001", "uav-003") == v1::DROP_REASON_OUT_OF_RANGE, "30 km out of range");
  check(r.send_one("uav-003", "uav-001") == v1::DROP_REASON_OUT_OF_RANGE, "30 km reverse out of range");
}

// ---- TC-LNK-002: 가시선(지형 능선, 지구 곡률) ----
void tc002() {
  // 위도 37.0~37.2, 0.05° 격자. 37.1° 행만 2000 m 능선
  dyn::GridSpec g{kLat0, kLon0 - 0.05, 0.05, 0.05, 5, 3};
  std::vector<float> h(15, 0.0f);
  for (int c = 0; c < 3; ++c) h[2 * 3 + c] = 2000.0f;
  dyn::GridTerrain ridge(g, h);
  const double north_ridge = 0.1 * kMPerDegLat;

  check(line_of_sight(nullptr, {37, 127, 0}, {38, 127, 0}), "no terrain: LOS");
  check(!line_of_sight(&ridge, {37.02, kLon0, 500}, {37.18, kLon0, 500}), "ridge blocks at 500 m");
  check(line_of_sight(&ridge, {37.02, kLon0, 3000}, {37.18, kLon0, 3000}), "clear above ridge");

  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, north_ridge - 8000.0, 500.0},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, north_ridge + 8000.0, 500.0}},
        {}, &ridge);
  r.tick();
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NO_LOS, "bus: ridge NO_LOS");
  check(!r.dl->pair_state("uav-001", "uav-002").los, "pair_state los false");
  r.ent("uav-001").alt_m = 3000.0;
  r.ent("uav-002").alt_m = 3000.0;
  r.tick();
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NONE, "bus: above ridge delivered");

  // 평지 + 곡률: 30 km, 고도 10 m면 처짐 0.25·d²/(2kR) ≈ 13 m로 차단, 1000 m면 통과
  dyn::FlatTerrain flat(0.0);
  check(!line_of_sight(&flat, {37.0, kLon0, 10}, {37.0 + 30000.0 / kMPerDegLat, kLon0, 10}), "curvature blocks 10 m");
  check(line_of_sight(&flat, {37.0, kLon0, 1000}, {37.0 + 30000.0 / kMPerDegLat, kLon0, 1000}), "curvature ok 1000 m");
}

// ---- TC-LNK-003: 재밍 영역 100% 손실 (DEC-009, DEC-028 수신단) ----
void tc003() {
  Rig r({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 5000.0}, {"uav-003", v1::ENTITY_KIND_UAV,
                                                                                   v1::SIDE_BLUE, -5000.0}});
  r.tick();
  r.jam("jam-01", 5000.0, 2000.0, true);
  int jammed = 0;
  for (int i = 0; i < 100; ++i) jammed += r.send_one("uav-001", "uav-002") == v1::DROP_REASON_JAMMED;
  check(jammed == 100, "all messages to jammed receiver dropped JAMMED");
  check(r.send_one("uav-001", "uav-003") == v1::DROP_REASON_NONE, "link outside zone unaffected");
  check(r.dl->pair_state("uav-001", "uav-002").jammed, "pair_state jammed");
  r.jam("jam-01", 5000.0, 2000.0, false);
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NONE, "zone deactivated: delivered");
}

// ---- TC-LNK-004: Gilbert-Elliott 버스트 통계 ----
void tc004() {
  const GilbertElliott p{0.05, 0.25, 0.0, 1.0};
  const double expect_loss = p.p_gb / (p.p_gb + p.p_bg);  // 1/6
  Rng rng(42);
  GilbertElliottChannel ch;
  const int n = 400000;
  int lost = 0, bursts = 0, run = 0;
  for (int i = 0; i < n; ++i) {
    if (ch.lost(p, rng)) {
      ++lost;
      ++run;
    } else if (run > 0) {
      ++bursts;
      run = 0;
    }
  }
  check_near(static_cast<double>(lost) / n, expect_loss, 0.005, "GE steady-state loss");
  check_near(static_cast<double>(lost) / bursts, 1.0 / p.p_bg, 0.1, "GE mean burst length 1/p_bg");

  // 버스: 같은 GE 프로파일로 5000개
  DatalinkConfig cfg;
  LinkProfile ge = clean_profile();
  ge.ge = p;
  cfg.profiles["ge"] = ge;
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "ge"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0, 1000.0, "ge"}},
        cfg);
  r.tick();
  r.outcomes.clear();
  for (int k = 0; k < 500; ++k) {
    for (int i = 0; i < 10; ++i) r.tx("uav-001", {"uav-002"});
    r.tick();
  }
  const double loss = static_cast<double>(r.count(v1::DROP_REASON_BURST_LOSS)) / 5000.0;
  check(r.outcomes.size() == 5000, "bus: 5000 outcomes");
  check_near(loss, expect_loss, 0.04, "bus: GE loss rate");
}

// ---- TC-LNK-005: 지연·지터 분포와 tick 기준 전달 시점 ----
void tc005() {
  LinkProfile p;
  p.latency_ms = 30.0;
  p.jitter_ms = 5.0;
  Rng rng(1);
  const int n = 100000;
  double sum = 0.0, sq = 0.0;
  for (int i = 0; i < n; ++i) {
    const double d = static_cast<double>(sample_delay_us(p, rng));
    sum += d;
    sq += d * d;
  }
  const double mean = sum / n, sd = std::sqrt(sq / n - mean * mean);
  check_near(mean, 30000.0, 100.0, "delay mean");
  check_near(sd, 5000.0, 100.0, "delay stddev");
  p.latency_ms = 1.0;
  p.jitter_ms = 10.0;
  bool nonneg = true;
  for (int i = 0; i < 10000; ++i) nonneg = nonneg && sample_delay_us(p, rng) < (1ULL << 62);
  check(nonneg, "delay truncated at 0");

  // 버스: 지연 50 ms, 프레임 20 ms. t=20 ms 송신 → 도착 70 ms → t=80 ms tick에서 전달.
  // lockstep이므로 rx_time은 전달 틱 시각 아래로 내려가지 않는다 (DEC-054). realtime 값은 TC-LNK-023에서 본다
  DatalinkConfig cfg;
  LinkProfile fixed = clean_profile();
  fixed.latency_ms = 50.0;
  cfg.profiles["fixed"] = fixed;
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "fixed"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0, 1000.0, "fixed"}},
        cfg);
  r.tick();  // t=0
  r.tick();  // t=20 ms
  r.tx("uav-001", {"uav-002"});
  r.tick();  // t=40: 처리, 아직 전송 중
  r.tick();  // t=60
  check(r.rx.empty(), "not delivered before arrival time");
  check(r.dl->in_flight() == 1, "one message in flight");
  r.tick();  // t=80: 전달
  check(r.rx.size() == 1, "delivered at first tick after arrival");
  if (!r.rx.empty()) check(r.rx[0].second.rx_time_us() == 80000, "rx_time = max(tx + latency, T_k)");
  check(r.outcomes.size() == 1 && r.outcomes[0].tx_time_us() == 20000 && r.outcomes[0].rx_time_us() == 80000,
        "outcome tx/rx time");
}

// ---- TC-LNK-006: 토큰 버킷 대역폭 큐 ----
void tc006() {
  TokenBucket tb(8000.0, 100.0, 3);  // 1000 B/s, 깊이 100 B, 대기 3
  std::uint64_t dep = 0;
  check(tb.admit(0, 100, dep) && dep == 0, "first uses burst tokens");
  check(tb.admit(0, 100, dep) && dep == 100000, "second waits 100 ms");
  check(tb.admit(0, 100, dep) && dep == 200000, "third waits 200 ms");
  check(tb.admit(0, 100, dep) && dep == 300000, "fourth waits 300 ms");
  check(!tb.admit(0, 100, dep), "fifth overflows (queue 3)");
  check(tb.queued(150000) == 2, "two left in queue at 150 ms");
  check(tb.admit(150000, 100, dep) && dep == 400000, "FIFO after queue");
  TokenBucket unlimited(0.0, 0.0, 1);
  check(unlimited.admit(5, 1 << 20, dep) && dep == 5, "rate 0 is unlimited");

  // 버스: 깊이 1 B, 대기 2 → 한 tick에 10개 보내면 2개 대기, 8개 QUEUE_OVERFLOW
  DatalinkConfig cfg;
  LinkProfile slow = clean_profile();
  slow.bandwidth_bps = 64000.0;
  slow.bucket_bytes = 1.0;
  slow.queue_len = 2;
  cfg.profiles["slow"] = slow;
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "slow"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0, 1000.0, "slow"}},
        cfg);
  r.tick();
  for (int i = 0; i < 10; ++i) r.tx("uav-001", {"uav-002"});
  for (int k = 0; k < 20; ++k) r.tick();
  check(r.count(v1::DROP_REASON_QUEUE_OVERFLOW) == 8, "bus: 8 queue overflow");
  check(r.rx.size() == 2, "bus: 2 delivered after draining");
}

// ---- TC-LNK-007: 고장 주입 LINK_CUT, GCS_LINK_CUT (REQ-LNK-002, REQ-LNK-003) ----
void tc007() {
  Rig r({{"gcs-01", v1::ENTITY_KIND_GCS}, {"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 2000.0}});
  r.tick();
  r.fault("uav-001", v1::FAULT_KIND_LINK_CUT);
  check(r.send_one("gcs-01", "uav-001") == v1::DROP_REASON_FAULT_INJECTED, "LINK_CUT gcs->uav1");
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_FAULT_INJECTED, "LINK_CUT uav1->uav2");
  check(r.send_one("gcs-01", "uav-002") == v1::DROP_REASON_NONE, "LINK_CUT leaves others");
  r.fault("uav-001", v1::FAULT_KIND_LINK_CUT, 0.0, true);
  check(r.send_one("gcs-01", "uav-001") == v1::DROP_REASON_NONE, "LINK_CUT cleared");

  // GCS_LINK_CUT 0.1 s: uav-002↔gcs만 차단, 시간이 지나면 복구
  r.fault("uav-002", v1::FAULT_KIND_GCS_LINK_CUT, 0.1);
  check(r.send_one("uav-002", "gcs-01") == v1::DROP_REASON_FAULT_INJECTED, "GCS_LINK_CUT uav2->gcs");
  check(r.send_one("gcs-01", "uav-002") == v1::DROP_REASON_FAULT_INJECTED, "GCS_LINK_CUT gcs->uav2");
  check(r.send_one("uav-002", "uav-001") == v1::DROP_REASON_NONE, "GCS_LINK_CUT keeps uav-uav");
  for (int i = 0; i < 6; ++i) r.tick();
  check(r.send_one("gcs-01", "uav-002") == v1::DROP_REASON_NONE, "GCS_LINK_CUT expired");

  // 대상이 GCS면 그 GCS의 모든 링크
  r.fault("gcs-01", v1::FAULT_KIND_GCS_LINK_CUT);
  check(r.send_one("gcs-01", "uav-001") == v1::DROP_REASON_FAULT_INJECTED, "GCS target: gcs->uav1");
  check(r.send_one("uav-002", "gcs-01") == v1::DROP_REASON_FAULT_INJECTED, "GCS target: uav2->gcs");
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NONE, "GCS target: uav-uav ok");
  // 링크 외 고장은 무시
  r.fault("uav-001", v1::FAULT_KIND_ENGINE);
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NONE, "ENGINE fault ignored");
}

// ---- TC-LNK-008: lockstep 결정론 ----
std::vector<std::tuple<std::string, std::string, std::uint32_t, int, std::uint64_t>> run_det(std::uint64_t seed,
                                                                                               bool reverse) {
  DatalinkConfig cfg;
  LinkProfile noisy = *find_builtin_profile("uav_default");
  noisy.ge = {0.1, 0.3, 0.02, 0.8};
  noisy.jitter_ms = 8.0;
  noisy.bandwidth_bps = 16000.0;  // 링크당 약 3000 B/s 송신 > 2000 B/s
  noisy.bucket_bytes = 200.0;
  noisy.queue_len = 4;
  cfg.profiles["noisy"] = noisy;
  std::vector<Ent> e;
  for (int i = 0; i < 6; ++i) {
    char id[16];
    std::snprintf(id, sizeof(id), "uav-%03d", i + 1);
    e.push_back({id, v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, i * 5000.0, 1000.0, "noisy"});
  }
  Rig r(e, cfg, nullptr, seed);
  std::vector<int> order = {0, 1, 2, 3, 4, 5};
  if (reverse) std::reverse(order.begin(), order.end());
  for (int k = 0; k < 150; ++k) {
    for (int i : order) r.tx(e[i].id, {});
    r.tick();
  }
  std::vector<std::tuple<std::string, std::string, std::uint32_t, int, std::uint64_t>> out;
  for (const auto& o : r.outcomes) out.emplace_back(o.src(), o.dst(), o.seq(), o.reason(), o.rx_time_us());
  return out;
}

void tc008() {
  const auto a = run_det(1234, false);
  const auto b = run_det(1234, true);
  const auto c = run_det(99, false);
  check(a.size() > 1000, "enough outcomes");
  check(a == b, "same seed, different arrival order: identical outcome sequence");
  check(a != c, "different seed: different outcomes");
  std::map<int, int> by;
  for (const auto& x : a) ++by[std::get<3>(x)];
  check(by[v1::DROP_REASON_NONE] > 0 && by[v1::DROP_REASON_BURST_LOSS] > 0 && by[v1::DROP_REASON_QUEUE_OVERFLOW] > 0 &&
            by[v1::DROP_REASON_OUT_OF_RANGE] > 0,
        "mix of delivered, burst, queue and range outcomes");
}

// ---- TC-LNK-009: 중계 기본 동작 (키, 브로드캐스트, 생존, FrameDone, LoadScenario) ----
void tc009() {
  DatalinkConfig cfg;
  cfg.participant_id = "datalink-0";
  Rig r({{"gcs-01", v1::ENTITY_KIND_GCS},
         {"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 2000.0},
         {"uav-003", v1::ENTITY_KIND_UAV, v1::SIDE_RED, 2000.0},
         {"tgt-001", v1::ENTITY_KIND_GROUND_TARGET, v1::SIDE_BLUE, 1000.0, 0.0, ""}},
        cfg, nullptr, 31, /*via_cmd=*/true);
  check(r.dl->seed() == 31, "seed from LoadScenario.run");
  r.tick();
  check(r.dones.size() == 1 && r.dones[0].participant() == "datalink-0" && r.dones[0].frame() == 0,
        "FrameDone per tick");

  r.tx("gcs-01", {"uav-001"}, 40, keys::Iface::C2, "TaskCommand");
  r.tick();
  check(r.rx.size() == 1, "unicast delivered once");
  if (!r.rx.empty()) {
    check(r.rx[0].first == "swarm/uav-001/rx/c2/TaskCommand", "rx key");
    check(r.rx[0].second.header().source() == "gcs-01", "source preserved");
    check(r.rx[0].second.payload() == std::string(40, 'x'), "payload preserved");
    check(r.rx[0].second.rx_time_us() == 20000, "lockstep zero latency: rx_time = T_k (DEC-054)");
  }
  check(r.outcomes.size() == 1 && r.outcomes[0].outcome() == v1::LINK_OUTCOME_KIND_DELIVERED &&
            r.outcomes[0].iface() == v1::L1_INTERFACE_C2 && r.outcomes[0].msg_type() == "swarm.v1.TaskCommand",
        "outcome fields");

  // 브로드캐스트: 같은 편 무전기 엔티티(gcs-01, uav-002)만. 적(uav-003)·무전기 없는 표적·자신 제외
  r.rx.clear();
  r.outcomes.clear();
  r.tx("uav-001", {});
  r.tick();
  std::vector<std::string> got;
  for (const auto& [k, e] : r.rx) got.push_back(k);
  std::sort(got.begin(), got.end());
  check(got == std::vector<std::string>{"swarm/gcs-01/rx/p2p/PeerStatus", "swarm/uav-002/rx/p2p/PeerStatus"},
        "broadcast recipients");

  // 존재하지 않는 수신자, 죽은 수신자, 자기 자신
  check(r.send_one("uav-001", "uav-999") == v1::DROP_REASON_NODE_DEAD, "unknown dst NODE_DEAD");
  r.ent("uav-002").alive = false;
  r.tick();
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NODE_DEAD, "dead dst NODE_DEAD");
  r.outcomes.clear();
  r.tx("uav-001", {"uav-001"});
  r.tick();
  check(r.outcomes.empty(), "self destination skipped");
  check(r.dones.size() == r.frame, "FrameDone every tick");
}

// ---- TC-LNK-010: LinkState 주기 발행 ----
void tc010() {
  DatalinkConfig cfg;
  cfg.state_period_s = 0.1;
  cfg.profiles["clean"] = clean_profile();
  Rig r({{"uav-001"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 3000.0},
         {"uav-003", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 15000.0},
         {"uav-004", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 40000.0}},
        cfg);
  r.tick();
  check(r.states.size() == 6, "6 pairs at first tick");
  auto find = [&](const std::string& a, const std::string& b) -> const v1::LinkState* {
    for (auto it = r.states.rbegin(); it != r.states.rend(); ++it)
      if (it->a() == a && it->b() == b) return &*it;
    return nullptr;
  };
  auto s12 = find("uav-001", "uav-002");
  auto s13 = find("uav-001", "uav-003");
  auto s14 = find("uav-001", "uav-004");
  check(s12 && s12->state() == v1::LINK_STATE_KIND_UP && s12->los(), "3 km UP");
  check(s13 && s13->state() == v1::LINK_STATE_KIND_DEGRADED, "15 km DEGRADED (SNR margin)");
  check(s14 && s14->state() == v1::LINK_STATE_KIND_DOWN, "40 km DOWN");
  if (s12) check_near(s12->snr_db(), 136.0 - fspl_db(3000.0, 2400.0), 0.1, "SNR reported");

  r.states.clear();
  for (int i = 0; i < 4; ++i) r.tick();  // 20~80 ms: 주기 전
  check(r.states.empty(), "no state before period");
  r.jam("jam-01", 3000.0, 500.0, true);
  r.fault("uav-001", v1::FAULT_KIND_LINK_CUT, 0.05);
  r.tx("uav-001", {"uav-002"});
  r.tick();  // 100 ms
  s12 = find("uav-001", "uav-002");
  check(s12 && s12->state() == v1::LINK_STATE_KIND_DOWN && s12->jammed() && s12->loss_rate() == 1.0,
        "jammed pair DOWN with loss 1");
  check(s12 && s12->header().sim_time_us() == 100000, "state header time");
}

// ---- TC-LNK-011: 프로파일 표, 시드·초기화 명령 ----
void tc011() {
  for (const char* n : {"default", "uav_default", "gcs_default", "fpv_default", "ideal"})
    check(find_builtin_profile(n) != nullptr, n);
  check(find_builtin_profile("nope") == nullptr, "unknown builtin null");
  check(default_profile_name(v1::ENTITY_KIND_GCS) == "gcs_default", "gcs default name");
  check(default_profile_name(v1::ENTITY_KIND_UAV) == "uav_default", "uav default name");
  check(default_profile_name(v1::ENTITY_KIND_GROUND_TARGET) == "default", "fallback default name");
  const auto& g = *find_builtin_profile("gcs_default");
  const auto& u = *find_builtin_profile("uav_default");
  check(in_range(g, u, 100000.0) && in_range(u, g, 100000.0), "GCS link 100 km both ways");
  check(!in_range(u, u, 100000.0), "UAV-UAV not 100 km");
  check(link_seed(1, "a-1", "b-1") != link_seed(1, "b-1", "a-1"), "directional link seed");

  std::vector<std::string> logs;
  DatalinkConfig cfg;
  cfg.log = [&](const std::string& m) { logs.push_back(m); };
  LinkProfile slow = clean_profile();
  slow.latency_ms = 500.0;
  cfg.profiles["slow"] = slow;
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "slow"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0, 1000.0, "mystery"}},
        cfg);
  r.tick();
  check(r.send_one("uav-002", "uav-001") != static_cast<v1::DropReason>(-1), "unknown profile still routes");
  check(std::any_of(logs.begin(), logs.end(), [](const std::string& m) { return m.find("mystery") != std::string::npos; }),
        "unknown profile logged");

  v1::SimCommand start;
  start.mutable_start()->set_seed(555);
  r.cmd(start);
  check(r.dl->seed() == 555, "Start.seed overrides");
  r.tx("uav-001", {"uav-002"});
  r.tick();
  check(r.dl->in_flight() == 1, "in flight before reset");
  v1::SimCommand reset;
  reset.mutable_reset();
  r.cmd(reset);
  check(r.dl->in_flight() == 0, "Reset clears in-flight");
}

// ---- TC-LNK-012: 송신단만 재밍 영역 안이면 전달 (DEC-028) ----
void tc012() {
  Rig r({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 5000.0}});
  r.tick();
  r.jam("jam-01", 5000.0, 2000.0, true);  // uav-002만 영역 안
  int delivered = 0, jammed = 0;
  for (int i = 0; i < 20; ++i) {
    delivered += r.send_one("uav-002", "uav-001") == v1::DROP_REASON_NONE;
    jammed += r.send_one("uav-001", "uav-002") == v1::DROP_REASON_JAMMED;
  }
  check(delivered == 20, "sender inside zone: delivered");
  check(jammed == 20, "receiver inside zone: JAMMED");
  check(r.dl->pair_state("uav-001", "uav-002").jammed, "link/state jammed if either end inside");
  check(r.dl->pair_state("uav-002", "uav-001").jammed, "link/state jammed symmetric");
}

// ---- TC-LNK-013: Area 재밍 판정 — 다각형, 고도대, zone 대체 (DEC-030) ----
void tc013() {
  // 오목 다각형(북쪽이 열린 U자, 홈은 lat 1~4 × lon 1~3). 좌표는 (lat, lon)
  const std::vector<GeoPoint> u = {{0, 0, 0}, {0, 4, 0}, {4, 4, 0}, {4, 3, 0},
                                   {1, 3, 0}, {1, 1, 0}, {4, 1, 0}, {4, 0, 0}};
  check(in_polygon({0.5, 0.5, 0}, u), "polygon: corner inside");
  check(in_polygon({3.5, 0.5, 0}, u), "polygon: arm inside");
  check(!in_polygon({2.0, 2.0, 0}, u), "polygon: notch outside");
  check(!in_polygon({2.0, 5.0, 0}, u), "polygon: far outside");
  check(!in_polygon({2.0, -0.1, 0}, u), "polygon: just west outside");

  JamArea a;
  a.polygon = {{0, 0, 0}, {0, 1, 0}, {1, 1, 0}, {1, 0, 0}};
  a.min_alt_m = 500.0;
  a.max_alt_m = 2000.0;
  check(in_jam_area({0.5, 0.5, 500.0}, a), "alt band: min inclusive");
  check(in_jam_area({0.5, 0.5, 2000.0}, a), "alt band: max inclusive");
  check(!in_jam_area({0.5, 0.5, 499.9}, a), "alt band: below min");
  check(!in_jam_area({0.5, 0.5, 2000.1}, a), "alt band: above max");
  check(!in_jam_area({1.5, 0.5, 1000.0}, a), "alt band ok but outside polygon");
  a.max_alt_m = 0.0;
  check(in_jam_area({0.5, 0.5, 1.0e5}, a), "max_alt 0: no upper bound");
  JamArea c;
  c.center = {37.0, 127.0, 0.0};
  c.radius_m = 1000.0;
  check(in_jam_area({37.0 + 900.0 / kMPerDegLat, 127.0, -50.0}, c), "legacy circle: altitude ignored");
  check(!in_jam_area({37.0 + 1100.0 / kMPerDegLat, 127.0, 0.0}, c), "legacy circle: outside radius");

  // 버스: 북쪽 4~6 km, 동서 ±1 km 사각형, 고도 500~1500 m
  Rig r({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 5000.0, 1000.0},
         {"uav-003", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 5000.0, 3000.0}});
  r.tick();
  r.jam_area("jam-01", {{4000, -1000}, {6000, -1000}, {6000, 1000}, {4000, 1000}}, 500.0, 1500.0);
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_JAMMED, "bus: inside polygon and band JAMMED");
  check(r.send_one("uav-001", "uav-003") == v1::DROP_REASON_NONE, "bus: above band delivered");
  r.ent("uav-002").alt_m = 400.0;
  r.tick();
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_NONE, "bus: below band delivered");

  // area가 있으면 폐기 예정 zone은 읽지 않는다
  v1::TruthEvent ev;
  auto* j = ev.mutable_jam_zone();
  j->set_owner("jam-01");
  j->set_active(true);
  j->mutable_zone()->mutable_center()->set_lat_deg(kLat0 + 5000.0 / kMPerDegLat);
  j->mutable_zone()->mutable_center()->set_lon_deg(kLon0);
  j->mutable_zone()->set_radius_m(5000.0);
  auto* circ = j->mutable_area()->mutable_circle();
  circ->mutable_center()->set_lat_deg(kLat0 + 20000.0 / kMPerDegLat);
  circ->mutable_center()->set_lon_deg(kLon0);
  circ->set_radius_m(100.0);
  put(r.bus, keys::truth_event("jam_zone"), ev);
  check(r.send_one("uav-001", "uav-003") == v1::DROP_REASON_NONE, "area takes precedence over zone");
  j->clear_area();
  put(r.bus, keys::truth_event("jam_zone"), ev);
  check(r.send_one("uav-001", "uav-003") == v1::DROP_REASON_JAMMED, "zone used when area absent");
}

// ---- TC-LNK-014: 시나리오 link_profiles 적용 (DEC-029) ----
void tc014() {
  // 단위: 값이 있는 필드만 덮어쓰고 ge는 네 값 모두 대체
  v1::LinkProfile spec;
  spec.set_name("x");
  spec.set_latency_ms(77.0);
  spec.set_queue_len(0);
  spec.mutable_ge()->set_p_gb(0.2);
  const LinkProfile& u = *find_builtin_profile("uav_default");
  const LinkProfile o = apply_override(u, spec);
  check(o.name == "x", "override name");
  check(o.latency_ms == 77.0 && o.queue_len == 0, "set fields overridden (explicit 0 too)");
  check(o.tx_power_dbm == u.tx_power_dbm && o.jitter_ms == u.jitter_ms && o.bandwidth_bps == u.bandwidth_bps,
        "unset fields kept");
  check(o.ge.p_gb == 0.2 && o.ge.p_bg == 0.0 && o.ge.loss_good == 0.0 && o.ge.loss_bad == 0.0,
        "ge replaces all four values");

  std::vector<std::string> logs;
  DatalinkConfig cfg;
  cfg.log = [&](const std::string& m) { logs.push_back(m); };
  std::vector<v1::LinkProfile> lps(4);
  // short: clean(설정 프로파일) 기반, 최대 5 km
  lps[0].set_name("short");
  lps[0].set_base("clean");
  lps[0].set_max_range_m(5000.0);
  // short_slow: 앞 항목 short 기반, 지연 100 ms
  lps[1].set_name("short_slow");
  lps[1].set_base("short");
  lps[1].set_latency_ms(100.0);
  // clean: base 비움 → 같은 이름 프로파일 위에 지연 40 ms
  lps[2].set_name("clean");
  lps[2].set_latency_ms(40.0);
  // orphan: 없는 base → default + 로그
  lps[3].set_name("orphan");
  lps[3].set_base("nope");
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "short"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 10000.0, 1000.0, "clean"},
         {"uav-003", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0, 1000.0, "short_slow"},
         {"uav-004", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 2000.0, 1000.0, "orphan"}},
        cfg, nullptr, 7, /*via_cmd=*/true, lps);
  r.tick();
  check(r.send_one("uav-001", "uav-002") == v1::DROP_REASON_OUT_OF_RANGE, "short: 10 km beyond max_range 5 km");
  check(r.send_one("uav-002", "uav-001") == v1::DROP_REASON_OUT_OF_RANGE, "short as receiver: max_range applies");

  // clean 재정의: 손실·지터 없음은 유지, 지연만 40 ms. 수신은 orphan(default, 거리 상한 없음)
  r.rx.clear();
  const std::uint64_t t_clean = (r.frame - 1) * r.dt_us;
  r.tx("uav-002", {"uav-004"});
  for (int i = 0; i < 4; ++i) r.tick();
  check(r.rx.size() == 1 && r.rx[0].second.rx_time_us() == t_clean + 40000, "same-name base kept, latency 40 ms");

  // short_slow: short의 max_range 상속 + 지연 100 ms
  r.rx.clear();
  const std::uint64_t t_slow = (r.frame - 1) * r.dt_us;
  r.tx("uav-003", {"uav-001"});
  for (int i = 0; i < 7; ++i) r.tick();
  check(r.rx.size() == 1 && r.rx[0].second.rx_time_us() == t_slow + 100000, "chained base, latency 100 ms");
  r.ent("uav-003").north_m = 6000.0;  // uav-001과 6 km
  r.tick();
  check(r.send_one("uav-003", "uav-001") == v1::DROP_REASON_OUT_OF_RANGE, "chained base inherits max_range");

  check(std::any_of(logs.begin(), logs.end(), [](const std::string& m) { return m.find("'nope'") != std::string::npos; }),
        "unknown base logged");
  check(std::none_of(logs.begin(), logs.end(),
                     [](const std::string& m) { return m.find("unknown link profile") != std::string::npos; }),
        "scenario profiles resolved by name");

  // 다시 불러오면 이전 시나리오의 재정의는 사라진다
  v1::Scenario sc;
  for (const char* id : {"uav-001", "uav-002"}) {
    auto* e = sc.add_entities();
    e->set_id(id);
    e->set_kind(v1::ENTITY_KIND_UAV);
    e->set_link_profile("short");
  }
  r.dl->load(sc);
  r.tick();
  r.send_one("uav-001", "uav-002");
  check(std::any_of(logs.begin(), logs.end(),
                    [](const std::string& m) { return m.find("unknown link profile 'short'") != std::string::npos; }),
        "reload drops previous scenario profiles");
}

// ---- TC-LNK-015: 브로드캐스트에서 닿지 않는 수신자마다 outcome (DEC-032) ----
void tc015() {
  Rig r({{"uav-001"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0},
         {"uav-003", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 40000.0},
         {"uav-004", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 2000.0},
         {"uav-005", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, -5000.0},
         {"uav-006", v1::ENTITY_KIND_UAV, v1::SIDE_RED, 1000.0}});
  r.ent("uav-004").alive = false;
  r.tick();
  r.jam("jam-01", -5000.0, 1000.0, true);
  r.outcomes.clear();
  r.rx.clear();
  r.tx("uav-001", {});
  r.tick();
  std::map<std::string, std::vector<v1::DropReason>> by;
  for (const auto& o : r.outcomes) by[o.dst()].push_back(o.reason());
  using V = std::vector<v1::DropReason>;
  check(by.size() == 4, "one outcome per same-side recipient");
  check(by["uav-002"] == V{v1::DROP_REASON_NONE}, "uav-002 delivered");
  check(by["uav-003"] == V{v1::DROP_REASON_OUT_OF_RANGE}, "uav-003 OUT_OF_RANGE outcome");
  check(by["uav-004"] == V{v1::DROP_REASON_NODE_DEAD}, "uav-004 NODE_DEAD outcome");
  check(by["uav-005"] == V{v1::DROP_REASON_JAMMED}, "uav-005 JAMMED outcome");
  check(!by.count("uav-006"), "other side: no outcome");
  for (const auto& o : r.outcomes)
    if (o.reason() != v1::DROP_REASON_NONE) check(o.outcome() == v1::LINK_OUTCOME_KIND_DROPPED, "dropped kind");
  check(r.rx.size() == 1 && r.rx[0].first == "swarm/uav-002/rx/p2p/PeerStatus", "only reachable recipient gets rx");
}

// ---- TC-LNK-016: sim/ctrl/scenario 적재와 lockstep 준비 신호 (DEC-037) ----
v1::Scenario scenario_msg(const std::string& name, v1::RunMode mode, double latency_ms, double north_b_m) {
  v1::Scenario sc;
  sc.set_name(name);
  sc.mutable_run()->set_mode(mode);
  sc.mutable_run()->set_seed(5);
  auto* lp = sc.add_link_profiles();
  lp->set_name("slow");
  lp->set_base("uav_default");
  lp->set_latency_ms(latency_ms);
  for (const auto& [id, north] : {std::pair<std::string, double>{"uav-001", 0.0}, {"uav-002", north_b_m}}) {
    auto* e = sc.add_entities();
    e->set_id(id);
    e->set_kind(v1::ENTITY_KIND_UAV);
    e->set_side(v1::SIDE_BLUE);
    e->set_link_profile("slow");
    auto* p = e->mutable_initial()->mutable_position();
    p->set_lat_deg(kLat0 + north / kMPerDegLat);
    p->set_lon_deg(kLon0);
    p->set_alt_m(1000.0);
  }
  return sc;
}

void tc016() {
  InMemoryBus bus;
  std::vector<v1::FrameDone> dones;
  auto sub = bus.subscribe("sim/clock/done/*", [&](const Sample& s) { dones.push_back(parse<v1::FrameDone>(s)); });
  DatalinkConfig cfg;
  cfg.state_period_s = 0.0;
  Datalink dl(bus, nullptr, cfg);

  // LoadScenario 없이 sim/ctrl/scenario만으로 적재, lockstep이면 준비 신호 1건
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("s1", v1::RUN_MODE_LOCKSTEP, 40.0, 1000.0));
  check(dl.seed() == 5, "seed from published scenario");
  check(dl.pair_state("uav-001", "uav-002").range_m > 900.0, "entities loaded from published scenario");
  check(dones.size() == 1, "one ready signal after load");
  if (!dones.empty()) {
    check(dones[0].participant() == "datalink-0", "ready participant");
    check(dones[0].frame() == 0, "ready frame 0");
  }

  // 같은 name 재발행(1 s 주기)은 무시: 상태·준비 신호 변화 없음. 내용이 달라도 name이 같으면 무시한다
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("s1", v1::RUN_MODE_LOCKSTEP, 40.0, 1000.0));
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("s1", v1::RUN_MODE_LOCKSTEP, 40.0, 9000.0));
  check(dones.size() == 1, "same name: no new ready signal");
  check(dl.pair_state("uav-001", "uav-002").range_m < 1500.0, "same name: not reloaded");

  // 다른 name이면 다시 적재하고 준비 신호를 다시 보낸다
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("s2", v1::RUN_MODE_LOCKSTEP, 40.0, 3000.0));
  check(dl.pair_state("uav-001", "uav-002").range_m > 2900.0, "different name: reloaded");
  check(dones.size() == 2, "different name: ready signal again");

  // LoadScenario(명령)로 적재한 뒤 같은 name 재발행은 무시한다
  v1::SimCommand cmd;
  *cmd.mutable_load()->mutable_scenario() = scenario_msg("s3", v1::RUN_MODE_LOCKSTEP, 40.0, 2000.0);
  put(bus, std::string(keys::kSimCtrlCmd), cmd);
  check(dones.size() == 3, "LoadScenario: ready signal");
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("s3", v1::RUN_MODE_LOCKSTEP, 40.0, 2000.0));
  check(dones.size() == 3, "LoadScenario then republish: ignored");

  // 실시간 시나리오는 준비 신호를 보내지 않지만 적재는 한다
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("s4", v1::RUN_MODE_REALTIME, 40.0, 4000.0));
  check(dones.size() == 3, "realtime: no ready signal");
  check(dl.pair_state("uav-001", "uav-002").range_m > 3900.0, "realtime: loaded");

  // participant_id를 비우면 lockstep이어도 보내지 않는다
  InMemoryBus bus2;
  int n2 = 0;
  auto sub2 = bus2.subscribe("sim/clock/done/*", [&](const Sample&) { ++n2; });
  DatalinkConfig cfg2;
  cfg2.participant_id = "";
  Datalink dl2(bus2, nullptr, cfg2);
  put(bus2, std::string(keys::kSimCtrlScenario), scenario_msg("s1", v1::RUN_MODE_LOCKSTEP, 40.0, 1000.0));
  check(n2 == 0, "empty participant: no ready signal");
  check(dl2.seed() == 5, "empty participant: still loaded");
}

// 적재한 시나리오의 링크 프로파일이 실제 지연에 반영된다 (sim/ctrl/scenario 경유)
void tc016_delay() {
  InMemoryBus bus;
  int rx = 0;
  auto sub = bus.subscribe("swarm/*/rx/**", [&](const Sample&) { ++rx; });
  DatalinkConfig cfg;
  cfg.state_period_s = 0.0;
  Datalink dl(bus, nullptr, cfg);
  put(bus, std::string(keys::kSimCtrlScenario), scenario_msg("d1", v1::RUN_MODE_REALTIME, 100.0, 1000.0));
  v1::LinkEnvelope env;
  env.mutable_header()->set_source("uav-001");
  env.add_dst("uav-002");
  env.set_iface(v1::L1_INTERFACE_P2P);
  env.set_msg_type("swarm.v1.PeerStatus");
  env.set_payload("x");
  put(bus, keys::tx("uav-001", keys::Iface::P2P, "PeerStatus"), env);
  auto tick = [&](std::uint64_t us) {
    v1::ClockTick t;
    t.set_sim_time_us(us);
    t.set_dt_us(20000);
    put(bus, std::string(keys::kClockTick), t);
  };
  tick(0);
  tick(50000);
  check(rx == 0, "scenario profile latency 100 ms: not yet delivered at 50 ms");
  tick(150000);
  check(rx == 1, "scenario profile latency 100 ms: delivered by 150 ms");
}

// ---- TC-LNK-017: 입력 폭주 보호 (DEC-039, QA-012) ----
void tc017() {
  DatalinkConfig cfg;
  cfg.max_pending = 1000;
  cfg.max_routes_per_tick = 400;
  cfg.max_in_flight = 3000;
  cfg.max_overflow_outcomes = 200;
  LinkProfile slow = clean_profile();
  slow.latency_ms = 5000.0;  // 전송 중 목록이 쌓이게 한다
  cfg.profiles["slow"] = slow;
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "slow"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0, 1000.0, "slow"}},
        cfg);
  r.tick();
  r.dones.clear();
  r.outcomes.clear();

  // 한 프레임에 5만 건. 입력 큐는 상한에서 멈춘다
  for (int i = 0; i < 50000; ++i) r.tx("uav-001", {"uav-002"});
  check(r.dl->pending() <= cfg.max_pending, "pending bounded during flood");

  std::size_t max_pending_seen = 0, max_flight_seen = 0, ticks = 0;
  for (int k = 0; k < 40; ++k) {
    r.tick();
    ++ticks;
    max_pending_seen = std::max(max_pending_seen, r.dl->pending());
    max_flight_seen = std::max(max_flight_seen, r.dl->in_flight());
  }
  check(max_pending_seen <= cfg.max_pending, "pending bounded after ticks");
  check(max_flight_seen <= cfg.max_in_flight, "in-flight bounded");
  check(r.dones.size() == ticks, "frame done every tick during and after flood");
  check(r.count(v1::DROP_REASON_QUEUE_OVERFLOW) > 0, "overflow recorded as QUEUE_OVERFLOW");
  check(r.outcomes.size() < 5000, "outcomes bounded (no per-message storm)");
  check(r.dl->pending() == 0, "queue drained after flood");

  // 홍수가 끝나면 정상 메시지가 다시 전달된다
  r.rx.clear();
  r.tx("uav-001", {"uav-002"});
  for (int k = 0; k < 300; ++k) r.tick();
  check(!r.rx.empty(), "message delivered after flood");

  // 틱당 처리량 상한: 400쌍/틱이므로 1000건은 3틱 이상에 걸쳐 처리된다
  Rig q({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0}}, [] {
    DatalinkConfig c;
    c.max_routes_per_tick = 100;
    return c;
  }());
  q.tick();
  q.outcomes.clear();
  for (int i = 0; i < 350; ++i) q.tx("uav-001", {"uav-002"});
  q.tick();
  check(q.outcomes.size() <= 120, "per-tick route budget respected");
  for (int k = 0; k < 6; ++k) q.tick();
  check(q.outcomes.size() == 350, "deferred messages processed in later ticks");
  check(q.count(v1::DROP_REASON_NONE) == 350, "deferred messages delivered");
}

// ---- TC-LNK-018: 불완전 링크 결정론 (DEC-039, QA-013) ----
struct Trace {
  std::vector<std::string> lines;
};

Trace run_lossy(bool send_before_tick, std::uint64_t seed) {
  DatalinkConfig cfg;
  LinkProfile lossy = clean_profile();
  lossy.ge = {0.05, 0.25, 0.01, 0.6};
  lossy.latency_ms = 40.0;
  lossy.jitter_ms = 15.0;
  lossy.bandwidth_bps = 20000.0;
  lossy.bucket_bytes = 2000;
  lossy.queue_len = 8;
  cfg.profiles["lossy"] = lossy;
  Rig r({{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 0.0, 1000.0, "lossy"},
         {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1500.0, 1000.0, "lossy"},
         {"uav-003", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 3000.0, 1000.0, "lossy"}},
        cfg, nullptr, seed);
  auto send = [&](std::uint64_t frame) {
    for (const char* src : {"uav-001", "uav-002", "uav-003"}) {
      for (int i = 0; i < 3; ++i) {
        v1::LinkEnvelope env;
        auto* h = env.mutable_header();
        h->set_source(src);
        h->set_frame(frame);
        h->set_sim_time_us(frame * r.dt_us);
        const std::string key = keys::tx(src, keys::Iface::P2P, "PeerStatus");
        h->set_seq(r.seq[key]++);
        env.set_iface(v1::L1_INTERFACE_P2P);
        env.set_msg_type("swarm.v1.PeerStatus");
        env.set_payload(std::string(200, 'x'));
        put(r.bus, key, env);
      }
    }
  };
  for (std::uint64_t k = 0; k < 200; ++k) {
    // 프레임 k(시각 k*dt)의 송신이 tick k 앞에 도착하느냐 뒤에 도착하느냐만 다르다
    if (send_before_tick) send(k);
    r.tick();
    if (!send_before_tick) send(k);
  }
  Trace t;
  for (const auto& o : r.outcomes)
    t.lines.push_back(o.src() + ">" + o.dst() + "#" + std::to_string(o.seq()) + ":" + std::to_string(o.reason()) +
                      "@" + std::to_string(o.rx_time_us()));
  std::sort(t.lines.begin(), t.lines.end());
  return t;
}

void tc018() {
  const Trace a = run_lossy(true, 20261104), b = run_lossy(false, 20261104), c = run_lossy(true, 20261104),
              d = run_lossy(true, 7);
  check(a.lines.size() > 1000, "lossy run produced outcomes");
  check(a.lines == c.lines, "same seed, same arrival order: identical outcomes");
  check(a.lines == b.lines, "same seed, different arrival order vs tick: identical outcomes");
  check(a.lines != d.lines, "different seed: different outcomes");
  std::size_t lost = 0;
  for (const auto& l : a.lines)
    if (l.find(":0@") == std::string::npos) ++lost;
  check(lost > 0 && lost < a.lines.size(), "run has both losses and deliveries");
}

// ---- TC-LNK-019: lockstep에서 다른 참여자의 FrameDone을 받은 뒤에 틱을 처리한다 (DEC-039) ----
void tc019() {
  InMemoryBus bus;
  std::vector<v1::FrameDone> dones;
  auto sub = bus.subscribe("sim/clock/done/*", [&](const Sample& s) {
    auto d = parse<v1::FrameDone>(s);
    if (d.participant() == "datalink-0") dones.push_back(d);
  });
  DatalinkConfig cfg;
  cfg.state_period_s = 0.0;
  Datalink dl(bus, nullptr, cfg);
  v1::Scenario sc = scenario_msg("s19", v1::RUN_MODE_LOCKSTEP, 40.0, 1000.0);
  sc.mutable_run()->add_participants("datalink-0");
  sc.mutable_run()->add_participants("agent-0");
  dl.load(sc);
  dones.clear();  // 준비 신호는 제외

  auto tick = [&](std::uint64_t frame) {
    v1::ClockTick t;
    t.set_frame(frame);
    t.set_sim_time_us(frame * 20000);
    t.set_dt_us(20000);
    t.set_mode(v1::RUN_MODE_LOCKSTEP);
    put(bus, std::string(keys::kClockTick), t);
  };
  auto agent_done = [&](std::uint64_t frame) {
    v1::FrameDone d;
    d.set_participant("agent-0");
    d.set_frame(frame);
    put(bus, keys::clock_done("agent-0"), d);
  };
  auto tx = [&](std::uint32_t seq, std::uint64_t t_us) {
    v1::LinkEnvelope env;
    auto* h = env.mutable_header();
    h->set_source("uav-001");
    h->set_sim_time_us(t_us);
    h->set_seq(seq);
    env.add_dst("uav-002");
    env.set_iface(v1::L1_INTERFACE_P2P);
    env.set_msg_type("swarm.v1.PeerStatus");
    env.set_payload("x");
    put(bus, keys::tx("uav-001", keys::Iface::P2P, "PeerStatus"), env);
  };

  tick(0);  // 첫 틱은 기다리지 않는다
  check(dones.size() == 1 && dones[0].frame() == 0, "first tick processed without waiting");
  tick(1);  // agent-0의 frame 0 FrameDone이 없다
  check(dones.size() == 1, "tick 1 deferred until participant done");
  tx(0, 20000 - 1000);  // 틱 1을 받은 뒤에 도착한 이전 프레임 송신
  check(dl.pending() == 1, "late tx held while waiting");
  agent_done(0);
  check(dones.size() == 2 && dones[1].frame() == 1, "tick 1 processed after participant done");
  check(dl.pending() == 0, "tx from before the tick processed in that tick");
  check(dl.sim_time_us() == 20000, "clock advanced");
  tick(2);
  check(dones.size() == 2, "tick 2 deferred again");
  agent_done(1);
  check(dones.size() == 3 && dones[2].frame() == 2, "tick 2 processed after next done");
  // 순서가 뒤바뀌어도(FrameDone이 틱보다 먼저) 같은 결과
  agent_done(2);
  tick(3);
  check(dones.size() == 4 && dones[3].frame() == 3, "done before tick: processed immediately");
}

// ---- TC-LNK-020: 틱 f의 rx·outcome·link/state를 모두 발행한 뒤에 FrameDone{f}를 보낸다 (DEC-040) ----
void tc020() {
  DatalinkConfig cfg;
  cfg.state_period_s = 0.02;
  Rig r({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0}}, cfg);
  std::vector<std::string> log;
  auto sub = r.bus.subscribe("**", [&](const Sample& s) {
    if (s.key.rfind("swarm/", 0) == 0 && s.key.find("/rx/") != std::string::npos) log.push_back("rx");
    else if (s.key.rfind("link/", 0) == 0) log.push_back("link");
    else if (s.key.rfind("sim/clock/done/", 0) == 0) log.push_back("done");
  });
  std::size_t delivered = 0;
  for (int f = 0; f < 20; ++f) {
    log.clear();
    r.tx("uav-001", {"uav-002"});
    r.tick();
    check(!log.empty() && log.back() == "done", "FrameDone is the last publication of the tick");
    check(std::count(log.begin(), log.end(), "done") == 1, "exactly one FrameDone per tick");
    delivered += static_cast<std::size_t>(std::count(log.begin(), log.end(), "rx"));
  }
  check(delivered > 0, "rx published before FrameDone");
}

// ---- TC-LNK-021: on_tick과 on_done이 다른 스레드에서 동시에 불려도 rx가 FrameDone보다 먼저 나간다 (DEC-040) ----
void tc021() {
  InMemoryBus bus;
  std::mutex mu;
  std::vector<std::string> log;
  auto sub = bus.subscribe("**", [&](const Sample& s) {
    std::lock_guard lock(mu);
    if (s.key.find("/rx/") != std::string::npos) log.push_back("rx");
    else if (s.key == keys::clock_done("datalink-0")) log.push_back("done");
  });
  DatalinkConfig cfg;
  cfg.state_period_s = 0.0;
  Datalink dl(bus, nullptr, cfg);
  v1::Scenario sc = scenario_msg("s21", v1::RUN_MODE_LOCKSTEP, 0.0, 1000.0);
  sc.mutable_run()->add_participants("datalink-0");
  sc.mutable_run()->add_participants("agent-0");
  dl.load(sc);
  for (int f = 0; f < 300; ++f) {
    {
      std::lock_guard lock(mu);
      log.clear();
    }
    v1::LinkEnvelope env;
    auto* h = env.mutable_header();
    h->set_source("uav-001");
    h->set_sim_time_us(f == 0 ? 0 : static_cast<std::uint64_t>(f) * 20000 - 1000);
    h->set_seq(static_cast<std::uint32_t>(f));
    env.add_dst("uav-002");
    env.set_iface(v1::L1_INTERFACE_P2P);
    env.set_msg_type("swarm.v1.PeerStatus");
    env.set_payload("x");
    put(bus, keys::tx("uav-001", keys::Iface::P2P, "PeerStatus"), env);
    v1::ClockTick t;
    t.set_frame(static_cast<std::uint64_t>(f));
    t.set_sim_time_us(static_cast<std::uint64_t>(f) * 20000);
    t.set_dt_us(20000);
    t.set_mode(v1::RUN_MODE_LOCKSTEP);
    v1::FrameDone d;
    d.set_participant("agent-0");
    d.set_frame(f > 0 ? static_cast<std::uint64_t>(f - 1) : 0);
    std::thread a([&] { put(bus, std::string(keys::kClockTick), t); });
    std::thread b([&] { put(bus, keys::clock_done("agent-0"), d); });
    a.join();
    b.join();
    std::lock_guard lock(mu);
    check(!log.empty() && log.back() == "done" && std::count(log.begin(), log.end(), "done") == 1,
          "FrameDone last, once, under concurrent callbacks");
  }
}

// ---- TC-LNK-022: 송신 개수 장벽 (DEC-044) ----
struct BarrierRig {
  InMemoryBus bus;
  std::vector<v1::FrameDone> dones;  // datalink-0만
  std::uint64_t rx_count = 0;
  std::vector<std::uint64_t> rx_at_done;
  std::unique_ptr<Subscription> s1, s2;
  std::unique_ptr<Datalink> dl;
  std::uint32_t seq = 0;

  BarrierRig(double north_b_m, v1::RunMode mode) {
    s1 = bus.subscribe("sim/clock/done/*", [&](const Sample& s) {
      auto d = parse<v1::FrameDone>(s);
      if (d.participant() != "datalink-0") return;
      dones.push_back(d);
      rx_at_done.push_back(rx_count);
    });
    s2 = bus.subscribe("swarm/*/rx/**", [&](const Sample&) { ++rx_count; });
    DatalinkConfig cfg;
    cfg.state_period_s = 0.0;
    dl = std::make_unique<Datalink>(bus, nullptr, cfg);
    v1::Scenario sc = scenario_msg("s22", mode, 0.0, north_b_m);
    sc.mutable_run()->add_participants("datalink-0");
    sc.mutable_run()->add_participants("agent-0");
    dl->load(sc);
    dones.clear();
    rx_at_done.clear();
  }
  void tick(std::uint64_t frame, v1::RunMode mode = v1::RUN_MODE_LOCKSTEP) {
    v1::ClockTick t;
    t.set_frame(frame);
    t.set_sim_time_us(frame * 20000);
    t.set_dt_us(20000);
    t.set_mode(mode);
    put(bus, std::string(keys::kClockTick), t);
  }
  void agent_done(std::uint64_t frame, std::uint64_t sent) {
    v1::FrameDone d;
    d.set_participant("agent-0");
    d.set_frame(frame);
    if (sent) (*d.mutable_sent_count())["uav-001"] = sent;
    put(bus, keys::clock_done("agent-0"), d);
  }
  void tx(std::uint64_t t_us) {
    v1::LinkEnvelope env;
    auto* h = env.mutable_header();
    h->set_source("uav-001");
    h->set_sim_time_us(t_us);
    h->set_seq(seq++);
    env.add_dst("uav-002");
    env.set_iface(v1::L1_INTERFACE_P2P);
    env.set_msg_type("swarm.v1.PeerStatus");
    env.set_payload("x");
    put(bus, keys::tx("uav-001", keys::Iface::P2P, "PeerStatus"), env);
  }
};

void tc022() {
  {  // 개수 부족이면 대기, 채워지면 진행
    BarrierRig r(1000.0, v1::RUN_MODE_LOCKSTEP);
    r.tick(0);
    r.tx(0);
    r.agent_done(0, 3);  // 3건 보냈다고 알리지만 1건만 받았다
    r.tick(1);
    check(r.dones.size() == 1, "tick 1 waits: sent_count 3 > received 1");
    check(r.dl->pending() == 1, "received message held");
    r.tx(0);
    check(r.dones.size() == 1, "still waiting at 2 of 3");
    r.tx(0);
    check(r.dones.size() == 2 && r.dones[1].frame() == 1, "tick 1 processed when count reached");
    check(r.dl->pending() == 0, "all three processed in the tick");
  }
  {  // sent_count가 없으면(구버전) 개수 조건 없이 FrameDone만으로 진행
    BarrierRig r(1000.0, v1::RUN_MODE_LOCKSTEP);
    r.tick(0);
    r.agent_done(0, 0);
    r.tick(1);
    check(r.dones.size() == 2, "no sent_count: no count condition");
  }
  {  // Datalink의 sent_count = 발행한 rx 누적 수
    BarrierRig r(1000.0, v1::RUN_MODE_LOCKSTEP);
    r.tick(0);
    std::uint64_t last = 0;
    for (std::uint64_t f = 1; f <= 10; ++f) {
      r.tx(f * 20000 - 1000);
      r.agent_done(f - 1, 0);
      r.tick(f);
      const auto& d = r.dones.back();
      const auto it = d.sent_count().find("uav-002");
      const std::uint64_t n = it == d.sent_count().end() ? 0 : it->second;
      check(n == r.rx_at_done.back(), "sent_count equals rx published before FrameDone");
      check(n >= last, "cumulative");
      last = n;
    }
    check(last > 0, "some rx delivered");
  }
  {  // 모의 손실로 버린 메시지(통신 범위 밖)는 세지 않는다
    BarrierRig r(40000.0, v1::RUN_MODE_LOCKSTEP);
    r.tick(0);
    for (std::uint64_t f = 1; f <= 5; ++f) {
      r.tx(f * 20000 - 1000);
      r.agent_done(f - 1, 0);
      r.tick(f);
    }
    check(r.rx_count == 0, "out-of-range messages are not delivered");
    check(r.dones.back().sent_count().empty(), "dropped messages are not counted");
  }
  {  // realtime: 참여자 FrameDone·개수와 무관하게 틱 즉시 처리, sent_count 없음
    BarrierRig r(1000.0, v1::RUN_MODE_REALTIME);
    r.tick(0, v1::RUN_MODE_REALTIME);
    r.agent_done(0, 99);
    for (std::uint64_t f = 1; f <= 3; ++f) {
      r.tx(f * 20000 - 1000);
      r.tick(f, v1::RUN_MODE_REALTIME);
    }
    check(r.dones.size() == 4, "realtime ticks processed without waiting");
    check(r.dones.back().sent_count().empty(), "realtime: no sent_count");
  }
}

// ---- TC-LNK-023: lockstep rx 불변식 rx_time >= T_k (DEC-054, QA-019) ----
// 틱 k에서 나온 rx를 모두 모아 rx_time_us >= T_k인지 본다. 지연 0, 틱 사이 도착(5 ms), 처리량 상한 이월을 함께 시험한다
struct RxBound {
  std::size_t rx = 0, violations = 0, outcome_violations = 0;
  std::uint64_t min_rx = UINT64_MAX;
};

RxBound run_rx_bound(double latency_ms, std::size_t max_routes, int burst, v1::RunMode mode) {
  DatalinkConfig cfg;
  LinkProfile p = clean_profile();
  p.latency_ms = latency_ms;
  cfg.profiles["clean"] = p;
  cfg.max_routes_per_tick = max_routes;
  Rig r({{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0}}, cfg);
  RxBound b;
  for (int k = 0; k < 12; ++k) {
    const std::uint64_t t_k = r.frame * r.dt_us;
    const std::size_t rx0 = r.rx.size(), o0 = r.outcomes.size();
    r.tick(mode);
    for (std::size_t i = rx0; i < r.rx.size(); ++i) {
      ++b.rx;
      b.min_rx = std::min<std::uint64_t>(b.min_rx, r.rx[i].second.rx_time_us());
      if (r.rx[i].second.rx_time_us() < t_k) ++b.violations;
    }
    for (std::size_t i = o0; i < r.outcomes.size(); ++i)
      if (r.outcomes[i].reason() == v1::DROP_REASON_NONE && r.outcomes[i].rx_time_us() < t_k) ++b.outcome_violations;
    // 에이전트처럼 방금 처리한 틱 시각으로 보낸다
    if (k < 3)
      for (int i = 0; i < burst; ++i) r.tx("uav-001", {"uav-002"}, 32, keys::Iface::P2P, "PeerStatus", t_k);
  }
  return b;
}

void tc023() {
  // 지연 0: 틱 k에 송신 시각 T(k-1)로 처리되지만 rx_time은 T_k 이상이다
  const RxBound z = run_rx_bound(0.0, 4096, 3, v1::RUN_MODE_LOCKSTEP);
  check(z.rx == 9, "zero delay: all delivered");
  check(z.violations == 0, "zero delay: rx_time >= T_k");
  check(z.outcome_violations == 0, "zero delay: outcome rx_time >= T_k");
  // 틱 사이 도착(5 ms < dt)
  const RxBound s = run_rx_bound(5.0, 4096, 3, v1::RUN_MODE_LOCKSTEP);
  check(s.rx == 9 && s.violations == 0 && s.outcome_violations == 0, "sub-tick delay: rx_time >= T_k");
  // 처리량 상한 이월: 틱당 2쌍, 틱마다 5건이면 대부분 다음 틱 이후로 넘어간다
  const RxBound c = run_rx_bound(0.0, 2, 5, v1::RUN_MODE_LOCKSTEP);
  check(c.rx == 15, "carry-over: all delivered eventually");
  check(c.violations == 0 && c.outcome_violations == 0, "carry-over: rx_time >= T_k");
  // realtime은 바뀌지 않는다: 표본 도착 시각(송신 시각 + 지연)을 그대로 쓴다
  const RxBound rt = run_rx_bound(0.0, 4096, 3, v1::RUN_MODE_REALTIME);
  check(rt.rx == 9, "realtime: all delivered");
  check(rt.violations > 0, "realtime: rx_time not clamped to tick time");
  check(rt.min_rx == 0, "realtime: zero delay keeps tx time");
}

// ---- TC-LNK-024~026: 프레임 0 송신 시각 (QA O-23, DEC-039, DEC-054, DEC-077) ----
DatalinkConfig latency_cfg(double latency_ms) {
  DatalinkConfig cfg;
  LinkProfile p = clean_profile();
  p.latency_ms = latency_ms;
  cfg.profiles["clean"] = p;
  return cfg;
}

std::vector<Ent> pair_ents() { return {{"uav-001"}, {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, 1000.0}}; }
constexpr keys::Iface kC2 = keys::Iface::C2;

void tc024() {
  // 정상 순서: 프레임 0(ACCEPTED) 다음 프레임 1(EXECUTING)
  {
    Rig r(pair_ents(), latency_cfg(30.0));
    r.tick();  // T=0
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Accepted", 0);
    r.tick();  // T=20: 프레임 0 송신 처리
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Executing", 20000);
    for (int k = 0; k < 4; ++k) r.tick();
    check(r.rx.size() == 2, "both delivered");
    if (r.rx.size() == 2) {
      check(r.rx[0].first.ends_with("/Accepted") && r.rx[1].first.ends_with("/Executing"), "frame 0 arrives first");
      check(r.rx[0].second.rx_time_us() == 40000 && r.rx[1].second.rx_time_us() == 60000, "lockstep rx times");
    }
    check(r.outcomes.size() == 2 && r.outcomes[0].tx_time_us() == 0, "frame 0 keeps tx time 0");
  }
  // QA 재현: 프레임 0 송신이 프레임 1 송신보다 늦게, 틱이 진행된 뒤에 도착해도 시각 0을 유지한다
  {
    Rig r(pair_ents(), latency_cfg(30.0));
    for (int k = 0; k < 4; ++k) r.tick(v1::RUN_MODE_REALTIME);  // 마지막 틱 60 ms
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Executing", 20000);
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Accepted", 0);
    r.tick(v1::RUN_MODE_REALTIME);  // T=80: 둘 다 도착 시각이 지났다
    check(r.rx.size() == 2, "late frame 0: both delivered");
    if (r.rx.size() == 2) {
      check(r.rx[0].first.ends_with("/Accepted") && r.rx[0].second.rx_time_us() == 30000, "late frame 0: first, rx 30 ms");
      check(r.rx[1].first.ends_with("/Executing") && r.rx[1].second.rx_time_us() == 50000, "frame 1: rx 50 ms");
    }
  }
  // lockstep에서도 늦은 프레임 0이 프레임 1보다 뒤로 가지 않고 DEC-054 하한을 지킨다
  {
    Rig r(pair_ents(), latency_cfg(30.0));
    for (int k = 0; k < 4; ++k) r.tick();
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Executing", 20000);
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Accepted", 0);
    r.tick();  // T=80
    check(r.rx.size() == 2 && r.rx[0].first.ends_with("/Accepted"), "lockstep late frame 0: delivered first");
    for (const auto& [key, env] : r.rx) check(env.rx_time_us() >= 80000, "lockstep late frame 0: rx_time >= T_k");
  }
  // 지연 0: 시각 0 송신의 rx도 DEC-054를 지킨다
  {
    Rig r(pair_ents(), latency_cfg(0.0));
    r.tx("uav-001", {"uav-002"}, 32, kC2, "Accepted", 0);
    r.tick();  // T=0: 틱 0에는 처리하지 않는다
    check(r.rx.empty(), "frame 0 tx not processed at tick 0");
    r.tick();  // T=20
    check(r.rx.size() == 1 && r.rx[0].second.rx_time_us() == 20000, "zero delay: rx_time = T_1");
  }
}

void tc025() {
  // publisher가 있고 시각이 0이면 마지막 틱 시각을 쓴다
  Rig r(pair_ents(), latency_cfg(0.0));
  for (int k = 0; k < 3; ++k) r.tick();  // 마지막 틱 40 ms
  r.tx("uav-001", {"uav-002"}, 32, kC2, "TaskCommand");
  r.tick();
  check(r.outcomes.size() == 1 && r.outcomes[0].tx_time_us() == 40000, "publisher + time 0: last tick time");
  check(r.rx.size() == 1 && r.rx[0].second.publisher() == "rig-ground", "publisher forwarded");
  // publisher가 있어도 시각을 찍었으면 그 시각을 쓴다
  r.outcomes.clear();
  v1::LinkEnvelope env;
  env.mutable_header()->set_source("uav-001");
  env.mutable_header()->set_sim_time_us(50000);
  env.mutable_header()->set_seq(99);
  env.set_publisher("ui-01");
  env.add_dst("uav-002");
  env.set_iface(v1::L1_INTERFACE_C2);
  env.set_msg_type("swarm.v1.TaskCommand");
  env.set_payload("x");
  put(r.bus, keys::tx("uav-001", kC2, "TaskCommand"), env);
  r.tick();
  check(r.outcomes.size() == 1 && r.outcomes[0].tx_time_us() == 50000, "publisher + time: header time");
  // publisher가 없고 시각이 0이면 0이 유효한 시각이다
  r.outcomes.clear();
  r.tx("uav-001", {"uav-002"}, 32, kC2, "Accepted", 0);
  r.tick();
  check(r.outcomes.size() == 1 && r.outcomes[0].tx_time_us() == 0, "no publisher + time 0: valid time 0");
}

std::vector<std::string> run_frame0(bool before_tick0, double latency_ms, double jitter_ms) {
  DatalinkConfig cfg;
  LinkProfile p = clean_profile();
  p.latency_ms = latency_ms;
  p.jitter_ms = jitter_ms;
  p.ge = {0.05, 0.3, 0.0, 0.5};
  cfg.profiles["clean"] = p;
  Rig r(pair_ents(), cfg, nullptr, 11);
  auto send0 = [&] {
    for (int i = 0; i < 20; ++i) {
      r.tx("uav-001", {"uav-002"}, 32, kC2, "Accepted", 0);
      r.tx("uav-002", {"uav-001"}, 32, kC2, "Accepted", 0);
    }
  };
  if (before_tick0) send0();
  r.tick();
  if (!before_tick0) send0();
  for (int k = 1; k < 12; ++k) {
    const std::uint64_t t = (r.frame - 1) * r.dt_us;
    if (k < 5) r.tx("uav-001", {"uav-002"}, 32, kC2, "Executing", t);
    r.tick();
  }
  std::vector<std::string> out;
  for (const auto& [key, env] : r.rx)
    out.push_back(key + " " + std::to_string(env.header().seq()) + " " + std::to_string(env.rx_time_us()));
  for (const auto& o : r.outcomes)
    out.push_back(o.src() + ">" + o.dst() + " " + std::to_string(o.seq()) + " " + std::to_string(o.reason()) + " " +
                  std::to_string(o.tx_time_us()) + " " + std::to_string(o.rx_time_us()));
  return out;
}

void tc026() {
  // 지연 0이면 틱 0에서 처리될 때 rx_time이 달라지므로 도착 경쟁이 그대로 드러난다
  for (const auto& [latency, jitter] : {std::pair{30.0, 8.0}, std::pair{0.0, 0.0}}) {
    const auto a = run_frame0(true, latency, jitter), b = run_frame0(true, latency, jitter);
    const auto c = run_frame0(false, latency, jitter);
    check(!a.empty(), "trace not empty");
    check(a == b, "same input, same output");
    // 틱 0은 기다리지 않으므로 프레임 0 송신은 틱 0보다 먼저도 뒤에도 올 수 있다. 결과는 같아야 한다 (DEC-039)
    check(a == c, "frame 0 tx before or after tick 0: same output");
  }
}

struct Case {
  const char* id;
  void (*fn)();
};

const Case kCases[] = {
    {"TC-LNK-001", tc001}, {"TC-LNK-002", tc002}, {"TC-LNK-003", tc003}, {"TC-LNK-004", tc004},
    {"TC-LNK-005", tc005}, {"TC-LNK-006", tc006}, {"TC-LNK-007", tc007}, {"TC-LNK-008", tc008},
    {"TC-LNK-009", tc009}, {"TC-LNK-010", tc010}, {"TC-LNK-011", tc011}, {"TC-LNK-012", tc012},
    {"TC-LNK-013", tc013}, {"TC-LNK-014", tc014}, {"TC-LNK-015", tc015},
    {"TC-LNK-016", [] { tc016(); tc016_delay(); }},
    {"TC-LNK-017", tc017}, {"TC-LNK-018", tc018}, {"TC-LNK-019", tc019}, {"TC-LNK-020", tc020}, {"TC-LNK-021", tc021}, {"TC-LNK-022", tc022},
    {"TC-LNK-023", tc023}, {"TC-LNK-024", tc024}, {"TC-LNK-025", tc025}, {"TC-LNK-026", tc026},
};

}  // namespace

int main(int argc, char** argv) {
  int ran = 0;
  for (const auto& c : kCases) {
    if (argc > 1 && std::strcmp(argv[1], c.id) != 0) continue;
    c.fn();
    ++ran;
  }
  if (ran == 0) {
    std::fprintf(stderr, "unknown test id\n");
    return EXIT_FAILURE;
  }
  if (g_failures == 0) std::puts("swarm_datalink_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
