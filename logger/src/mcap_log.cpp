// IMP-LOG-001~004: MCAP 기록·재생 (DEC-011, PRP-LOG-001)
#define MCAP_IMPLEMENTATION
#include <mcap/mcap.hpp>

#include "swarm/logger/mcap_log.hpp"

#include <google/protobuf/descriptor.h>
#include <google/protobuf/descriptor.pb.h>

#include <algorithm>
#include <chrono>
#include <map>
#include <mutex>
#include <set>
#include <stdexcept>
#include <thread>
#include <utility>

#include "swarm/v1/c2.pb.h"
#include "swarm/v1/common.pb.h"
#include "swarm/v1/entity.pb.h"
#include "swarm/v1/fa.pb.h"
#include "swarm/v1/link.pb.h"
#include "swarm/v1/mp.pb.h"
#include "swarm/v1/ms.pb.h"
#include "swarm/v1/p2p.pb.h"
#include "swarm/v1/sim.pb.h"
#include "swarm/v1/truth.pb.h"
#include "swarm/v1/vi.pb.h"

namespace swarm::logger {

namespace {
constexpr std::string_view kProtobufPrefix = "application/protobuf;";
constexpr std::string_view kRawEncoding = "application/octet-stream";

void add_file(const google::protobuf::FileDescriptor* f, std::set<std::string>& seen,
              google::protobuf::FileDescriptorSet& out) {
  if (!seen.insert(std::string(f->name())).second) return;
  for (int i = 0; i < f->dependency_count(); ++i) add_file(f->dependency(i), seen, out);
  f->CopyTo(out.add_file());
}
}  // namespace

std::uint64_t system_clock_ns() {
  using namespace std::chrono;
  return static_cast<std::uint64_t>(duration_cast<nanoseconds>(system_clock::now().time_since_epoch()).count());
}

std::uint64_t steady_clock_ns() {
  using namespace std::chrono;
  return static_cast<std::uint64_t>(duration_cast<nanoseconds>(steady_clock::now().time_since_epoch()).count());
}

std::string file_descriptor_set(const google::protobuf::Descriptor* d) {
  google::protobuf::FileDescriptorSet set;
  std::set<std::string> seen;
  add_file(d->file(), seen, set);
  return set.SerializeAsString();
}

std::string_view protobuf_type_of(std::string_view encoding) {
  if (!encoding.starts_with(kProtobufPrefix)) return {};
  return encoding.substr(kProtobufPrefix.size());
}

void ensure_swarm_descriptors() {
  // .proto 파일마다 메시지 하나를 참조하면 그 파일의 디스크립터가 등록된다
  static const bool done = [] {
    (void)v1::TaskCommand::descriptor();
    (void)v1::Header::descriptor();
    (void)v1::EntitySpec::descriptor();
    (void)v1::ControlOutput::descriptor();
    (void)v1::LinkEnvelope::descriptor();
    (void)v1::MissionPlan::descriptor();
    (void)v1::Detection::descriptor();
    (void)v1::PeerStatus::descriptor();
    (void)v1::SimCommand::descriptor();
    (void)v1::TruthFrame::descriptor();
    (void)v1::FlightCommand::descriptor();
    return true;
  }();
  (void)done;
}

// ---------------------------------------------------------------- Recorder

struct Recorder::Impl {
  RecorderOptions opts;
  mutable std::mutex mu;
  mcap::McapWriter writer;
  bool open = false;
  std::map<std::string, mcap::SchemaId> schemas;                          // 타입 이름 → id
  std::map<std::pair<std::string, std::string>, mcap::ChannelId> channels;  // (키, 인코딩) → id
  std::map<mcap::ChannelId, std::uint32_t> seq;
  std::uint64_t count = 0;
  std::unique_ptr<Subscription> sub;

  mcap::SchemaId schema_for(std::string_view type_name) {
    if (type_name.empty()) return 0;
    const std::string name(type_name);
    if (auto it = schemas.find(name); it != schemas.end()) return it->second;
    mcap::SchemaId id = 0;
    if (const auto* d = google::protobuf::DescriptorPool::generated_pool()->FindMessageTypeByName(name)) {
      mcap::Schema schema(name, "protobuf", file_descriptor_set(d));
      writer.addSchema(schema);
      id = schema.id;
    }
    schemas.emplace(name, id);  // 모르는 타입은 스키마 없이(0) 기록한다
    return id;
  }

  mcap::ChannelId channel_for(const Sample& s) {
    auto key = std::make_pair(s.key, s.encoding);
    if (auto it = channels.find(key); it != channels.end()) return it->second;
    const auto type_name = protobuf_type_of(s.encoding);
    const auto schema_id = schema_for(type_name);
    std::string msg_encoding = schema_id != 0 ? "protobuf" : (s.encoding.empty() ? std::string(kRawEncoding) : s.encoding);
    mcap::Channel ch(s.key, msg_encoding, schema_id, {{std::string(kEncodingMetaKey), s.encoding}});
    writer.addChannel(ch);
    channels.emplace(std::move(key), ch.id);
    return ch.id;
  }

