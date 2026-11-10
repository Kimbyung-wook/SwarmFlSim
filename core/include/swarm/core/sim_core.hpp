// IMP-CORE-002: 프레임 스케줄러와 실행 모드 (DEC-005, REQ-SIM-002, REQ-DYN-003, PRP-SIM-002)
// IMP-CORE-004: 제어 입력 → 동역학 입력, 항법 발행
// IMP-CORE-029: 프레임당 onboard_batch/NavigationBatch 1건 발행 (DEC-081)
// IMP-CORE-030: onboard_batch/ControlBatch/<participant> 구독 → 동역학 입력 (DEC-081)
// IMP-CORE-009: 지면 교차 이벤트로 엔티티를 죽이고 truth/event/kill(cause=ground)을 발행한다
// IMP-CORE-013: 동역학 매개변수. SetParams는 poll 시작(프레임 경계)에 적용하고 sim/param/<id>/dynamics를 발행한다 (DEC-035)
// IMP-CORE-011: InjectFault. KILL, ENGINE(속도 명령 최소), NAV(NavigationReport 중단), SENSOR(기록만).
//               LINK_CUT·GCS_LINK_CUT의 효과는 Datalink(WP4)가 내고 Core는 SystemStatus용으로 기록만 한다 (IMP-CORE-028)
//
// 프레임 N의 순서
//   1. truth/state, onboard_batch/NavigationBatch, sim/clock/tick(N)을 발행한다 (시각 t_N의 상태)
//   2. 참여자는 tick(N)을 받아 ControlBatch를 보내고, lockstep이면 sim/clock/done/<p>에 FrameDone(N)을 보낸다
//   3. 진행 조건(lockstep 장벽, 배속 기한)을 만족하면 받은 입력으로 [t_N, t_N+dt]를 적분하고 N+1로 넘어간다
#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <random>
#include <string>
#include <vector>

#include <google/protobuf/message.h>

#include "swarm/api/bus.hpp"
#include "swarm/core/dynamics_provider.hpp"
#include "swarm/core/entity_store.hpp"
#include "swarm/core/scenario.hpp"
#include "swarm/payload/payload.hpp"
#include "swarm/v1/fa.pb.h"
#include "swarm/v1/sim.pb.h"
#include "swarm/v1/vi.pb.h"

namespace swarm::core {

// NavigationReport 잡음 훅. 기본은 없음(참값 그대로). rng는 실행 시드로 고정된다
using NavNoiseFn = std::function<void(const std::string& entity_id, v1::NavigationReport& nav, std::mt19937_64& rng)>;
using LogFn = std::function<void(const std::string&)>;

struct CoreConfig {
  std::string participant_id = "core-0";  // 발행 Header.source
  std::vector<std::string> participants;  // lockstep 장벽 참여자. 시나리오의 participants와 합친다
  NavNoiseFn nav_noise;
  LogFn log;                              // 비우면 stderr
  std::uint64_t stop_after_frames = 0;    // 0이 아니면 이 프레임에 도달한 뒤 정지(STOPPED)
};

class SimCore {
 public:
  using Clock = std::chrono::steady_clock;

  SimCore(Bus& bus, DynamicsProvider provider, CoreConfig cfg = {});
  ~SimCore();

  SimCore(const SimCore&) = delete;
  SimCore& operator=(const SimCore&) = delete;

  // 시나리오를 읽어 LOADED로 둔다. RUNNING/PAUSED이면 거부(false). 검증 실패(DEC-038)도 거부하고 기존 상태를 그대로 둔다
  bool load(const Scenario& sc);

  // 명령을 큐에 넣는다. sim/ctrl/cmd 구독과 같은 경로로 처리된다. 어느 스레드에서나 호출할 수 있다
  void submit(const v1::SimCommand& cmd);

  // 한 번 돈다: 받은 명령·제어·완료 신호를 처리하고, 진행 조건을 만족하면 한 프레임 진행한다.
  // 진행했으면 true. poll과 아래 조회 함수는 같은 스레드에서 호출한다
  bool poll(Clock::time_point now);

