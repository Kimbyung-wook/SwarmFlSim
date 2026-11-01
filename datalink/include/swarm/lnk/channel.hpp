// IMP-LNK-002~007: 링크 모델 요소 (PRP-LNK-001, REQ-LNK-001, DEC-009)
// 버스와 무관한 순수 계산이다. Emulator가 링크(송신→수신 방향)마다 상태를 하나씩 가진다.
#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <random>
#include <string_view>

#include "swarm/api/dynamics.hpp"
#include "swarm/lnk/profile.hpp"

namespace swarm::lnk {

struct GeoPoint {
  double lat_deg = 0.0;
  double lon_deg = 0.0;
  double alt_m = 0.0;  // MSL
};

inline constexpr double kEarthMeanRadiusM = 6371008.8;
inline constexpr double kEffectiveEarthK = 4.0 / 3.0;  // 표준 대기 굴절

// IMP-LNK-002: 기하와 경로손실
void to_ecef(const GeoPoint& p, double out[3]);
double slant_range_m(const GeoPoint& a, const GeoPoint& b);   // WGS84 ECEF 직선거리
double ground_range_m(const GeoPoint& a, const GeoPoint& b);  // 평균 반경 구면 대원거리
double fspl_db(double range_m, double freq_mhz);              // 자유공간 경로손실 20log10(4πdf/c)
double snr_db(const LinkProfile& tx, const LinkProfile& rx, double range_m);
// SNR ≥ snr_min이고 max_range_m 안이면 true
bool in_range(const LinkProfile& tx, const LinkProfile& rx, double range_m);

// IMP-LNK-003: 가시선. 두 점을 잇는 직선이 지형(+ 유효 지구 반경 k·R의 곡률)보다 위에 있는지
// terrain이 nullptr이면 true. step_m 간격으로 표본을 잡는다(최대 2000점)
bool line_of_sight(const dyn::Terrain* terrain, const GeoPoint& a, const GeoPoint& b, double step_m = 100.0,
                   double k_factor = kEffectiveEarthK);

// IMP-LNK-007: 재밍 영역(원, 고도 무관 기둥). 영역 안이면 true
bool in_jam_zone(const GeoPoint& p, const GeoPoint& center, double radius_m);

// 결정론 난수. 분포 변환을 직접 구현해 표준 라이브러리 구현과 무관하게 같은 값을 낸다
class Rng {
 public:
  explicit Rng(std::uint64_t seed = 0) : eng_(seed) {}
  double uniform();  // [0, 1)
  double normal();   // N(0, 1), Box-Muller

 private:
  std::mt19937_64 eng_;
};

// FNV-1a 64. 링크별 난수 시드를 이름에서 안정적으로 만든다
std::uint64_t stable_hash(std::string_view s);
std::uint64_t link_seed(std::uint64_t seed, std::string_view src, std::string_view dst);

// IMP-LNK-004: Gilbert-Elliott 버스트 손실
class GilbertElliottChannel {
 public:
  // 상태 천이 후 손실 여부를 판정한다
  bool lost(const GilbertElliott& p, Rng& rng);
  bool bad() const { return bad_; }

 private:
  bool bad_ = false;
};

// IMP-LNK-005: 지연·지터 (µs). latency + jitter·N(0,1), 0 이상
std::uint64_t sample_delay_us(const LinkProfile& p, Rng& rng);

// IMP-LNK-006: 토큰 버킷 대역폭 큐. 메시지는 들어온 순서로 나간다(FIFO)
class TokenBucket {
 public:
  TokenBucket() = default;
  TokenBucket(double rate_bps, double depth_bytes, std::size_t queue_len);

  // t_us에 bytes 크기 메시지가 들어온다. 대기열이 차 있으면 false.
  // 받으면 depart_us에 송출 시각(토큰이 모이는 시각)을 넣는다
  bool admit(std::uint64_t t_us, std::size_t bytes, std::uint64_t& depart_us);
  std::size_t queued(std::uint64_t t_us);

 private:
  double rate_bpus_ = 0.0;  // byte/µs. 0이면 무제한
  double depth_ = 0.0;
  std::size_t queue_len_ = 0;
  double tokens_ = 0.0;
  double t_ref_us_ = 0.0;  // tokens_가 유효한 시각 = 마지막 송출 시각
  std::deque<std::uint64_t> departures_;
};

}  // namespace swarm::lnk
