// IMP-PAY-003: 센서(PO) FOV·거리·가시선 탐지, SENSOR 고장 (DEC-018, DEC-047, REQ-PAY-002)
// IMP-PAY-004: 재머(EA)·jammer_site 재밍 구역과 JamZone 이벤트 (DEC-009, DEC-028, DEC-030, REQ-PAY-003)
// IMP-PAY-006: Strike·Store 발사 판정, 잔량, 탄착·살상반경 파괴 (DEC-012, DEC-019, REQ-PAY-004, REQ-PAY-005)
// IMP-PAY-007: 프레임 계산기. 결정적 순서와 출력 조립 (DEC-046, REQ-SIM-001)
#include "swarm/payload/payload.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <stdexcept>

#include "swarm/dyn/geo.hpp"

namespace swarm::payload {

namespace geo = swarm::dyn::geo;

std::string_view event_kind(const v1::TruthEvent& ev) {
  switch (ev.event_case()) {
    case v1::TruthEvent::kLaunch: return "launch";
    case v1::TruthEvent::kImpact: return "impact";
    case v1::TruthEvent::kKill: return "kill";
    case v1::TruthEvent::kJamZone: return "jam_zone";
    case v1::TruthEvent::kSpawn: return "spawn";
    default: return "";
  }
}

namespace {

enum class Cat { kCamera, kJammer, kWeapon };
enum class PointMode { kBody, kGeo, kTrack };

struct Station {
  v1::PayloadSpec spec;
  ParamMap params;
  Cat cat = Cat::kCamera;
  WeaponType wtype = WeaponType::kAam;
  WeaponParams wp;
  // 실행 상태
  std::uint32_t count = 0;
  bool enabled = false;
  std::string corr;
  bool cmd_this_frame = false;
  // 카메라 지향
  PointMode pmode = PointMode::kBody;
  double az_deg = 0.0, el_deg = 0.0;
  Geo geo_point;
  std::string track;
  bool has_last = false;
  Vec3 last_ned;
  // 재머
  double radius_m = 0.0;
  bool zone_active = false;  // 마지막으로 낸 JamZone 상태
  Geo zone_center;
  double zone_radius = 0.0;
};

struct Carrier {
  std::string id;
  v1::EntityKind kind = v1::ENTITY_KIND_UNSPECIFIED;
  std::vector<Station> st;  // payload_id 순
  std::uint32_t next_seq = 1;
  bool loadout_dirty = true;
};

struct Weapon {
  std::string id, shooter, station, target;
  WeaponType type = WeaponType::kAam;
  WeaponParams p;
  v1::Side side = v1::SIDE_UNSPECIFIED;
  WeaponState s;
  bool alive = true;
  GuidanceTarget last;  // 표적이 사라지면 마지막 위치로 좌표 유도
};

struct Body {
  std::string id;
  v1::EntityKind kind = v1::ENTITY_KIND_UNSPECIFIED;
  v1::Side side = v1::SIDE_UNSPECIFIED;
  Geo pos;
  Vec3 vel;
  double quat[4] = {1.0, 0.0, 0.0, 0.0};
  bool alive = true;
  bool weapon = false;
  bool sensor_fault = false;
};

Geo to_geo(const v1::Geodetic& g) { return {g.lat_deg(), g.lon_deg(), g.alt_m()}; }
void put_geo(const Geo& g, v1::Geodetic* out) {
  out->set_lat_deg(g.lat_deg);
  out->set_lon_deg(g.lon_deg);
  out->set_alt_m(g.alt_m);
}
void put_vec(Vec3 v, v1::Vec3* out) {
  out->set_x(v.x);
  out->set_y(v.y);
  out->set_z(v.z);
}
void put_header(v1::Header* h, std::uint64_t t_us, std::uint64_t frame, const std::string& src,
                const std::string& corr = {}) {
  h->set_sim_time_us(t_us);
  h->set_frame(frame);
  h->set_source(src);
  if (!corr.empty()) h->set_correlation_id(corr);
}

Cat category(const std::string& type, WeaponType& wt) {
  if (type == "camera") return Cat::kCamera;
  if (type == "jammer") return Cat::kJammer;
  if (type == "aam_short") { wt = WeaponType::kAam; return Cat::kWeapon; }
  if (type == "agm_short") { wt = WeaponType::kAgm; return Cat::kWeapon; }
  if (type == "fpv") { wt = WeaponType::kFpv; return Cat::kWeapon; }
  throw std::invalid_argument("payload: unknown type '" + type + "'");
}

double angle_deg(Vec3 a, Vec3 b) {
  return std::acos(std::clamp(dot(unit(a), unit(b)), -1.0, 1.0)) * geo::kRadToDeg;
}

}  // namespace

struct PayloadSystem::Impl {
  LosFn los;
  const dyn::Terrain* terrain = nullptr;
  Options opt;
  std::map<std::string, Carrier> carriers0, carriers;
  std::set<std::string> scenario_ids;
  std::set<std::string> spawned_ids;  // owns() 판정. reset까지 유지
  std::map<std::string, Weapon> weapons;
  std::set<std::string> killed;
  std::uint64_t step_count = 0;

