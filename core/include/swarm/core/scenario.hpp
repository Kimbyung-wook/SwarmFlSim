// IMP-CORE-006: 최소 시나리오 (WP7 스키마 확정 전 임시 형식, REQ-CFG-001)
//
// {
//   "name": "demo", "frame_hz": 50, "mode": "lockstep", "rate": 0, "seed": 1,
//   "participants": ["agent-host-1"],
//   "entities": [ <EntitySpec proto JSON>, ... ]
// }
// entities 원소는 proto JSON 매핑(EntitySpec)을 그대로 쓴다. 모르는 최상위 키는 무시한다.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "swarm/v1/entity.pb.h"
#include "swarm/v1/sim.pb.h"

namespace swarm::core {

struct Scenario {
  std::string name;
  std::uint32_t frame_hz = 50;
  v1::RunMode mode = v1::RUN_MODE_REALTIME;
  double rate = 1.0;
  std::uint64_t seed = 0;
  std::vector<std::string> participants;  // lockstep 장벽 참여자 (sim/clock/done/<participant>)
  std::vector<v1::EntitySpec> entities;
};

// 형식 오류면 std::invalid_argument
Scenario parse_scenario_json(const std::string& json);

// 내장 시나리오: 한반도 중부 상공 고정익 n대(2-DoF) + GCS 1
Scenario builtin_scenario(int uav_count = 20);

}  // namespace swarm::core
