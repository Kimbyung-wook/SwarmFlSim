// TC-LOG-001~006: InMemoryBus로 기록 → 재생 결과 일치
#include <mcap/reader.hpp>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/descriptor.pb.h>
#include <google/protobuf/dynamic_message.h>
#include <google/protobuf/util/message_differencer.h>

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
  check(swarm::logger::protobuf_type_of("application/protobuf;swarm.v1.X") == "swarm.v1.X", "type of");
  check(swarm::logger::protobuf_type_of("text/plain").empty(), "type of non-protobuf");
  std::error_code ec;
  fs::remove_all(dir, ec);
  if (g_failures == 0) std::printf("swarm_logger_tests: all passed\n");
  return g_failures == 0 ? 0 : 1;
}
