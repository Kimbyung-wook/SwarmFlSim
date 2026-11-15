// TC-API-009: Zenoh put 경로 비용 측정 (DEC-086). 시험이 아니라 측정 도구다.
// 사용: swarm_bus_bench [반복수]
// 발행 세션과 구독 세션을 tcp 루프백으로 잇고 `link/state/<a>/<b>` 모양 키(쌍 4,950개)에 120 B를 낸다.
// 변경 전후 빌드에서 같은 명령으로 재 비교한다.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>
#include <vector>

#include "swarm/bus/zenoh_bus.hpp"

using clk = std::chrono::steady_clock;

int main(int argc, char** argv) {
  const int reps = argc > 1 ? std::atoi(argv[1]) : 50000;
  std::vector<std::string> keys;
  for (int a = 0; a < 100; ++a)
    for (int b = a + 1; b < 100; ++b) keys.push_back("link/state/uav-" + std::to_string(a) + "/uav-" + std::to_string(b));
  std::vector<std::uint8_t> payload(120, 0x5a);
  const std::string enc = "application/protobuf;swarm.link.v1.LinkState";

  swarm::bus::ZenohOptions pub_o;
  pub_o.listen = {"tcp/127.0.0.1:17499"};
  pub_o.multicast_scouting = false;
  swarm::bus::ZenohBus bus(pub_o);

  swarm::bus::ZenohOptions sub_o;
  sub_o.connect = {"tcp/127.0.0.1:17499"};
  sub_o.multicast_scouting = false;
  swarm::bus::ZenohBus sub_bus(sub_o);
  std::atomic<long> got{0};
  auto sub = sub_bus.subscribe("link/state/**", [&](const swarm::Sample&) { got.fetch_add(1); });
  std::this_thread::sleep_for(std::chrono::milliseconds(800));

  auto run = [&](const char* name, auto&& put_one) {
    long before = got.load();
    auto t0 = clk::now();
    for (int i = 0; i < reps; ++i) put_one(keys[i % keys.size()]);
    double us = std::chrono::duration<double, std::micro>(clk::now() - t0).count() / reps;
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    std::printf("%-5s %.3f us/put  received %ld/%d\n", name, us, got.load() - before, reps);
  };

  for (int round = 0; round < 5; ++round) {
    run("bus", [&](const std::string& k) { bus.put(k, payload, enc); });
  }
  return 0;
}
