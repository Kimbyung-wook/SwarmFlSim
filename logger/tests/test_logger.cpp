// TC-LOG-001~010: InMemoryBus로 기록 → 재생 결과 일치
#include <mcap/reader.hpp>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/descriptor.pb.h>
#include <google/protobuf/dynamic_message.h>
#include <google/protobuf/util/message_differencer.h>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <psapi.h>
#pragma comment(lib, "psapi.lib")
#endif

#include <atomic>
#include <cstdio>
#include <filesystem>
#include <map>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

#include "swarm/api/bus.hpp"
#include "swarm/api/keys.hpp"
#include "swarm/logger/mcap_log.hpp"
#include "swarm/v1/link.pb.h"
#include "swarm/v1/sim.pb.h"
#include "swarm/v1/truth.pb.h"

namespace {
int g_failures = 0;

void check(bool cond, const char* what) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}

using Rec = std::tuple<std::string, std::vector<std::uint8_t>, std::string>;  // 키, 페이로드, 인코딩

struct FakeClock {
  std::uint64_t t = 1'000'000'000;
  std::uint64_t operator()() const { return t; }
};

template <typename M>
void put(swarm::Bus& bus, std::string_view key, const M& m) {
  const auto bytes = m.SerializeAsString();
  bus.put(key, {reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size()},
          swarm::protobuf_encoding(M::descriptor()->full_name()));
}

