// IMP-LNK-001: 링크 프로파일 (PRP-LNK-001, REQ-LNK-001, REQ-LNK-004)
// EntitySpec.link_profile 이름 → 파라미터. 값은 공개 일반값 수준의 대표값이다.
// 시나리오 JSON 재정의는 다음 단계(DatalinkConfig::profiles로 코드에서 추가·덮어쓰기만 된다).
#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/v1/entity.pb.h"

namespace swarm::lnk {

// 2-상태 Gilbert-Elliott. 메시지마다 상태 천이 후 상태별 손실률로 판정한다
struct GilbertElliott {
  double p_gb = 0.0;       // Good → Bad
  double p_bg = 1.0;       // Bad → Good
  double loss_good = 0.0;
  double loss_bad = 0.0;
};

// 송신 측 값(송신 전력·이득·주파수·지연·대역폭·GE)은 송신 엔티티의 프로파일,
// 수신 측 값(이득·잡음·최소 SNR)은 수신 엔티티의 프로파일에서 가져온다
struct LinkProfile {
  std::string name;
  double freq_mhz = 2400.0;
  double tx_power_dbm = 30.0;
  double antenna_gain_dbi = 3.0;
  double noise_floor_dbm = -100.0;
  double snr_min_db = 10.0;      // 이보다 낮으면 OUT_OF_RANGE
  double max_range_m = 0.0;      // 0이면 SNR로만 판정
  bool unlimited_range = false;  // 경로손실·거리 판정을 하지 않는다 (시험·이상 링크)
  double latency_ms = 20.0;      // 고정 지연
  double jitter_ms = 5.0;        // 정규 지터 표준편차. 지연 합은 0 이상으로 자른다
  double bandwidth_bps = 1.0e6;  // 토큰 버킷 채움 속도. 0이면 무제한
  double bucket_bytes = 4096.0;  // 토큰 버킷 깊이
  std::size_t queue_len = 64;    // 대기 메시지 수 상한. 넘치면 QUEUE_OVERFLOW. 0이면 무제한
  GilbertElliott ge;
};

// 내장 프로파일: default, uav_default, gcs_default, fpv_default, ideal
const LinkProfile* find_builtin_profile(std::string_view name);
std::vector<std::string> builtin_profile_names();

// link_profile이 비었을 때 엔티티 종류별 기본 프로파일 이름
std::string_view default_profile_name(v1::EntityKind kind);

}  // namespace swarm::lnk
