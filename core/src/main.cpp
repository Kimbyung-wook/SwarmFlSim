// IMP-CORE-006: 실행 파일 swarm_core
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

#include "swarm/core/mock_dynamics.hpp"
#include "swarm/core/sim_core.hpp"
#ifdef SWARM_CORE_WITH_ZENOH
#include "swarm/core/zenoh_bus.hpp"
#endif

namespace {

constexpr const char* kUsage = R"(usage: swarm_core [options]
  --scenario <file.json>   시나리오 파일. 없으면 내장 시나리오(고정익 --uavs 대 + GCS 1)
  --uavs <n>               내장 시나리오 기체 수 (기본 20)
  --autostart              불러온 뒤 바로 시작한다. 없으면 sim/ctrl/cmd의 Start를 기다린다
  --mode <m>               realtime | lockstep | freerun (--autostart 시)
  --rate <r>               목표 배속. 0이면 최대 속도 (lockstep/freerun)
  --hz <n>                 프레임 주파수 50..100
  --seed <n>               난수 시드
  --participant <id>       lockstep 장벽 참여자 (반복 가능)
  --frames <n>             n 프레임 진행 후 종료
  --bus <zenoh|memory>     버스 백엔드 (기본 zenoh, 없으면 memory)
  --zenoh-config <file>    zenoh json5 설정
  --zenoh-mode <m>         peer | client | router
  --connect <endpoint>     예: tcp/127.0.0.1:7447 (반복 가능)
  --listen <endpoint>      예: tcp/0.0.0.0:7447 (반복 가능)
)";

swarm::core::SimCore* g_core = nullptr;

void on_signal(int) {
  if (!g_core) return;
  swarm::v1::SimCommand cmd;
  cmd.set_issuer("signal");
  cmd.mutable_shutdown();
  g_core->submit(cmd);
}

std::string read_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open " + path);
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

}  // namespace

int main(int argc, char** argv) {
  using namespace swarm;
  std::string scenario_file, bus_kind, mode, rate, hz, seed;
  int uavs = 20;
  bool autostart = false;
  core::CoreConfig cfg;
#ifdef SWARM_CORE_WITH_ZENOH
  core::ZenohOptions zopt;
  bus_kind = "zenoh";
#else
  bus_kind = "memory";
#endif

  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    auto next = [&]() -> std::string {
      if (i + 1 >= argc) {
        std::cerr << "missing value for " << a << "\n";
        std::exit(2);
      }
      return argv[++i];
    };
    if (a == "--scenario") scenario_file = next();
    else if (a == "--uavs") uavs = std::stoi(next());
    else if (a == "--autostart") autostart = true;
    else if (a == "--mode") mode = next();
    else if (a == "--rate") rate = next();
    else if (a == "--hz") hz = next();
    else if (a == "--seed") seed = next();
    else if (a == "--participant") cfg.participants.push_back(next());
    else if (a == "--frames") cfg.stop_after_frames = std::stoull(next());
    else if (a == "--bus") bus_kind = next();
#ifdef SWARM_CORE_WITH_ZENOH
    else if (a == "--zenoh-config") zopt.config_file = next();
    else if (a == "--zenoh-mode") zopt.mode = next();
    else if (a == "--connect") zopt.connect.push_back(next());
    else if (a == "--listen") zopt.listen.push_back(next());
#endif
    else {
      std::cerr << kUsage;
      return a == "--help" || a == "-h" ? 0 : 2;
    }
  }

  try {
    std::unique_ptr<Bus> bus;
#ifdef SWARM_CORE_WITH_ZENOH
    if (bus_kind == "zenoh") bus = std::make_unique<core::ZenohBus>(zopt);
#endif
    if (bus_kind == "memory") bus = std::make_unique<InMemoryBus>();
    if (!bus) throw std::runtime_error("unsupported bus: " + bus_kind);

    core::Scenario sc = scenario_file.empty() ? core::builtin_scenario(uavs)
                                              : core::parse_scenario_json(read_file(scenario_file));
    // WP2 통합 전에는 목 동역학을 쓴다 (DEC-006)
    core::SimCore sim(*bus, core::mock::provider(), cfg);
    if (!sim.load(sc)) return 1;

    g_core = &sim;
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    if (autostart) {
      v1::SimCommand cmd;
      cmd.set_issuer("cli");
      auto* s = cmd.mutable_start();
      s->set_mode(sc.mode);
      if (mode == "realtime") s->set_mode(v1::RUN_MODE_REALTIME);
      else if (mode == "lockstep") s->set_mode(v1::RUN_MODE_LOCKSTEP);
      else if (mode == "freerun") s->set_mode(v1::RUN_MODE_FREERUN);
      else if (!mode.empty()) throw std::runtime_error("unknown mode: " + mode);
      s->set_rate(rate.empty() ? sc.rate : std::stod(rate));
      s->set_frame_hz(hz.empty() ? sc.frame_hz : static_cast<std::uint32_t>(std::stoul(hz)));
      s->set_seed(seed.empty() ? sc.seed : std::stoull(seed));
      sim.submit(cmd);
    }

    std::fprintf(stderr, "[swarm_core] bus=%s, waiting for %s\n", bus_kind.c_str(),
                 autostart ? "frames" : "sim/ctrl/cmd");
    sim.run();
    std::fprintf(stderr, "[swarm_core] stopped at frame %llu, sim_time %.3f s, overruns %llu\n",
                 static_cast<unsigned long long>(sim.frame()), sim.sim_time_us() * 1e-6,
                 static_cast<unsigned long long>(sim.frame_overruns()));
    g_core = nullptr;
    // 마지막 상태 보고가 네트워크로 나갈 시간을 준다
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  } catch (const std::exception& e) {
    std::cerr << "swarm_core: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