  // STOPPED가 될 때까지 poll을 반복한다. 실시간·배속 기한까지는 대기한다
  void run();

  v1::SimRunState state() const { return state_; }
  v1::RunMode mode() const { return mode_; }
  std::uint64_t frame() const { return frame_; }
  std::uint64_t sim_time_us() const { return sim_time_us_; }
  std::uint32_t frame_hz() const { return frame_hz_; }
  std::uint32_t dt_us() const { return dt_us_; }
  double rate() const { return rate_; }
  std::uint64_t seed() const { return seed_; }
  std::uint64_t frame_overruns() const { return overruns_; }
  std::uint64_t control_mismatches() const { return control_mismatches_; }
  // 현재 시각에 고장이 걸려 있는가 (ENGINE, NAV, SENSOR)
  bool fault_active(const std::string& entity_id, v1::FaultKind kind) const;
  const EntityStore& entities() const { return store_; }
  v1::SimStatus status() const;

 private:
  struct Inbox {
    std::vector<v1::SimCommand> commands;
    // IMP-CORE-030: 참여자별 수신 순 ControlBatch. 적분 때 참여자 이름 순으로 합쳐 도착 순서와 무관하게 한다
    std::map<std::string, std::vector<v1::ControlBatch>> control_batches;
    std::vector<v1::FrameDone> dones;
    // IMP-CORE-022: 임무장비 명령 (onboard/<id>/{Sensor,Jammer,Strike}Command). 프레임 적분 때 payload에 넘긴다
    std::vector<payload::Addressed<v1::SensorCommand>> sensor_cmds;
    std::vector<payload::Addressed<v1::JammerCommand>> jammer_cmds;
    std::vector<payload::Addressed<v1::StrikeCommand>> strike_cmds;
  };

  void handle(const v1::SimCommand& cmd, Clock::time_point now);
  void handle_start(const v1::Start& s, Clock::time_point now);
  void log_waiting(Clock::time_point now, bool ready_phase);
  void update_waiting(Clock::time_point now, bool ready_phase);
  void clear_waiting(Clock::time_point now);
  void handle_fault(const v1::InjectFault& f);
  void handle_set_params(const v1::SetParams& p);
  void publish_params(std::size_t i);
  void publish_all_params();
  void publish_scenario();
  bool fault_active(std::size_t i, v1::FaultKind kind) const;
  void kill(std::size_t i, const char* cause, std::uint64_t sim_time_us, std::uint64_t frame);
  // IMP-CORE-026: DEM 지형보다 낮게 시작하는 공중 엔티티를 찾는다 (DEC-060)
  void find_below_terrain_starts();
  void reset_run_state();
  bool barrier_ok() const;
  bool paced() const;
  void integrate_frame();
  std::vector<std::string> step_payload(std::vector<payload::Addressed<v1::SensorCommand>> sensor,
                                        std::vector<payload::Addressed<v1::JammerCommand>> jammer,
                                        std::vector<payload::Addressed<v1::StrikeCommand>> strike);
  void publish_frame();
  // IMP-CORE-028: onboard/<id>/SystemStatus 발행 (DEC-073)
  void publish_system_status();
  v1::SystemStatus system_status(std::size_t i) const;
  void publish_truth();
  void publish_status(Clock::time_point now);
  void set_state(v1::SimRunState s, Clock::time_point now);
  void anchor(Clock::time_point now);
  Clock::time_point next_deadline() const;
  void publish(const std::string& key, const google::protobuf::Message& msg);
  void log(const std::string& msg) const;
  void wake();

  Bus& bus_;
  DynamicsProvider provider_;
  CoreConfig cfg_;

  // 버스 콜백 → 코어 스레드
  std::mutex inbox_mu_;
  Inbox inbox_;
  std::mutex wake_mu_;
  std::condition_variable wake_cv_;
  bool wake_flag_ = false;

  std::vector<std::unique_ptr<Subscription>> subs_;

