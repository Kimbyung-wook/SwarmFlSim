// IMP-CORE-006: 실행 파일 swarm_core
// IMP-CORE-012: WP2 동역학(--integrator), 평지 지형(--terrain-flat)
// IMP-CORE-013: Windows Ctrl+Break(SIGBREAK) 정상 종료
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

#include "swarm/bus/open_bus.hpp"
#include "swarm/core/sim_core.hpp"
#include "swarm/core/wp2_dynamics.hpp"

namespace {

constexpr const char* kUsage = R"(usage: swarm_core [options]
  --scenario <file>        시나리오 파일(.pb 또는 proto JSON, swarm-scenario export로 만든다).
                           없으면 내장 시나리오(고정익 --uavs 대 + GCS 1)
  --uavs <n>               내장 시나리오 기체 수 (기본 20)
  --autostart              불러온 뒤 바로 시작한다. 없으면 sim/ctrl/cmd의 Start를 기다린다
  --mode <m>               realtime | lockstep | freerun (--autostart 시)
  --rate <r>               목표 배속. 0이면 최대 속도 (lockstep/freerun)
  --hz <n>                 프레임 주파수 50..100
  --seed <n>               난수 시드
  --participant <id>       lockstep 장벽 참여자 (반복 가능)
  --frames <n>             n 프레임 진행 후 종료
  --integrator <name>      rk4 | rk45 (기본 rk45)
  --terrain-flat <m>       평지 지형 고도 (기본 0). 지면 아래로 내려가면 kill(cause=ground)
  --terrain-dem <file>     DEM 지형 (자리만 있음, DEC-016)
)";

swarm::core::SimCore* g_core = nullptr;

void on_signal(int) {
  if (!g_core) return;
  swarm::v1::SimCommand cmd;
  cmd.set_issuer("signal");
  cmd.mutable_shutdown();
  g_core->submit(cmd);
}

}  // namespace

int main(int argc, char** argv) {
  using namespace swarm;
  std::string scenario_file, mode, rate, hz, seed;
  int uavs = 20;
  bool autostart = false;
  core::CoreConfig cfg;
  core::Wp2DynamicsOptions dyn_opt;
  std::string dem_file;
  bus::BusConfig bus_cfg;

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
    else if (a == "--integrator") dyn_opt.integrator = next();
    else if (a == "--terrain-flat") dyn_opt.terrain_flat_m = std::stod(next());
    else if (a == "--terrain-dem") dem_file = next();
    else if (bus::parse_bus_arg(bus_cfg, a, next)) continue;
    else {
      std::cerr << kUsage << bus::kBusUsage;
      return a == "--help" || a == "-h" ? 0 : 2;
    }
  }

  try {
    // DEM 로더(dyn::DemLoader)는 WP2에 인터페이스만 있다. 구현되면 dyn_opt.terrain에 넣는다
    if (!dem_file.empty()) throw std::runtime_error("--terrain-dem: DEM loader not implemented yet");
    core::DynamicsProvider provider = core::wp2_provider(dyn_opt);

    const std::string bus_kind = bus_cfg.backend.empty() ? bus::default_backend() : bus_cfg.backend;
    std::unique_ptr<Bus> bus = bus::open_bus(bus_cfg);

    core::Scenario sc = scenario_file.empty() ? core::builtin_scenario(uavs)
                                              : core::read_scenario_file(scenario_file);
    core::SimCore sim(*bus, std::move(provider), cfg);
    if (!sim.load(sc)) return 1;

    g_core = &sim;
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
#ifdef SIGBREAK
    // Windows: 별도 프로세스 그룹으로 띄운 경우 Ctrl+Break로 멈춘다 (IMP-CORE-013)
    std::signal(SIGBREAK, on_signal);
#endif

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

    std::fprintf(stderr, "[swarm_core] bus=%s, integrator=%s, terrain-flat=%.1f m, waiting for %s\n",
                 bus_kind.c_str(), dyn_opt.integrator.c_str(), dyn_opt.terrain_flat_m,
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
