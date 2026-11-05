// IMP-PAY-005: 무장 비행 모델 (PRP-DYN-003, DEC-005, DEC-012)
#include "swarm/payload/weapon.hpp"

#include <algorithm>
#include <cmath>

#include "swarm/dyn/geo.hpp"

namespace swarm::payload {

namespace geo = swarm::dyn::geo;

WeaponParams WeaponParams::from(WeaponType type, const ParamMap& m) {
  WeaponParams p;
  p.max_range_m = need(m, "max_range_m");
  p.lock_range_m = need(m, "lock_range_m");
  p.seeker_fov_deg = need(m, "seeker_fov_deg");
  p.seeker_el_deg = need(m, "seeker_el_deg");
  p.launch_speed_mps = need(m, "launch_speed_mps");
  p.max_flight_time_s = need(m, "max_flight_time_s");
  p.arm_time_s = need(m, "arm_time_s");
  p.proximity_m = need(m, "proximity_m");
  p.lethal_radius_m = need(m, "lethal_radius_m");
  if (type == WeaponType::kFpv) {
    p.max_speed_mps = need(m, "max_speed_mps");
    p.max_accel_mps2 = need(m, "max_accel_mps2");
    p.tau_s = std::max(need(m, "tau_s"), 1e-3);
  } else {
    p.thrust_accel_mps2 = need(m, "thrust_accel_mps2");
    p.burn_time_s = need(m, "burn_time_s");
    p.drag_k_per_m = need(m, "drag_k_per_m");
    p.max_g = need(m, "max_g");
    p.nav_gain = need(m, "nav_gain");
  }
  return p;
}

Vec3 pn_accel(double nav_gain, Vec3 r, Vec3 v_rel, Vec3 vm) {
  const double r2 = dot(r, r);
  if (r2 < 1e-6) return {};
  const Vec3 omega = (1.0 / r2) * cross(r, v_rel);  // 시선 각속도
  const double vc = -dot(r, v_rel) / std::sqrt(r2);  // 접근 속도
  Vec3 a = (nav_gain * vc) * cross(omega, unit(r));
  const Vec3 um = unit(vm);
  return a - dot(a, um) * um;
}

namespace {

Vec3 limit(Vec3 a, double max_norm) {
  const double n = norm(a);
  return n > max_norm && n > 0.0 ? (max_norm / n) * a : a;
}

bool in_seeker_fov(const WeaponParams& p, Vec3 axis, Vec3 r) {
  if (p.seeker_fov_deg >= 360.0) return true;
  const double c = dot(unit(axis), unit(r));
  return std::acos(std::clamp(c, -1.0, 1.0)) <= 0.5 * p.seeker_fov_deg * geo::kDegToRad;
}

Vec3 accel(WeaponType type, const WeaponParams& p, WeaponState& s, bool guide, Vec3 r, Vec3 vt) {
  const double g = geo::kStdGravity;
  if (guide && !s.coordinate_mode && s.seeker_locked && !in_seeker_fov(p, s.vel_ned, r)) s.seeker_locked = false;
  const bool steer = guide && (s.coordinate_mode || s.seeker_locked);
  if (type == WeaponType::kFpv) {
    Vec3 vcmd = s.vel_ned;
    if (steer) {
      const double tgo = norm(r) / std::max(p.max_speed_mps, 1.0);
      vcmd = p.max_speed_mps * unit(r + tgo * vt);
    }
    return limit((1.0 / p.tau_s) * (vcmd - s.vel_ned), p.max_accel_mps2);
  }
  const double v = norm(s.vel_ned);
  const Vec3 u = unit(s.vel_ned);
  Vec3 a{0.0, 0.0, g};
  if (s.t_flight_s < p.burn_time_s) a = a + p.thrust_accel_mps2 * u;
  a = a - (p.drag_k_per_m * v * v) * u;
  if (steer) {
    const Vec3 up{0.0, 0.0, -g};
    const Vec3 gcomp = up - dot(up, u) * u;  // 중력의 횡성분 상쇄
    a = a + limit(pn_accel(p.nav_gain, r, vt - s.vel_ned, s.vel_ned) + gcomp, p.max_g * g);
  }
  return a;
}

double ground_clearance(const Geo& x, const dyn::Terrain* terrain) {
  return x.alt_m - (terrain ? terrain->elevation_m(x.lat_deg, x.lon_deg) : 0.0);
}

}  // namespace

WeaponStepResult advance_weapon(WeaponType type, const WeaponParams& p, WeaponState& s, const GuidanceTarget& tgt,
                                double dt, const dyn::Terrain* terrain, double max_substep_s) {
  const int n = std::max(1, static_cast<int>(std::ceil(dt / std::max(max_substep_s, 1e-6) - 1e-9)));
  const double h = dt / n;
  for (int k = 0; k < n; ++k) {
    const double tau0 = k * h;
    Vec3 r{}, vt{};
    if (tgt.valid) {
      vt = tgt.vel_ned;
      r = ned_between(s.pos, tgt.pos) + tau0 * vt;
    }
    const Vec3 a = accel(type, p, s, tgt.valid, r, vt);
    const Vec3 v0 = s.vel_ned;
    auto disp = [&](double t) { return t * v0 + (0.5 * t * t) * a; };

    // 근접 신관: 지정 표적(또는 조준점)과의 최근접점을 부 스텝 안에서 찾는다
    double t_prox = -1.0;
    if (tgt.valid && s.t_flight_s >= p.arm_time_s) {
      const Vec3 w = v0 + (0.5 * h) * a - vt;
      const double ww = dot(w, w);
      const double ts = ww > 0.0 ? std::clamp(dot(r, w) / ww, 0.0, h) : 0.0;
      if (norm(disp(ts) - (r + ts * vt)) <= p.proximity_m) t_prox = ts;
    }
    // 지면 교차: 끝점이 지면 아래면 이분법으로 교차 시점을 찾는다 (DEC-005)
    double t_ground = -1.0;
    if (ground_clearance(offset(s.pos, disp(h)), terrain) <= 0.0) {
      double lo = 0.0, hi = h;
      if (ground_clearance(s.pos, terrain) <= 0.0) {
        hi = 0.0;
      } else {
        for (int it = 0; it < 48; ++it) {
          const double mid = 0.5 * (lo + hi);
          (ground_clearance(offset(s.pos, disp(mid)), terrain) > 0.0 ? lo : hi) = mid;
        }
      }
      t_ground = hi;
    }
    if (t_prox >= 0.0 || t_ground >= 0.0) {
      const bool prox_first = t_prox >= 0.0 && (t_ground < 0.0 || t_prox <= t_ground);
      const double te = prox_first ? t_prox : t_ground;
      s.pos = offset(s.pos, disp(te));
      s.vel_ned = v0 + te * a;
      s.t_flight_s += te;
      return {prox_first ? StepEnd::kProximity : StepEnd::kGround, tau0 + te};
    }
    s.pos = offset(s.pos, disp(h));
    s.vel_ned = v0 + h * a;
    if (type == WeaponType::kFpv) s.vel_ned = limit(s.vel_ned, p.max_speed_mps);
    s.t_flight_s += h;
    if (s.t_flight_s >= p.max_flight_time_s - 1e-9) return {StepEnd::kExpired, tau0 + h};
  }
  return {StepEnd::kFlying, dt};
}

}  // namespace swarm::payload
