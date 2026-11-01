// IMP-LOG-005: swarm_logger 실행 파일
//
//   swarm_logger info <file.mcap>
//   swarm_logger record --out <file.mcap> [--key <expr>] [--backend <name>]
//   swarm_logger replay <file.mcap> [--rate <x>] [--key <expr>] [--backend <name>] [--dry-run]
//
// 버스 백엔드는 make_bus()가 고른다. Zenoh 백엔드(WP1)는 통합 단계에서 연결한다.
#include <atomic>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <stop_token>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "swarm/logger/mcap_log.hpp"

namespace {

std::atomic<bool> g_interrupted{false};

void on_signal(int) { g_interrupted = true; }

std::unique_ptr<swarm::Bus> make_bus(const std::string& backend) {
  if (backend == "memory") return std::make_unique<swarm::InMemoryBus>();
  throw std::invalid_argument("unknown bus backend: " + backend + " (available: memory)");
}

struct Args {
  std::string cmd;
  std::string file;
  std::string key = "**";
  std::string backend = "memory";
  double rate = 1.0;
  bool dry_run = false;
};

int usage() {
  std::fprintf(stderr,
               "usage:\n"
               "  swarm_logger info <file.mcap>\n"
               "  swarm_logger record --out <file.mcap> [--key <expr>] [--backend <name>]\n"
               "  swarm_logger replay <file.mcap> [--rate <x>] [--key <expr>] [--backend <name>] [--dry-run]\n");
  return 2;
}

bool parse(int argc, char** argv, Args& a) {
  if (argc < 2) return false;
  a.cmd = argv[1];
  for (int i = 2; i < argc; ++i) {
    const std::string_view s = argv[i];
    auto value = [&]() -> std::string {
      if (i + 1 >= argc) throw std::invalid_argument(std::string(s) + " needs a value");
      return argv[++i];
    };
    if (s == "--out") a.file = value();
    else if (s == "--key") a.key = value();
    else if (s == "--backend") a.backend = value();
    else if (s == "--rate") a.rate = std::stod(value());
    else if (s == "--dry-run") a.dry_run = true;
    else if (!s.starts_with("--") && a.file.empty()) a.file = s;
    else return false;
  }
  return !a.file.empty();
}

int cmd_info(const Args& a) {
  const auto info = swarm::logger::inspect(a.file);
  std::printf("messages: %llu  span: %.3f s  channels: %zu\n", static_cast<unsigned long long>(info.messages),
              static_cast<double>(info.end_ns - info.start_ns) * 1e-9, info.channels.size());
  for (const auto& c : info.channels)
    std::printf("  %-48s %8llu  %s\n", c.topic.c_str(), static_cast<unsigned long long>(c.messages),
                c.encoding.c_str());
  return 0;
}

int cmd_record(const Args& a) {
  auto bus = make_bus(a.backend);
  swarm::logger::Recorder rec(*bus, a.file, {.keyexpr = a.key});
  std::printf("recording %s -> %s (Ctrl+C to stop)\n", a.key.c_str(), a.file.c_str());
  while (!g_interrupted) std::this_thread::sleep_for(std::chrono::milliseconds(100));
  rec.close();
  std::printf("recorded %llu messages on %zu channels\n", static_cast<unsigned long long>(rec.message_count()),
              rec.channel_count());
  return 0;
}

int cmd_replay(const Args& a) {
  std::unique_ptr<swarm::Bus> bus;
  std::unique_ptr<swarm::Subscription> echo;
  if (a.dry_run) {
    bus = std::make_unique<swarm::InMemoryBus>();
    echo = bus->subscribe("**", [](const swarm::Sample& s) {
      std::printf("%s %zu B %s\n", s.key.c_str(), s.payload.size(), s.encoding.c_str());
    });
  } else {
    bus = make_bus(a.backend);
  }
  std::stop_source stop;
  std::jthread watch([&](std::stop_token st) {
    while (!st.stop_requested() && !g_interrupted) std::this_thread::sleep_for(std::chrono::milliseconds(50));
    stop.request_stop();
  });
  const auto stats = swarm::logger::replay(*bus, a.file, {.rate = a.dry_run ? 0.0 : a.rate, .keyexpr = a.key},
                                           stop.get_token());
  watch.request_stop();
  std::printf("replayed %llu messages (skipped %llu)%s\n", static_cast<unsigned long long>(stats.messages),
              static_cast<unsigned long long>(stats.skipped), stats.stopped ? ", interrupted" : "");
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  Args a;
  try {
    if (!parse(argc, argv, a)) return usage();
    std::signal(SIGINT, on_signal);
    if (a.cmd == "info") return cmd_info(a);
    if (a.cmd == "record") return cmd_record(a);
    if (a.cmd == "replay") return cmd_replay(a);
    return usage();
  } catch (const std::exception& e) {
    std::fprintf(stderr, "error: %s\n", e.what());
    return 1;
  }
}