swarm::v1::TruthFrame truth_frame(std::uint64_t frame) {
  swarm::v1::TruthFrame f;
  f.mutable_header()->set_frame(frame);
  f.mutable_header()->set_sim_time_us(frame * 20'000);
  auto* e = f.add_entities();
  e->set_id("uav-001");
  e->set_kind(swarm::v1::ENTITY_KIND_UAV);
  e->mutable_kinematics()->mutable_position()->set_lat_deg(37.4 + 1e-5 * static_cast<double>(frame));
  e->set_alive(true);
  return f;
}

// 시각 0, 10, 20 ms ... 에 여러 종류의 메시지를 발행하면서 기록한다
std::vector<Rec> record_sample(const std::filesystem::path& path, std::vector<std::uint64_t>* times = nullptr) {
  swarm::InMemoryBus bus;
  FakeClock clock;
  std::vector<Rec> sent;
  auto mirror = bus.subscribe("**", [&](const swarm::Sample& s) {
    sent.emplace_back(s.key, s.payload, s.encoding);
    if (times) times->push_back(clock.t);
  });
  swarm::logger::Recorder rec(bus, path, {.keyexpr = "**", .clock = std::ref(clock)});
  for (std::uint64_t f = 0; f < 5; ++f) {
    swarm::v1::ClockTick tick;
    tick.set_frame(f);
    tick.set_sim_time_us(f * 20'000);
    tick.set_dt_us(20'000);
    tick.set_mode(swarm::v1::RUN_MODE_LOCKSTEP);
    put(bus, swarm::keys::kClockTick, tick);
    put(bus, swarm::keys::kTruthState, truth_frame(f));
    clock.t += 10'000'000;
    if (f % 2 == 0) {
      swarm::v1::LinkEnvelope env;
      env.mutable_header()->set_source("uav-001");
      env.add_dst("gcs-01");
      env.set_msg_type("swarm.v1.NavigationReport");
      env.set_payload(std::string("\x01\x02\x00\x03", 4));
      put(bus, swarm::keys::tx("uav-001", swarm::keys::Iface::VI, "NavigationReport"), env);
    }
    const std::uint8_t raw[] = {0xde, 0xad, static_cast<std::uint8_t>(f)};
    bus.put("debug/raw", raw, "application/octet-stream");
    bus.put("debug/unknown", raw, "application/protobuf;other.v1.Unknown");
    clock.t += 10'000'000;
  }
  rec.close();
  check(rec.message_count() == sent.size(), "recorder counted every sample");
  check(rec.channel_count() == 5, "one channel per key");
  return sent;
}

// TC-LOG-001: MCAP 채널 = 키, 스키마 = protobuf FileDescriptorSet
void test_channels_and_schema(const std::filesystem::path& path) {
  record_sample(path);
  mcap::McapReader reader;
  check(reader.open(path.string()).ok(), "open mcap");
  std::map<std::string, std::pair<mcap::ChannelPtr, mcap::SchemaPtr>> seen;
  std::string truth_bytes;
  mcap::ReadMessageOptions o;
  for (const auto& mv : reader.readMessages([](const mcap::Status&) {}, o)) {
    seen[mv.channel->topic] = {mv.channel, mv.schema};
    if (mv.channel->topic == "truth/state" && truth_bytes.empty())
      truth_bytes.assign(reinterpret_cast<const char*>(mv.message.data), mv.message.dataSize);
  }
  check(seen.size() == 5, "five topics");

  const auto& [tick_ch, tick_schema] = seen["sim/clock/tick"];
  check(tick_ch && tick_ch->messageEncoding == "protobuf", "tick message encoding");
  check(tick_schema && tick_schema->name == "swarm.v1.ClockTick" && tick_schema->encoding == "protobuf",
        "tick schema");
  check(tick_ch && tick_ch->metadata.at(std::string(swarm::logger::kEncodingMetaKey)) ==
                       "application/protobuf;swarm.v1.ClockTick",
        "zenoh encoding in metadata");

  // 스키마만으로 페이로드를 해석할 수 있어야 한다 (외부 도구 호환)
  const auto& truth_schema = seen["truth/state"].second;
  check(truth_schema != nullptr, "truth schema");
  if (truth_schema) {
    google::protobuf::FileDescriptorSet set;
    check(set.ParseFromArray(truth_schema->data.data(), static_cast<int>(truth_schema->data.size())), "parse fds");
    google::protobuf::DescriptorPool pool;
    bool built = true;
    for (const auto& f : set.file()) built = built && pool.BuildFile(f) != nullptr;  // 의존 파일이 먼저 온다
    check(built, "build pool from fds in order");
    const auto* d = pool.FindMessageTypeByName("swarm.v1.TruthFrame");
    check(d != nullptr, "TruthFrame in fds");
    if (d) {
      google::protobuf::DynamicMessageFactory factory(&pool);
      std::unique_ptr<google::protobuf::Message> m(factory.GetPrototype(d)->New());
      check(m->ParseFromString(truth_bytes), "dynamic parse");
      swarm::v1::TruthFrame expect = truth_frame(0);
      check(m->SerializeAsString() == expect.SerializeAsString(), "dynamic message equals original");
    }
  }

  const auto& [raw_ch, raw_schema] = seen["debug/raw"];
  check(raw_ch && raw_ch->schemaId == 0 && !raw_schema, "raw has no schema");
  check(raw_ch && raw_ch->messageEncoding == "application/octet-stream", "raw encoding kept");
  check(seen["debug/unknown"].first && seen["debug/unknown"].first->schemaId == 0, "unknown type has no schema");
  reader.close();
}

// TC-LOG-002: 재생 결과(키, 페이로드, 인코딩, 순서)가 기록 시와 같다
void test_replay_equal(const std::filesystem::path& path) {
  const auto sent = record_sample(path);
  swarm::InMemoryBus bus;
  std::vector<Rec> got;
  auto sub = bus.subscribe("**", [&](const swarm::Sample& s) { got.emplace_back(s.key, s.payload, s.encoding); });
  const auto stats = swarm::logger::replay(bus, path, {.rate = 0.0});
  check(stats.messages == sent.size() && stats.skipped == 0, "replay count");
  check(got == sent, "replayed samples equal recorded samples");
  check(stats.log_span_ns == 90'000'000, "log span");

  const auto info = swarm::logger::inspect(path);
  check(info.messages == sent.size() && info.channels.size() == 5, "inspect totals");
  check(info.channels.front().topic == "debug/raw", "inspect sorted by topic");
}

// TC-LOG-003: 원래 시각 간격 / 배속으로 발행한다
void test_replay_timing(const std::filesystem::path& path) {
  std::vector<std::uint64_t> rec_times;
  record_sample(path, &rec_times);
  for (const double rate : {1.0, 2.0, 0.5}) {
    swarm::InMemoryBus bus;
    std::uint64_t now = 5'000;
    std::vector<std::uint64_t> pub_times;
    auto sub = bus.subscribe("**", [&](const swarm::Sample&) { pub_times.push_back(now); });
    swarm::logger::replay(bus, path,
                          {.rate = rate,
                           .now = [&] { return now; },
                           .wait_until = [&](std::uint64_t until) { now = std::max(now, until); }});
    bool ok = pub_times.size() == rec_times.size();
    for (std::size_t i = 0; ok && i < pub_times.size(); ++i) {
      const auto expect = 5'000 + static_cast<std::uint64_t>(static_cast<double>(rec_times[i] - rec_times[0]) / rate);
      ok = pub_times[i] == expect;
    }
    check(ok, "publish offsets = recorded offsets / rate");
  }
  // rate 0: 기다리지 않는다
  swarm::InMemoryBus bus;
  int waits = 0;
  swarm::logger::replay(bus, path, {.rate = 0.0, .wait_until = [&](std::uint64_t) { ++waits; }});
  check(waits == 0, "rate 0 never waits");
}

// TC-LOG-004: 키 표현식 필터 (기록·재생)
void test_filters(const std::filesystem::path& path) {
  record_sample(path);
  swarm::InMemoryBus bus;
  std::vector<std::string> keys;
  auto sub = bus.subscribe("**", [&](const swarm::Sample& s) { keys.push_back(s.key); });
  const auto stats = swarm::logger::replay(bus, path, {.rate = 0.0, .keyexpr = "swarm/*/tx/**"});
  check(stats.messages == 3 && keys.size() == 3, "replay filter tx only");
  check(stats.skipped == 20, "skipped count");

  const auto filtered = path.parent_path() / "filtered.mcap";
  {
    swarm::InMemoryBus src;
    swarm::logger::Recorder rec(src, filtered, {.keyexpr = "truth/**"});
    swarm::logger::replay(src, path, {.rate = 0.0});
    rec.close();
    check(rec.message_count() == 5, "record filter truth only");
  }
  check(swarm::logger::inspect(filtered).channels.size() == 1, "filtered file has one channel");
}

// TC-LOG-005: 정지 요청으로 재생을 멈춘다
void test_stop(const std::filesystem::path& path) {
  record_sample(path);
  swarm::InMemoryBus bus;
  std::stop_source stop;
  int n = 0;
  auto sub = bus.subscribe("**", [&](const swarm::Sample&) {
    if (++n == 4) stop.request_stop();
  });
  const auto stats = swarm::logger::replay(bus, path, {.rate = 0.0}, stop.get_token());
  check(stats.stopped && stats.messages == 4, "stopped after 4");
}

// TC-LOG-007: 재생한 SimStatus는 replay=true, 나머지 필드는 기록값 그대로 (DEC-031)
void test_replay_status(const std::filesystem::path& path) {
  {
    swarm::InMemoryBus bus;
    swarm::logger::Recorder rec(bus, path);
    swarm::v1::SimStatus st;
    st.set_frame(42);
    st.set_state(swarm::v1::SIM_RUN_STATE_RUNNING);
    put(bus, swarm::keys::kSimCtrlStatus, st);
    rec.close();
  }
  swarm::InMemoryBus bus;
  swarm::v1::SimStatus got;
  auto sub = bus.subscribe(swarm::keys::kSimCtrlStatus, [&](const swarm::Sample& s) {
    got.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()));
  });
  swarm::logger::replay(bus, path, {.rate = 0.0});
  check(got.replay() && got.frame() == 42 && got.state() == swarm::v1::SIM_RUN_STATE_RUNNING, "replay flag set");
}

// TC-LOG-006: 여러 스레드에서 동시에 들어오는 샘플을 모두 기록한다
void test_concurrent(const std::filesystem::path& path) {
  constexpr int kThreads = 4, kPerThread = 500;
  {
    swarm::InMemoryBus bus;
    swarm::logger::Recorder rec(bus, path);
    std::vector<std::thread> ts;
    for (int t = 0; t < kThreads; ++t)
      ts.emplace_back([&, t] {
        for (int i = 0; i < kPerThread; ++i) put(bus, "truth/state", truth_frame(static_cast<std::uint64_t>(t * kPerThread + i)));
      });
    for (auto& th : ts) th.join();
    rec.close();
    check(rec.message_count() == kThreads * kPerThread, "concurrent count");
  }
  check(swarm::logger::inspect(path).messages == kThreads * kPerThread, "concurrent file count");
}

// TC-LOG-008: 쓰기 큐 상한 — 상한을 넘는 샘플은 버리고 센다. 쓴 수 + 버린 수 = 보낸 수
void test_queue_bound(const std::filesystem::path& path) {
  constexpr int kSent = 20000;
  {  // 바이트 상한 0: 모두 버린다
    swarm::InMemoryBus bus;
    swarm::logger::Recorder rec(bus, path, {.max_queue_bytes = 0});
    for (int i = 0; i < kSent; ++i) put(bus, "truth/state", truth_frame(static_cast<std::uint64_t>(i)));
    rec.close();
    check(rec.dropped_count() == kSent && rec.message_count() == 0, "queue bytes 0: all dropped");
  }
  {  // 메시지 상한 8: 큐 길이가 상한을 넘지 않고, 쓴 수 + 버린 수 = 보낸 수
    swarm::InMemoryBus bus;
    swarm::logger::Recorder rec(bus, path, {.max_queue_messages = 8});
    for (int i = 0; i < kSent; ++i) put(bus, "truth/state", truth_frame(static_cast<std::uint64_t>(i)));
    rec.close();
    const auto st = rec.stats();
    check(st.peak_queue_messages <= 8, "queue peak within bound");
    check(st.written + st.dropped == kSent, "written + dropped == sent");
    check(st.written > 0 && st.queue_messages == 0, "queue drained at close");
    check(swarm::logger::inspect(path).messages == st.written, "file count == written");
  }
}

std::size_t rss_bytes() {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS pmc{};
  GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof pmc);
  return pmc.WorkingSetSize;
#else
  std::FILE* f = std::fopen("/proc/self/statm", "r");
  long a = 0, b = 0;
  if (f) {
    if (std::fscanf(f, "%ld %ld", &a, &b) != 2) b = 0;
    std::fclose(f);
  }
  return static_cast<std::size_t>(b) * 4096;
#endif
}

