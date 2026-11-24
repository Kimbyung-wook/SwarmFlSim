// ASB(Abstract Service Bus) 계약 (PRP-NET-001).
// Zenoh 백엔드는 WP1이 구현한다. InMemoryBus는 각 WP의 단독 시험용이다.
#pragma once

#include <chrono>
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

// IMP-API-026 (DEC-109): 조회 응답 함수. 요청 키 표현을 받아 답할 샘플들을 돌려준다(없으면 빈 목록).
// 샘플 키는 요청 키 표현과 맞아야 한다. 응답 함수는 버스 내부 스레드에서 호출될 수 있다.
using QueryHandler = std::function<std::vector<Sample>(std::string_view keyexpr)>;

class Bus {
 public:
  virtual ~Bus() = default;
  virtual void put(std::string_view key, std::span<const std::uint8_t> payload, std::string_view encoding) = 0;
  virtual std::unique_ptr<Subscription> subscribe(std::string_view keyexpr, SampleCallback cb) = 0;
  // IMP-API-026 (DEC-109): keyexpr에 대한 조회에 답한다. 반환 객체를 소멸하면 응답을 멈춘다.
  // 조회를 지원하지 않는 구현은 std::logic_error를 던진다.
  virtual std::unique_ptr<Subscription> serve(std::string_view keyexpr, QueryHandler handler) {
    (void)keyexpr;
    (void)handler;
    throw std::logic_error("bus does not support queries");
  }
  // IMP-API-026 (DEC-109): keyexpr을 조회해 timeout 안에 온 응답을 돌려준다. 응답자가 없으면 빈 목록.
  virtual std::vector<Sample> get(std::string_view keyexpr, std::chrono::milliseconds timeout) {
    (void)keyexpr;
    (void)timeout;
    throw std::logic_error("bus does not support queries");
  }
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

  std::unique_ptr<Subscription> serve(std::string_view keyexpr, QueryHandler handler) override {
    std::lock_guard lock(mu_);
    const auto id = next_id_++;
    servers_.emplace(id, Server{std::string(keyexpr), std::move(handler)});
    return std::make_unique<Handle>(*this, id);
  }

  // 동기식: 키 표현이 겹치는 응답자를 바로 호출한다. timeout은 쓰지 않는다
  std::vector<Sample> get(std::string_view keyexpr, std::chrono::milliseconds) override {
    std::vector<QueryHandler> targets;
    {
      std::lock_guard lock(mu_);
      for (const auto& [id, srv] : servers_)
        // 근사: 한쪽이 다른 쪽을 포함하면 겹친다고 본다
        if (keys::keyexpr_matches(srv.keyexpr, keyexpr) || keys::keyexpr_matches(keyexpr, srv.keyexpr))
          targets.push_back(srv.handler);
    }
    std::vector<Sample> out;
    for (const auto& h : targets)
      for (auto& s : h(keyexpr))
        if (keys::keyexpr_matches(keyexpr, s.key)) out.push_back(std::move(s));
    return out;
  }

 private:
  struct Entry {
    std::string keyexpr;
    SampleCallback cb;
  };
  struct Server {
    std::string keyexpr;
    QueryHandler handler;
  };

  class Handle final : public Subscription {
   public:
    Handle(InMemoryBus& bus, std::uint64_t id) : bus_(bus), id_(id) {}
    ~Handle() override {
      std::lock_guard lock(bus_.mu_);
      bus_.subs_.erase(id_);
      bus_.servers_.erase(id_);
    }

   private:
    InMemoryBus& bus_;
    std::uint64_t id_;
  };

  std::mutex mu_;
  std::map<std::uint64_t, Entry> subs_;
  std::map<std::uint64_t, Server> servers_;
  std::uint64_t next_id_ = 0;
};

}  // namespace swarm
