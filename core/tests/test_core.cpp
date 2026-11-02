// TC-CORE-002~012: SimCore 단위 시험 (InMemoryBus, 목 동역학)
// TC-CORE-013~017: WP2 동역학 통합, 지면 충돌, 스크립트 경로, 고장 주입
// TC-CORE-019~023: 동역학 매개변수 (DEC-035)
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
  std::vector<v1::EntityParams> params;
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
    subs.push_back(bus.subscribe("sim/param/**", [this](const Sample& s) {
      params.push_back(decode<v1::EntityParams>(s));
      CHECK(s.encoding == "application/protobuf;swarm.v1.EntityParams");
      CHECK(s.key == "sim/param/" + params.back().entity_id() + "/dynamics");
    }));
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

// lockstep 준비 신호: 첫 틱 전의 FrameDone{frame=0} (DEC-037)
void ready(Bus& bus, const char* participant) {
  v1::FrameDone d;
  d.set_participant(participant);
  d.set_frame(0);
  put(bus, keys::clock_done(participant), d);
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
  ready(bus, "agent-host-1");
  ready(bus, "agent-host-2");
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
    ready(bus, "agent-host-1");
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
  ready(bus, "agent-host-1");
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
    ready(bus, "agent-host-1");
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

// ---------------------------------------------------------------- 동역학 매개변수 (TC-CORE-019~023, DEC-035)

void set_number(google::protobuf::Struct* st, const char* name, double v) {
  (*st->mutable_fields())[name].set_number_value(v);
}

v1::SimCommand set_params_cmd(const char* id, v1::ParamOwner owner, std::function<void(google::protobuf::Struct*)> f) {
  v1::SimCommand c;
  c.set_issuer("ui-test");
  c.mutable_set_params()->set_entity_id(id);
  c.mutable_set_params()->set_owner(owner);
  f(c.mutable_set_params()->mutable_values());
  return c;
}

const v1::EntityParams* latest_params(const Recorder& rec, const std::string& id) {
  for (auto it = rec.params.rbegin(); it != rec.params.rend(); ++it)
    if (it->entity_id() == id) return &*it;
  return nullptr;
}

std::size_t count_params(const Recorder& rec, const std::string& id) {
  std::size_t n = 0;
  for (const auto& p : rec.params) n += p.entity_id() == id;
  return n;
}

double value_of(const v1::EntityParams& ep, const char* name) {
  const auto it = ep.values().fields().find(name);
  return it == ep.values().fields().end() ? -1e300 : it->second.number_value();
}

std::string rejected_str(const v1::EntityParams& ep) {
  std::string s;
  for (const auto& r : ep.rejected()) s += r.name() + ":" + r.reason() + " ";
  return s;
}

// TC-CORE-019: 값 순서 기본값 → airframe 표 → dynamics_params. 적재 직후 EntityParams 내용(선언, 값, 거부 사유)
void test_params_load() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::wp2_provider(), quiet());
  auto sc = one_uav();
  sc.entities[0].set_airframe("skywalker_x8");  // min 12, max 28
  auto* dp = sc.entities[0].mutable_dynamics_params();
  set_number(dp, "max_speed_mps", 30.0);  // airframe 위에 덮어쓴다
  set_number(dp, "tau_speed_s", 1e6);     // 범위 밖
  set_number(dp, "bogus", 1.0);           // 선언하지 않은 이름
  set_number(dp, "tau_bank_s", 0.4);      // 2-DoF에는 없는 이름
  (*dp->mutable_fields())["min_speed_mps"].set_string_value("x");  // 타입 위반
  v1::EntitySpec b = sc.entities[0];      // 모르는 airframe은 기본값, dynamics_params는 적용
  b.set_id("uav-002");
  b.set_dynamics(v1::DYNAMICS_KIND_DOF3);
  b.set_airframe("mystery");
  b.clear_dynamics_params();
  set_number(b.mutable_dynamics_params(), "min_speed_mps", 5.0);
  sc.entities.push_back(b);
  CHECK(sim.load(sc));

  CHECK(count_params(rec, "uav-001") == 1 && count_params(rec, "uav-002") == 1);
  CHECK(count_params(rec, "gcs-01") == 0);  // 매개변수가 없는 엔티티는 발행하지 않는다
  const auto* a = latest_params(rec, "uav-001");
  CHECK(a && a->owner() == v1::PARAM_OWNER_DYNAMICS && a->plugin() == "dof2" && a->specs_size() == 7);
  if (a) {
    CHECK(value_of(*a, "min_speed_mps") == 12.0);   // airframe 표
    CHECK(value_of(*a, "max_speed_mps") == 30.0);   // 시나리오
    CHECK(value_of(*a, "tau_speed_s") == 1.0);      // 범위 위반이라 기본값 유지
    CHECK(a->values().fields_size() == 7 && a->sim_time_us() == 0);
    CHECK(rejected_str(*a) == "bogus:unknown min_speed_mps:type tau_bank_s:unknown tau_speed_s:range ");
    const v1::ParamSpec* spec = nullptr;
    for (const auto& sp : a->specs())
      if (sp.name() == "tau_speed_s") spec = &sp;
    CHECK(spec && spec->layer() == v1::PARAM_LAYER_CONTROL && spec->unit() == "s" && spec->runtime());
    CHECK(spec && spec->has_min() && spec->min() == 0.05 && spec->max() == 30.0);
    CHECK(spec && spec->default_value().number_value() == 1.0 && !spec->description().empty());
    bool airframe_layer = false;
    for (const auto& sp : a->specs()) airframe_layer |= sp.layer() == v1::PARAM_LAYER_AIRFRAME;
    CHECK(airframe_layer);
  }
  const auto* c = latest_params(rec, "uav-002");
  CHECK(c && c->plugin() == "dof3" && c->specs_size() == 8 && c->rejected_size() == 0);
  if (c) {
    CHECK(value_of(*c, "min_speed_mps") == 5.0);
    CHECK(std::abs(value_of(*c, "max_bank_rad") - 1.0471975511965976) < 1e-12);
  }
  // 적용한 값은 모델에 반영돼 있다
  CHECK(sim.entities().model(0)->get_param("max_speed_mps") == 30.0);
}

