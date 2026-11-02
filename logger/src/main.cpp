// IMP-LOG-005: swarm_logger 실행 파일
//
//   swarm_logger info <file.mcap>
//   swarm_logger record --out <file.mcap> [--key <expr>] [--stats <초>] [--max-queue-messages <n>] [--max-queue-mib <n>] [버스 옵션]
//   swarm_logger replay <file.mcap> [--rate <x>] [--key <expr>] [버스 옵션] [--dry-run]
//
// 버스는 공용 open_bus()로 연다 (DEC-026). 버스 옵션은 swarm/bus/open_bus.hpp의 kBusUsage.
#include <atomic>
#include <csignal>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <stop_token>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "swarm/bus/open_bus.hpp"
#include "swarm/logger/mcap_log.hpp"

namespace {

std::atomic<bool> g_interrupted{false};

void on_signal(int) { g_interrupted = true; }

struct Args {
  std::string cmd;
  std::string file;
  std::string key = "**";
  swarm::bus::BusConfig bus;
  double rate = 1.0;
  bool dry_run = false;
  double stats_s = 0.0;  // record: 이 주기(초)마다 큐 길이·드롭 수를 stderr에 낸다
  std::size_t max_queue_messages = swarm::logger::RecorderOptions{}.max_queue_messages;
  std::size_t max_queue_mib = swarm::logger::RecorderOptions{}.max_queue_bytes >> 20;
};

int usage() {
  std::fprintf(stderr,
               "usage:\n"
               "  swarm_logger info <file.mcap>\n"
               "  swarm_logger record --out <file.mcap> [--key <expr>] [--stats <s>]\n"
               "                       [--max-queue-messages <n>] [--max-queue-mib <n>] [bus options]\n"
               "  swarm_logger replay <file.mcap> [--rate <x>] [--key <expr>] [bus options] [--dry-run]\n"
               "bus options:\n%s",
               swarm::bus::kBusUsage);
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
    else if (s == "--backend") a.bus.backend = value();  // 이전 이름
    else if (swarm::bus::parse_bus_arg(a.bus, s, value)) continue;
    else if (s == "--rate") a.rate = std::stod(value());
    else if (s == "--dry-run") a.dry_run = true;
    else if (s == "--stats") a.stats_s = std::stod(value());
    else if (s == "--max-queue-messages") a.max_queue_messages = std::stoull(value());
    else if (s == "--max-queue-mib") a.max_queue_mib = std::stoull(value());
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
  auto bus = swarm::bus::open_bus(a.bus);
  swarm::logger::Recorder rec(*bus, a.file,
                              {.keyexpr = a.key,
                               .max_queue_messages = a.max_queue_messages,
                               .max_queue_bytes = a.max_queue_mib << 20});
  std::printf("recording %s -> %s (Ctrl+C to stop)\n", a.key.c_str(), a.file.c_str());
  auto next_report = std::chrono::steady_clock::now();
  std::uint64_t reported_drops = 0;
  while (!g_interrupted) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    const auto now = std::chrono::steady_clock::now();
    const bool periodic = a.stats_s > 0;
    if (now < next_report) continue;
    const auto st = rec.stats();
    // 드롭이 새로 생기면 알리고, --stats면 주기마다 큐 상태도 낸다
    if (periodic || st.dropped != reported_drops) {
      std::fprintf(stderr, "[swarm_logger] written=%llu queue=%zu msgs/%zu B peak=%zu msgs/%zu B dropped=%llu\n",
                   static_cast<unsigned long long>(st.written), st.queue_messages, st.queue_bytes,
                   st.peak_queue_messages, st.peak_queue_bytes, static_cast<unsigned long long>(st.dropped));
      reported_drops = st.dropped;
    }
    next_report = now + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                            std::chrono::duration<double>(periodic ? a.stats_s : 5.0));
  }
  rec.close();
  const auto st = rec.stats();
  std::printf("recorded %llu messages on %zu channels, dropped %llu (queue peak %zu msgs / %zu B)\n",
              static_cast<unsigned long long>(rec.message_count()), rec.channel_count(),
              static_cast<unsigned long long>(st.dropped), st.peak_queue_messages, st.peak_queue_bytes);
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
    bus = swarm::bus::open_bus(a.bus);
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
    std::signal(SIGTERM, on_signal);
#ifdef SIGBREAK
    // Windows: 별도 프로세스 그룹으로 띄운 경우 Ctrl+Break로 멈춘다 (IMP-LOG-009)
    std::signal(SIGBREAK, on_signal);
#endif
    if (a.cmd == "info") return cmd_info(a);
    if (a.cmd == "record") return cmd_record(a);
    if (a.cmd == "replay") return cmd_replay(a);
    return usage();
  } catch (const std::exception& e) {
    std::fprintf(stderr, "error: %s\n", e.what());
    return 1;
  }
}