  bool visible(const Geo& a, const Geo& b) const { return !los || los(a, b); }

  // 프레임 단위 작업 상태
  std::uint64_t t_us = 0, frame = 0;
  std::map<std::string, Body> bodies;
  std::map<std::string, OnboardOutput> ob;
  FrameOutput* out = nullptr;
  std::uint64_t ev_seq = 0;
  std::vector<std::pair<std::uint64_t, std::uint64_t>> ev_order;  // (시각, 생성 순)

  OnboardOutput& onboard(const std::string& id) {
    auto& o = ob[id];
    o.entity = id;
    return o;
  }
  bool body_alive(const std::string& id) const {
    auto it = bodies.find(id);
    return it != bodies.end() && it->second.alive;
  }
  v1::TruthEvent& event(std::uint64_t at_us, const std::string& src) {
    out->events.emplace_back();
    ev_order.emplace_back(at_us, ev_seq++);
    put_header(out->events.back().mutable_header(), at_us, frame, src);
    return out->events.back();
  }

  void fill_weapon_state(const Weapon& w, v1::EntityState& e) const {
    e.set_id(w.id);
    e.set_kind(w.type == WeaponType::kFpv ? v1::ENTITY_KIND_FPV : v1::ENTITY_KIND_MISSILE);
    e.set_side(w.side);
    e.set_alive(w.alive);
    e.set_energy_frac(w.p.max_flight_time_s > 0.0
                          ? std::clamp(1.0 - w.s.t_flight_s / w.p.max_flight_time_s, 0.0, 1.0)
                          : 0.0);
    auto* k = e.mutable_kinematics();
    put_geo(w.s.pos, k->mutable_position());
    put_vec(w.s.vel_ned, k->mutable_velocity_ned_mps());
    const Vec3 v = w.s.vel_ned;
    const double yaw = std::atan2(v.y, v.x);
    const double pitch = std::atan2(-v.z, std::hypot(v.x, v.y));
    double q[4];
    geo::euler_to_quat(yaw, pitch, 0.0, q);
    auto* qa = k->mutable_attitude();
    qa->set_w(q[0]);
    qa->set_x(q[1]);
    qa->set_y(q[2]);
    qa->set_z(q[3]);
    k->mutable_angular_rate_frd_rps();
  }

  void strike_activity(const std::string& shooter, const std::string& station, const std::string& weapon,
                       v1::StrikeState st, const std::string& reason, std::uint64_t at_us,
                       const std::string& corr = {}) {
    if (!body_alive(shooter)) return;
    auto& a = onboard(shooter).strike_activity.emplace_back();
    put_header(a.mutable_header(), at_us, frame, shooter, corr);
    a.set_payload_id(station);
    a.set_weapon_entity(weapon);
    a.set_state(st);
    a.set_reason(reason);
  }

  Station* find_station(const std::string& entity, const std::string& pid) {
    auto it = carriers.find(entity);
    if (it == carriers.end()) return nullptr;
    for (auto& s : it->second.st)
      if (s.spec.id() == pid) return &s;
    return nullptr;
  }

