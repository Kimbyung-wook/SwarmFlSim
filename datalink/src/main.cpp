// IMP-LNK-011: 실행 파일 swarm_datalink (PRP-LNK-002, DEC-026)
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

#include <google/protobuf/util/json_util.h>

#include "swarm/bus/open_bus.hpp"
#include "swarm/dyn/terrain.hpp"
#include "swarm/lnk/emulator.hpp"

namespace {

constexpr const char* kUsage = R"(usage: swarm_datalink [options]
  --scenario <file>        시나리오 파일(.pb 또는 proto JSON). 없으면 sim/ctrl/cmd의 LoadScenario를 기다린다.
                           엔티티는 truth/state로도 등록된다
  --participant <id>       lockstep 참여자 ID. sim/clock/done/<id>에 FrameDone을 보낸다 (기본 datalink-0)
  --no-frame-done          FrameDone을 보내지 않는다
  --seed <n>               난수 시드 (LoadScenario.run.seed, Start.seed가 0이 아니면 그 값을 쓴다)
  --terrain-flat <m>       평지 지형 고도 (기본 0). 가시선 판정에 쓴다
  --no-los                 가시선 판정을 끈다
  --state-period <s>       link/state 발행 주기, 시뮬레이션 초 (기본 1, 0이면 끔)
  --heartbeat-hz <hz>      GCS Heartbeat 주기, 시뮬레이션 시각 기준 (기본 1, 0이면 끔)
  --quiet                  로그를 끈다
)";

swarm::lnk::Datalink* g_link = nullptr;

void on_signal(int) {
  if (g_link) g_link->request_shutdown();
}

swarm::v1::Scenario read_scenario(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::invalid_argument("cannot open " + path);
  std::ostringstream ss;
  ss << in.rdbuf();
  const std::string text = ss.str();
  swarm::v1::Scenario sc;
  if (path.size() >= 3 && path.compare(path.size() - 3, 3, ".pb") == 0) {
    if (!sc.ParseFromString(text)) throw std::invalid_argument("scenario pb: parse failed: " + path);
    return sc;
  }
  google::protobuf::util::JsonParseOptions opt;
  opt.ignore_unknown_fields = true;
  if (auto st = google::protobuf::util::JsonStringToMessage(text, &sc, opt); !st.ok())
    throw std::invalid_argument("scenario proto json: " + std::string(st.message()));
  return sc;
}

}  // namespace

int main(int argc, char** argv) {
  using namespace swarm;
  std::string scenario_file;
  double terrain_flat_m = 0.0;
  bool los = true, quiet = false;
  lnk::DatalinkConfig cfg;
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
    else if (a == "--participant") cfg.participant_id = next();
    else if (a == "--no-frame-done") cfg.participant_id.clear();
    else if (a == "--seed") cfg.seed = std::stoull(next());
    else if (a == "--terrain-flat") terrain_flat_m = std::stod(next());
    else if (a == "--no-los") los = false;
    else if (a == "--state-period") cfg.state_period_s = std::stod(next());
    else if (a == "--heartbeat-hz") cfg.heartbeat_hz = std::stod(next());
    else if (a == "--quiet") quiet = true;
    else if (bus::parse_bus_arg(bus_cfg, a, next)) continue;
    else {
      std::cerr << kUsage << bus::kBusUsage;
      return a == "--help" || a == "-h" ? 0 : 2;
    }
  }
  if (!quiet) cfg.log = [](const std::string& m) { std::fprintf(stderr, "[swarm_datalink] %s\n", m.c_str()); };

  try {
    const std::string bus_kind = bus_cfg.backend.empty() ? bus::default_backend() : bus_cfg.backend;
    std::unique_ptr<Bus> bus = bus::open_bus(bus_cfg);
    // DEM 로더가 생기면 GridTerrain으로 바꾼다 (DEC-016)
    dyn::FlatTerrain terrain(terrain_flat_m);
    lnk::Datalink link(*bus, los ? &terrain : nullptr, cfg);
    if (!scenario_file.empty()) link.load(read_scenario(scenario_file));

    g_link = &link;
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
#ifdef SIGBREAK
    // Windows: 별도 프로세스 그룹으로 띄운 경우 Ctrl+Break로 멈춘다 (IMP-LNK-015)
    std::signal(SIGBREAK, on_signal);
#endif
    std::fprintf(stderr, "[swarm_datalink] bus=%s, participant=%s, waiting for sim/clock/tick\n", bus_kind.c_str(),
                 cfg.participant_id.empty() ? "(none)" : cfg.participant_id.c_str());
    link.wait_shutdown();
    g_link = nullptr;
    std::fprintf(stderr, "[swarm_datalink] stopped at sim_time %.3f s\n", link.sim_time_us() * 1e-6);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  } catch (const std::exception& e) {
    std::cerr << "swarm_datalink: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
