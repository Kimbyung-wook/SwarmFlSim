// IMP-API-007: ZenohBus (zenoh-cpp, zenoh-c 백엔드). WP1 IMP-CORE-001에서 옮김 (DEC-026)
#include "swarm/bus/zenoh_bus.hpp"

#include <optional>
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

}  // namespace swarm::bus
