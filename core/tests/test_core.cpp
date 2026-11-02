// TC-CORE-002~012: SimCore 단위 시험 (InMemoryBus, 목 동역학)
// TC-CORE-013~017: WP2 동역학 통합, 지면 충돌, 스크립트 경로, 고장 주입
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <numbers>
#include <stdexcept>
#include <string>
#include <vector>

#include "swarm/api/bus.hpp"
#include "swarm/api/keys.hpp"
#include "swarm/core/mock_dynamics.hpp"
#include "swarm/core/scenario.hpp"
#include "swarm/core/sim_core.hpp"
#include "swarm/core/wp2_dynamics.hpp"
#include "swarm/v1/truth.pb.h"

namespace {

using namespace swarm;
using namespace std::chrono_literals;
using Clock = core::SimCore::Clock;

int g_failures = 0;

#define CHECK(cond)                                                    \
  do {                                                                 \
    if (!(cond)) {                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
      ++g_failures;                                                    \
    }                                                                  \
  } while (0)

template <class T>
T decode(const Sample& s) {
  T m;
  (void)m.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()));
  return m;
}

template <class T>
void put(Bus& bus, const std::string& key, const T& msg) {
  const std::string b = msg.SerializeAsString();
  bus.put(key, {reinterpret_cast<const std::uint8_t*>(b.data()), b.size()},
          protobuf_encoding(msg.GetDescriptor()->full_name()));
}

// 버스에서 받은 메시지를 모은다
struct Recorder {
  std::vector<v1::ClockTick> ticks;
  std::vector<v1::TruthFrame> truths;
  std::vector<v1::SimStatus> statuses;
  std::vector<v1::NavigationReport> navs;
  std::vector<v1::TruthEvent> events;
  std::vector<std::string> truth_bytes;
  std::vector<std::unique_ptr<Subscription>> subs;

  explicit Recorder(Bus& bus) {
    subs.push_back(bus.subscribe(keys::kClockTick, [this](const Sample& s) { ticks.push_back(decode<v1::ClockTick>(s)); }));
    subs.push_back(bus.subscribe(keys::kTruthState, [this](const Sample& s) {
      truths.push_back(decode<v1::TruthFrame>(s));
      truth_bytes.emplace_back(s.payload.begin(), s.payload.end());
      CHECK(s.encoding == "application/protobuf;swarm.v1.TruthFrame");
    }));
    subs.push_back(
        bus.subscribe(keys::kSimCtrlStatus, [this](const Sample& s) { statuses.push_back(decode<v1::SimStatus>(s)); }));
    subs.push_back(
        bus.subscribe("onboard/*/NavigationReport", [this](const Sample& s) { navs.push_back(decode<v1::NavigationReport>(s)); }));
    subs.push_back(bus.subscribe("truth/event/**", [this](const Sample& s) { events.push_back(decode<v1::TruthEvent>(s)); }));
  }
};

v1::SimCommand start_cmd(v1::RunMode mode, double rate, std::uint32_t hz = 50, std::uint64_t seed = 7) {
  v1::SimCommand c;
  c.set_issuer("ui-test");
  auto* s = c.mutable_start();
  s->set_mode(mode);
  s->set_rate(rate);
  s->set_frame_hz(hz);
  s->set_seed(seed);
  return c;
}

v1::SimCommand simple(std::function<void(v1::SimCommand&)> f) {
  v1::SimCommand c;
  c.set_issuer("ui-test");
  f(c);
  return c;
}

// 북쪽으로 25 m/s 등속 비행하는 기체 1대 + GCS
core::Scenario one_uav() {
  core::Scenario sc;
  sc.name = "one";
  v1::EntitySpec u;
  u.set_id("uav-001");
  u.set_kind(v1::ENTITY_KIND_UAV);
  u.set_side(v1::SIDE_BLUE);
  u.set_dynamics(v1::DYNAMICS_KIND_DOF2);
  u.mutable_initial()->mutable_position()->set_lat_deg(37.0);
  u.mutable_initial()->mutable_position()->set_lon_deg(127.0);
  u.mutable_initial()->mutable_position()->set_alt_m(500.0);
  u.mutable_initial()->mutable_velocity_ned_mps()->set_x(25.0);
  sc.entities.push_back(u);
  v1::EntitySpec g;
  g.set_id("gcs-01");
  g.set_kind(v1::ENTITY_KIND_GCS);
  g.set_dynamics(v1::DYNAMICS_KIND_STATIC);
  g.mutable_initial()->mutable_position()->set_lat_deg(36.9);
  sc.entities.push_back(g);
  return sc;
}

core::CoreConfig quiet(std::vector<std::string> participants = {}) {
  core::CoreConfig cfg;
  cfg.participants = std::move(participants);
  cfg.log = [](const std::string&) {};
  return cfg;
}