// TC-CORE-020: 실행 중 SetParams. 적용·거부 사유·발행 내용, 다른 소유자·모르는 엔티티 무시, Reset 복원
void test_params_runtime() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::wp2_provider(), quiet());
  auto sc = one_uav();
  set_number(sc.entities[0].mutable_dynamics_params(), "tau_bank_s", 0.4);  // 거부 → 첫 발행에 실린다
  CHECK(sim.load(sc));
  CHECK(latest_params(rec, "uav-001")->rejected_size() == 1);
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  run_frames(sim, 10);
  CHECK(count_params(rec, "uav-001") == 1);

  sim.submit(set_params_cmd("uav-001", v1::PARAM_OWNER_DYNAMICS, [](auto* st) {
    set_number(st, "max_heading_rate_rps", 0.2);
    set_number(st, "bogus", 1.0);
    set_number(st, "tau_speed_s", 0.0);
    (*st->mutable_fields())["min_speed_mps"].set_bool_value(true);
  }));
  run_frames(sim, 1);
  CHECK(count_params(rec, "uav-001") == 2);
  const auto* p = latest_params(rec, "uav-001");
  CHECK(p && value_of(*p, "max_heading_rate_rps") == 0.2 && value_of(*p, "tau_speed_s") == 1.0);
  CHECK(p && value_of(*p, "min_speed_mps") == 0.0);
  CHECK(p && rejected_str(*p) == "bogus:unknown min_speed_mps:type tau_speed_s:range ");  // 직전 변경의 거부만
  CHECK(p && p->sim_time_us() == 10 * 20000);  // 프레임 10 시작에 적용
  CHECK(sim.entities().model(0)->get_param("max_heading_rate_rps") == 0.2);

  // FA·MA 소유자, 모르는 엔티티, 매개변수 없는 엔티티는 Core가 처리하지 않는다
  sim.submit(set_params_cmd("uav-001", v1::PARAM_OWNER_FA, [](auto* st) { set_number(st, "max_heading_rate_rps", 0.9); }));
  sim.submit(set_params_cmd("uav-099", v1::PARAM_OWNER_DYNAMICS, [](auto* st) { set_number(st, "x", 1.0); }));
  sim.submit(set_params_cmd("gcs-01", v1::PARAM_OWNER_DYNAMICS, [](auto* st) { set_number(st, "x", 1.0); }));
  run_frames(sim, 1);
  CHECK(count_params(rec, "uav-001") == 2 && count_params(rec, "gcs-01") == 0);
  CHECK(sim.entities().model(0)->get_param("max_heading_rate_rps") == 0.2);

  // 거부 목록은 마지막 변경 것으로 바뀐다
  sim.submit(set_params_cmd("uav-001", v1::PARAM_OWNER_DYNAMICS, [](auto* st) { set_number(st, "max_heading_rate_rps", 0.4); }));
  run_frames(sim, 1);
  CHECK(count_params(rec, "uav-001") == 3 && latest_params(rec, "uav-001")->rejected_size() == 0);
  CHECK(value_of(*latest_params(rec, "uav-001"), "max_heading_rate_rps") == 0.4);

  // Reset은 시나리오 값으로 되돌리고 다시 발행한다(첫 발행의 거부 포함)
  sim.submit(simple([](auto& c) { c.mutable_reset(); }));
  sim.poll(Clock::now());
  CHECK(count_params(rec, "uav-001") == 4);
  const auto* r = latest_params(rec, "uav-001");
  CHECK(r && value_of(*r, "max_heading_rate_rps") == 1.0 && rejected_str(*r) == "tau_bank_s:unknown ");
  CHECK(sim.entities().model(0)->get_param("max_heading_rate_rps") == 1.0);
}

