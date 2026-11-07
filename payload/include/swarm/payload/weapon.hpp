// IMP-PAY-005: 무장 비행 모델 (PRP-DYN-003, DEC-005, DEC-012)
// - aam_short·agm_short: 질점 + 비례항법(PN). 추력·연소 시간, 항력 k·V², 최대 기동 G, 탐색기 FOV
// - fpv: 소형 멀티콥터 3-DoF(속도 1차 추종, 중력은 추력이 상쇄) + 선행 추적 종말 유도
// - 부 스텝 안에서 가속도를 상수로 두고 위치를 해석적으로 옮긴다. 지면 교차는 이분법으로 시점을 보정한다
#pragma once

#include <cstdint>
#include <string>

#include "swarm/api/dynamics.hpp"
#include "swarm/payload/geometry.hpp"
#include "swarm/payload/profiles.hpp"

namespace swarm::payload {

enum class WeaponType { kAam, kAgm, kFpv };

// 프로파일 키와 같은 이름. 형식에 따라 쓰지 않는 값은 0
struct WeaponParams {
  double max_range_m = 0.0;        // 발사 가능 거리 (발사 시 표적·조준점까지)
  double lock_range_m = 0.0;       // 락온 거리 (표적 지정 시)
  double seeker_fov_deg = 0.0;     // 탐색기 전체 시야각. 360 이상이면 각도 판정 없음
  double seeker_el_deg = 0.0;      // 발사 전 락온 판정 축의 기체 기준 고각
  double launch_speed_mps = 0.0;   // 발사 시 기체 전방으로 더하는 속도
  double thrust_accel_mps2 = 0.0;  // 추력 가속도 (aam·agm)
  double burn_time_s = 0.0;
  double drag_k_per_m = 0.0;       // 항력 가속도 = k·V²
  double max_g = 0.0;              // 횡가속도 한계 (g)
  double nav_gain = 0.0;           // PN 항법 상수 N
  double max_speed_mps = 0.0;      // fpv
  double max_accel_mps2 = 0.0;     // fpv
  double tau_s = 0.0;              // fpv 속도 추종 시정수
  double max_flight_time_s = 0.0;  // 지나면 MISSED
  double arm_time_s = 0.0;         // 근접 신관 활성까지 시간
  double proximity_m = 0.0;        // 근접 신관 거리
  double lethal_radius_m = 0.0;    // 살상반경 (DEC-012)

  static WeaponParams from(WeaponType type, const ParamMap& m);
};

// 유도 대상의 프레임 시작 시점 상태. 프레임 안에서는 등속으로 외삽한다
struct GuidanceTarget {
  bool valid = false;
  Geo pos;
  Vec3 vel_ned;
};

struct WeaponState {
  Geo pos;
  Vec3 vel_ned;
  double t_flight_s = 0.0;
  bool seeker_locked = true;  // 표적 유도 중 탐색기 FOV를 벗어나면 false가 되고 유도를 멈춘다
  bool coordinate_mode = false;  // 좌표 유도. 탐색기 판정을 하지 않는다
};

enum class StepEnd { kFlying, kProximity, kGround, kExpired };

struct WeaponStepResult {
  StepEnd end = StepEnd::kFlying;
  double tau_s = 0.0;  // 종료 시점(프레임 시작 기준). 비행 중이면 dt
};

// 무장 한 개를 dt만큼 진행한다. terrain이 nullptr이면 지면 고도 0
WeaponStepResult advance_weapon(WeaponType type, const WeaponParams& p, WeaponState& s, const GuidanceTarget& tgt,
                                double dt, const dyn::Terrain* terrain, double max_substep_s);

// 탐색기 축 axis(비행 중에는 속도 방향) 기준 시야각 안에 r이 있는지
bool in_seeker_fov(const WeaponParams& p, Vec3 axis, Vec3 r);

// PN 가속 명령 (속도에 수직 성분만, 한계 미적용). r = 표적 - 무장, v_rel = 표적 속도 - 무장 속도
Vec3 pn_accel(double nav_gain, Vec3 r, Vec3 v_rel, Vec3 vm);

}  // namespace swarm::payload