// TC-CORE-002: FREERUN 최대 속도는 poll마다 한 프레임 진행하고, 프레임마다 tick·truth를 발행한다
void test_freerun_progress() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());
  CHECK(sim.load(core::builtin_scenario(20)));
  CHECK(sim.state() == v1::SIM_RUN_STATE_LOADED);
  CHECK(rec.truths.size() == 1);  // 불러온 직후 초기 상태
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 100));
  const auto t = Clock::now();
  for (int i = 0; i < 10; ++i) CHECK(sim.poll(t));
  CHECK(sim.frame() == 10);
  CHECK(sim.dt_us() == 10000);
  CHECK(sim.sim_time_us() == 100000);
  CHECK(rec.ticks.size() == 11);  // tick 0..10
  CHECK(rec.ticks.back().frame() == 10 && rec.ticks.back().sim_time_us() == 100000);
  CHECK(rec.ticks.back().mode() == v1::RUN_MODE_FREERUN && rec.ticks.back().dt_us() == 10000);
  CHECK(rec.truths.size() == 12);
  CHECK(rec.truths.back().entities_size() == 21);
  CHECK(rec.truths.back().header().frame() == 10);
  CHECK(rec.navs.size() == 11 * 20);  // GCS는 NavigationReport 대상이 아니다
}

// TC-CORE-003: REALTIME은 dt마다 진행하고, 한 프레임 이상 늦으면 overrun을 센다. 배속 명령은 무시한다
void test_realtime_pacing() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());
  sim.load(one_uav());
  const auto t0 = Clock::now();
  sim.submit(start_cmd(v1::RUN_MODE_REALTIME, 5.0, 50));
  CHECK(!sim.poll(t0));
  CHECK(sim.rate() == 1.0);  // REALTIME은 배속 1
  CHECK(!sim.poll(t0 + 19ms));
  CHECK(sim.poll(t0 + 20ms));
  CHECK(!sim.poll(t0 + 39ms));
  CHECK(sim.poll(t0 + 40ms));
  CHECK(sim.frame() == 2 && sim.frame_overruns() == 0);
  CHECK(sim.poll(t0 + 200ms));  // 기한 60 ms보다 140 ms 늦음
  CHECK(sim.frame_overruns() == 1);
  CHECK(!sim.poll(t0 + 210ms));
  CHECK(sim.poll(t0 + 220ms));  // 기준점을 다시 잡은 뒤 20 ms 간격
  sim.submit(simple([](auto& c) { c.mutable_set_rate()->set_rate(4.0); }));
  sim.poll(t0 + 221ms);
  CHECK(sim.rate() == 1.0);
}

// TC-CORE-004: LOCKSTEP은 모든 참여자의 FrameDone(N)을 받아야 N+1로 간다
void test_lockstep_barrier() {
  InMemoryBus bus;
  core::SimCore sim(bus, core::mock::provider(), quiet({"agent-host-1", "agent-host-2"}));
  sim.load(one_uav());
  sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0));
  const auto t = Clock::now();
  auto done = [&](const char* p, std::uint64_t f) {
    v1::FrameDone d;
    d.set_participant(p);
    d.set_frame(f);
    put(bus, keys::clock_done(p), d);
  };
  CHECK(!sim.poll(t));
  CHECK(sim.frame() == 0);
  done("agent-host-1", 0);
  CHECK(!sim.poll(t));  // 한쪽만 완료
  done("agent-uuu-9", 0);  // 등록되지 않은 참여자는 무시
  CHECK(!sim.poll(t));
  done("agent-host-2", 0);
  CHECK(sim.poll(t));
  CHECK(sim.frame() == 1);
  CHECK(!sim.poll(t));  // frame 1 완료 대기
  done("agent-host-1", 0);  // 지난 프레임 완료는 장벽을 풀지 않는다
  done("agent-host-2", 1);
  CHECK(!sim.poll(t));
  done("agent-host-1", 1);
  CHECK(sim.poll(t));
  CHECK(sim.frame() == 2);
}

// TC-CORE-005: LOCKSTEP 결정론. 같은 시드·같은 입력이면 truth 바이트열이 같다
void test_lockstep_determinism() {
  auto run_once = [] {
    InMemoryBus bus;
    Recorder rec(bus);
    core::CoreConfig cfg = quiet({"agent-host-1"});
    cfg.nav_noise = [](const std::string&, v1::NavigationReport& nav, std::mt19937_64& rng) {
      std::normal_distribution<double> n(0.0, 3.0);
      nav.mutable_kinematics()->mutable_position()->set_alt_m(nav.kinematics().position().alt_m() + n(rng));
      nav.set_position_sigma_m(3.0);
    };
    core::SimCore sim(bus, core::mock::provider(), cfg);
    // 참여자: tick(N)을 받으면 선회 명령을 보내고 완료를 알린다
    auto sub = bus.subscribe(keys::kClockTick, [&](const Sample& s) {
      const auto tick = decode<v1::ClockTick>(s);
      v1::ControlOutput c;
      c.mutable_kinematic()->set_speed_mps(25.0 + 0.1 * static_cast<double>(tick.frame()));
      c.mutable_kinematic()->set_heading_rate_rps(0.05);
      put(bus, keys::onboard("uav-001", "ControlOutput"), c);
      v1::FrameDone d;
      d.set_participant("agent-host-1");
      d.set_frame(tick.frame());
      put(bus, keys::clock_done("agent-host-1"), d);
    });
    sim.load(one_uav());
    sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 50, 42));
    const auto t = Clock::now();
    // 완료 신호는 다음 poll에서 반영되므로 진행하지 않는 poll이 섞인다
    for (int i = 0; i < 300 && sim.frame() < 100; ++i) sim.poll(t);
    CHECK(sim.frame() == 100);
    std::string navs;
    for (const auto& n : rec.navs) navs += n.SerializeAsString();
    return rec.truth_bytes.back() + navs;
  };
  const auto a = run_once(), b = run_once();
  CHECK(!a.empty() && a == b);
}

