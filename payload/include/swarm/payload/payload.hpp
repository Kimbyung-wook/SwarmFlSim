// IMP-PAY-003~007: 임무장비·무장 계산기 (DEC-046, PRP-PAY-001, REQ-PAY-001~005, REQ-SIM-001)
// Core(WP1)가 링크해 프레임마다 step()을 한 번 부른다. 벽시계·난수를 쓰지 않고, 같은 입력이면 같은 출력을 낸다.
// 출력 순서는 엔티티 ID(사전순) → payload_id → 대상 ID로 고정한다.
#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/api/dynamics.hpp"
#include "swarm/payload/geometry.hpp"
#include "swarm/payload/profiles.hpp"
#include "swarm/payload/weapon.hpp"
#include "swarm/v1/entity.pb.h"
#include "swarm/v1/ms.pb.h"
#include "swarm/v1/truth.pb.h"

namespace swarm::payload {

struct Options {
  double max_substep_s = 0.005;         // 무장 부 스텝 상한
  std::uint32_t activity_period_frames = 1;  // SensorActivity·JammerActivity 주기(프레임). 명령을 받은 프레임에는 항상 낸다
};

// 엔티티 하나의 프레임 시작 상태
struct EntityInput {
  v1::EntityState state;     // id, kind, side, kinematics, alive
  bool sensor_fault = false;  // FAULT_KIND_SENSOR 활성 (DEC-047)
};

// onboard/<entity>/<Command>로 받은 명령. entity는 키의 <id>
template <class M>
struct Addressed {
  std::string entity;
  M msg;
};

struct FrameInput {
  std::uint64_t frame = 0;  // 출력 Header.frame에 그대로 쓴다
  std::uint64_t t_us = 0;   // 프레임 시작 sim 시각. entities 상태의 시각
  double dt_s = 0.02;       // 무장을 t_us → t_us + dt로 진행한다
  std::vector<EntityInput> entities;  // 이 라이브러리가 만든 무장 엔티티는 넣지 않아도 된다(넣으면 무시)
  std::vector<Addressed<v1::SensorCommand>> sensor_cmds;
  std::vector<Addressed<v1::JammerCommand>> jammer_cmds;
  std::vector<Addressed<v1::StrikeCommand>> strike_cmds;
};

// 기체 하나의 onboard 출력. Header.source = 기체 ID, seq는 비워 둔다(발행자가 채운다)
struct OnboardOutput {
  std::string entity;
  std::vector<v1::Detection> detections;
  std::vector<v1::SensorActivity> sensor_activity;
  std::vector<v1::JammerActivity> jammer_activity;
  std::vector<v1::StrikeActivity> strike_activity;
  std::optional<v1::StoreLoadout> loadout;  // 처음 프레임과 잔량이 바뀐 프레임에만
};

struct FrameOutput {
  std::vector<OnboardOutput> onboard;     // 출력이 있는 살아 있는 기체만, ID 순
  std::vector<v1::EntityState> spawned;   // 이번 프레임에 만든 무장의 발사 시점 상태 (SpawnEvent와 같다)
  std::vector<v1::EntityState> weapons;   // 무장의 t_us + dt 상태, ID 순. 이번 프레임에 끝난 무장은 alive=false로 한 번 더 나온다
  std::vector<v1::TruthEvent> events;     // truth/event/<kind>. sim_time_us 순(같으면 생성 순)
  std::vector<std::string> killed;        // 살상반경으로 이번 프레임에 파괴한 엔티티(무장 제외), ID 순. Core가 alive=false로 만든다
};

// 비행 중 무장의 유도 상태 (DEC-064). 버스로 보고하지 않는다(계약에 필드가 없다)
struct WeaponTrack {
  std::string target;          // 지정 표적. 조준점 발사면 빈 문자열
  bool locked = false;         // 표적을 추적 중 (지정 표적, 가시선·탐색기 FOV 유지)
  bool los_lost = false;       // 가시선 상실로 락을 풀고 좌표 유도 중
  bool coordinate_mode = false;
  Geo guide_point;             // 좌표 유도 지점(마지막으로 본 표적 위치 또는 조준점)
};

// TruthEvent의 oneof → 키 꼬리 (launch, impact, kill, jam_zone, spawn). 없으면 빈 문자열
std::string_view event_kind(const v1::TruthEvent& ev);

class PayloadSystem {
 public:
  // specs: 시나리오 엔티티 전체. 탑재 장비는 EntitySpec.payloads. jammer_site에 jammer가 없으면 기본 프로파일 jam0을 둔다.
  // los: 가시선 판정(nullptr이면 항상 보임). terrain: 무장 지면 교차(nullptr이면 고도 0 평지). 둘 다 이 객체보다 오래 살아야 한다.
  // 프로파일·재정의 오류는 std::invalid_argument
  PayloadSystem(const ProfileLibrary& lib, const std::vector<v1::EntitySpec>& specs, LosFn los,
                const dyn::Terrain* terrain, Options opt = {});
  ~PayloadSystem();
  PayloadSystem(const PayloadSystem&) = delete;
  PayloadSystem& operator=(const PayloadSystem&) = delete;

  // 시나리오 적재 직후 상태로 되돌린다 (잔량, 센서·재머 상태, 무장, 순번)
  void reset();
  FrameOutput step(const FrameInput& in);

  // 이 라이브러리가 만든 무장 엔티티인지 (Core는 이 엔티티를 적분하지 않는다)
  bool owns(const std::string& entity_id) const;
  // 현재 잔량 포함 탑재 구성. 모르는 엔티티면 빈 목록
  std::vector<v1::PayloadSpec> loadout(const std::string& entity_id) const;
  // 해석된 장비 매개변수 (프로파일 + 재정의). 없으면 nullptr
  const ParamMap* params(const std::string& entity_id, const std::string& payload_id) const;
  // 비행 중 무장의 유도 상태 (마지막 step 뒤). 끝난 무장이나 모르는 ID면 nullopt
  std::optional<WeaponTrack> weapon_track(const std::string& weapon_id) const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace swarm::payload
