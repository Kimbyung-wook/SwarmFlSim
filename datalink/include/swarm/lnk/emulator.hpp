// IMP-LNK-008~010: Datalink Emulator (PRP-LNK-001, PRP-LNK-002, REQ-LNK-001~004, DEC-009, DEC-005)
//
// - swarm/*/tx/** (LinkEnvelope)를 받아 링크 모델을 적용하고 swarm/<dst>/rx/<iface>/<msg>로 전달한다.
// - 위치·생존은 truth/state, 재밍 영역은 truth/event/jam_zone, 엔티티 목록·링크 프로파일은
//   sim/ctrl/cmd의 LoadScenario.scenario(또는 load())에서 얻는다.
// - 시간은 sim/clock/tick만 따른다. 받은 송신은 다음 tick에서 (송신 시각, src, 키, seq) 순으로 처리하고,
//   도착 시각이 지난 메시지를 그 tick에 전달한다. 난수는 방향 링크(src→dst)마다 따로 두어
//   메시지 도착 순서가 프로세스마다 달라도 결과가 같다(lockstep 결정론).
// - 구독 콜백은 버스 스레드에서 불린다. 내부 상태는 뮤텍스로 보호하고, 발행은 잠금 밖에서 한다.
#pragma once

#include <condition_variable>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include "swarm/api/bus.hpp"
#include "swarm/api/dynamics.hpp"
#include "swarm/lnk/channel.hpp"
#include "swarm/lnk/profile.hpp"
#include "swarm/v1/link.pb.h"
#include "swarm/v1/sim.pb.h"
#include "swarm/v1/truth.pb.h"

namespace swarm::lnk {

struct DatalinkConfig {
  std::string participant_id = "datalink-0";  // FrameDone 발행 ID. 비우면 FrameDone을 보내지 않는다
  std::uint64_t seed = 0;                     // LoadScenario.run.seed, Start.seed가 0이 아니면 덮어쓴다
  double state_period_s = 1.0;                // link/state 발행 주기(시뮬레이션 시각). 0이면 발행하지 않는다
  double degraded_margin_db = 6.0;            // SNR이 snr_min + 이 값보다 낮으면 DEGRADED
  double degraded_loss_rate = 0.1;            // 최근 구간 손실률이 이 값 이상이면 DEGRADED
  double los_step_m = 100.0;
  std::map<std::string, LinkProfile> profiles;  // 내장 프로파일에 더하거나 덮어쓴다
  std::function<void(const std::string&)> log;
};

// LinkState 계산 결과(시험·진단용)
struct PairState {
  bool known = false;  // 두 엔티티의 위치를 안다
  double range_m = 0.0;
  double snr_db = 0.0;  // 두 방향 중 낮은 값
  bool in_range = false;
  bool los = false;
  bool jammed = false;
  bool cut = false;
  bool dead = false;
};

class Datalink {
 public:
  // terrain은 Datalink보다 오래 살아야 한다. nullptr이면 가시선 판정을 하지 않는다
  Datalink(Bus& bus, const dyn::Terrain* terrain, DatalinkConfig cfg = {});
  ~Datalink();

  Datalink(const Datalink&) = delete;
  Datalink& operator=(const Datalink&) = delete;

  // 시나리오를 불러온다. 엔티티 표·링크 상태·지연 큐·고장·재밍 영역을 모두 초기화한다
  void load(const v1::Scenario& sc);

  // Shutdown 명령을 받을 때까지 기다린다. timeout_ms < 0이면 무한
  bool wait_shutdown(int timeout_ms = -1);
  void request_shutdown();

  std::uint64_t sim_time_us() const;
  std::uint64_t seed() const;
  std::size_t in_flight() const;
  PairState pair_state(const std::string& a, const std::string& b) const;

 private:
  struct Node {
    std::string id;
    v1::EntityKind kind = v1::ENTITY_KIND_UNSPECIFIED;
    v1::Side side = v1::SIDE_UNSPECIFIED;
    std::string profile_name;
    GeoPoint pos;
    bool has_pos = false;
    bool alive = true;
  };

  struct Channel {
    Rng rng;
    GilbertElliottChannel ge;
    TokenBucket bucket;
    std::uint64_t sent = 0;  // LinkState 구간 통계
    std::uint64_t lost = 0;
  };

  struct Pending {
    std::uint64_t tx_time_us;
    std::string src;
    std::string key;
    std::uint32_t seq;
    std::uint64_t arrival;  // 받은 순서. 같은 키·seq가 겹칠 때만 쓴다
    std::string suffix;     // tx 뒤의 <iface>/<msg>
    std::size_t size;
    v1::LinkEnvelope env;
  };

  struct InFlight {
    std::uint64_t arrive_us;
    std::uint64_t tx_time_us;
    std::string src;
    std::string dst;
    std::string suffix;
    std::size_t size;
    std::shared_ptr<const v1::LinkEnvelope> env;
  };

  struct Fault {
    std::string entity;
    v1::FaultKind kind;
    std::uint64_t until_us;  // 0이면 해제 명령까지
  };

  struct Out {
    std::string key;
    std::string bytes;
    std::string encoding;
  };

  void on_tx(const Sample& s);
  void on_tick(const Sample& s);
  void on_truth(const Sample& s);
  void on_event(const Sample& s);
  void on_cmd(const Sample& s);

  // 아래는 mu_를 잡은 상태에서 부른다
  void load_locked(const v1::Scenario& sc);
  void reset_locked();
  Node& node_locked(const std::string& id);
  const LinkProfile& profile_locked(const Node& n) const;
  Channel& channel_locked(const std::string& src, const std::string& dst);
  bool comm_node(const Node& n) const;
  bool peers(const Node& a, const Node& b) const;
  bool jammed_locked(const Node& n) const;
  bool cut_locked(const std::string& a, const std::string& b) const;
  PairState pair_state_locked(const Node& a, const Node& b) const;
  v1::DropReason static_check_locked(const Node* src, const Node* dst) const;
  void process_locked(Pending& p, std::vector<Out>& out);
  void route_locked(const Pending& p, const std::string& dst, std::vector<Out>& out);
  void deliver_locked(std::vector<Out>& out);
  void publish_states_locked(std::vector<Out>& out);
  void outcome_locked(const std::string& src, const std::string& dst, const v1::LinkEnvelope& env, std::size_t size,
                      v1::DropReason reason, std::uint64_t tx_us, std::uint64_t rx_us, std::vector<Out>& out);
  void log(const std::string& msg) const;

  void publish(std::vector<Out>& out);

  Bus& bus_;
  const dyn::Terrain* terrain_;
  DatalinkConfig cfg_;

  mutable std::mutex mu_;
  std::map<std::string, LinkProfile> profiles_;
  std::map<std::string, Node> nodes_;
  std::map<std::pair<std::string, std::string>, Channel> channels_;
  struct JamZone {
    GeoPoint center;
    double radius_m;
  };
  std::map<std::string, JamZone> jam_zones_;  // 소유자 → 영역
  std::vector<Fault> faults_;
  std::vector<Pending> pending_;
  std::vector<InFlight> in_flight_;
  std::uint64_t seed_ = 0;
  std::uint64_t now_us_ = 0;
  std::uint64_t frame_ = 0;
  std::uint64_t arrival_ = 0;
  std::uint64_t next_state_us_ = 0;
  std::uint32_t state_seq_ = 0;
  mutable std::map<std::string, bool> warned_;

  std::mutex shutdown_mu_;
  std::condition_variable shutdown_cv_;
  bool shutdown_ = false;

  std::vector<std::unique_ptr<Subscription>> subs_;
};

}  // namespace swarm::lnk
