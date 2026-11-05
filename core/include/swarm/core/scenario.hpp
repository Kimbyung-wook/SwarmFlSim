// IMP-CORE-006: 시나리오 (REQ-CFG-001)
// IMP-CORE-007: swarm.v1.Scenario(proto)를 기본 형식으로 받는다 (DEC-024, DEC-025)
//
// 아래 최소 JSON 형식은 폐기 예정(LoadScenario.scenario_json)이며 호환을 위해 남겨 둔다.
// {
//   "name": "demo", "frame_hz": 50, "mode": "lockstep", "rate": 0, "seed": 1,
//   "participants": ["agent-host-1"],
//   "entities": [ <EntitySpec proto JSON>, ... ]
// }
// entities 원소는 proto JSON 매핑(EntitySpec)을 그대로 쓴다. 모르는 최상위 키는 무시한다.
#pragma once

#include <cstdint>
#include <optional>
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
  std::optional<v1::Scenario> source;  // proto로 받은 시나리오 원본. 재발행에 쓴다 (DEC-037)
};

// 형식 오류면 std::invalid_argument
Scenario parse_scenario_json(const std::string& json);

Scenario from_proto(const v1::Scenario& msg);

// IMP-CORE-017: 배속 상한. 0은 제한 없음(lockstep·free-run). NaN·inf·음수·상한 초과는 거부한다 (DEC-038)
constexpr double kMaxRate = 1000.0;
bool valid_rate(double rate);

// IMP-CORE-017: 적재 전 입력 검증 (DEC-038). 비유한 값, 범위 밖 위경도, 빈 엔티티, frame_hz·배속 범위,
// 없는 링크 프로파일을 std::invalid_argument로 거부한다. 중복 ID·동역학 지원 여부는 EntityStore가 본다
// IMP-CORE-025: 엔티티 ID 형식·25자 초과(DEC-050), 엔티티당 재머 2개 이상(DEC-049)도 거부한다
constexpr std::size_t kMaxScenarioEntityId = 25;
void validate_scenario(const Scenario& sc);

// CLI 실행 재정의. 빈 문자열은 재정의 없음. 모드가 틀리면 std::invalid_argument
struct RunOverride {
  std::string mode, rate, hz, seed;
};
// 적재할 필드와 재발행할 원본(source.run)에 같이 반영한다 (DEC-037)
void apply_run_override(Scenario& sc, const RunOverride& o);

// sim/ctrl/scenario 재발행용 (DEC-037). 원본이 있으면 그대로, 없으면 Scenario 필드에서 만든다
v1::Scenario to_proto(const Scenario& sc);

// 파일: .pb는 swarm.v1.Scenario 바이너리, 그 밖은 JSON.
// JSON에 "run" 객체가 있으면 swarm.v1.Scenario의 proto JSON(swarm-scenario export 출력), 없으면 최소 형식
Scenario read_scenario_file(const std::string& path);

// 내장 시나리오: 한반도 중부 상공 고정익 n대(2-DoF) + GCS 1
Scenario builtin_scenario(int uav_count = 20);

}  // namespace swarm::core