// TC-CORE-006: 일시정지·스텝·재개·배속
void test_pause_step_rate() {
  InMemoryBus bus;
  core::SimCore sim(bus, core::mock::provider(), quiet());
  sim.load(one_uav());
  const auto t0 = Clock::now();
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 2.0, 50));  // 20 ms 프레임을 10 ms마다
  sim.poll(t0);
  CHECK(sim.poll(t0 + 10ms) && sim.frame() == 1);
  sim.submit(simple([](auto& c) { c.mutable_pause(); }));
  CHECK(!sim.poll(t0 + 100ms));
  CHECK(sim.state() == v1::SIM_RUN_STATE_PAUSED && sim.frame() == 1);
  sim.submit(simple([](auto& c) { c.mutable_step()->set_frames(3); }));
  CHECK(sim.poll(t0 + 100ms));  // 스텝은 배속 기한과 무관하게 바로 진행
  CHECK(sim.poll(t0 + 100ms));
  CHECK(sim.poll(t0 + 100ms));
  CHECK(!sim.poll(t0 + 100ms));
  CHECK(sim.frame() == 4 && sim.state() == v1::SIM_RUN_STATE_PAUSED);
  sim.submit(simple([](auto& c) { c.mutable_resume(); }));
  CHECK(!sim.poll(t0 + 200ms));  // 재개 시점이 새 기준점
  CHECK(sim.poll(t0 + 210ms) && sim.frame() == 5);
  sim.submit(simple([](auto& c) { c.mutable_set_rate()->set_rate(10.0); }));  // 2 ms 간격
  CHECK(!sim.poll(t0 + 211ms));  // 배속 변경 시점(211 ms)이 새 기준점
  CHECK(!sim.poll(t0 + 212ms));
  CHECK(sim.poll(t0 + 213ms) && sim.frame() == 6);
  CHECK(sim.rate() == 10.0);
  sim.submit(simple([](auto& c) { c.mutable_set_rate()->set_rate(0.0); }));  // 최대 속도
  CHECK(sim.poll(t0 + 213ms) && sim.poll(t0 + 213ms));
  CHECK(sim.frame() == 8);
}

// TC-CORE-007: truth/state와 NavigationReport 내용. 등속 비행 해석해와 비교
void test_truth_and_nav() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());
  sim.load(one_uav());
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  const auto t = Clock::now();
  for (int i = 0; i < 500; ++i) sim.poll(t);  // 10 s
  const auto& tf = rec.truths.back();
  CHECK(tf.header().sim_time_us() == 10000000 && tf.header().source() == "core-0");
  CHECK(tf.entities_size() == 2);
  const auto& u = tf.entities(0);
  CHECK(u.id() == "uav-001" && u.kind() == v1::ENTITY_KIND_UAV && u.alive());
  const double expect_lat = 37.0 + 25.0 * 10.0 / core::mock::kEarthRadiusM * 180.0 / std::numbers::pi;
  CHECK(std::abs(u.kinematics().position().lat_deg() - expect_lat) < 1e-9);
  CHECK(std::abs(u.kinematics().position().lon_deg() - 127.0) < 1e-12);
  CHECK(std::abs(u.kinematics().velocity_ned_mps().x() - 25.0) < 1e-9);
  CHECK(std::abs(u.kinematics().attitude().w() - 1.0) < 1e-12);  // 북쪽 수평 비행
  const auto& g = tf.entities(1);
  CHECK(g.id() == "gcs-01" && std::abs(g.kinematics().position().lat_deg() - 36.9) < 1e-12);

  const auto& nav = rec.navs.back();
  CHECK(nav.header().source() == "uav-001" && nav.header().frame() == 500 && nav.header().seq() == 500);
  CHECK(nav.kinematics().SerializeAsString() == u.kinematics().SerializeAsString());  // 잡음 훅 없음 = 참값
}