// TC-LOG-009: 채널이 많은 장시간 기록에서도 RSS가 부하에 비례해 늘지 않는다 (QA-006).
// 메시지 색인을 쓰면 1.5M건에 약 250 MB, 쓰지 않으면 약 50 MB 이하 (debug)
void test_memory_bounded(const std::filesystem::path& path) {
  constexpr int kChannels = 15000, kMsgs = 1'500'000;
  swarm::InMemoryBus bus;
  swarm::logger::Recorder rec(bus, path, {.max_queue_messages = 20000});
  const std::vector<std::uint8_t> payload(180, 7);
  const auto r0 = rss_bytes();
  std::size_t peak = 0;
  for (int i = 0; i < kMsgs; ++i) {
    bus.put("link/outcome/a" + std::to_string(i % kChannels), payload, "application/octet-stream");
    if (i % 1000 == 999)
      while (rec.stats().queue_messages > 10000) std::this_thread::yield();  // 드롭 없이 쓰기에 맞춘다
    if (i % 100000 == 99999) peak = (std::max)(peak, rss_bytes() > r0 ? rss_bytes() - r0 : std::size_t{0});
  }
  rec.close();
  const auto st = rec.stats();
  std::printf("memory test: written=%llu dropped=%llu rss growth peak=%.1f MB\n",
              static_cast<unsigned long long>(st.written), static_cast<unsigned long long>(st.dropped),
              static_cast<double>(peak) / 1048576.0);
  check(st.written == kMsgs && st.dropped == 0, "memory test: all written");
  check(peak < (100u << 20), "memory test: RSS growth < 100 MB");
  check(swarm::logger::inspect(path).messages == kMsgs, "memory test: file replayable");
}