// 시험용: 목 모델에 매개변수를 붙인다. mass_kg는 실행 중 변경 불가
class GuardedMock final : public dyn::DynamicsModel {
 public:
  std::string_view name() const override { return "guarded_mock"; }
  int dof() const override { return 2; }
  std::size_t state_size() const override { return inner_.state_size(); }
  std::size_t input_size() const override { return inner_.input_size(); }
  void derivatives(double t, std::span<const double> x, std::span<const double> u, const dyn::Environment& env,
                   std::span<double> dxdt) const override {
    inner_.derivatives(t, x, u, env, dxdt);
  }
  bool map_control(const v1::ControlOutput& c, std::span<double> u) const override { return inner_.map_control(c, u); }
  void to_kinematic(std::span<const double> x, const dyn::Environment& env, dyn::KinematicSample& o) const override {
    inner_.to_kinematic(x, env, o);
  }
  void from_kinematic(const dyn::KinematicSample& in, std::span<double> x) const override { inner_.from_kinematic(in, x); }

  std::span<const dyn::ParamDesc> param_descs() const override { return kDescs; }
  double get_param(std::string_view n) const override { return n == "mass_kg" ? mass_ : n == "gain" ? gain_ : 0.0; }
  bool set_param(std::string_view n, double v) override {
    for (const auto& d : kDescs)
      if (d.name == n) {
        if (!(v >= d.min && v <= d.max)) return false;
        (n == "mass_kg" ? mass_ : gain_) = v;
        return true;
      }
    return false;
  }

 private:
  static constexpr dyn::ParamDesc kDescs[] = {
      {"mass_kg", dyn::ParamLayer::kAirframe, 10.0, "kg", 1.0, 100.0, false, "질량"},
      {"gain", dyn::ParamLayer::kControl, 1.0, "", 0.0, 5.0, true, "이득"},
  };
  core::mock::ConstantVelocity2Dof inner_;
  double mass_ = 10.0, gain_ = 1.0;
};

