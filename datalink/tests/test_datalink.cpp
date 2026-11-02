// TC-LNK-001~015: 데이터링크 시험. InMemoryBus에 Datalink를 붙이고 tick·truth·tx를 직접 발행한다.
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
          keys::Iface iface = keys::Iface::P2P, const std::string& msg = "PeerStatus") {
    v1::LinkEnvelope env;
    auto* h = env.mutable_header();
    h->set_source(src);
    h->set_frame(frame);
    const std::string key = keys::tx(src, iface, msg);
    h->set_seq(seq[key]++);
    for (auto& d : dst) env.add_dst(d);
    env.set_iface(static_cast<v1::L1Interface>(static_cast<int>(iface) + 1));
    env.set_msg_type("swarm.v1." + msg);
    env.set_payload(std::string(payload, 'x'));
    put(bus, key, env);
  }

  // Core 순서와 같게 truth를 먼저, tick을 나중에 보낸다
  void tick() {
    truth();
    v1::ClockTick t;
    t.set_frame(frame);
    t.set_sim_time_us(frame * dt_us);
    t.set_dt_us(dt_us);
    t.set_mode(v1::RUN_MODE_LOCKSTEP);
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

  // 버스: 지연 50 ms, 프레임 20 ms. t=20 ms 송신 → 도착 70 ms → t=80 ms tick에서 전달
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
  if (!r.rx.empty()) check(r.rx[0].second.rx_time_us() == 70000, "rx_time = tx + latency");
  check(r.outcomes.size() == 1 && r.outcomes[0].tx_time_us() == 20000 && r.outcomes[0].rx_time_us() == 70000,
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
    check(r.rx[0].second.rx_time_us() == 0, "rx_time on zero-latency link = tx time");
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

struct Case {
  const char* id;
  void (*fn)();
};

const Case kCases[] = {
    {"TC-LNK-001", tc001}, {"TC-LNK-002", tc002}, {"TC-LNK-003", tc003}, {"TC-LNK-004", tc004},
    {"TC-LNK-005", tc005}, {"TC-LNK-006", tc006}, {"TC-LNK-007", tc007}, {"TC-LNK-008", tc008},
    {"TC-LNK-009", tc009}, {"TC-LNK-010", tc010}, {"TC-LNK-011", tc011}, {"TC-LNK-012", tc012},
    {"TC-LNK-013", tc013}, {"TC-LNK-014", tc014}, {"TC-LNK-015", tc015},
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
