// ASB(Abstract Service Bus) 계약 (PRP-NET-001).
// Zenoh 백엔드는 WP1이 구현한다. InMemoryBus는 각 WP의 단독 시험용이다.
#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/api/keys.hpp"

namespace swarm {

struct Sample {
  std::string key;
  std::vector<std::uint8_t> payload;
  std::string encoding;  // 예: "application/protobuf;swarm.v1.LinkEnvelope"
};

using SampleCallback = std::function<void(const Sample&)>;

class Subscription {
 public:
  virtual ~Subscription() = default;  // 소멸 시 구독 해제
};

class Bus {
 public:
  virtual ~Bus() = default;
  virtual void put(std::string_view key, std::span<const std::uint8_t> payload, std::string_view encoding) = 0;
  virtual std::unique_ptr<Subscription> subscribe(std::string_view keyexpr, SampleCallback cb) = 0;
};

inline std::string protobuf_encoding(std::string_view full_name) {
  return "application/protobuf;" + std::string(full_name);
}

// 동기식 단일 프로세스 버스. put 안에서 일치하는 구독 콜백을 바로 호출한다.
// InMemoryBus는 구독 객체보다 오래 살아야 한다.
class InMemoryBus final : public Bus {
 public:
  void put(std::string_view key, std::span<const std::uint8_t> payload, std::string_view encoding) override {
    if (key.find('*') != std::string_view::npos) throw std::invalid_argument("wildcard in put key");
    Sample s{std::string(key), {payload.begin(), payload.end()}, std::string(encoding)};
    std::vector<SampleCallback> targets;
    {
      std::lock_guard lock(mu_);
      for (const auto& [id, sub] : subs_)
        if (keys::keyexpr_matches(sub.keyexpr, key)) targets.push_back(sub.cb);
    }
    for (const auto& cb : targets) cb(s);
  }

  std::unique_ptr<Subscription> subscribe(std::string_view keyexpr, SampleCallback cb) override {
    std::lock_guard lock(mu_);
    const auto id = next_id_++;
    subs_.emplace(id, Entry{std::string(keyexpr), std::move(cb)});
    return std::make_unique<Handle>(*this, id);
  }

 private:
  struct Entry {
    std::string keyexpr;
    SampleCallback cb;
  };

  class Handle final : public Subscription {
   public:
    Handle(InMemoryBus& bus, std::uint64_t id) : bus_(bus), id_(id) {}
    ~Handle() override {
      std::lock_guard lock(bus_.mu_);
      bus_.subs_.erase(id_);
    }

   private:
    InMemoryBus& bus_;
    std::uint64_t id_;
  };

  std::mutex mu_;
  std::map<std::uint64_t, Entry> subs_;
  std::uint64_t next_id_ = 0;
};

}  // namespace swarm