// TC-CORE-021: runtime=false 항목은 시나리오 적재에서는 적용되고 실행 중 SetParams에서는 not_runtime으로 거부된다
void test_params_not_runtime() {
  InMemoryBus bus;
  Recorder rec(bus);
  auto provider = core::mock::provider();
  provider.make_model = [](const v1::EntitySpec&) { return std::make_unique<GuardedMock>(); };
  core::SimCore sim(bus, std::move(provider), quiet());
  auto sc = one_uav();
  set_number(sc.entities[0].mutable_dynamics_params(), "mass_kg", 20.0);
  CHECK(sim.load(sc));
  CHECK(value_of(*latest_params(rec, "uav-001"), "mass_kg") == 20.0 && latest_params(rec, "uav-001")->rejected_size() == 0);
  CHECK(latest_params(rec, "uav-001")->plugin() == "guarded_mock");

  sim.submit(set_params_cmd("uav-001", v1::PARAM_OWNER_DYNAMICS, [](auto* st) {
    set_number(st, "mass_kg", 30.0);
    set_number(st, "gain", 2.0);
  }));
  sim.poll(Clock::now());
  const auto* p = latest_params(rec, "uav-001");
  CHECK(p && value_of(*p, "mass_kg") == 20.0 && value_of(*p, "gain") == 2.0);
  CHECK(p && rejected_str(*p) == "mass_kg:not_runtime ");
  bool spec_not_runtime = false;
  for (const auto& sp : p->specs()) spec_not_runtime |= sp.name() == "mass_kg" && !sp.runtime();
  CHECK(spec_not_runtime);

  sim.submit(set_params_cmd("uav-001", v1::PARAM_OWNER_DYNAMICS, [](auto* st) { set_number(st, "gain", 9.0); }));
  sim.poll(Clock::now());
  CHECK(rejected_str(*latest_params(rec, "uav-001")) == "gain:range " && value_of(*latest_params(rec, "uav-001"), "gain") == 2.0);
}

// TC-CORE-022: lockstep 재현성. 같은 시드·같은 프레임의 SetParams면 truth가 같고, 프레임이 다르거나 없으면 다르다
void test_params_lockstep() {
  struct Result {
    std::string bytes;
    double heading;
  };
  auto run_once = [](int set_frame) {
    InMemoryBus bus;
    Recorder rec(bus);
    core::SimCore sim(bus, core::wp2_provider(), quiet({"agent-host-1"}));
    auto sub = bus.subscribe(keys::kClockTick, [&](const Sample& s) {
      const auto tick = decode<v1::ClockTick>(s);
      v1::ControlOutput c;
      c.mutable_kinematic()->set_speed_mps(25.0);
      c.mutable_kinematic()->set_heading_rate_rps(0.5);
      put(bus, keys::onboard("uav-001", "ControlOutput"), c);
      v1::FrameDone d;
      d.set_participant("agent-host-1");
      d.set_frame(tick.frame());
      put(bus, keys::clock_done("agent-host-1"), d);
    });
    CHECK(sim.load(one_uav()));
    ready(bus, "agent-host-1");
    sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 50, 42));
    const auto t = Clock::now();
    bool sent = false;
    for (int i = 0; i < 2000 && sim.frame() < 200; ++i) {
      if (!sent && set_frame >= 0 && sim.frame() == static_cast<std::uint64_t>(set_frame)) {
        sim.submit(set_params_cmd("uav-001", v1::PARAM_OWNER_DYNAMICS,
                                  [](auto* st) { set_number(st, "max_heading_rate_rps", 0.2); }));
        sent = true;
      }
      sim.poll(t);
    }
    CHECK(sim.frame() == 200);
    if (set_frame >= 0) {
      // 프레임 경계에서 적용된다: 발행된 EntityParams의 시각은 set_frame의 시작이다
      const auto* p = latest_params(rec, "uav-001");
      CHECK(p && p->sim_time_us() == static_cast<std::uint64_t>(set_frame) * 20000);
    }
    const auto& v = entity(rec.truths.back(), "uav-001").kinematics().velocity_ned_mps();
    return Result{rec.truth_bytes.back(), std::atan2(v.y(), v.x())};
  };
  const auto a = run_once(50), b = run_once(50), c = run_once(51), d = run_once(-1);
  CHECK(a.bytes == b.bytes && !a.bytes.empty());
  CHECK(a.bytes != c.bytes);
  CHECK(a.bytes != d.bytes);
  // 제한을 0.2 rad/s로 낮추면 4 s(프레임 50~200 = 3 s) 동안 덜 돈다
  CHECK(a.heading < d.heading - 0.5);
}