  // 시나리오
  Scenario scenario_;
  EntityStore store_;
  std::vector<std::unique_ptr<dyn::Integrator>> integrators_;
  std::vector<dyn::EventFn> ground_events_;  // 비어 있으면 이벤트 없음
  // IMP-CORE-026: 시작 프레임에 kill(cause=ground)할 엔티티 (DEC-060)
  struct BelowStart {
    std::size_t index;
    double alt_m, terrain_m;
  };
  std::vector<BelowStart> below_start_;
  std::vector<double> u_scratch_;
  std::vector<std::uint32_t> nav_seq_;
  std::uint32_t nav_batch_seq_ = 0;
  std::vector<std::string> participants_;
  // IMP-CORE-022: 임무장비·무장 계산기 (WP8, DEC-046). 시나리오를 적재할 때 만든다
  std::unique_ptr<payload::PayloadSystem> payload_;
  std::vector<v1::EntityState> weapons_;  // 무장 엔티티의 현재 상태. TruthFrame에 덧붙인다
  std::map<std::string, std::uint32_t> onboard_seq_;  // 임무장비 출력 키별 순번
  // IMP-CORE-024: 활성 재밍 구역 owner → 마지막 JamZone 이벤트. 1 s 모의 시간마다 다시 발행한다 (DEC-052)
  std::map<std::string, v1::TruthEvent> active_zones_;
  std::uint64_t next_zone_us_ = 0;  // 다음 주기 재발행 시각(모의 µs)
  // IMP-CORE-028: SystemStatus. 엔티티 ID 순 색인, 키, 마지막 발행 내용(health·subsystems), 다음 주기 시각
  std::vector<std::size_t> id_order_;
  std::vector<std::string> sys_keys_;
  std::vector<std::string> sys_last_;
  std::vector<std::uint32_t> sys_seq_;
  std::uint64_t next_sys_us_ = 0;

  // 실행 상태
  v1::SimRunState state_ = v1::SIM_RUN_STATE_IDLE;
  v1::RunMode mode_ = v1::RUN_MODE_REALTIME;
  std::uint32_t frame_hz_ = 50;
  std::uint32_t dt_us_ = 20000;
  double rate_ = 1.0;
  std::uint64_t seed_ = 0;
  std::mt19937_64 rng_;
  std::uint64_t frame_ = 0;
  std::uint64_t sim_time_us_ = 0;
  bool frame_published_ = false;  // 현재 프레임의 tick을 발행했는가
  std::uint32_t step_budget_ = 0;  // PAUSED에서 진행할 남은 프레임 수
  std::map<std::string, std::uint64_t> done_;  // 참여자별 마지막 완료 프레임 + 1 (0 = 없음)
  std::uint64_t overruns_ = 0;
  std::uint64_t control_mismatches_ = 0;
  // (엔티티, 고장 종류) → 해제 시각 µs. 해제 명령까지면 UINT64_MAX
  std::map<std::pair<std::size_t, v1::FaultKind>, std::uint64_t> faults_;

  // 배속 기한: anchor_wall_ + (frame - anchor_frame_ + 1) × dt / rate
  Clock::time_point anchor_wall_{};
  std::uint64_t anchor_frame_ = 0;

  // 상태 보고
  Clock::time_point last_status_wall_{};
  Clock::time_point last_params_wall_{};
  Clock::time_point last_wait_log_{};
  // IMP-CORE-020: lockstep 대기 시작 시각과, 5 s 넘게 응답이 없는 참여자 (DEC-041)
  bool blocked_ = false;
  Clock::time_point wait_since_{};
  std::vector<std::string> waiting_;
  std::set<std::string> ready_;  // lockstep 준비 신호(FrameDone{frame=0})를 보낸 참여자 (DEC-037)
  Clock::time_point rate_wall_{};
  std::uint64_t rate_sim_us_ = 0;
  double rate_actual_ = 0.0;
  std::uint32_t seq_truth_ = 0, seq_event_ = 0;
};

}  // namespace swarm::core