  void on_sensor_cmd(const Addressed<v1::SensorCommand>& c) {
    if (!body_alive(c.entity)) return;
    Station* s = find_station(c.entity, c.msg.payload_id());
    if (!s || s->cat != Cat::kCamera) return;
    s->enabled = c.msg.enable();
    s->corr = c.msg.header().correlation_id();
    s->cmd_this_frame = true;
    if (!c.msg.has_pointing()) return;
    const auto& p = c.msg.pointing();
    switch (p.target_case()) {
      case v1::GimbalPointing::kAzElDeg:
        s->pmode = PointMode::kBody;
        s->az_deg = p.az_el_deg().x();
        s->el_deg = p.az_el_deg().y();
        break;
      case v1::GimbalPointing::kGeoPoint:
        s->pmode = PointMode::kGeo;
        s->geo_point = to_geo(p.geo_point());
        break;
      case v1::GimbalPointing::kTrackEntity:
        s->pmode = PointMode::kTrack;
        s->track = p.track_entity();
        break;
      default: break;
    }
  }

  void on_jammer_cmd(const Addressed<v1::JammerCommand>& c) {
    if (!body_alive(c.entity)) return;
    Station* s = find_station(c.entity, c.msg.payload_id());
    if (!s || s->cat != Cat::kJammer) return;
    s->enabled = c.msg.enable();
    const double max_r = need(s->params, "max_radius_m");
    s->radius_m = c.msg.radius_m() > 0.0 ? std::min(c.msg.radius_m(), max_r) : need(s->params, "radius_m");
    s->corr = c.msg.header().correlation_id();
    s->cmd_this_frame = true;
  }

  std::string next_weapon_id(Carrier& c) {
    for (;;) {
      char buf[16];
      std::snprintf(buf, sizeof(buf), "%02u", c.next_seq++);
      std::string id = "wpn-" + c.id + "-" + buf;
      if (!scenario_ids.count(id) && !spawned_ids.count(id)) return id;
    }
  }

  void on_strike_cmd(const Addressed<v1::StrikeCommand>& c) {
    if (!body_alive(c.entity)) return;
    const std::string& pid = c.msg.payload_id();
    const std::string& corr = c.msg.header().correlation_id();
    auto reject = [&](const char* reason) {
      strike_activity(c.entity, pid, "", v1::STRIKE_STATE_REJECTED, reason, t_us, corr);
    };
    Station* s = find_station(c.entity, pid);
    if (!s) return reject("unknown_station");
    if (s->cat != Cat::kWeapon) return reject("not_a_weapon");
    if (s->count == 0) return reject("no_stores");
    const Body& sh = bodies.at(c.entity);
    const WeaponParams& p = s->wp;
    GuidanceTarget tgt;
    bool coordinate = false;
    if (!c.msg.target_id().empty()) {
      auto it = bodies.find(c.msg.target_id());
      if (it == bodies.end() || !it->second.alive || it->first == c.entity) return reject("unknown_target");
      const Vec3 r = ned_between(sh.pos, it->second.pos);
      const double range = norm(r);
      if (range > p.max_range_m) return reject("out_of_range");
      const Vec3 axis = frd_to_ned(sh.quat, az_el_to_frd(0.0, p.seeker_el_deg));
      const bool in_fov = p.seeker_fov_deg >= 360.0 || angle_deg(axis, r) <= 0.5 * p.seeker_fov_deg;
      if (range > p.lock_range_m || !in_fov || !visible(sh.pos, it->second.pos)) return reject("lock_failed");
      tgt = {true, it->second.pos, it->second.vel};
    } else if (c.msg.has_aim_point()) {
      if (s->wtype == WeaponType::kAam) return reject("no_target");
      const Geo aim = to_geo(c.msg.aim_point());
      if (distance_m(sh.pos, aim) > p.max_range_m) return reject("out_of_range");
      tgt = {true, aim, {}};
      coordinate = true;
    } else {
      return reject("no_target");
    }
    Carrier& car = carriers.at(c.entity);
    --s->count;
    car.loadout_dirty = true;
    Weapon w;
    w.id = next_weapon_id(car);
    w.shooter = c.entity;
    w.station = pid;
    w.target = c.msg.target_id();
    w.type = s->wtype;
    w.p = p;
    w.side = sh.side;
    w.s.pos = sh.pos;
    w.s.vel_ned = sh.vel + p.launch_speed_mps * frd_to_ned(sh.quat, {1.0, 0.0, 0.0});
    w.s.coordinate_mode = coordinate;
    w.last = tgt;
    spawned_ids.insert(w.id);

    strike_activity(c.entity, pid, w.id, v1::STRIKE_STATE_LAUNCHED, "", t_us, corr);
    auto& le = *event(t_us, c.entity).mutable_launch();
    le.set_shooter(c.entity);
    le.set_weapon_entity(w.id);
    le.set_target_id(w.target);
    auto& sp = *event(t_us, c.entity).mutable_spawn();
    fill_weapon_state(w, *sp.mutable_entity());
    out->spawned.push_back(sp.entity());
    weapons.emplace(w.id, std::move(w));
  }

