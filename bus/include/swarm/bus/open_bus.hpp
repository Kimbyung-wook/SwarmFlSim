// IMP-API-007: 버스 생성 공통화 (DEC-026, PRP-NET-001)
// 프로세스는 버스 구현을 직접 만들지 않고 open_bus()로 연다. 명령행 옵션도 같은 이름을 쓴다.
#pragma once

#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/api/bus.hpp"

namespace swarm::bus {

struct BusConfig {
  std::string backend;               // "zenoh" | "memory". 비우면 default_backend()
  std::string zenoh_config_file;     // json5 설정 파일
  std::string zenoh_mode;            // peer | client | router
  std::vector<std::string> connect;  // 예: tcp/192.168.0.10:7447
  std::vector<std::string> listen;   // 예: tcp/0.0.0.0:7447
  bool multicast_scouting = true;
};

// 이 빌드에 Zenoh 백엔드가 들어 있는지
bool zenoh_available();

// Zenoh가 있으면 "zenoh", 없으면 "memory"
std::string default_backend();

// 지원하지 않는 백엔드면 std::invalid_argument
std::unique_ptr<Bus> open_bus(const BusConfig& config = {});

// 공통 명령행 옵션을 해석한다. flag가 버스 옵션이면 필요한 값을 next()로 읽고 true
bool parse_bus_arg(BusConfig& config, std::string_view flag, const std::function<std::string()>& next);

inline constexpr const char* kBusUsage =
    "  --bus <zenoh|memory>     버스 백엔드 (기본: Zenoh가 있으면 zenoh)\n"
    "  --zenoh-config <file>    Zenoh json5 설정 파일\n"
    "  --zenoh-mode <m>         peer | client | router\n"
    "  --connect <endpoint>     접속할 Zenoh 엔드포인트 (반복 가능)\n"
    "  --listen <endpoint>      들을 Zenoh 엔드포인트 (반복 가능)\n"
    "  --no-multicast           멀티캐스트 스카우팅을 끈다\n";

}  // namespace swarm::bus