// TC-CORE-008: ControlOutput → 동역학 입력. 형식이 맞지 않으면 버리고 이전 입력을 유지한다
void test_control_input() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());
  sim.load(one_uav());
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  const auto t = Clock::now();
  sim.poll(t);
  v1::ControlOutput c;
  c.mutable_kinematic()->set_speed_mps(25.0);
  c.mutable_kinematic()->set_heading_rate_rps(std::numbers::pi / 2 / 10.0);  // 10 s에 90°
  put(bus, keys::onboard("uav-001", "ControlOutput"), c);
  v1::ControlOutput bad;
  bad.mutable_actuator()->set_throttle(1.0);
  for (int i = 0; i < 500; ++i) {
    if (i == 250) put(bus, keys::onboard("uav-001", "ControlOutput"), bad);
    sim.poll(t);
  }
  CHECK(sim.control_mismatches() == 1);
  const auto& v = rec.truths.back().entities(0).kinematics().velocity_ned_mps();
  CHECK(std::abs(v.x()) < 1e-6 && std::abs(v.y() - 25.0) < 1e-6);  // 동쪽으로 선회 완료
}

// TC-CORE-009: 시나리오 JSON, 명령 검증, 상태 보고, 초기화, 격추 고장
void test_scenario_status_reset() {
  const std::string json = R"({
    "name": "json-demo", "frame_hz": 60, "mode": "lockstep", "rate": 0, "seed": 3,
    "participants": ["agent-host-1"],
    "entities": [
      {"id": "uav-001", "kind": "ENTITY_KIND_UAV", "side": "SIDE_BLUE", "dynamics": "DYNAMICS_KIND_DOF3",
       "initial": {"position": {"latDeg": 37.5, "lonDeg": 127.0, "altM": 800},
                   "velocityNedMps": {"x": 0, "y": 20, "z": 0}}, "futureField": 1},
      {"id": "tgt-001", "kind": "ENTITY_KIND_GROUND_TARGET", "side": "SIDE_RED", "dynamics": "DYNAMICS_KIND_SCRIPTED",
       "initial": {"position": {"lat_deg": 37.6, "lon_deg": 127.1}}}
    ]})";
  const auto sc = core::parse_scenario_json(json);
  CHECK(sc.name == "json-demo" && sc.frame_hz == 60 && sc.mode == v1::RUN_MODE_LOCKSTEP && sc.seed == 3);
  CHECK(sc.participants.size() == 1 && sc.entities.size() == 2);
  CHECK(sc.entities[0].dynamics() == v1::DYNAMICS_KIND_DOF3);
  CHECK(sc.entities[1].initial().position().lat_deg() == 37.6);

  bool threw = false;
  try {
    core::parse_scenario_json(R"({"entities": 3})");
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  CHECK(threw);

  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());

  // 형식이 잘못된 ID는 불러오기 실패
  auto bad = one_uav();
  bad.entities[0].set_id("UAV_1");
  threw = false;
  try {
    sim.load(bad);
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  CHECK(threw && sim.state() == v1::SIM_RUN_STATE_IDLE);

  // sim/ctrl/cmd 버스 경로로 불러오기
  v1::SimCommand load;
  load.mutable_load()->set_scenario_json(json);
  put(bus, std::string(keys::kSimCtrlCmd), load);
  const auto t = Clock::now();
  sim.poll(t);
  CHECK(sim.state() == v1::SIM_RUN_STATE_LOADED && sim.entities().size() == 2);
  CHECK(rec.statuses.back().state() == v1::SIM_RUN_STATE_LOADED && rec.statuses.back().scenario_name() == "json-demo");

  sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 120));  // 50..100 밖이면 거부
  sim.poll(t);
  CHECK(sim.state() == v1::SIM_RUN_STATE_LOADED);

  // Start.frame_hz가 0이면 시나리오 값(60 Hz)을 쓴다. 장벽 참여자는 시나리오에서 온다
  sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 0));
  sim.poll(t);
  CHECK(sim.state() == v1::SIM_RUN_STATE_RUNNING && sim.frame_hz() == 60 && sim.dt_us() == 16666);
  CHECK(rec.statuses.back().state() == v1::SIM_RUN_STATE_RUNNING && rec.statuses.back().entity_count() == 2);
  for (std::uint64_t f = 0; f < 3; ++f) {
    v1::FrameDone d;
    d.set_participant("agent-host-1");
    d.set_frame(f);
    put(bus, keys::clock_done("agent-host-1"), d);
    CHECK(sim.poll(t));
  }
  CHECK(sim.frame() == 3);

  v1::SimCommand kill;
  kill.mutable_fault()->set_entity_id("uav-001");
  kill.mutable_fault()->set_fault(v1::FAULT_KIND_KILL);
  sim.submit(kill);
  sim.poll(t);
  CHECK(!sim.entities().alive(0));
  CHECK(rec.events.size() == 1 && rec.events[0].kill().entity_id() == "uav-001");

  const auto initial = rec.truths.front().entities(0).SerializeAsString();
  sim.submit(simple([](auto& c) { c.mutable_reset(); }));
  sim.poll(t);
  CHECK(sim.state() == v1::SIM_RUN_STATE_LOADED && sim.frame() == 0 && sim.entities().alive(0));
  CHECK(rec.truths.back().entities(0).SerializeAsString() == initial);

  sim.submit(simple([](auto& c) { c.mutable_shutdown(); }));
  sim.poll(t);
  CHECK(sim.state() == v1::SIM_RUN_STATE_STOPPED);
  CHECK(rec.statuses.back().state() == v1::SIM_RUN_STATE_STOPPED);
}