  // 카메라 시선 (NED 단위 벡터)
  Vec3 boresight(Station& s, const Body& b) {
    Vec3 f;
    if (s.pmode == PointMode::kGeo) {
      f = unit(ned_between(b.pos, s.geo_point));
    } else if (s.pmode == PointMode::kTrack && body_alive(s.track) && s.track != b.id) {
      f = unit(ned_between(b.pos, bodies.at(s.track).pos));
    } else if (s.pmode == PointMode::kTrack && s.has_last) {
      f = s.last_ned;
    } else {
      f = unit(frd_to_ned(b.quat, az_el_to_frd(s.az_deg, s.el_deg)));
    }
    s.last_ned = f;
    s.has_last = true;
    return f;
  }

  void run_sensors(bool periodic) {
    for (auto& [id, car] : carriers) {
      if (!body_alive(id)) continue;
      const Body& b = bodies.at(id);
      for (auto& s : car.st) {
        if (s.cat != Cat::kCamera) continue;
        const double hfov = need(s.params, "hfov_deg"), vfov = need(s.params, "vfov_deg");
        const double max_r = need(s.params, "max_range_m");
        const Vec3 f = boresight(s, b);
        const bool active = s.enabled && !b.sensor_fault;  // DEC-047
        if (periodic || s.cmd_this_frame) {
          auto& a = onboard(id).sensor_activity.emplace_back();
          put_header(a.mutable_header(), t_us, frame, id, s.corr);
          a.set_payload_id(s.spec.id());
          a.set_active(active);
          put_vec(f, a.mutable_boresight_ned());
          a.set_hfov_deg(hfov);
          a.set_vfov_deg(vfov);
          a.set_max_range_m(max_r);
        }
        if (!active) continue;
        // 카메라 좌표: 전방 f, 오른쪽 r(수평 유지), 아래 d
        Vec3 right = cross({0.0, 0.0, 1.0}, f);
        if (norm(right) < 1e-6) right = frd_to_ned(b.quat, {0.0, 1.0, 0.0});
        right = unit(right - dot(right, f) * f, {0.0, 1.0, 0.0});
        const Vec3 down = cross(f, right);
        for (const auto& [tid, t] : bodies) {
          if (tid == id || !t.alive) continue;
          const Vec3 v = ned_between(b.pos, t.pos);
          const double range = norm(v);
          if (range > max_r || range < 1e-6) continue;
          const double fx = dot(v, f);
          if (fx <= 0.0) continue;
          const double h = std::atan2(dot(v, right), fx) * geo::kRadToDeg;
          const double e = std::atan2(dot(v, down), fx) * geo::kRadToDeg;
          if (std::abs(h) > 0.5 * hfov || std::abs(e) > 0.5 * vfov) continue;
          if (!visible(b.pos, t.pos)) continue;
          auto& d = onboard(id).detections.emplace_back();
          put_header(d.mutable_header(), t_us, frame, id, s.corr);
          d.set_payload_id(s.spec.id());
          d.set_target_id(tid);
          d.set_kind(t.kind);
          d.set_side(t.side);
          put_geo(t.pos, d.mutable_position());
          put_vec(t.vel, d.mutable_velocity_ned_mps());
          d.set_range_m(range);
        }
      }
    }
  }

  void kill_at(const Geo& det, double radius, double tau, const std::string& self,
               std::vector<std::string>& killed_now) {
    for (auto& [id, b] : bodies) {
      if (!b.alive || id == self) continue;
      Geo p = b.pos;
      if (b.weapon) {
        p = weapons.at(id).s.pos;
      } else {
        p = offset(b.pos, tau * b.vel);
      }
      if (distance_m(det, p) <= radius) killed_now.push_back(id);
    }
  }

