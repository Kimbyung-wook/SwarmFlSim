// TC-CORE-002~009: SimCore 단위 시험 (InMemoryBus, 목 동역학)
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
  if (g_failures == 0) std::puts("swarm_core_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