// TC-CORE-010: run() 실시간 루프. 50 Hz로 25 프레임이면 약 0.5 s
void test_run_loop() {
  InMemoryBus bus;
  core::CoreConfig cfg = quiet();
  cfg.stop_after_frames = 25;
  core::SimCore sim(bus, core::mock::provider(), cfg);
  sim.load(core::builtin_scenario(20));
  sim.submit(start_cmd(v1::RUN_MODE_REALTIME, 1.0, 50));
  const auto t0 = Clock::now();
  sim.run();
  const double wall = std::chrono::duration<double>(Clock::now() - t0).count();
  CHECK(sim.frame() == 25 && sim.state() == v1::SIM_RUN_STATE_STOPPED);
  CHECK(wall > 0.45 && wall < 0.75);
}

// TC-CORE-012: proto 시나리오(LoadScenario.scenario)와 RunSpec.participants (DEC-024, DEC-025)
void test_proto_scenario() {
  v1::Scenario msg;
  msg.set_name("proto-demo");
  msg.mutable_run()->set_mode(v1::RUN_MODE_LOCKSTEP);
  msg.mutable_run()->set_frame_hz(60);
  msg.mutable_run()->set_seed(7);
  msg.mutable_run()->add_participants("agent-host-1");
  for (const auto& e : one_uav().entities) *msg.add_entities() = e;

  const auto sc = core::from_proto(msg);
  CHECK(sc.name == "proto-demo" && sc.frame_hz == 60 && sc.mode == v1::RUN_MODE_LOCKSTEP && sc.seed == 7);
  CHECK(sc.participants == std::vector<std::string>{"agent-host-1"} && sc.entities.size() == 2);
  CHECK(sc.rate == 1.0);  // 0은 기본값 유지

  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());
  v1::SimCommand load;
  *load.mutable_load()->mutable_scenario() = msg;
  put(bus, std::string(keys::kSimCtrlCmd), load);
  sim.poll(Clock::now());
  CHECK(sim.state() == v1::SIM_RUN_STATE_LOADED && sim.entities().size() == 2);
  CHECK(rec.statuses.back().scenario_name() == "proto-demo");
}

// ---------------------------------------------------------------- WP2 동역학 통합 (TC-CORE-013~017)

core::Wp2DynamicsOptions flat(double elevation_m, std::string integrator = "rk45") {
  core::Wp2DynamicsOptions o;
  o.integrator = std::move(integrator);
  o.terrain_flat_m = elevation_m;
  return o;
}

// FREERUN 최대 속도로 n 프레임 진행한다
void run_frames(core::SimCore& sim, std::uint64_t n) {
  const auto t = Clock::now();
  const auto target = sim.frame() + n;
  while (sim.frame() < target) CHECK(sim.poll(t));
}

v1::SimCommand fault_cmd(const char* id, v1::FaultKind kind, double duration_s = 0.0, bool clear = false) {
  v1::SimCommand c;
  c.set_issuer("ui-test");
  c.mutable_fault()->set_entity_id(id);
  c.mutable_fault()->set_fault(kind);
  c.mutable_fault()->set_duration_s(duration_s);
  c.mutable_fault()->set_clear(clear);
  return c;
}

double ground_speed(const v1::EntityState& e) {
  return std::hypot(e.kinematics().velocity_ned_mps().x(), e.kinematics().velocity_ned_mps().y());
}

const v1::EntityState& entity(const v1::TruthFrame& tf, const std::string& id) {
  for (const auto& e : tf.entities())
    if (e.id() == id) return e;
  throw std::runtime_error("no entity " + id);
}

// 국소 평면 근사 북·동 거리(m). WGS84 곡률 반경
void north_east_m(double lat0, double lon0, double lat, double lon, double& n, double& e) {
  const double r = std::numbers::pi / 180.0, a = 6378137.0, e2 = 6.69437999014e-3;
  const double s = std::sin(lat0 * r), w = 1.0 - e2 * s * s;
  n = (lat - lat0) * r * a * (1.0 - e2) / (w * std::sqrt(w));
  e = (lon - lon0) * r * a / std::sqrt(w) * std::cos(lat0 * r);
}