  void on_sample(const Sample& s) {
    const auto t = opts.clock();
    std::lock_guard lock(mu);
    if (!open) return;
    mcap::Message m;
    m.channelId = channel_for(s);
    m.sequence = seq[m.channelId]++;
    m.logTime = t;
    m.publishTime = t;
    m.data = reinterpret_cast<const std::byte*>(s.payload.data());
    m.dataSize = s.payload.size();
    if (const auto st = writer.write(m); !st.ok()) throw std::runtime_error("mcap write: " + st.message);
    ++count;
  }
};

Recorder::Recorder(Bus& bus, const std::filesystem::path& path, RecorderOptions opts)
    : impl_(std::make_unique<Impl>()) {
  ensure_swarm_descriptors();
  impl_->opts = std::move(opts);
  mcap::McapWriterOptions wopts("");
  wopts.library = "swarm-logger";
  wopts.compression = mcap::Compression::None;
  if (const auto st = impl_->writer.open(path.string(), wopts); !st.ok())
    throw std::runtime_error("mcap open " + path.string() + ": " + st.message);
  impl_->open = true;
  impl_->sub = bus.subscribe(impl_->opts.keyexpr, [impl = impl_.get()](const Sample& s) { impl->on_sample(s); });
}

Recorder::~Recorder() { close(); }

void Recorder::close() {
  impl_->sub.reset();
  std::lock_guard lock(impl_->mu);
  if (!impl_->open) return;
  impl_->writer.close();
  impl_->open = false;
}

std::uint64_t Recorder::message_count() const {
  std::lock_guard lock(impl_->mu);
  return impl_->count;
}

std::size_t Recorder::channel_count() const {
  std::lock_guard lock(impl_->mu);
  return impl_->channels.size();
}

// ---------------------------------------------------------------- Replay

namespace {
std::string replay_encoding(const mcap::Channel& ch, const mcap::SchemaPtr& schema) {
  if (auto it = ch.metadata.find(std::string(kEncodingMetaKey)); it != ch.metadata.end()) return it->second;
  if (schema && schema->encoding == "protobuf") return protobuf_encoding(schema->name);  // 외부 도구가 만든 파일
  return ch.messageEncoding;
}

class Reader {
 public:
  explicit Reader(const std::filesystem::path& path) {
    if (const auto st = reader_.open(path.string()); !st.ok())
      throw std::runtime_error("mcap open " + path.string() + ": " + st.message);
  }
  ~Reader() { reader_.close(); }

  template <typename F>
  void for_each(F&& f) {
    mcap::ReadMessageOptions o;
    o.readOrder = mcap::ReadMessageOptions::ReadOrder::LogTimeOrder;
    std::string problem;
    auto view = reader_.readMessages([&](const mcap::Status& st) { problem = st.message; }, o);
    for (const auto& mv : view)
      if (!f(mv)) return;
    if (!problem.empty()) throw std::runtime_error("mcap read: " + problem);
  }

 private:
  mcap::McapReader reader_;
};
}  // namespace

ReplayStats replay(Bus& bus, const std::filesystem::path& path, const ReplayOptions& opts, std::stop_token stop) {
  ReplayStats stats;
  Reader reader(path);
  std::map<mcap::ChannelId, std::string> encodings;
  bool first = true;
  std::uint64_t log0 = 0, wall0 = 0;
  std::function<void(std::uint64_t)> wait = opts.wait_until;
  if (!wait) {
    wait = [&opts](std::uint64_t until) {
      const auto now = opts.now();
      if (until > now) std::this_thread::sleep_for(std::chrono::nanoseconds(until - now));
    };
  }

  reader.for_each([&](const mcap::MessageView& mv) {
    if (stop.stop_requested()) {
      stats.stopped = true;
      return false;
    }
    const auto& ch = *mv.channel;
    if (!keys::keyexpr_matches(opts.keyexpr, ch.topic)) {
      ++stats.skipped;
      return true;
    }
    const auto t = mv.message.logTime;
    if (first) {
      log0 = t;
      wall0 = opts.now();
      first = false;
    } else if (opts.rate > 0) {
      wait(wall0 + static_cast<std::uint64_t>(static_cast<double>(t - log0) / opts.rate));
    }
    auto it = encodings.find(ch.id);
    if (it == encodings.end()) it = encodings.emplace(ch.id, replay_encoding(ch, mv.schema)).first;
    const std::span<const std::uint8_t> data{reinterpret_cast<const std::uint8_t*>(mv.message.data),
                                             mv.message.dataSize};
    // IMP-LOG-008: 재생 중임을 SimStatus.replay로 알린다 (DEC-031)
    v1::SimStatus status;
    if (ch.topic == keys::kSimCtrlStatus && status.ParseFromArray(data.data(), static_cast<int>(data.size()))) {
      status.set_replay(true);
      const auto bytes = status.SerializeAsString();
      bus.put(ch.topic, {reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size()}, it->second);
    } else {
      bus.put(ch.topic, data, it->second);
    }
    stats.log_span_ns = t - log0;
    ++stats.messages;
    return true;
  });
  return stats;
}

McapInfo inspect(const std::filesystem::path& path) {
  McapInfo info;
  std::map<std::string, ChannelInfo> by_topic;
  Reader reader(path);
  reader.for_each([&](const mcap::MessageView& mv) {
    auto& ci = by_topic[mv.channel->topic];
    if (ci.messages == 0) {
      ci.topic = mv.channel->topic;
      ci.encoding = replay_encoding(*mv.channel, mv.schema);
      ci.schema_name = mv.schema ? mv.schema->name : "";
    }
    ++ci.messages;
    const auto t = mv.message.logTime;
    if (info.messages == 0) info.start_ns = t;
    info.end_ns = t;
    ++info.messages;
    return true;
  });
  for (auto& [_, ci] : by_topic) info.channels.push_back(std::move(ci));
  return info;
}

}  // namespace swarm::logger