// TC-LOG-010: 색인 없는 파일도 log_time 순으로 읽는다. 시계가 거꾸로 가도 기록 시각은 줄지 않는다.
// 색인을 켠 파일(message_index=true)도 같은 재생 결과
void test_unindexed_order(const std::filesystem::path& path) {
  for (const bool indexed : {false, true}) {
    std::uint64_t t = 5'000'000'000;
    swarm::InMemoryBus bus;
    {
      swarm::logger::Recorder rec(bus, path, {.clock = [&] { return t -= (t % 7 == 0 ? 3 : 0) + 1; }, .message_index = indexed});
      for (int i = 0; i < 300; ++i) put(bus, i % 2 ? "truth/state" : "truth/other", truth_frame(static_cast<std::uint64_t>(i)));
    }
    mcap::McapReader r;
    check(r.open(path.string()).ok(), "order: open");
    std::uint64_t prev = 0;
    std::size_t n = 0;
    bool sorted = true;
    for (const auto& mv : r.readMessages()) {
      sorted = sorted && mv.message.logTime >= prev;
      prev = mv.message.logTime;
      ++n;
    }
    r.close();
    check(sorted && n == 300, "order: file order is log_time order");
    swarm::InMemoryBus out;
    std::uint64_t got = 0;
    std::vector<std::uint64_t> frames;
    auto sub = out.subscribe("**", [&](const swarm::Sample& s) {
      swarm::v1::TruthFrame f;
      if (f.ParseFromArray(s.payload.data(), static_cast<int>(s.payload.size()))) frames.push_back(f.header().frame());
      ++got;
    });
    const auto stats = swarm::logger::replay(out, path, {.rate = 0});
    bool in_order = frames.size() == 300;
    for (std::size_t i = 0; i < frames.size(); ++i) in_order = in_order && frames[i] == i;
    check(stats.messages == 300 && got == 300 && in_order, indexed ? "order: indexed replay" : "order: unindexed replay");
  }
}
}  // namespace

int main() {
  namespace fs = std::filesystem;
  const fs::path dir = fs::temp_directory_path() / "swarm_logger_tests";
  fs::create_directories(dir);
  test_channels_and_schema(dir / "schema.mcap");
  test_replay_equal(dir / "replay.mcap");
  test_replay_timing(dir / "timing.mcap");
  test_filters(dir / "filter.mcap");
  test_stop(dir / "stop.mcap");
  test_concurrent(dir / "concurrent.mcap");
  test_replay_status(dir / "status.mcap");
  test_queue_bound(dir / "queue.mcap");
  test_unindexed_order(dir / "order.mcap");
  test_memory_bounded(dir / "memory.mcap");
  check(swarm::logger::protobuf_type_of("application/protobuf;swarm.v1.X") == "swarm.v1.X", "type of");
  check(swarm::logger::protobuf_type_of("text/plain").empty(), "type of non-protobuf");
  std::error_code ec;
  fs::remove_all(dir, ec);
  if (g_failures == 0) std::printf("swarm_logger_tests: all passed\n");
  return g_failures == 0 ? 0 : 1;
}
