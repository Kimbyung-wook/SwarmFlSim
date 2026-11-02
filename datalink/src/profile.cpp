// IMP-LNK-001: 내장 링크 프로파일 (PRP-LNK-001)
// IMP-LNK-014: 시나리오 재정의 (DEC-029)
#include "swarm/lnk/profile.hpp"

#include <array>

namespace swarm::lnk {
namespace {

LinkProfile make_uav(std::string name) {
  // 2.4 GHz, 1 W, 3 dBi 전방향. UAV↔UAV 최대 거리 약 20 km(SNR 10 dB)
  LinkProfile p;
  p.name = std::move(name);
  p.ge = {0.01, 0.25, 0.0, 0.5};
  return p;
}

LinkProfile make_gcs() {
  // 지상 통제 링크. 10 W, 12 dBi, 저잡음 수신기. GCS↔UAV 약 150 km
  LinkProfile p;
  p.name = "gcs_default";
  p.tx_power_dbm = 40.0;
  p.antenna_gain_dbi = 12.0;
  p.noise_floor_dbm = -105.0;
  p.snr_min_db = 6.0;
  p.latency_ms = 50.0;
  p.jitter_ms = 10.0;
  p.bandwidth_bps = 2.0e6;
  p.bucket_bytes = 16384.0;
  p.queue_len = 128;
  p.ge = {0.005, 0.3, 0.0, 0.3};
  return p;
}

LinkProfile make_fpv() {
  // 5.8 GHz 소형 링크. FPV↔FPV 약 3 km
  LinkProfile p;
  p.name = "fpv_default";
  p.freq_mhz = 5800.0;
  p.tx_power_dbm = 25.0;
  p.antenna_gain_dbi = 2.0;
  p.noise_floor_dbm = -95.0;
  p.latency_ms = 10.0;
  p.jitter_ms = 3.0;
  p.bandwidth_bps = 5.0e5;
  p.bucket_bytes = 2048.0;
  p.queue_len = 32;
  p.ge = {0.02, 0.25, 0.0, 0.5};
  return p;
}

LinkProfile make_ideal() {
  LinkProfile p;
  p.name = "ideal";
  p.unlimited_range = true;
  p.latency_ms = 0.0;
  p.jitter_ms = 0.0;
  p.bandwidth_bps = 0.0;
  p.ge = {0.0, 1.0, 0.0, 0.0};
  return p;
}

const std::array<LinkProfile, 5>& table() {
  static const std::array<LinkProfile, 5> t = {make_uav("default"), make_uav("uav_default"), make_gcs(),
                                               make_fpv(), make_ideal()};
  return t;
}

}  // namespace

const LinkProfile* find_builtin_profile(std::string_view name) {
  for (const auto& p : table())
    if (p.name == name) return &p;
  return nullptr;
}

std::vector<std::string> builtin_profile_names() {
  std::vector<std::string> out;
  for (const auto& p : table()) out.push_back(p.name);
  return out;
}

std::string_view default_profile_name(v1::EntityKind kind) {
  switch (kind) {
    case v1::ENTITY_KIND_GCS: return "gcs_default";
    case v1::ENTITY_KIND_UAV: return "uav_default";
    case v1::ENTITY_KIND_FPV: return "fpv_default";
    default: return "default";
  }
}

LinkProfile apply_override(const LinkProfile& base, const v1::LinkProfile& spec) {
  LinkProfile p = base;
  p.name = spec.name();
  if (spec.has_freq_mhz()) p.freq_mhz = spec.freq_mhz();
  if (spec.has_tx_power_dbm()) p.tx_power_dbm = spec.tx_power_dbm();
  if (spec.has_antenna_gain_dbi()) p.antenna_gain_dbi = spec.antenna_gain_dbi();
  if (spec.has_noise_floor_dbm()) p.noise_floor_dbm = spec.noise_floor_dbm();
  if (spec.has_snr_min_db()) p.snr_min_db = spec.snr_min_db();
  if (spec.has_max_range_m()) p.max_range_m = spec.max_range_m();
  if (spec.has_unlimited_range()) p.unlimited_range = spec.unlimited_range();
  if (spec.has_latency_ms()) p.latency_ms = spec.latency_ms();
  if (spec.has_jitter_ms()) p.jitter_ms = spec.jitter_ms();
  if (spec.has_bandwidth_bps()) p.bandwidth_bps = spec.bandwidth_bps();
  if (spec.has_bucket_bytes()) p.bucket_bytes = spec.bucket_bytes();
  if (spec.has_queue_len()) p.queue_len = spec.queue_len();
  if (spec.has_ge()) p.ge = {spec.ge().p_gb(), spec.ge().p_bg(), spec.ge().loss_good(), spec.ge().loss_bad()};
  return p;
}

}  // namespace swarm::lnk