// TC-CORE-013: WP2 2/3-DoF 모델(rk45)로 20대 lockstep 결정론. DynamicsKind → WP2 모델
void test_wp2_lockstep_determinism() {
  auto scenario = [] {
    auto sc = core::builtin_scenario(20);
    for (std::size_t i = 1; i < sc.entities.size(); i += 2) {
      sc.entities[i].set_dynamics(v1::DYNAMICS_KIND_DOF3);
      sc.entities[i].set_airframe("skywalker_x8");
    }
    return sc;
  };
  auto run_once = [&](std::string& model_names) {
    InMemoryBus bus;
    Recorder rec(bus);
    core::CoreConfig cfg = quiet({"agent-host-1"});
    cfg.nav_noise = [](const std::string&, v1::NavigationReport& nav, std::mt19937_64& rng) {
      std::normal_distribution<double> n(0.0, 2.0);
      nav.mutable_kinematics()->mutable_position()->set_alt_m(nav.kinematics().position().alt_m() + n(rng));
    };
    core::SimCore sim(bus, core::wp2_provider(), cfg);
    // 참여자: 기체마다 다른 선회 명령(2-DoF는 heading_rate, 3-DoF는 bank)을 보내고 완료를 알린다
    auto sub = bus.subscribe(keys::kClockTick, [&](const Sample& s) {
      const auto tick = decode<v1::ClockTick>(s);
      for (int i = 1; i <= 20; ++i) {
        char id[16];
        std::snprintf(id, sizeof id, "uav-%03d", i);
        v1::ControlOutput c;
        auto* k = c.mutable_kinematic();
        k->set_speed_mps(22.0 + 0.2 * i);
        k->set_heading_rate_rps(0.01 * i * std::sin(0.01 * static_cast<double>(tick.frame())));
        k->set_bank_rad(0.02 * i);
        k->set_climb_rate_mps(i % 3 - 1.0);
        put(bus, keys::onboard(id, "ControlOutput"), c);
      }
      v1::FrameDone d;
      d.set_participant("agent-host-1");
      d.set_frame(tick.frame());
      put(bus, keys::clock_done("agent-host-1"), d);
    });
    CHECK(sim.load(scenario()));
    model_names.clear();
    for (std::size_t i = 0; i < sim.entities().size(); ++i)
      model_names += sim.entities().model(i) ? std::string(sim.entities().model(i)->name()) + "," : "-,";
    sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 50, 42));
    const auto t = Clock::now();
    for (int i = 0; i < 1000 && sim.frame() < 250; ++i) sim.poll(t);
    CHECK(sim.frame() == 250);
    CHECK(sim.control_mismatches() == 0);
    // 5 s 동안 명령 속도 쪽으로 움직였다
    const auto& last = rec.truths.back();
    CHECK(std::abs(ground_speed(entity(last, "uav-020")) - 26.0) < 1.0);
    std::string out = rec.truth_bytes.back();
    for (const auto& n : rec.navs) out += n.SerializeAsString();
    return out;
  };
  std::string names_a, names_b;
  const auto a = run_once(names_a), b = run_once(names_b);
  CHECK(!a.empty() && a == b);
  CHECK(names_a.rfind("-,dof3,dof2,dof3,", 0) == 0);  // GCS는 모델 없음
}

// TC-CORE-014: 지면 교차 → kill(cause=ground). 교차 시점에서 멈추고, 지면 위에서 시작하지 않은 엔티티는 제외
void test_ground_kill() {
  for (const char* integ : {"rk45", "rk4"}) {
    InMemoryBus bus;
    Recorder rec(bus);
    core::SimCore sim(bus, core::wp2_provider(flat(50.0, integ)), quiet());
    core::Scenario sc;
    sc.name = "ground";
    v1::EntitySpec u;  // 고도 100.5 m에서 10 m/s로 하강 → 5.05 s에 평지 50 m에 닿는다
    u.set_id("uav-001");
    u.set_kind(v1::ENTITY_KIND_UAV);
    u.set_dynamics(v1::DYNAMICS_KIND_DOF2);
    u.mutable_initial()->mutable_position()->set_lat_deg(37.0);
    u.mutable_initial()->mutable_position()->set_lon_deg(127.0);
    u.mutable_initial()->mutable_position()->set_alt_m(100.5);
    u.mutable_initial()->mutable_velocity_ned_mps()->set_x(20.0);
    u.mutable_initial()->mutable_velocity_ned_mps()->set_z(10.0);
    sc.entities.push_back(u);
    v1::EntitySpec g = u;  // 지면 높이(고도 = 지형)에서 수평으로 달리는 지상 표적(DOF2)
    g.set_id("tgt-001");
    g.set_kind(v1::ENTITY_KIND_GROUND_TARGET);
    g.mutable_initial()->mutable_position()->set_alt_m(50.0);
    g.mutable_initial()->mutable_velocity_ned_mps()->set_z(0.0);
    sc.entities.push_back(g);
    CHECK(sim.load(sc));
    sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
    run_frames(sim, 300);  // 6 s

    CHECK(!sim.entities().alive(0) && sim.entities().alive(1));
    CHECK(rec.events.size() == 1);
    if (!rec.events.empty()) {
      const auto& ev = rec.events[0];
      CHECK(ev.kill().entity_id() == "uav-001" && ev.kill().cause() == "ground");
      CHECK(std::abs(static_cast<double>(ev.header().sim_time_us()) - 5.05e6) < 10.0);
      CHECK(ev.header().frame() == 253);  // 교차 구간 [5.04, 5.06] s(프레임 252) → 처음 죽은 채 발행되는 프레임 253
    }
    const auto& dead = entity(rec.truths.back(), "uav-001");
    CHECK(!dead.alive() && std::abs(dead.kinematics().position().alt_m() - 50.0) < 0.01);
    // 죽은 뒤에는 NavigationReport를 내지 않는다
    std::size_t navs_uav = 0;
    for (const auto& n : rec.navs) navs_uav += n.header().source() == "uav-001";
    CHECK(navs_uav == 253);  // 프레임 0..252
  }
}