// TC-CORE-023: 적재 상태에서 1초(벽시계)마다 EntityParams를 다시 발행한다. 실행 중에는 발행하지 않는다
void test_params_periodic() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::wp2_provider(), quiet());
  CHECK(sim.load(one_uav()));
  CHECK(count_params(rec, "uav-001") == 1);
  const auto t0 = Clock::now();
  sim.poll(t0 + 300ms);
  CHECK(count_params(rec, "uav-001") == 1);
  sim.poll(t0 + 1200ms);
  CHECK(count_params(rec, "uav-001") == 2);
  sim.poll(t0 + 1500ms);
  CHECK(count_params(rec, "uav-001") == 2);
  sim.poll(t0 + 2300ms);
  CHECK(count_params(rec, "uav-001") == 3);
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  run_frames(sim, 5);
  sim.poll(t0 + 10s);
  CHECK(count_params(rec, "uav-001") == 3);
}

// TC-CORE-024: 적재 직후와 LOADED 상태 1초마다 sim/ctrl/scenario에 Scenario 전체를 발행한다 (DEC-037)
void test_scenario_publish() {
  InMemoryBus bus;
  std::vector<v1::Scenario> got;
  bool encoding_ok = true;
  auto sub = bus.subscribe(keys::kSimCtrlScenario, [&](const Sample& s) {
    encoding_ok = encoding_ok && s.encoding == protobuf_encoding("swarm.v1.Scenario");
    got.push_back(decode<v1::Scenario>(s));
  });
  core::SimCore sim(bus, core::wp2_provider(), quiet());

  // proto로 받은 시나리오는 지도·임무 계획까지 원본 그대로 나간다
  v1::Scenario msg;
  msg.set_name("pub-demo");
  msg.set_description("원본 보존");
  msg.mutable_run()->set_mode(v1::RUN_MODE_FREERUN);
  msg.mutable_run()->set_frame_hz(60);
  msg.mutable_run()->set_seed(9);
  *msg.add_entities() = core::builtin_scenario(1).entities.at(1);
  v1::SimCommand load;
  *load.mutable_load()->mutable_scenario() = msg;
  sim.submit(load);
  const auto t0 = Clock::now();
  sim.poll(t0);
  CHECK(sim.state() == v1::SIM_RUN_STATE_LOADED && got.size() == 1 && encoding_ok);
  CHECK(got[0].SerializeAsString() == msg.SerializeAsString());

  sim.poll(t0 + 300ms);
  CHECK(got.size() == 1);
  sim.poll(t0 + 1200ms);
  CHECK(got.size() == 2);
  sim.poll(t0 + 2300ms);
  CHECK(got.size() == 3 && got[2].SerializeAsString() == msg.SerializeAsString());

  // Reset 직후에도 낸다. 실행 중에는 내지 않는다
  sim.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  run_frames(sim, 3);
  sim.poll(t0 + 10s);
  CHECK(got.size() == 3);
  sim.submit(simple([](auto& c) { c.mutable_reset(); }));
  sim.poll(t0 + 10s);
  CHECK(got.size() == 4);

  // 최소 JSON·내장 시나리오(원본 없음)는 Scenario 필드에서 만든다
  core::Scenario sc = core::builtin_scenario(2);
  sc.name = "builtin-pub";
  sc.mode = v1::RUN_MODE_LOCKSTEP;
  sc.seed = 5;
  sc.participants = {"agent-host-1"};
  CHECK(sim.load(sc));
  const auto& last = got.back();
  CHECK(got.size() == 5 && last.name() == "builtin-pub" && last.run().mode() == v1::RUN_MODE_LOCKSTEP);
  CHECK(last.run().seed() == 5 && last.run().frame_hz() == sc.frame_hz && last.run().participants_size() == 1);
  CHECK(last.entities_size() == 3);
}

