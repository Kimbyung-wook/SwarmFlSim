// IMP-API-007: ZenohBus (zenoh-cpp, zenoh-c 백엔드). WP1 IMP-CORE-001에서 옮김 (DEC-026)
#include "swarm/bus/zenoh_bus.hpp"

#include <optional>
#include <variant>
#include <stdexcept>
#include <utility>

#include "zenoh.hxx"

namespace swarm::bus {

namespace {

std::string json_string_list(const std::vector<std::string>& items) {
  std::string out = "[";
  for (std::size_t i = 0; i < items.size(); ++i) {
    if (i) out += ",";
    out += "\"" + items[i] + "\"";
  }
  return out + "]";
}

zenoh::Config make_config(const ZenohOptions& o) {
  auto config = o.config_file.empty() ? zenoh::Config::create_default() : zenoh::Config::from_file(o.config_file);
  if (!o.mode.empty()) config.insert_json5("mode", "\"" + o.mode + "\"");
  if (!o.connect.empty()) config.insert_json5("connect/endpoints", json_string_list(o.connect));
  if (!o.listen.empty()) config.insert_json5("listen/endpoints", json_string_list(o.listen));
  if (!o.multicast_scouting) config.insert_json5("scouting/multicast/enabled", "false");
  return config;
}

// DEC-043: lockstep 장벽과 데이터링크 경로(`sim/clock/**`, `swarm/**`)
bool is_lockstep_path_key(std::string_view key) {
  return key.starts_with("sim/clock/") || key.starts_with("swarm/");
}

class ZenohSubscription final : public Subscription {
 public:
  explicit ZenohSubscription(zenoh::Subscriber<void>&& sub) : sub_(std::move(sub)) {}
  ~ZenohSubscription() override {
    // 1.x는 소멸 시 구독을 해제하지만, 해제 오류가 소멸자 밖으로 나가지 않도록 명시적으로 처리한다
    if (sub_) {
      zenoh::ZResult err = 0;
      std::move(*sub_).undeclare(&err);
    }
  }

 private:
  std::optional<zenoh::Subscriber<void>> sub_;
};

class ZenohQueryable final : public Subscription {
 public:
  explicit ZenohQueryable(zenoh::Queryable<void>&& q) : q_(std::move(q)) {}
  ~ZenohQueryable() override {
    if (q_) {
      zenoh::ZResult err = 0;
      std::move(*q_).undeclare(&err);
    }
  }

 private:
  std::optional<zenoh::Queryable<void>> q_;
};

}  // namespace

struct ZenohBus::Impl {
  zenoh::Session session;
  explicit Impl(const ZenohOptions& o) : session(zenoh::Session::open(make_config(o))) {}
};

ZenohBus::ZenohBus(const ZenohOptions& options) : impl_(std::make_unique<Impl>(options)) {}

ZenohBus::~ZenohBus() = default;

void ZenohBus::put(std::string_view key, std::span<const std::uint8_t> payload, std::string_view encoding) {
  if (key.find('*') != std::string_view::npos) throw std::invalid_argument("wildcard in put key");
  zenoh::Session::PutOptions opts;
  // DEC-043: lockstep 경로 키는 같은 우선순위·BLOCK으로 보내 혼잡 시 버리지 않고 링크 큐 하나의 순서를 지킨다
  opts.priority = Z_PRIORITY_DATA;
  opts.is_express = false;
  if (is_lockstep_path_key(key)) opts.congestion_control = Z_CONGESTION_CONTROL_BLOCK;
  if (!encoding.empty()) opts.encoding = zenoh::Encoding(encoding);
  impl_->session.put(zenoh::KeyExpr(key), zenoh::Bytes(std::vector<std::uint8_t>(payload.begin(), payload.end())),
                     std::move(opts));
}

std::unique_ptr<Subscription> ZenohBus::subscribe(std::string_view keyexpr, SampleCallback cb) {
  auto on_sample = [cb = std::move(cb)](zenoh::Sample& z) {
    Sample s;
    s.key = std::string(z.get_keyexpr().as_string_view());
    s.payload = z.get_payload().as_vector();
    s.encoding = z.get_encoding().as_string();
    cb(s);
  };
  auto sub = impl_->session.declare_subscriber(zenoh::KeyExpr(keyexpr), std::move(on_sample), zenoh::closures::none);
  return std::make_unique<ZenohSubscription>(std::move(sub));
}

// IMP-API-026 (DEC-109): 조회 응답. 응답 샘플마다 reply 한 건
std::unique_ptr<Subscription> ZenohBus::serve(std::string_view keyexpr, QueryHandler handler) {
  auto on_query = [handler = std::move(handler)](zenoh::Query& q) {
    const auto samples = handler(q.get_keyexpr().as_string_view());
    for (const auto& s : samples) {
      auto ro = zenoh::Query::ReplyOptions::create_default();
      if (!s.encoding.empty()) ro.encoding = zenoh::Encoding(s.encoding);
      zenoh::ZResult err = 0;
      q.reply(zenoh::KeyExpr(s.key), zenoh::Bytes(std::vector<std::uint8_t>(s.payload)), std::move(ro), &err);
    }
  };
  auto q = impl_->session.declare_queryable(zenoh::KeyExpr(keyexpr), std::move(on_query), zenoh::closures::none);
  return std::make_unique<ZenohQueryable>(std::move(q));
}

// IMP-API-026 (DEC-109): timeout 안에 온 정상 응답만 모은다. 같은 키의 응답은 Zenoh 기본 통합 규칙을 따른다
std::vector<Sample> ZenohBus::get(std::string_view keyexpr, std::chrono::milliseconds timeout) {
  zenoh::Session::GetOptions opts;
  opts.timeout_ms = timeout.count() > 0 ? static_cast<std::uint64_t>(timeout.count()) : 1;
  auto replies = impl_->session.get(zenoh::KeyExpr(keyexpr), "", zenoh::channels::FifoChannel(64), std::move(opts));
  std::vector<Sample> out;
  for (auto r = replies.recv(); std::holds_alternative<zenoh::Reply>(r); r = replies.recv()) {
    const auto& reply = std::get<zenoh::Reply>(r);
    if (!reply.is_ok()) continue;
    const auto& z = reply.get_ok();
    Sample s;
    s.key = std::string(z.get_keyexpr().as_string_view());
    s.payload = z.get_payload().as_vector();
    s.encoding = z.get_encoding().as_string();
    out.push_back(std::move(s));
  }
  return out;
}

}  // namespace swarm::bus