// TC-CORE-015: DYNAMICS_KIND_SCRIPTED. 초기 위치 → script_path를 초기 속도 크기로 따라가고 끝점에 멈춘다
void test_scripted_path() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::wp2_provider(), quiet());
  constexpr double lat0 = 37.0, lon0 = 127.0;
  double n1, e1, n2, e2;
  core::Scenario sc;
  sc.name = "scripted";
  v1::EntitySpec t;
  t.set_id("tgt-001");
  t.set_kind(v1::ENTITY_KIND_GROUND_TARGET);
  t.set_side(v1::SIDE_RED);
  t.set_dynamics(v1::DYNAMICS_KIND_SCRIPTED);
  t.mutable_initial()->mutable_position()->set_lat_deg(lat0);
  t.mutable_initial()->mutable_position()->set_lon_deg(lon0);
  t.mutable_initial()->mutable_velocity_ned_mps()->set_y(10.0);  // 크기만 쓴다
  auto* p1 = t.add_script_path();  // 북쪽 약 1 km
  p1->set_lat_deg(lat0 + 0.009);
  p1->set_lon_deg(lon0);
  auto* p2 = t.add_script_path();  // 다시 동쪽 약 1 km
  p2->set_lat_deg(lat0 + 0.009);
  p2->set_lon_deg(lon0 + 0.0112);
  north_east_m(lat0, lon0, p1->lat_deg(), p1->lon_deg(), n1, e1);
  north_east_m(p1->lat_deg(), lon0, p2->lat_deg(), p2->lon_deg(), n2, e2);
  sc.entities.push_back(t);
  v1::EntitySpec fixed = t;  // 경로가 없으면 초기 위치 고정
  fixed.set_id("tgt-002");
  fixed.clear_script_path();
  sc.entities.push_back(fixed);
  CHECK(sim.load(sc));
  CHECK(sim.entities().model(0) && sim.entities().model(0)->name() == "scripted" && !sim.entities().model(1));
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));

  auto at = [&](double& n, double& e, double& vn, double& ve) {
    const auto& k = entity(rec.truths.back(), "tgt-001").kinematics();
    north_east_m(lat0, lon0, k.position().lat_deg(), k.position().lon_deg(), n, e);
    vn = k.velocity_ned_mps().x();
    ve = k.velocity_ned_mps().y();
  };
  double n, e, vn, ve;
  run_frames(sim, 2500);  // 50 s: 첫 구간 500 m
  at(n, e, vn, ve);
  CHECK(std::abs(n - 500.0) < 1.0 && std::abs(e) < 0.1);
  CHECK(std::abs(vn - 10.0) < 1e-9 && std::abs(ve) < 1e-9);
  const double t_corner = n1 / 10.0;
  run_frames(sim, static_cast<std::uint64_t>((t_corner + 50.0) * 50) - 2500);  // 모퉁이 + 50 s
  at(n, e, vn, ve);
  CHECK(std::abs(n - n1) < 1.0 && std::abs(e - 500.0) < 1.0);
  CHECK(std::abs(ve - 10.0) < 1e-9 && std::abs(vn) < 1e-9);
  run_frames(sim, 100 * 50);  // 끝점 지나 정지
  at(n, e, vn, ve);
  CHECK(std::abs(n - n1) < 1.0 && std::abs(e - e2) < 1.0 && vn == 0.0 && ve == 0.0);
  const auto& f = entity(rec.truths.back(), "tgt-002").kinematics().position();
  CHECK(f.lat_deg() == lat0 && f.lon_deg() == lon0);
  // 고도 0 m = 평지에서 시작했으므로 지면 이벤트가 걸리지 않는다
  CHECK(sim.entities().alive(0) && rec.events.empty());
}