// TC-CORE-025: lockstep은 RunSpec.participants 전원의 준비 신호(FrameDone{frame=0}) 뒤에 첫 틱을 낸다 (DEC-037)
void test_lockstep_ready() {
  InMemoryBus bus;
  Recorder rec(bus);
  core::SimCore sim(bus, core::mock::provider(), quiet());
  core::Scenario sc = one_uav();
  sc.mode = v1::RUN_MODE_LOCKSTEP;
  sc.participants = {"agent-host-1", "link-host"};  // 시나리오 쪽 참여자
  CHECK(sim.load(sc));
  sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 50));
  const auto t = Clock::now();

  CHECK(!sim.poll(t));
  CHECK(sim.state() == v1::SIM_RUN_STATE_RUNNING && rec.ticks.empty());  // 준비 전에는 틱이 없다
  ready(bus, "agent-host-1");
  ready(bus, "agent-uuu-9");  // 등록되지 않은 참여자는 준비로 치지 않는다
  CHECK(!sim.poll(t));
  CHECK(rec.ticks.empty());
  ready(bus, "link-host");
  CHECK(!sim.poll(t));  // 첫 틱을 내지만 프레임 0의 완료 응답을 기다린다
  CHECK(rec.ticks.size() == 1 && rec.ticks[0].frame() == 0 && sim.frame() == 0);

  // 준비 신호는 프레임 0의 완료로 세지 않는다
  CHECK(!sim.poll(t));
  CHECK(sim.frame() == 0);
  auto done = [&](const char* p, std::uint64_t f) {
    v1::FrameDone d;
    d.set_participant(p);
    d.set_frame(f);
    put(bus, keys::clock_done(p), d);
  };
  done("agent-host-1", 0);
  CHECK(!sim.poll(t));
  done("link-host", 0);
  CHECK(sim.poll(t) && sim.frame() == 1);

  // 시작 후에는 frame=0 신호가 준비로 쓰이지 않는다
  ready(bus, "agent-host-1");
  CHECK(!sim.poll(t));
  CHECK(sim.frame() == 1);

  // Start 전에 보낸 준비 신호도 인정한다. 비lockstep 모드는 준비 신호를 기다리지 않는다
  InMemoryBus bus2;
  Recorder rec2(bus2);
  core::SimCore sim2(bus2, core::mock::provider(), quiet({"agent-host-1"}));
  sim2.load(one_uav());
  ready(bus2, "agent-host-1");
  sim2.poll(t);
  sim2.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 50));
  sim2.poll(t);
  CHECK(rec2.ticks.size() == 1);

  InMemoryBus bus3;
  Recorder rec3(bus3);
  core::SimCore sim3(bus3, core::mock::provider(), quiet({"agent-host-1"}));
  sim3.load(one_uav());
  sim3.submit(start_cmd(v1::RUN_MODE_FREERUN, 0.0, 50));
  CHECK(sim3.poll(t) && sim3.frame() == 1 && !rec3.ticks.empty());
}

