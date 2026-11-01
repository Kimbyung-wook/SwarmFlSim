// TC-API-004: open_bus 백엔드 선택·명령행 옵션, Zenoh가 있으면 두 세션 간 송수신 (DEC-026)
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "swarm/api/keys.hpp"
#include "swarm/bus/open_bus.hpp"

namespace {

using namespace swarm;
using namespace std::chrono_literals;

int g_failures = 0;

void check(bool cond, const char* what) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}

std::vector<std::uint8_t> bytes(std::string_view s) { return {s.begin(), s.end()}; }

}  // namespace

int main() {
  // 명령행 옵션: 버스 옵션만 소비한다
  bus::BusConfig cfg;
  const std::vector<std::string> argv = {"--bus", "memory", "--connect", "tcp/10.0.0.1:7447", "--no-multicast",
                                         "--frames"};
  std::size_t i = 0, consumed = 0;
  while (i < argv.size()) {
    const std::string flag = argv[i++];
    if (!bus::parse_bus_arg(cfg, flag, [&] { return argv.at(i++); })) break;
    ++consumed;
  }
  check(consumed == 3 && cfg.backend == "memory" && cfg.connect.size() == 1 && !cfg.multicast_scouting,
        "parse_bus_arg consumes bus options only");

  // memory 백엔드
  auto mem = bus::open_bus(cfg);
  int got = 0;
  {
    auto sub = mem->subscribe("truth/**", [&](const Sample&) { ++got; });
    const auto p = bytes("x");
    mem->put(keys::kTruthState, p, "");
  }
  check(got == 1, "memory backend delivers");

  bool threw = false;
  try {
    bus::open_bus({.backend = "dds"});
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  check(threw, "unknown backend throws");
  check(bus::default_backend() == (bus::zenoh_available() ? "zenoh" : "memory"), "default backend");

  // Zenoh 백엔드: 멀티캐스트에 의존하지 않도록 한쪽이 듣고 다른 쪽이 접속한다
  if (bus::zenoh_available()) {
    bus::BusConfig a{.backend = "zenoh", .zenoh_mode = "peer", .listen = {"tcp/127.0.0.1:17457"},
                     .multicast_scouting = false};
    bus::BusConfig b{.backend = "zenoh", .zenoh_mode = "peer", .connect = {"tcp/127.0.0.1:17457"},
                     .multicast_scouting = false};
    auto za = bus::open_bus(a);
    auto zb = bus::open_bus(b);
    std::atomic<int> n{0};
    std::mutex mu;
    std::string enc;
    auto sub = zb->subscribe(keys::kTxAll, [&](const Sample& s) {
      if (s.payload == bytes("hello")) {
        std::lock_guard lock(mu);
        enc = s.encoding;
        ++n;
      }
    });
    const auto key = keys::tx("uav-001", keys::Iface::P2P, "PeerStatus");
    const auto payload = bytes("hello");
    const auto end = std::chrono::steady_clock::now() + 5s;
    while (n == 0 && std::chrono::steady_clock::now() < end) {
      za->put(key, payload, protobuf_encoding("swarm.v1.LinkEnvelope"));
      std::this_thread::sleep_for(50ms);
    }
    check(n > 0, "zenoh backend delivers across sessions");
    std::lock_guard lock(mu);
    check(enc == protobuf_encoding("swarm.v1.LinkEnvelope"), "zenoh preserves encoding");
  } else {
    std::puts("swarm_bus_tests: zenoh not built, zenoh case skipped");
  }

  if (g_failures == 0) std::puts("swarm_bus_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