// TC-CORE-016: InjectFault ENGINE(속도 명령 최소, 기간 후 복귀), NAV(NavigationReport 중단·해제), SENSOR(기록),
//              LINK_CUT·GCS_LINK_CUT 무시, Reset 시 해제
void test_faults() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::wp2_provider(), quiet());
  auto sc = one_uav();
  sc.entities[0].set_airframe("skywalker_x8");  // 최소 속도 12 m/s
  CHECK(sim.load(sc));
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  run_frames(sim, 50);
  CHECK(std::abs(ground_speed(entity(rec.truths.back(), "uav-001")) - 25.0) < 1e-6);

  sim.submit(fault_cmd("uav-001", v1::FAULT_KIND_ENGINE, 3.0));
  run_frames(sim, 150);  // 3 s: 25 → 12 + 13·e^-3 ≈ 12.65
  CHECK(std::abs(ground_speed(entity(rec.truths.back(), "uav-001")) - 12.65) < 0.1);
  CHECK(!sim.fault_active("uav-001", v1::FAULT_KIND_ENGINE));  // 기간이 지나 풀렸다
  run_frames(sim, 500);  // 마지막 명령(25 m/s)으로 돌아간다
  CHECK(std::abs(ground_speed(entity(rec.truths.back(), "uav-001")) - 25.0) < 0.01);

  auto navs = [&] {
    std::size_t c = 0;
    for (const auto& n : rec.navs) c += n.header().source() == "uav-001";
    return c;
  };
  sim.submit(fault_cmd("uav-001", v1::FAULT_KIND_NAV));
  sim.poll(Clock::now());
  CHECK(sim.fault_active("uav-001", v1::FAULT_KIND_NAV));
  const auto before = navs();
  run_frames(sim, 20);
  CHECK(navs() == before);
  sim.submit(fault_cmd("uav-001", v1::FAULT_KIND_NAV, 0.0, true));
  run_frames(sim, 20);
  CHECK(navs() == before + 20 && !sim.fault_active("uav-001", v1::FAULT_KIND_NAV));

  sim.submit(fault_cmd("uav-001", v1::FAULT_KIND_SENSOR));
  sim.submit(fault_cmd("uav-001", v1::FAULT_KIND_LINK_CUT));
  sim.submit(fault_cmd("uav-001", v1::FAULT_KIND_GCS_LINK_CUT));
  sim.submit(fault_cmd("gcs-01", v1::FAULT_KIND_ENGINE));  // 모델 없는 엔티티
  run_frames(sim, 1);
  CHECK(sim.fault_active("uav-001", v1::FAULT_KIND_SENSOR));
  CHECK(!sim.fault_active("uav-001", v1::FAULT_KIND_LINK_CUT) && !sim.fault_active("gcs-01", v1::FAULT_KIND_ENGINE));
  CHECK(sim.entities().alive(0) && rec.events.empty());

  sim.submit(simple([](auto& c) { c.mutable_reset(); }));
  sim.poll(Clock::now());
  CHECK(!sim.fault_active("uav-001", v1::FAULT_KIND_SENSOR));

  // 목 공급자에는 engine_out이 없으므로 ENGINE을 처리하지 않는다
  InMemoryBus bus2;
  core::SimCore mock(bus2, core::mock::provider(), quiet());
  mock.load(one_uav());
  mock.submit(fault_cmd("uav-001", v1::FAULT_KIND_ENGINE));
  mock.poll(Clock::now());
  CHECK(!mock.fault_active("uav-001", v1::FAULT_KIND_ENGINE));
}

// TC-CORE-017: WP2 공급자 설정. 적분기 이름 검사, airframe 파라미터, rk4/rk45 결과 일치, 바람 반영(DEC-023)
void test_wp2_provider() {
  bool threw = false;
  try {
    core::wp2_provider(flat(0.0, "euler"));
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  CHECK(threw);
  CHECK(core::airframe_params(v1::DYNAMICS_KIND_DOF2, "skywalker_x8").at("min_speed_mps") == 12.0);
  CHECK(core::airframe_params(v1::DYNAMICS_KIND_DOF3, "aerosonde").count("max_bank_rad") == 1);
  CHECK(core::airframe_params(v1::DYNAMICS_KIND_DOF2, "aerosonde").count("max_bank_rad") == 0);
  CHECK(core::airframe_params(v1::DYNAMICS_KIND_DOF2, "generic").empty());

  auto final_state = [](const char* integ, double wind_e) {
    InMemoryBus bus;
    Recorder rec(bus);
    auto p = core::wp2_provider(flat(0.0, integ));
    p.env.wind_ned_mps[1] = wind_e;
    core::SimCore sim(bus, std::move(p), quiet());
    sim.load(one_uav());
    sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
    run_frames(sim, 500);  // 10 s
    return entity(rec.truths.back(), "uav-001").kinematics();
  };
  const auto a = final_state("rk45", 0.0), b = final_state("rk4", 0.0), w = final_state("rk45", 5.0);
  double n, e;
  north_east_m(37.0, 127.0, a.position().lat_deg(), a.position().lon_deg(), n, e);
  CHECK(std::abs(n - 250.0) < 0.05 && std::abs(e) < 1e-6);  // 고도 500 m의 곡률 반경 차 0.02 m
  north_east_m(a.position().lat_deg(), a.position().lon_deg(), b.position().lat_deg(), b.position().lon_deg(), n, e);
  CHECK(std::abs(n) < 1e-3 && std::abs(e) < 1e-3);
  north_east_m(37.0, 127.0, w.position().lat_deg(), w.position().lon_deg(), n, e);
  CHECK(std::abs(e - 50.0) < 0.05 && std::abs(w.velocity_ned_mps().y() - 5.0) < 1e-9);
}

}  // namespace

int main() {
  test_freerun_progress();
  test_realtime_pacing();
  test_lockstep_barrier();
  test_lockstep_determinism();
  test_pause_step_rate();
  test_truth_and_nav();
  test_control_input();
  test_scenario_status_reset();
  test_run_loop();
  test_proto_scenario();
  test_wp2_lockstep_determinism();
  test_ground_kill();
  test_scripted_path();
  test_faults();
  test_wp2_provider();
  if (g_failures == 0) std::puts("swarm_core_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