  void run_weapons(double dt, std::map<std::string, std::uint64_t>& kill_time) {
    for (auto& [wid, w] : weapons) {
      if (!w.alive) continue;
      GuidanceTarget tgt = w.last;
      if (!w.target.empty()) {
        if (body_alive(w.target)) {
          const Body& t = bodies.at(w.target);
          tgt = {true, t.pos, t.vel};
          w.last = tgt;
        } else {
          w.s.coordinate_mode = true;  // 표적 소실: 마지막 위치로 좌표 유도
          tgt = {w.last.valid, w.last.pos, {}};
        }
      }
      const WeaponStepResult r = advance_weapon(w.type, w.p, w.s, tgt, dt, terrain, opt.max_substep_s);
      if (r.end == StepEnd::kFlying) continue;
      const std::uint64_t at = t_us + static_cast<std::uint64_t>(std::llround(r.tau_s * 1e6));
      w.alive = false;
      bodies[wid].alive = false;
      if (r.end == StepEnd::kExpired) {
        strike_activity(w.shooter, w.station, wid, v1::STRIKE_STATE_MISSED, "expired", at);
        continue;
      }
      std::vector<std::string> killed_now;
      kill_at(w.s.pos, w.p.lethal_radius_m, r.tau_s, wid, killed_now);
      auto& im = *event(at, wid).mutable_impact();
      im.set_weapon_entity(wid);
      put_geo(w.s.pos, im.mutable_position());
      im.set_lethal_radius_m(w.p.lethal_radius_m);
      for (const auto& k : killed_now) im.add_killed(k);
      strike_activity(w.shooter, w.station, wid, v1::STRIKE_STATE_IMPACT,
                      r.end == StepEnd::kGround ? "ground" : "proximity", at);
      for (const auto& k : killed_now) {
        auto& ke = *event(at, wid).mutable_kill();
        ke.set_entity_id(k);
        ke.set_cause("impact");
        Body& kb = bodies.at(k);
        kb.alive = false;
        if (kb.weapon) {
          Weapon& o = weapons.at(k);
          if (o.alive) strike_activity(o.shooter, o.station, k, v1::STRIKE_STATE_MISSED, "destroyed", at);
          o.alive = false;
        } else {
          killed.insert(k);
          out->killed.push_back(k);
          kill_time[k] = at;
        }
      }
    }
  }

