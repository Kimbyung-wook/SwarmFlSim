// TC-CORE-001: ZenohBus 송수신 (두 세션, 로컬 TCP) + SimCore가 Zenoh로 tick·truth 발행
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "swarm/api/keys.hpp"
#include "swarm/core/mock_dynamics.hpp"
#include "swarm/core/sim_core.hpp"
#include "swarm/bus/open_bus.hpp"
#include "swarm/v1/truth.pb.h"

namespace {

using namespace swarm;
using namespace std::chrono_literals;

int g_failures = 0;

#define CHECK(cond)                                                        \
  do {                                                                     \
    if (!(cond)) {                                                         \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
      ++g_failures;                                                        \
    }                                                                      \
  } while (0)

template <class Pred>
bool wait_for(Pred p, std::chrono::milliseconds timeout = 3000ms) {
  const auto end = std::chrono::steady_clock::now() + timeout;
  while (std::chrono::steady_clock::now() < end) {
    if (p()) return true;
    std::this_thread::sleep_for(5ms);
  }
  return p();
}

}  // namespace

int main() {
  // 멀티캐스트 스카우팅에 의존하지 않도록 한쪽이 듣고 다른 쪽이 접속한다
  bus::BusConfig a_opt, b_opt;
  a_opt.backend = b_opt.backend = "zenoh";
  a_opt.zenoh_mode = b_opt.zenoh_mode = "peer";
  a_opt.multicast_scouting = b_opt.multicast_scouting = false;
  a_opt.listen = {"tcp/127.0.0.1:17447"};
  b_opt.connect = {"tcp/127.0.0.1:17447"};
  b_opt.listen = {"tcp/127.0.0.1:17448"};

  auto a_bus = bus::open_bus(a_opt);
  auto b_bus = bus::open_bus(b_opt);
  Bus& a = *a_bus;
  Bus& b = *b_bus;

  // 1. 와일드카드 구독, 페이로드·인코딩·키 보존
  std::mutex mu;
  std::vector<Sample> got;
  {
    auto sub = b.subscribe(keys::kTxAll, [&](const Sample& s) {
      std::lock_guard lock(mu);
      got.push_back(s);
    });
    const std::vector<std::uint8_t> payload{0, 1, 2, 250, 255};
    const auto key = keys::tx("uav-001", keys::Iface::VI, "NavigationReport");
    // 구독 선언이 상대에게 전파될 때까지 반복 발행한다
    CHECK(wait_for([&] {
      a.put(key, payload, protobuf_encoding("swarm.v1.LinkEnvelope"));
      std::lock_guard lock(mu);
      return !got.empty();
    }));
    a.put(keys::rx("uav-001", keys::Iface::VI, "NavigationReport"), payload, "");  // 일치하지 않는 키
    std::this_thread::sleep_for(200ms);
    std::lock_guard lock(mu);
    CHECK(!got.empty());
    bool all_match = true;
    for (const auto& s : got)
      all_match = all_match && s.key == key && s.payload == payload &&
                  s.encoding == "application/protobuf;swarm.v1.LinkEnvelope";
    CHECK(all_match);
  }
  // 구독 해제 뒤에는 받지 않는다
  const std::size_t before = got.size();
  a.put(keys::tx("uav-001", keys::Iface::VI, "NavigationReport"), std::vector<std::uint8_t>{1}, "");
  std::this_thread::sleep_for(200ms);
  CHECK(got.size() == before);

  // 2. SimCore(세션 a)가 발행한 tick·truth를 세션 b가 받는다. 명령도 b에서 보낸다
  std::atomic<int> ticks{0}, truths{0};
  std::atomic<std::uint64_t> last_frame{0};
  std::atomic<int> entity_count{0};
  auto s1 = b.subscribe(keys::kClockTick, [&](const Sample& s) {
    v1::ClockTick t;
    (void)t.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()));
    last_frame = t.frame();
    ++ticks;
  });
  auto s2 = b.subscribe(keys::kTruthState, [&](const Sample& s) {
    v1::TruthFrame f;
    (void)f.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()));
    entity_count = f.entities_size();
    ++truths;
  });

  core::CoreConfig cfg;
  cfg.stop_after_frames = 50;
  cfg.log = [](const std::string&) {};
  core::SimCore sim(a, core::mock::provider(), cfg);
  sim.load(core::builtin_scenario(20));
  std::thread runner([&] { sim.run(); });

  v1::SimCommand start;
  start.set_issuer("ui-test");
  start.mutable_start()->set_mode(v1::RUN_MODE_REALTIME);
  start.mutable_start()->set_frame_hz(50);
  const std::string bytes = start.SerializeAsString();
  std::this_thread::sleep_for(300ms);  // core 구독 전파
  b.put(keys::kSimCtrlCmd, {reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size()},
        protobuf_encoding("swarm.v1.SimCommand"));

  runner.join();  // 50 프레임 = 약 1 s
  std::this_thread::sleep_for(300ms);
  CHECK(sim.frame() == 50);
  CHECK(ticks >= 45);  // tick 0..50. 첫 몇 개는 구독 전파 전에 지나갈 수 있다
  CHECK(last_frame == 50);
  CHECK(truths >= 45);
  CHECK(entity_count == 21);
  std::printf("zenoh: ticks=%d truths=%d last_frame=%llu\n", ticks.load(), truths.load(),
              static_cast<unsigned long long>(last_frame.load()));

  if (g_failures == 0) std::puts("swarm_core_zenoh_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
