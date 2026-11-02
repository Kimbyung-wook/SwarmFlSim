// IMP-LNK-002~007, IMP-LNK-013: 링크 모델 요소 (PRP-LNK-001, REQ-LNK-001, DEC-009, DEC-030)
#include "swarm/lnk/channel.hpp"

#include <algorithm>
#include <cmath>
#include <numbers>

namespace swarm::lnk {
namespace {

constexpr double kDeg = std::numbers::pi / 180.0;
constexpr double kWgs84A = 6378137.0;
constexpr double kWgs84F = 1.0 / 298.257223563;
constexpr double kWgs84E2 = kWgs84F * (2.0 - kWgs84F);
constexpr double kLightMps = 299792458.0;

}  // namespace

void to_ecef(const GeoPoint& p, double out[3]) {
  const double lat = p.lat_deg * kDeg, lon = p.lon_deg * kDeg;
  const double s = std::sin(lat), c = std::cos(lat);
  const double n = kWgs84A / std::sqrt(1.0 - kWgs84E2 * s * s);
  out[0] = (n + p.alt_m) * c * std::cos(lon);
  out[1] = (n + p.alt_m) * c * std::sin(lon);
  out[2] = (n * (1.0 - kWgs84E2) + p.alt_m) * s;
}

double slant_range_m(const GeoPoint& a, const GeoPoint& b) {
  double ea[3], eb[3];
  to_ecef(a, ea);
  to_ecef(b, eb);
  return std::sqrt((ea[0] - eb[0]) * (ea[0] - eb[0]) + (ea[1] - eb[1]) * (ea[1] - eb[1]) +
                   (ea[2] - eb[2]) * (ea[2] - eb[2]));
}

double ground_range_m(const GeoPoint& a, const GeoPoint& b) {
  const double la = a.lat_deg * kDeg, lb = b.lat_deg * kDeg;
  const double dlat = lb - la, dlon = (b.lon_deg - a.lon_deg) * kDeg;
  const double h = std::sin(dlat / 2) * std::sin(dlat / 2) +
                   std::cos(la) * std::cos(lb) * std::sin(dlon / 2) * std::sin(dlon / 2);
  return 2.0 * kEarthMeanRadiusM * std::asin(std::min(1.0, std::sqrt(h)));
}

double fspl_db(double range_m, double freq_mhz) {
  const double d = std::max(range_m, 1.0);
  return 20.0 * std::log10(4.0 * std::numbers::pi * d * freq_mhz * 1.0e6 / kLightMps);
}

double snr_db(const LinkProfile& tx, const LinkProfile& rx, double range_m) {
  return tx.tx_power_dbm + tx.antenna_gain_dbi + rx.antenna_gain_dbi - fspl_db(range_m, tx.freq_mhz) -
         rx.noise_floor_dbm;
}

bool in_range(const LinkProfile& tx, const LinkProfile& rx, double range_m) {
  if (tx.unlimited_range || rx.unlimited_range) return true;
  for (const LinkProfile* p : {&tx, &rx})
    if (p->max_range_m > 0.0 && range_m > p->max_range_m) return false;
  return snr_db(tx, rx, range_m) >= rx.snr_min_db;
}

bool line_of_sight(const dyn::Terrain* terrain, const GeoPoint& a, const GeoPoint& b, double step_m, double k_factor) {
  if (!terrain) return true;
  const double d = ground_range_m(a, b);
  const int n = std::clamp(static_cast<int>(std::ceil(d / std::max(step_m, 1.0))), 2, 2000);
  const double re = k_factor * kEarthMeanRadiusM;
  for (int i = 1; i < n; ++i) {
    const double s = static_cast<double>(i) / n;
    // 짧은 구간이므로 위경도는 선형 보간한다. 곡률은 현(弦) 아래로 처지는 높이 s(1−s)d²/(2kR)로 넣는다
    const double lat = a.lat_deg + s * (b.lat_deg - a.lat_deg);
    const double lon = a.lon_deg + s * (b.lon_deg - a.lon_deg);
    const double ray = a.alt_m + s * (b.alt_m - a.alt_m) - s * (1.0 - s) * d * d / (2.0 * re);
    if (ray < terrain->elevation_m(lat, lon)) return false;
  }
  return true;
}

bool in_jam_zone(const GeoPoint& p, const GeoPoint& center, double radius_m) {
  return ground_range_m(p, center) <= radius_m;
}

bool in_polygon(const GeoPoint& p, const std::vector<GeoPoint>& v) {
  bool inside = false;
  for (std::size_t i = 0, j = v.size() - 1; i < v.size(); j = i++) {
    const double yi = v[i].lat_deg, yj = v[j].lat_deg, xi = v[i].lon_deg, xj = v[j].lon_deg;
    if ((yi > p.lat_deg) != (yj > p.lat_deg) && p.lon_deg < (xj - xi) * (p.lat_deg - yi) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

bool in_jam_area(const GeoPoint& p, const JamArea& a) {
  if (p.alt_m < a.min_alt_m) return false;
  if (a.max_alt_m != 0.0 && p.alt_m > a.max_alt_m) return false;
  if (a.polygon.size() >= 3) return in_polygon(p, a.polygon);
  return in_jam_zone(p, a.center, a.radius_m);
}

double Rng::uniform() { return static_cast<double>(eng_() >> 11) * 0x1.0p-53; }

double Rng::normal() {
  const double u1 = 1.0 - uniform();  // (0, 1]
  const double u2 = uniform();
  return std::sqrt(-2.0 * std::log(u1)) * std::cos(2.0 * std::numbers::pi * u2);
}

std::uint64_t stable_hash(std::string_view s) {
  std::uint64_t h = 1469598103934665603ULL;
  for (unsigned char c : s) {
    h ^= c;
    h *= 1099511628211ULL;
  }
  return h;
}

std::uint64_t link_seed(std::uint64_t seed, std::string_view src, std::string_view dst) {
  // splitmix64 마무리로 시드와 이름 해시를 섞는다
  std::uint64_t z = seed ^ (stable_hash(src) * 0x9E3779B97F4A7C15ULL) ^ stable_hash(dst);
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
  return z ^ (z >> 31);
}

bool GilbertElliottChannel::lost(const GilbertElliott& p, Rng& rng) {
  const double u = rng.uniform();
  bad_ = bad_ ? !(u < p.p_bg) : (u < p.p_gb);
  return rng.uniform() < (bad_ ? p.loss_bad : p.loss_good);
}

std::uint64_t sample_delay_us(const LinkProfile& p, Rng& rng) {
  double ms = p.latency_ms;
  if (p.jitter_ms > 0.0) ms += p.jitter_ms * rng.normal();
  return static_cast<std::uint64_t>(std::llround(std::max(ms, 0.0) * 1000.0));
}

TokenBucket::TokenBucket(double rate_bps, double depth_bytes, std::size_t queue_len)
    : rate_bpus_(rate_bps > 0.0 ? rate_bps / 8.0e6 : 0.0),
      depth_(depth_bytes),
      queue_len_(queue_len),
      tokens_(depth_bytes) {}

std::size_t TokenBucket::queued(std::uint64_t t_us) {
  while (!departures_.empty() && departures_.front() <= t_us) departures_.pop_front();
  return departures_.size();
}

bool TokenBucket::admit(std::uint64_t t_us, std::size_t bytes, std::uint64_t& depart_us) {
  if (rate_bpus_ <= 0.0) {
    depart_us = t_us;
    return true;
  }
  if (queue_len_ > 0 && queued(t_us) >= queue_len_) return false;
  const double start = std::max(static_cast<double>(t_us), t_ref_us_);
  double tok = std::min(depth_, tokens_ + (start - t_ref_us_) * rate_bpus_);
  const double need = static_cast<double>(bytes);
  double dep = start;
  if (tok >= need) {
    tok -= need;
  } else {
    dep = start + (need - tok) / rate_bpus_;
    tok = 0.0;
  }
  tokens_ = tok;
  t_ref_us_ = dep;
  depart_us = static_cast<std::uint64_t>(std::ceil(dep));
  departures_.push_back(depart_us);
  return true;
}

}  // namespace swarm::lnk