  void run_jammers(bool periodic, const std::map<std::string, std::uint64_t>& kill_time) {
    for (auto& [id, car] : carriers) {
      auto bit = bodies.find(id);
      const bool alive = bit != bodies.end() && bit->second.alive;
      for (auto& s : car.st) {
        if (s.cat != Cat::kJammer) continue;
        const bool active = alive && s.enabled;
        Geo center = alive ? bit->second.pos : s.zone_center;
        bool emit = active != s.zone_active;
        if (active && s.zone_active)
          emit = s.radius_m != s.zone_radius ||
                 distance_m(center, s.zone_center) > need(s.params, "update_distance_m");
        if (emit) {
          auto kt = kill_time.find(id);
          const std::uint64_t at = kt != kill_time.end() ? kt->second : t_us;
          auto& jz = *event(at, id).mutable_jam_zone();
          jz.set_owner(id);
          jz.set_active(active);
          auto* area = jz.mutable_area();
          put_geo(center, area->mutable_circle()->mutable_center());
          area->mutable_circle()->set_radius_m(s.radius_m);
          area->set_min_alt_m(need(s.params, "min_alt_m"));
          area->set_max_alt_m(need(s.params, "max_alt_m"));
          *jz.mutable_zone() = area->circle();  // 폐기 예정 필드도 채운다 (DEC-030)
          s.zone_active = active;
          s.zone_center = center;
          s.zone_radius = s.radius_m;
        }
        if (alive && (periodic || s.cmd_this_frame)) {
          auto& a = onboard(id).jammer_activity.emplace_back();
          put_header(a.mutable_header(), t_us, frame, id, s.corr);
          a.set_payload_id(s.spec.id());
          a.set_active(active);
          put_geo(center, a.mutable_zone()->mutable_center());
          a.mutable_zone()->set_radius_m(s.radius_m);
        }
      }
    }
  }
};

PayloadSystem::PayloadSystem(const ProfileLibrary& lib, const std::vector<v1::EntitySpec>& specs, LosFn los,
                             const dyn::Terrain* terrain, Options opt)
    : impl_(std::make_unique<Impl>()) {
  impl_->los = std::move(los);
  impl_->terrain = terrain;
  impl_->opt = opt;
  if (impl_->opt.activity_period_frames == 0) impl_->opt.activity_period_frames = 1;
  for (const auto& e : specs) {
    impl_->scenario_ids.insert(e.id());
    std::vector<v1::PayloadSpec> pays(e.payloads().begin(), e.payloads().end());
    if (e.kind() == v1::ENTITY_KIND_JAMMER_SITE &&
        std::none_of(pays.begin(), pays.end(), [](const auto& p) { return p.type() == "jammer"; })) {
      v1::PayloadSpec j;
      j.set_id("jam0");
      j.set_type("jammer");
      j.set_profile("site_generic");
      pays.push_back(j);
    }
    if (pays.empty()) continue;
    Carrier c;
    c.id = e.id();
    c.kind = e.kind();
    int jammers = 0;
    for (const auto& p : pays) {
      Station s;
      s.spec = p;
      s.cat = category(p.type(), s.wtype);
      s.params = lib.resolve(p);
      s.count = p.count();
      if (s.cat == Cat::kCamera) {
        s.enabled = need(s.params, "default_enabled") != 0.0;
        s.az_deg = need(s.params, "default_az_deg");
        s.el_deg = need(s.params, "default_el_deg");
        need(s.params, "hfov_deg");
        need(s.params, "vfov_deg");
        need(s.params, "max_range_m");
      } else if (s.cat == Cat::kJammer) {
        ++jammers;
        // jammer_site는 런타임이 없어 처음부터 켠다
        s.enabled = e.kind() == v1::ENTITY_KIND_JAMMER_SITE || need(s.params, "default_enabled") != 0.0;
        s.radius_m = std::min(need(s.params, "radius_m"), need(s.params, "max_radius_m"));
        for (const char* k : {"min_alt_m", "max_alt_m", "update_distance_m"}) need(s.params, k);
      } else {
        s.wp = WeaponParams::from(s.wtype, s.params);
      }
      c.st.push_back(std::move(s));
    }
    // JamZoneEvent.owner는 엔티티 ID다. 엔티티당 재머 하나만 받는다
    if (jammers > 1) throw std::invalid_argument("payload " + e.id() + ": more than one jammer");
    std::sort(c.st.begin(), c.st.end(), [](const Station& a, const Station& b) { return a.spec.id() < b.spec.id(); });
    for (std::size_t i = 1; i < c.st.size(); ++i)
      if (c.st[i].spec.id() == c.st[i - 1].spec.id())
        throw std::invalid_argument("payload " + e.id() + ": duplicate payload id '" + c.st[i].spec.id() + "'");
    impl_->carriers0[c.id] = std::move(c);
  }
  reset();
}

PayloadSystem::~PayloadSystem() = default;

void PayloadSystem::reset() {
  impl_->carriers = impl_->carriers0;
  impl_->weapons.clear();
  impl_->spawned_ids.clear();
  impl_->killed.clear();
  impl_->step_count = 0;
}

bool PayloadSystem::owns(const std::string& id) const { return impl_->spawned_ids.count(id) != 0; }

std::vector<v1::PayloadSpec> PayloadSystem::loadout(const std::string& id) const {
  std::vector<v1::PayloadSpec> out;
  auto it = impl_->carriers.find(id);
  if (it == impl_->carriers.end()) return out;
  for (const auto& s : it->second.st) {
    out.push_back(s.spec);
    out.back().set_count(s.count);
  }
  return out;
}

const ParamMap* PayloadSystem::params(const std::string& entity, const std::string& pid) const {
  auto it = impl_->carriers.find(entity);
  if (it == impl_->carriers.end()) return nullptr;
  for (const auto& s : it->second.st)
    if (s.spec.id() == pid) return &s.params;
  return nullptr;
}

FrameOutput PayloadSystem::step(const FrameInput& in) {
  Impl& m = *impl_;
  FrameOutput out;
  m.out = &out;
  m.t_us = in.t_us;
  m.frame = in.frame;
  m.ob.clear();
  m.bodies.clear();
  m.ev_seq = 0;
  m.ev_order.clear();
  const bool periodic = m.step_count % m.opt.activity_period_frames == 0;

  // 1. 엔티티 (무장은 내부 상태를 쓴다)
  for (const auto& e : in.entities) {
    const auto& st = e.state;
    if (m.spawned_ids.count(st.id())) continue;
    Body b;
    b.id = st.id();
    b.kind = st.kind();
    b.side = st.side();
    b.pos = to_geo(st.kinematics().position());
    const auto& v = st.kinematics().velocity_ned_mps();
    b.vel = {v.x(), v.y(), v.z()};
    if (st.kinematics().has_attitude()) {
      const auto& q = st.kinematics().attitude();
      b.quat[0] = q.w();
      b.quat[1] = q.x();
      b.quat[2] = q.y();
      b.quat[3] = q.z();
    }
    b.alive = st.alive() && !m.killed.count(b.id);
    b.sensor_fault = e.sensor_fault;
    m.bodies[b.id] = std::move(b);
  }
  for (auto& [id, car] : m.carriers)
    for (auto& s : car.st) s.cmd_this_frame = false;

  // 2. 명령: 엔티티 ID 순, 같은 엔티티 안에서는 받은 순서
  auto by_entity = [](const auto& a, const auto& b) { return a.entity < b.entity; };
  auto sensor_cmds = in.sensor_cmds;
  auto jammer_cmds = in.jammer_cmds;
  auto strike_cmds = in.strike_cmds;
  std::stable_sort(sensor_cmds.begin(), sensor_cmds.end(), by_entity);
  std::stable_sort(jammer_cmds.begin(), jammer_cmds.end(), by_entity);
  std::stable_sort(strike_cmds.begin(), strike_cmds.end(), by_entity);
  for (const auto& c : sensor_cmds) m.on_sensor_cmd(c);
  for (const auto& c : jammer_cmds) m.on_jammer_cmd(c);
  for (const auto& c : strike_cmds) m.on_strike_cmd(c);

  // 3. 무장도 탐지·피격 대상이다
  for (const auto& [id, w] : m.weapons) {
    Body b;
    b.id = id;
    b.kind = w.type == WeaponType::kFpv ? v1::ENTITY_KIND_FPV : v1::ENTITY_KIND_MISSILE;
    b.side = w.side;
    b.pos = w.s.pos;
    b.vel = w.s.vel_ned;
    b.alive = w.alive;
    b.weapon = true;
    m.bodies[id] = std::move(b);
  }

  // 4. 센서 (t_us 상태)
  m.run_sensors(periodic);

  // 5. 무장 t_us → t_us + dt, 탄착·살상반경
  std::map<std::string, std::uint64_t> kill_time;
  m.run_weapons(in.dt_s, kill_time);

  // 6. 재머 (이번 프레임 파괴를 반영)
  m.run_jammers(periodic, kill_time);

  // 7. 탑재 구성
  for (auto& [id, car] : m.carriers) {
    if (!car.loadout_dirty || !m.body_alive(id)) continue;
    car.loadout_dirty = false;
    auto& lo = m.onboard(id).loadout.emplace();
    put_header(lo.mutable_header(), m.t_us, m.frame, id);
    for (const auto& p : loadout(id)) *lo.add_stores() = p;
  }

  // 8. 출력 조립
  for (auto& [id, o] : m.ob) out.onboard.push_back(std::move(o));
  for (auto it = m.weapons.begin(); it != m.weapons.end();) {
    m.fill_weapon_state(it->second, out.weapons.emplace_back());
    it = it->second.alive ? std::next(it) : m.weapons.erase(it);
  }
  std::sort(out.killed.begin(), out.killed.end());
  {
    std::vector<std::size_t> idx(out.events.size());
    for (std::size_t i = 0; i < idx.size(); ++i) idx[i] = i;
    std::stable_sort(idx.begin(), idx.end(), [&](std::size_t a, std::size_t b) { return m.ev_order[a] < m.ev_order[b]; });
    std::vector<v1::TruthEvent> sorted;
    sorted.reserve(idx.size());
    for (auto i : idx) sorted.push_back(std::move(out.events[i]));
    out.events = std::move(sorted);
  }
  ++m.step_count;
  m.out = nullptr;
  return out;
}

}  // namespace swarm::payload
