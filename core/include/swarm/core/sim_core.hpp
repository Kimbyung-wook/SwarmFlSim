// IMP-CORE-002: 프레임 스케줄러와 실행 모드 (DEC-005, REQ-SIM-002, REQ-DYN-003, PRP-SIM-002)
// IMP-CORE-004: onboard/<id>/ControlOutput → 동역학 입력, onboard/<id>/NavigationReport 발행
// IMP-CORE-009: 지면 교차 이벤트로 엔티티를 죽이고 truth/event/kill(cause=ground)을 발행한다
// IMP-CORE-013: 동역학 매개변수. SetParams는 poll 시작(프레임 경계)에 적용하고 sim/param/<id>/dynamics를 발행한다 (DEC-035)
// IMP-CORE-011: InjectFault. KILL, ENGINE(속도 명령 최소), NAV(NavigationReport 중단), SENSOR(기록만).
//               LINK_CUT·GCS_LINK_CUT은 Datalink(WP4)가 처리하므로 Core는 무시한다
//
// 프레임 N의 순서
//   1. truth/state, onboard/<id>/NavigationReport, sim/clock/tick(N)을 발행한다 (시각 t_N의 상태)
//   2. 참여자는 tick(N)을 받아 ControlOutput을 보내고, lockstep이면 sim/clock/done/<p>에 FrameDone(N)을 보낸다
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

  // 시나리오를 읽어 LOADED로 둔다. RUNNING/PAUSED이면 거부(false). 형식 오류는 예외
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
    std::map<std::string, v1::ControlOutput> controls;  // 엔티티별 최신값
    std::vector<v1::FrameDone> dones;
  };

  void handle(const v1::SimCommand& cmd, Clock::time_point now);
  void handle_start(const v1::Start& s, Clock::time_point now);
  void handle_fault(const v1::InjectFault& f);
  void handle_set_params(const v1::SetParams& p);
  void publish_params(std::size_t i);
  void publish_all_params();
  bool fault_active(std::size_t i, v1::FaultKind kind) const;
  void kill(std::size_t i, const char* cause, std::uint64_t sim_time_us, std::uint64_t frame);
  void reset_run_state();
  bool barrier_ok() const;
  bool paced() const;
  void integrate_frame();
  void publish_frame();
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
  std::vector<double> u_scratch_;
  std::vector<std::string> nav_keys_;
  std::vector<std::uint32_t> nav_seq_;
  std::vector<std::string> participants_;

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
  Clock::time_point rate_wall_{};
  std::uint64_t rate_sim_us_ = 0;
  double rate_actual_ = 0.0;
  std::uint32_t seq_truth_ = 0, seq_event_ = 0;
};

}  // namespace swarm::core