// TC-CORE-026: lockstep 준비 대기 중에도 시나리오를 1초마다 재발행하고, 첫 틱 이후에는 멈춘다 (DEC-037)
void test_scenario_late_joiner() {
  InMemoryBus bus;
  core::SimCore sim(bus, core::mock::provider(), quiet({"agent-host-1"}));
  core::Scenario sc = one_uav();
  sc.name = "late";
  sc.mode = v1::RUN_MODE_LOCKSTEP;
  CHECK(sim.load(sc));
  sim.submit(start_cmd(v1::RUN_MODE_LOCKSTEP, 0.0, 50));
  const auto t0 = Clock::now();
  sim.poll(t0);
  CHECK(sim.state() == v1::SIM_RUN_STATE_RUNNING);

  // 적재 뒤에 구독한 참여자가 대기 중 재발행을 받는다
  std::vector<v1::Scenario> got;
  auto sub = bus.subscribe(keys::kSimCtrlScenario, [&](const Sample& s) { got.push_back(decode<v1::Scenario>(s)); });
  sim.poll(t0 + 300ms);
  CHECK(got.empty());
  sim.poll(t0 + 1200ms);
  CHECK(got.size() == 1 && got[0].name() == "late" && got[0].run().mode() == v1::RUN_MODE_LOCKSTEP);
  sim.poll(t0 + 1500ms);
  CHECK(got.size() == 1);
  sim.poll(t0 + 2300ms);
  CHECK(got.size() == 2);

  ready(bus, "agent-host-1");
  sim.poll(t0 + 2400ms);  // 첫 틱
  CHECK(sim.frame() == 0);
  sim.poll(t0 + 10s);
  sim.poll(t0 + 20s);
  CHECK(got.size() == 2);
}

// TC-CORE-027: CLI의 --mode/--rate/--hz/--seed 재정의가 적재 필드와 발행하는 Scenario.run에 반영된다 (DEC-037)
void test_cli_override() {
  core::Scenario proto_sc = core::from_proto([] {
    v1::Scenario m;
    m.set_name("demo");
    m.mutable_run()->set_mode(v1::RUN_MODE_REALTIME);
    m.mutable_run()->set_frame_hz(50);
    m.mutable_run()->add_participants("agent-host-1");
    return m;
  }());
  core::apply_run_override(proto_sc, {"lockstep", "2.5", "60", "7"});
  CHECK(proto_sc.mode == v1::RUN_MODE_LOCKSTEP && proto_sc.rate == 2.5 && proto_sc.frame_hz == 60 && proto_sc.seed == 7);
  const auto out = core::to_proto(proto_sc);
  CHECK(out.run().mode() == v1::RUN_MODE_LOCKSTEP && out.run().rate() == 2.5 && out.run().frame_hz() == 60);
  CHECK(out.run().seed() == 7 && out.run().participants_size() == 1 && out.name() == "demo");

  // 재정의가 없으면 원본 그대로
  core::Scenario same = core::from_proto(out);
  core::apply_run_override(same, {});
  CHECK(core::to_proto(same).SerializeAsString() == out.SerializeAsString());

  // 원본 없는 시나리오
  core::Scenario b = core::builtin_scenario(1);
  core::apply_run_override(b, {"freerun", "", "", ""});
  CHECK(core::to_proto(b).run().mode() == v1::RUN_MODE_FREERUN && b.rate == 1.0);
  bool threw = false;
  try {
    core::apply_run_override(b, {"turbo", "", "", ""});
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  CHECK(threw);

  // 실제로 Core가 재정의한 모드로 발행한다
  InMemoryBus bus;
  std::vector<v1::Scenario> got;
  auto sub = bus.subscribe(keys::kSimCtrlScenario, [&](const Sample& s) { got.push_back(decode<v1::Scenario>(s)); });
  core::SimCore sim(bus, core::mock::provider(), quiet());
  CHECK(sim.load(proto_sc));
  CHECK(got.size() == 1 && got[0].run().mode() == v1::RUN_MODE_LOCKSTEP && got[0].run().seed() == 7);
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
  test_params_load();
  test_params_runtime();
  test_params_not_runtime();
  test_params_lockstep();
  test_params_periodic();
  test_scenario_publish();
  test_lockstep_ready();
  test_scenario_late_joiner();
  test_cli_override();
  if (g_failures == 0) std::puts("swarm_core_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
