// IMP-DYN-005 (REQ-SIM-003, DEC-004, DEC-005, DEC-016)
#include "swarm/dyn/terrain.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace swarm::dyn {

GridTerrain::GridTerrain(GridSpec spec, std::vector<float> heights_m, double outside_m)
    : spec_(spec), h_(std::move(heights_m)), outside_m_(outside_m) {
  if (spec_.rows < 2 || spec_.cols < 2) throw std::invalid_argument("GridTerrain: rows and cols must be >= 2");
  if (!(spec_.dlat_deg > 0.0) || !(spec_.dlon_deg > 0.0))
    throw std::invalid_argument("GridTerrain: spacing must be positive");
  if (h_.size() != spec_.rows * spec_.cols) throw std::invalid_argument("GridTerrain: heights size != rows * cols");
}

bool GridTerrain::contains(double lat_deg, double lon_deg) const {
  const double fr = (lat_deg - spec_.lat0_deg) / spec_.dlat_deg;
  const double fc = (lon_deg - spec_.lon0_deg) / spec_.dlon_deg;
  return fr >= 0.0 && fc >= 0.0 && fr <= static_cast<double>(spec_.rows - 1) &&
         fc <= static_cast<double>(spec_.cols - 1);
}

double GridTerrain::elevation_m(double lat_deg, double lon_deg) const {
  if (!contains(lat_deg, lon_deg)) return outside_m_;
  const double fr = (lat_deg - spec_.lat0_deg) / spec_.dlat_deg;
  const double fc = (lon_deg - spec_.lon0_deg) / spec_.dlon_deg;
  const std::size_t r = std::min(static_cast<std::size_t>(fr), spec_.rows - 2);
  const std::size_t c = std::min(static_cast<std::size_t>(fc), spec_.cols - 2);
  const double a = fr - static_cast<double>(r), b = fc - static_cast<double>(c);
  const auto at = [&](std::size_t i, std::size_t j) { return static_cast<double>(h_[i * spec_.cols + j]); };
  return (1 - a) * ((1 - b) * at(r, c) + b * at(r, c + 1)) + a * ((1 - b) * at(r + 1, c) + b * at(r + 1, c + 1));
}

EventFn make_ground_event(const DynamicsModel& model, const Terrain& terrain, double clearance_m) {
  return [&model, &terrain, clearance_m](double, std::span<const double> x) {
    KinematicSample k;
    model.to_kinematic(x, k);
    return k.alt_m - (terrain.elevation_m(k.lat_deg, k.lon_deg) + clearance_m);
  };
}

}  // namespace swarm::dyn
