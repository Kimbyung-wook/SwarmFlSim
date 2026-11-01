// C++ MA/FA 플러그인 인터페이스. Python 쪽은 api/python/src/swarm_api/plugin.py
// 공유 라이브러리 플러그인은 아래 extern "C" 팩토리를 내보낸다. 같은 컴파일러·같은 설정으로 빌드해야 한다.
#pragma once

#include <cstdint>
#include <memory>
#include <random>
#include <string>
#include <vector>

#include <google/protobuf/message.h>
#include <google/protobuf/struct.pb.h>

#include "swarm/v1/c2.pb.h"
#include "swarm/v1/fa.pb.h"
#include "swarm/v1/mp.pb.h"
#include "swarm/v1/ms.pb.h"
#include "swarm/v1/vi.pb.h"

namespace swarm {

using MessagePtr = std::shared_ptr<const google::protobuf::Message>;

class C2Port {
 public:
  virtual ~C2Port() = default;
  virtual std::vector<MessagePtr> inbox() = 0;  // 호출하면 비워진다
  virtual void send(const google::protobuf::Message& msg) = 0;
};

class VIPort {
 public:
  virtual ~VIPort() = default;
  virtual const v1::NavigationReport* nav() const = 0;  // 아직 없으면 nullptr
  virtual const v1::FlightCapability& capability() const = 0;
  virtual const v1::SystemStatus* system_status() const = 0;
  virtual void command(const v1::FlightCommand& cmd) = 0;
  virtual std::vector<v1::FlightCommandStatus> command_status() = 0;
};

class MSPort {
 public:
  virtual ~MSPort() = default;
  virtual const v1::StoreLoadout& loadout() const = 0;
  virtual std::vector<v1::Detection> detections() = 0;
  virtual void command(const google::protobuf::Message& msg) = 0;  // Sensor/Jammer/StrikeCommand
  virtual std::vector<MessagePtr> activities() = 0;
};

class MPPort {
 public:
  virtual ~MPPort() = default;
  virtual const v1::MissionPlan* mission_plan() const = 0;
  virtual std::vector<v1::RoutePlan> route_plans() const = 0;
  virtual const v1::EngagementCriteria* engagement_criteria() const = 0;
};

class P2PPort {
 public:
  virtual ~P2PPort() = default;
  virtual void send(const google::protobuf::Message& msg, const std::vector<std::string>& to = {}) = 0;  // 비우면 브로드캐스트
  virtual std::vector<MessagePtr> inbox() = 0;
};

class MDPort {
 public:
  virtual ~MDPort() = default;
  virtual void record(const std::string& name, double value) = 0;
  virtual void record(const std::string& name, const std::string& value) = 0;
};

struct Ports {
  C2Port* c2;
  VIPort* vi;
  MSPort* ms;
  MPPort* mp;
  P2PPort* p2p;
  MDPort* md;
};

struct AgentContext {
  std::string entity_id;
  std::uint64_t frame = 0;
  double sim_time_s = 0.0;
  double dt_s = 0.0;
  Ports ports{};
  const google::protobuf::Struct* params = nullptr;
  std::mt19937_64* rng = nullptr;  // 시드 고정. lockstep 결정론을 위해 이것만 쓴다
};

class MissionAutonomy {
 public:
  virtual ~MissionAutonomy() = default;
  virtual void on_init(AgentContext&) {}
  virtual void on_step(AgentContext& ctx) = 0;
  virtual void on_shutdown(AgentContext&) {}
};

class FlightAutonomy {
 public:
  virtual ~FlightAutonomy() = default;
  virtual v1::FlightCapability on_init(const std::string& entity_id, const google::protobuf::Struct& params) = 0;
  virtual v1::FlightCommandStatus on_command(const v1::FlightCommand& cmd) = 0;
  virtual v1::ControlOutput step(const v1::NavigationReport& nav, double dt_s) = 0;
  virtual std::vector<v1::FlightCommandStatus> pending_status() { return {}; }
};

inline constexpr std::uint32_t kPluginAbiVersion = 1;

}  // namespace swarm

// 공유 라이브러리 플러그인이 내보내는 심볼
extern "C" {
using swarm_plugin_abi_fn = std::uint32_t (*)();
using swarm_create_ma_fn = swarm::MissionAutonomy* (*)(const char* name);
using swarm_create_fa_fn = swarm::FlightAutonomy* (*)(const char* name);
}
