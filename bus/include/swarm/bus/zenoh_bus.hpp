// IMP-API-007: swarm::Bus의 Zenoh 백엔드. WP1 IMP-CORE-001에서 옮김 (PRP-NET-001, DEC-002, DEC-026)
// 직접 만들기보다 open_bus.hpp의 open_bus()를 쓴다.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "swarm/api/bus.hpp"

namespace swarm::bus {

struct ZenohOptions {
  std::string config_file;              // json5 설정 파일. 비우면 기본 설정
  std::string mode;                     // peer | client | router. 비우면 설정 파일·기본값
  std::vector<std::string> connect;     // 예: tcp/192.168.0.10:7447
  std::vector<std::string> listen;      // 예: tcp/0.0.0.0:7447
  bool multicast_scouting = true;
};

// 구독 콜백은 Zenoh 내부 스레드에서 호출된다. 콜백 안에서 오래 막지 않는다.
class ZenohBus final : public Bus {
 public:
  explicit ZenohBus(const ZenohOptions& options = {});
  ~ZenohBus() override;

  ZenohBus(const ZenohBus&) = delete;
  ZenohBus& operator=(const ZenohBus&) = delete;

  void put(std::string_view key, std::span<const std::uint8_t> payload, std::string_view encoding) override;
  std::unique_ptr<Subscription> subscribe(std::string_view keyexpr, SampleCallback cb) override;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace swarm::bus
