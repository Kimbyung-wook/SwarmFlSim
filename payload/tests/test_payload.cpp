// TC-PAY-001~018: 임무장비·무장 계산기 시험. 인자로 TC ID를 받아 해당 시험만 실행한다
#include <algorithm>
#include <chrono>
#include <optional>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

#include <google/protobuf/io/coded_stream.h>
#include <google/protobuf/io/zero_copy_stream_impl_lite.h>

#include "swarm/dyn/geo.hpp"
#include "swarm/dyn/terrain.hpp"
#include "swarm/payload/payload.hpp"

using namespace swarm::payload;
namespace v1 = swarm::v1;
namespace geo = swarm::dyn::geo;

namespace {

int g_failures = 0;

void check(bool cond, const char* what) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}

void check_near(double got, double want, double tol, const char* what) {
  if (!(std::abs(got - want) <= tol)) {
    std::fprintf(stderr, "FAIL: %s: got %.12g want %.12g (tol %.3g)\n", what, got, want, tol);
    ++g_failures;
  }
}

const Geo kOrigin{37.5, 127.0, 1000.0};
constexpr double kDt = 0.02;
constexpr std::uint64_t kDtUs = 20000;

// ---- 시나리오 구성 도우미 ----

v1::PayloadSpec pay(const std::string& id, const std::string& type, std::uint32_t count = 0,
                    std::vector<std::pair<std::string, double>> ov = {}) {
  v1::PayloadSpec p;
  p.set_id(id);
  p.set_type(type);
  p.set_count(count);
  for (auto& [k, v] : ov) (*p.mutable_overrides()->mutable_fields())[k].set_number_value(v);
  return p;
}

v1::EntitySpec spec(const std::string& id, v1::EntityKind kind, std::vector<v1::PayloadSpec> pays = {}) {
  v1::EntitySpec e;
  e.set_id(id);
  e.set_kind(kind);
  for (auto& p : pays) *e.add_payloads() = p;
  return e;
}

struct Ent {
  std::string id;
  v1::EntityKind kind = v1::ENTITY_KIND_UAV;
  v1::Side side = v1::SIDE_BLUE;
  Geo pos;
  Vec3 vel;
  double yaw_deg = 0.0;
  bool alive = true;
  bool fault = false;
};

EntityInput to_input(const Ent& e) {
  EntityInput in;
  auto& s = in.state;
  s.set_id(e.id);
  s.set_kind(e.kind);
  s.set_side(e.side);
  s.set_alive(e.alive);
  auto* k = s.mutable_kinematics();
  k->mutable_position()->set_lat_deg(e.pos.lat_deg);
  k->mutable_position()->set_lon_deg(e.pos.lon_deg);
  k->mutable_position()->set_alt_m(e.pos.alt_m);
  k->mutable_velocity_ned_mps()->set_x(e.vel.x);
  k->mutable_velocity_ned_mps()->set_y(e.vel.y);
  k->mutable_velocity_ned_mps()->set_z(e.vel.z);
  double q[4];
  geo::euler_to_quat(e.yaw_deg * geo::kDegToRad, 0.0, 0.0, q);
  k->mutable_attitude()->set_w(q[0]);
  k->mutable_attitude()->set_x(q[1]);
  k->mutable_attitude()->set_y(q[2]);
  k->mutable_attitude()->set_z(q[3]);
  in.sensor_fault = e.fault;
  return in;
}

// az: 북에서 시계방향(도), 수평 거리 d, 고도 차 dz(위 +)
Geo at(const Geo& from, double az_deg, double d, double dz = 0.0) {
  const double a = az_deg * geo::kDegToRad;
  return offset(from, {d * std::cos(a), d * std::sin(a), -dz});
}

FrameInput frame_in(std::uint64_t frame, const std::vector<Ent>& ents) {
  FrameInput in;
  in.frame = frame;
  in.t_us = frame * kDtUs;
  in.dt_s = kDt;
  for (const auto& e : ents) in.entities.push_back(to_input(e));
  return in;
}

const OnboardOutput* find_ob(const FrameOutput& o, const std::string& id) {
  for (const auto& x : o.onboard)
    if (x.entity == id) return &x;
  return nullptr;
}

bool detected(const FrameOutput& o, const std::string& by, const std::string& target) {
  const auto* ob = find_ob(o, by);
  if (!ob) return false;
  return std::any_of(ob->detections.begin(), ob->detections.end(),
                     [&](const v1::Detection& d) { return d.target_id() == target; });
}

std::vector<const v1::StrikeActivity*> strikes(const FrameOutput& o, const std::string& id) {
  std::vector<const v1::StrikeActivity*> r;
  if (const auto* ob = find_ob(o, id))
    for (const auto& a : ob->strike_activity) r.push_back(&a);
  return r;
}

std::vector<const v1::TruthEvent*> events_of(const FrameOutput& o, std::string_view kind) {
  std::vector<const v1::TruthEvent*> r;
  for (const auto& e : o.events)
    if (event_kind(e) == kind) r.push_back(&e);
  return r;
}

Addressed<v1::StrikeCommand> strike_target(const std::string& shooter, const std::string& pid, const std::string& tgt) {
  Addressed<v1::StrikeCommand> c;
  c.entity = shooter;
  c.msg.set_payload_id(pid);
  c.msg.set_target_id(tgt);
  c.msg.mutable_header()->set_correlation_id("c-" + tgt);
  return c;
}

Addressed<v1::StrikeCommand> strike_point(const std::string& shooter, const std::string& pid, const Geo& g) {
  Addressed<v1::StrikeCommand> c;
  c.entity = shooter;
  c.msg.set_payload_id(pid);
  c.msg.mutable_aim_point()->set_lat_deg(g.lat_deg);
  c.msg.mutable_aim_point()->set_lon_deg(g.lon_deg);
  c.msg.mutable_aim_point()->set_alt_m(g.alt_m);
  return c;
}

// 표적을 등속으로 옮기며 무장이 끝날 때까지 돌린다. 끝난 프레임의 출력을 모은다
struct RunResult {
  bool launched = false;
  bool ended = false;
  v1::StrikeState end_state = v1::STRIKE_STATE_UNSPECIFIED;
  std::string end_reason;
  std::uint64_t end_frame = 0;
  std::vector<std::string> killed;
  std::vector<v1::TruthEvent> events;
  v1::EntityState last_weapon;
};

RunResult fly(PayloadSystem& ps, std::vector<Ent> ents, const Addressed<v1::StrikeCommand>& cmd,
              std::uint64_t max_frames) {
  RunResult rr;
  for (std::uint64_t f = 0; f < max_frames; ++f) {
    FrameInput in = frame_in(f, ents);
    if (f == 0) in.strike_cmds.push_back(cmd);
    const FrameOutput o = ps.step(in);
    for (const auto& e : o.events) rr.events.push_back(e);
    for (const auto& k : o.killed) rr.killed.push_back(k);
    if (!o.weapons.empty()) rr.last_weapon = o.weapons.back();
    for (const auto* a : strikes(o, cmd.entity)) {
      if (a->state() == v1::STRIKE_STATE_LAUNCHED) rr.launched = true;
      if (a->state() == v1::STRIKE_STATE_IMPACT || a->state() == v1::STRIKE_STATE_MISSED ||
          a->state() == v1::STRIKE_STATE_REJECTED) {
        rr.ended = true;
        rr.end_state = a->state();
        rr.end_reason = a->reason();
        rr.end_frame = f;
      }
    }
    if (rr.ended) return rr;
    for (auto& e : ents) {
      if (std::find(o.killed.begin(), o.killed.end(), e.id) != o.killed.end()) e.alive = false;
      e.pos = offset(e.pos, kDt * e.vel);
    }
  }
  return rr;
}

bool contains(const std::vector<std::string>& v, const std::string& s) {
  return std::find(v.begin(), v.end(), s) != v.end();
}

// 시야 시험용 카메라: 고각 0, hfov 60, vfov 40, 거리 3000
std::vector<v1::EntitySpec> cam_specs() {
  return {spec("uav-001", v1::ENTITY_KIND_UAV,
               {pay("cam0", "camera", 0, {{"default_el_deg", 0.0}, {"hfov_deg", 60.0}, {"vfov_deg", 40.0}})}),
          spec("tgt-a", v1::ENTITY_KIND_AIR_TARGET), spec("tgt-b", v1::ENTITY_KIND_AIR_TARGET)};
}

// ---- 시험 ----

// FOV 경계: 수평 반각 30°, 수직 반각 20°
void tc_001() {
  PayloadSystem ps(ProfileLibrary::builtin(), cam_specs(), nullptr, nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {}, 0.0};
  auto run = [&](Geo a, Geo b) {
    return ps.step(frame_in(0, {u, {"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, a},
                                {"tgt-b", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, b}}));
  };
  auto o = run(at(kOrigin, 29.8, 1000.0), at(kOrigin, 30.2, 1000.0));
  check(detected(o, "uav-001", "tgt-a"), "az 29.8 inside hfov");
  check(!detected(o, "uav-001", "tgt-b"), "az 30.2 outside hfov");
  o = run(at(kOrigin, -29.8, 1000.0), at(kOrigin, -30.2, 1000.0));
  check(detected(o, "uav-001", "tgt-a"), "az -29.8 inside hfov");
  check(!detected(o, "uav-001", "tgt-b"), "az -30.2 outside hfov");
  const double d = 1000.0;
  o = run(at(kOrigin, 0.0, d, d * std::tan(19.8 * geo::kDegToRad)),
          at(kOrigin, 0.0, d, -d * std::tan(20.2 * geo::kDegToRad)));
  check(detected(o, "uav-001", "tgt-a"), "el +19.8 inside vfov");
  check(!detected(o, "uav-001", "tgt-b"), "el -20.2 outside vfov");
  o = run(at(kOrigin, 180.0, 500.0), at(kOrigin, 90.0, 500.0));
  check(!detected(o, "uav-001", "tgt-a"), "behind not detected");
  // 기체 방위를 돌리면 시야도 돈다
  Ent u2 = u;
  u2.yaw_deg = 90.0;
  o = ps.step(frame_in(1, {u2, {"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 90.0, 800.0)}}));
  check(detected(o, "uav-001", "tgt-a"), "yaw 90 sees east");
  const auto* ob = find_ob(o, "uav-001");
  check(ob && ob->sensor_activity.size() == 1 && ob->sensor_activity[0].active(), "sensor activity active");
  if (ob && !ob->detections.empty()) {
    const auto& det = ob->detections[0];
    check(det.payload_id() == "cam0" && det.kind() == v1::ENTITY_KIND_AIR_TARGET && det.side() == v1::SIDE_RED,
          "detection fields");
    check_near(det.range_m(), 800.0, 0.5, "detection range");
    check(det.header().source() == "uav-001" && det.header().frame() == 1, "detection header");
  }
}

// 탐지 거리: max_range 3000 m
void tc_002() {
  PayloadSystem ps(ProfileLibrary::builtin(), cam_specs(), nullptr, nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin};
  const auto o = ps.step(frame_in(0, {u, {"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 2990.0)},
                                      {"tgt-b", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 3010.0)}}));
  check(detected(o, "uav-001", "tgt-a"), "2990 m detected");
  check(!detected(o, "uav-001", "tgt-b"), "3010 m not detected");
  // 재정의로 거리를 늘리면 보인다
  auto sp = cam_specs();
  (*sp[0].mutable_payloads(0)->mutable_overrides()->mutable_fields())["max_range_m"].set_number_value(4000.0);
  PayloadSystem ps2(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  const auto o2 = ps2.step(frame_in(0, {u, {"tgt-b", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 3010.0)}}));
  check(detected(o2, "uav-001", "tgt-b"), "override max_range 4000");
}

// 가시선: 능선 차폐 (DEM)
void tc_003() {
  swarm::dyn::GridSpec g;
  g.lat0_deg = 37.45;
  g.lon0_deg = 126.95;
  g.dlat_deg = 0.0005;
  g.dlon_deg = 0.0005;
  g.rows = 201;
  g.cols = 201;
  std::vector<float> h(g.rows * g.cols, 0.0f);
  // 북쪽 약 500 m(위도 +0.0045°)에 높이 2000 m 능선
  for (std::size_t r = 0; r < g.rows; ++r) {
    const double lat = g.lat0_deg + r * g.dlat_deg;
    if (lat > 37.5040 && lat < 37.5050)
      for (std::size_t c = 0; c < g.cols; ++c) h[r * g.cols + c] = 2000.0f;
  }
  const swarm::dyn::GridTerrain ridge(g, h);
  const swarm::dyn::FlatTerrain flat(0.0);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin};
  const Ent north{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 1000.0)};
  const Ent east{"tgt-b", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 25.0, 300.0)};
  {
    PayloadSystem ps(ProfileLibrary::builtin(), cam_specs(), make_terrain_los(flat), nullptr);
    const auto o = ps.step(frame_in(0, {u, north, east}));
    check(detected(o, "uav-001", "tgt-a"), "flat terrain: visible");
  }
  {
    PayloadSystem ps(ProfileLibrary::builtin(), cam_specs(), make_terrain_los(ridge), nullptr);
    const auto o = ps.step(frame_in(0, {u, north, east}));
    check(!detected(o, "uav-001", "tgt-a"), "ridge occludes");
    check(detected(o, "uav-001", "tgt-b"), "short of ridge: visible");
  }
  // 지면 위 표적(고도 = 지형): 끝점 허용오차로 보인다
  {
    auto sp = cam_specs();
    (*sp[0].mutable_payloads(0)->mutable_overrides()->mutable_fields())["default_el_deg"].set_number_value(-45.0);
    PayloadSystem ps(ProfileLibrary::builtin(), sp, make_terrain_los(flat), nullptr);
    Geo gnd = at(kOrigin, 0.0, 1000.0);
    gnd.alt_m = 0.0;
    const auto o = ps.step(frame_in(0, {u, {"tgt-a", v1::ENTITY_KIND_GROUND_TARGET, v1::SIDE_RED, gnd}}));
    check(detected(o, "uav-001", "tgt-a"), "ground target on flat terrain visible");
  }
}

// SENSOR 고장: 탐지 없음, active=false (DEC-047)
void tc_004() {
  PayloadSystem ps(ProfileLibrary::builtin(), cam_specs(), nullptr, nullptr);
  Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin};
  const Ent t{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 1000.0)};
  auto o = ps.step(frame_in(0, {u, t}));
  check(detected(o, "uav-001", "tgt-a"), "no fault: detected");
  u.fault = true;
  o = ps.step(frame_in(1, {u, t}));
  check(!detected(o, "uav-001", "tgt-a"), "fault: no detection");
  const auto* ob = find_ob(o, "uav-001");
  check(ob && ob->sensor_activity.size() == 1 && !ob->sensor_activity[0].active(), "fault: active=false");
  u.fault = false;
  o = ps.step(frame_in(2, {u, t}));
  check(detected(o, "uav-001", "tgt-a"), "fault cleared: detected");
  // 명령으로 끈 센서도 탐지하지 않는다
  Addressed<v1::SensorCommand> off;
  off.entity = "uav-001";
  off.msg.set_payload_id("cam0");
  off.msg.set_enable(false);
  off.msg.mutable_header()->set_correlation_id("c-off");
  FrameInput in = frame_in(3, {u, t});
  in.sensor_cmds.push_back(off);
  o = ps.step(in);
  ob = find_ob(o, "uav-001");
  check(!detected(o, "uav-001", "tgt-a"), "disabled: no detection");
  check(ob && ob->sensor_activity.size() == 1 && !ob->sensor_activity[0].active() &&
            ob->sensor_activity[0].header().correlation_id() == "c-off",
        "disabled: activity carries correlation_id");
}

// 재밍 구역 on/off 이벤트: 바뀔 때만 낸다 (DEC-009)
void tc_005() {
  const std::vector<v1::EntitySpec> sp = {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("jam0", "jammer")}),
                                          spec("site-001", v1::ENTITY_KIND_JAMMER_SITE)};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_RED, kOrigin};
  Geo spos = at(kOrigin, 90.0, 10000.0);
  spos.alt_m = 100.0;
  const Ent site{"site-001", v1::ENTITY_KIND_JAMMER_SITE, v1::SIDE_RED, spos};

  auto o = ps.step(frame_in(0, {u, site}));
  auto jz = events_of(o, "jam_zone");
  check(jz.size() == 1, "frame 0: only site zone");
  if (jz.size() == 1) {
    const auto& z = jz[0]->jam_zone();
    check(z.owner() == "site-001" && z.active(), "site zone active");
    check_near(z.area().circle().radius_m(), 3000.0, 1e-9, "site_generic radius");
    check_near(z.zone().radius_m(), 3000.0, 1e-9, "deprecated zone filled");
  }
  o = ps.step(frame_in(1, {u, site}));
  check(events_of(o, "jam_zone").empty(), "frame 1: no change, no event");

  Addressed<v1::JammerCommand> on;
  on.entity = "uav-001";
  on.msg.set_payload_id("jam0");
  on.msg.set_enable(true);
  FrameInput in = frame_in(2, {u, site});
  in.jammer_cmds.push_back(on);
  o = ps.step(in);
  jz = events_of(o, "jam_zone");
  check(jz.size() == 1 && jz[0]->jam_zone().owner() == "uav-001" && jz[0]->jam_zone().active(), "enable: active event");
  if (jz.size() == 1) check_near(jz[0]->jam_zone().area().circle().radius_m(), 2000.0, 1e-9, "default radius");
  const auto* ob = find_ob(o, "uav-001");
  check(ob && ob->jammer_activity.size() == 1 && ob->jammer_activity[0].active(), "jammer activity");

  o = ps.step(frame_in(3, {u, site}));
  check(events_of(o, "jam_zone").empty(), "same zone: no event");
  u.pos = at(kOrigin, 0.0, 30.0);
  o = ps.step(frame_in(4, {u, site}));
  check(events_of(o, "jam_zone").empty(), "moved 30 m (< update_distance): no event");
  u.pos = at(kOrigin, 0.0, 80.0);
  o = ps.step(frame_in(5, {u, site}));
  check(events_of(o, "jam_zone").size() == 1, "moved 80 m: zone update event");

  Addressed<v1::JammerCommand> off = on;
  off.msg.set_enable(false);
  in = frame_in(6, {u, site});
  in.jammer_cmds.push_back(off);
  o = ps.step(in);
  jz = events_of(o, "jam_zone");
  check(jz.size() == 1 && jz[0]->jam_zone().owner() == "uav-001" && !jz[0]->jam_zone().active(), "disable: inactive event");
  o = ps.step(frame_in(7, {u, site}));
  check(events_of(o, "jam_zone").empty(), "stays off: no event");

  // 반경 명령은 max_radius_m로 자른다
  on.msg.set_radius_m(9000.0);
  in = frame_in(8, {u, site});
  in.jammer_cmds.push_back(on);
  o = ps.step(in);
  jz = events_of(o, "jam_zone");
  check(jz.size() == 1, "re-enable event");
  if (jz.size() == 1) check_near(jz[0]->jam_zone().area().circle().radius_m(), 5000.0, 1e-9, "radius clipped");

  // 사이트가 죽으면 끈다
  Ent dead = site;
  dead.alive = false;
  o = ps.step(frame_in(9, {u, dead}));
  jz = events_of(o, "jam_zone");
  check(jz.size() == 1 && jz[0]->jam_zone().owner() == "site-001" && !jz[0]->jam_zone().active(), "dead site: off");
}

// 잔량 0 거부, StoreLoadout 갱신
void tc_006() {
  const std::vector<v1::EntitySpec> sp = {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "agm_short", 1)})};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {20.0, 0.0, 0.0}};
  const Geo aim{37.51, 127.0, 0.0};
  FrameInput in = frame_in(0, {u});
  in.strike_cmds.push_back(strike_point("uav-001", "sta1", aim));
  auto o = ps.step(in);
  auto s = strikes(o, "uav-001");
  check(s.size() == 1 && s[0]->state() == v1::STRIKE_STATE_LAUNCHED, "first shot launched");
  if (s.size() == 1) check(s[0]->weapon_entity() == "wpn-uav-001-01", "weapon id wpn-<shooter>-<seq>");
  check(events_of(o, "launch").size() == 1 && events_of(o, "spawn").size() == 1, "launch + spawn events");
  check(o.spawned.size() == 1 && o.weapons.size() == 1, "spawned + weapon state");
  check(ps.owns("wpn-uav-001-01") && !ps.owns("uav-001"), "owns weapon");
  const auto* ob = find_ob(o, "uav-001");
  check(ob && ob->loadout && ob->loadout->stores_size() == 1 && ob->loadout->stores(0).count() == 0, "loadout count 0");

  in = frame_in(1, {u});
  in.strike_cmds.push_back(strike_point("uav-001", "sta1", aim));
  o = ps.step(in);
  s = strikes(o, "uav-001");
  check(s.size() == 1 && s[0]->state() == v1::STRIKE_STATE_REJECTED && s[0]->reason() == "no_stores", "no_stores reject");
  ob = find_ob(o, "uav-001");
  check(ob && !ob->loadout, "loadout not repeated when unchanged");
  check(events_of(o, "launch").empty(), "no launch event on reject");

  // 장비 없음, 무장 아님
  in = frame_in(2, {u});
  in.strike_cmds.push_back(strike_point("uav-001", "sta9", aim));
  o = ps.step(in);
  s = strikes(o, "uav-001");
  check(s.size() == 1 && s[0]->reason() == "unknown_station", "unknown_station reject");

  ps.reset();
  check(ps.loadout("uav-001").size() == 1 && ps.loadout("uav-001")[0].count() == 1, "reset restores stores");
  check(!ps.owns("wpn-uav-001-01"), "reset clears weapons");
}

// 락온 실패 거부
void tc_007() {
  const std::vector<v1::EntitySpec> sp = {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "aam_short", 4)}),
                                          spec("tgt-a", v1::ENTITY_KIND_AIR_TARGET)};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin};
  auto shoot = [&](std::uint64_t f, const Geo& tpos) {
    FrameInput in = frame_in(f, {u, {"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, tpos}});
    in.strike_cmds.push_back(strike_target("uav-001", "sta1", "tgt-a"));
    const auto o = ps.step(in);
    const auto s = strikes(o, "uav-001");
    return s.size() == 1 ? *s[0] : v1::StrikeActivity{};
  };
  auto a = shoot(0, at(kOrigin, 180.0, 2000.0));
  check(a.state() == v1::STRIKE_STATE_REJECTED && a.reason() == "lock_failed", "target behind: lock_failed");
  check(a.header().correlation_id() == "c-tgt-a", "reject carries correlation_id");
  a = shoot(1, at(kOrigin, 50.0, 2000.0));
  check(a.state() == v1::STRIKE_STATE_REJECTED && a.reason() == "lock_failed", "outside seeker fov 45: lock_failed");
  a = shoot(2, at(kOrigin, 0.0, 9000.0));
  check(a.state() == v1::STRIKE_STATE_REJECTED && a.reason() == "out_of_range", "9000 m: out_of_range");
  // aam은 좌표 사격을 받지 않는다
  FrameInput in = frame_in(3, {u});
  in.strike_cmds.push_back(strike_point("uav-001", "sta1", at(kOrigin, 0.0, 1000.0)));
  auto o = ps.step(in);
  auto s = strikes(o, "uav-001");
  check(s.size() == 1 && s[0]->reason() == "no_target", "aam aim point: no_target");
  check(ps.loadout("uav-001")[0].count() == 4, "rejects keep stores");
  // DEM 차폐도 락온 실패
  const swarm::dyn::FlatTerrain high(5000.0);
  PayloadSystem ps2(ProfileLibrary::builtin(), sp, make_terrain_los(high), nullptr);
  in = frame_in(0, {u, {"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 2000.0)}});
  in.strike_cmds.push_back(strike_target("uav-001", "sta1", "tgt-a"));
  o = ps2.step(in);
  s = strikes(o, "uav-001");
  check(s.size() == 1 && s[0]->reason() == "lock_failed", "LOS blocked: lock_failed");
}

// PN 도달: 횡단 공중 표적
void tc_008() {
  const std::vector<v1::EntitySpec> sp = {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "aam_short", 2)}),
                                          spec("tgt-a", v1::ENTITY_KIND_AIR_TARGET)};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {30.0, 0.0, 0.0}};
  const Ent t{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 10.0, 3000.0, 200.0), {0.0, 40.0, 0.0}};
  const auto r = fly(ps, {u, t}, strike_target("uav-001", "sta1", "tgt-a"), 2000);
  check(r.launched, "launched");
  check(r.ended && r.end_state == v1::STRIKE_STATE_IMPACT && r.end_reason == "proximity", "proximity impact");
  check(contains(r.killed, "tgt-a") && !contains(r.killed, "uav-001"), "target killed, shooter safe");
  int kills = 0, impacts = 0;
  for (const auto& e : r.events) {
    if (e.has_kill() && e.kill().entity_id() == "tgt-a" && e.kill().cause() == "impact") ++kills;
    if (e.has_impact()) {
      ++impacts;
      check(e.impact().weapon_entity() == "wpn-uav-001-01" && e.impact().killed_size() == 1, "impact event");
      check_near(e.impact().lethal_radius_m(), 10.0, 1e-9, "impact lethal radius");
    }
  }
  check(kills == 1 && impacts == 1, "one impact, one kill");
  check(!r.last_weapon.alive() && r.last_weapon.id() == "wpn-uav-001-01", "final weapon state alive=false");
  std::fprintf(stderr, "  PN hit at frame %llu\n", static_cast<unsigned long long>(r.end_frame));
}

// PN 빗나감: 기동 한계가 작고 비행 시간이 짧다 → MISSED, 표적 생존
void tc_009() {
  const std::vector<v1::EntitySpec> sp = {
      spec("uav-001", v1::ENTITY_KIND_UAV,
           {pay("sta1", "aam_short", 1, {{"max_g", 0.5}, {"max_flight_time_s", 6.0}})}),
      spec("tgt-a", v1::ENTITY_KIND_AIR_TARGET)};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {30.0, 0.0, 0.0}};
  const Ent t{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 20.0, 2500.0), {0.0, 200.0, 0.0}};
  const auto r = fly(ps, {u, t}, strike_target("uav-001", "sta1", "tgt-a"), 2000);
  check(r.launched, "launched");
  check(r.ended && r.end_state == v1::STRIKE_STATE_MISSED && r.end_reason == "expired", "missed (expired)");
  check(r.killed.empty(), "nothing killed");
  check_near(static_cast<double>(r.end_frame), 6.0 / kDt - 1.0, 1.0, "expires at max_flight_time");
  bool any_impact = false;
  for (const auto& e : r.events) any_impact |= e.has_impact() || e.has_kill();
  check(!any_impact, "no impact/kill events");
}

// 지면 탄착: 좌표 사격, 교차 시점 보정
void tc_010() {
  const std::vector<v1::EntitySpec> sp = {
      spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "agm_short", 1, {{"proximity_m", 0.0}})})};
  const swarm::dyn::FlatTerrain flat(50.0);
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, &flat);
  Geo start = kOrigin;
  start.alt_m = 600.0;
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, start, {25.0, 0.0, 0.0}};
  Geo aim = at(start, 0.0, 1500.0);
  aim.alt_m = 50.0;
  const auto r = fly(ps, {u}, strike_point("uav-001", "sta1", aim), 3000);
  check(r.ended && r.end_state == v1::STRIKE_STATE_IMPACT && r.end_reason == "ground", "ground impact");
  const v1::TruthEvent* im = nullptr;
  for (const auto& e : r.events)
    if (e.has_impact()) im = &e;
  check(im != nullptr, "impact event");
  if (im) {
    const auto& p = im->impact().position();
    check_near(p.alt_m(), 50.0, 1e-3, "impact altitude = terrain");
    const Geo ip{p.lat_deg(), p.lon_deg(), p.alt_m()};
    check(distance_m(ip, aim) < 5.0, "impact near aim point");
    const std::uint64_t t0 = r.end_frame * kDtUs;
    const std::uint64_t ti = im->header().sim_time_us();
    check(ti > t0 && ti <= t0 + kDtUs, "impact time inside frame");
    std::fprintf(stderr, "  ground impact t=%llu us, miss %.3f m\n", static_cast<unsigned long long>(ti),
                 distance_m(ip, aim));
  }
  check(r.last_weapon.kinematics().position().alt_m() >= 50.0 - 1e-3, "final state not below ground");
}

// 살상반경 다중 파괴: 반경 15 m 안 3개 파괴, 밖 1개 생존
void tc_011() {
  const std::vector<v1::EntitySpec> sp = {
      spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "agm_short", 1, {{"proximity_m", 0.0}})}),
      spec("gnd-001", v1::ENTITY_KIND_GROUND_TARGET), spec("gnd-002", v1::ENTITY_KIND_GROUND_TARGET),
      spec("gnd-003", v1::ENTITY_KIND_GROUND_TARGET), spec("gnd-004", v1::ENTITY_KIND_GROUND_TARGET)};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  Geo start = kOrigin;
  start.alt_m = 500.0;
  Geo aim = at(start, 0.0, 1200.0);
  aim.alt_m = 0.0;
  auto g = [&](const char* id, double az, double d) {
    Geo p = d > 0.0 ? at(aim, az, d) : aim;
    p.alt_m = 0.0;
    return Ent{id, v1::ENTITY_KIND_GROUND_TARGET, v1::SIDE_RED, p};
  };
  const std::vector<Ent> ents = {{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, start, {25.0, 0.0, 0.0}},
                                 g("gnd-001", 0.0, 0.0), g("gnd-002", 90.0, 6.0), g("gnd-003", 270.0, 6.0),
                                 g("gnd-004", 90.0, 60.0)};
  const auto r = fly(ps, ents, strike_point("uav-001", "sta1", aim), 3000);
  check(r.ended && r.end_state == v1::STRIKE_STATE_IMPACT, "impact");
  check(r.killed == std::vector<std::string>({"gnd-001", "gnd-002", "gnd-003"}), "three killed, sorted");
  int kills = 0;
  for (const auto& e : r.events) {
    if (e.has_kill()) ++kills;
    if (e.has_impact()) check(e.impact().killed_size() == 3, "impact lists 3 killed");
  }
  check(kills == 3, "three kill events");
  // 파괴된 표적은 다음 프레임부터 탐지·피격 대상이 아니다 (Core가 alive=false로 넣지 않아도)
  FrameInput in = frame_in(r.end_frame + 1, ents);
  const auto o = ps.step(in);
  check(o.killed.empty(), "no re-kill");
}

// 같은 입력 2회 → 같은 출력 (REQ-SIM-001)
std::string serialize(const google::protobuf::Message& m) {
  std::string s;
  {
    google::protobuf::io::StringOutputStream zs(&s);
    google::protobuf::io::CodedOutputStream cs(&zs);
    cs.SetSerializationDeterministic(true);
    (void)m.SerializeToCodedStream(&cs);
  }
  return s;
}

std::string run_mixed(PayloadSystem& ps) {
  std::string acc;
  std::vector<Ent> ents = {
      {"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {30.0, 0.0, 0.0}},
      {"uav-002", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, at(kOrigin, 270.0, 200.0), {30.0, 0.0, 0.0}},
      {"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 10.0, 2500.0, 100.0), {0.0, 30.0, 0.0}},
      {"gnd-001", v1::ENTITY_KIND_GROUND_TARGET, v1::SIDE_RED, at(Geo{37.5, 127.0, 0.0}, 0.0, 1500.0)},
      {"site-001", v1::ENTITY_KIND_JAMMER_SITE, v1::SIDE_RED, at(kOrigin, 90.0, 5000.0, -900.0)}};
  for (std::uint64_t f = 0; f < 1500; ++f) {
    FrameInput in = frame_in(f, ents);
    if (f == 0) {
      in.strike_cmds.push_back(strike_target("uav-001", "sta1", "tgt-a"));
      Addressed<v1::JammerCommand> j;
      j.entity = "uav-002";
      j.msg.set_payload_id("jam0");
      j.msg.set_enable(true);
      in.jammer_cmds.push_back(j);
    }
    if (f == 10) {
      Geo aim = ents[3].pos;
      in.strike_cmds.push_back(strike_point("uav-002", "sta1", aim));
      in.strike_cmds.push_back(strike_point("uav-002", "sta1", aim));
    }
    const auto o = ps.step(in);
    for (const auto& ob : o.onboard) {
      acc += ob.entity;
      for (const auto& m : ob.detections) acc += serialize(m);
      for (const auto& m : ob.sensor_activity) acc += serialize(m);
      for (const auto& m : ob.jammer_activity) acc += serialize(m);
      for (const auto& m : ob.strike_activity) acc += serialize(m);
      if (ob.loadout) acc += serialize(*ob.loadout);
    }
    for (const auto& m : o.spawned) acc += serialize(m);
    for (const auto& m : o.weapons) acc += serialize(m);
    for (const auto& m : o.events) acc += serialize(m);
    for (const auto& k : o.killed) acc += k;
    for (auto& e : ents) {
      if (std::find(o.killed.begin(), o.killed.end(), e.id) != o.killed.end()) e.alive = false;
      e.pos = offset(e.pos, kDt * e.vel);
    }
  }
  return acc;
}

std::vector<v1::EntitySpec> mixed_specs() {
  return {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("cam0", "camera"), pay("sta1", "aam_short", 2)}),
          spec("uav-002", v1::ENTITY_KIND_UAV,
               {pay("sta1", "agm_short", 2), pay("jam0", "jammer"), pay("cam0", "camera", 0, {{"hfov_deg", 90.0}})}),
          spec("tgt-a", v1::ENTITY_KIND_AIR_TARGET), spec("gnd-001", v1::ENTITY_KIND_GROUND_TARGET),
          spec("site-001", v1::ENTITY_KIND_JAMMER_SITE)};
}

void tc_012() {
  PayloadSystem a(ProfileLibrary::builtin(), mixed_specs(), nullptr, nullptr);
  PayloadSystem b(ProfileLibrary::builtin(), mixed_specs(), nullptr, nullptr);
  const std::string ra = run_mixed(a);
  const std::string rb = run_mixed(b);
  check(!ra.empty() && ra == rb, "two instances: identical output");
  a.reset();
  const std::string rc = run_mixed(a);
  check(ra == rc, "after reset: identical output");
  check(ra.find("wpn-uav-002-02") != std::string::npos, "mixed run produced weapons");
  std::fprintf(stderr, "  output bytes %zu\n", ra.size());
}

// 프로파일과 재정의 (DEC-019)
void tc_013() {
  const auto& lib = ProfileLibrary::builtin();
  const auto types = lib.types();
  check(types == std::vector<std::string>({"aam_short", "agm_short", "camera", "fpv", "jammer"}), "builtin types");
  for (const char* p : {"eo_wide", "ea_generic", "agm_generic", "fpv_generic", "aam_generic", "site_generic"}) {
    const bool found = lib.has("camera", p) || lib.has("jammer", p) || lib.has("agm_short", p) ||
                       lib.has("fpv", p) || lib.has("aam_short", p);
    check(found, p);
  }
  auto m = lib.resolve(pay("cam0", "camera"));
  check_near(need(m, "hfov_deg"), 60.0, 0.0, "default profile eo_wide");
  auto s = pay("cam0", "camera", 0, {{"max_range_m", 1234.0}});
  s.set_profile("eo_narrow");
  m = lib.resolve(s);
  check_near(need(m, "max_range_m"), 1234.0, 0.0, "override applied");
  check_near(need(m, "hfov_deg"), 15.0, 0.0, "named profile");
  auto expect_throw = [](const char* what, auto fn) {
    bool thrown = false;
    try {
      fn();
    } catch (const std::invalid_argument&) {
      thrown = true;
    }
    check(thrown, what);
  };
  expect_throw("unknown override key", [&] { lib.resolve(pay("cam0", "camera", 0, {{"zoom", 2.0}})); });
  expect_throw("unknown type", [&] { lib.resolve(pay("x", "laser")); });
  expect_throw("unknown profile", [&] {
    auto p = pay("cam0", "camera");
    p.set_profile("nope");
    lib.resolve(p);
  });
  expect_throw("string override", [&] {
    auto p = pay("cam0", "camera");
    (*p.mutable_overrides()->mutable_fields())["hfov_deg"].set_string_value("wide");
    lib.resolve(p);
  });
  expect_throw("two jammers on one entity", [&] {
    PayloadSystem ps(lib, {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("jam0", "jammer"), pay("jam1", "jammer")})},
                     nullptr, nullptr);
  });
  expect_throw("duplicate payload id", [&] {
    PayloadSystem ps(lib, {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("cam0", "camera"), pay("cam0", "camera")})},
                     nullptr, nullptr);
  });
  // 시나리오에 같은 이름 엔티티가 있으면 번호를 건너뛴다
  PayloadSystem ps(lib,
                   {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "agm_short", 1)}),
                    spec("wpn-uav-001-01", v1::ENTITY_KIND_MISSILE)},
                   nullptr, nullptr);
  FrameInput in = frame_in(0, {{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin}});
  in.strike_cmds.push_back(strike_point("uav-001", "sta1", Geo{37.51, 127.0, 0.0}));
  const auto o = ps.step(in);
  const auto st = strikes(o, "uav-001");
  check(st.size() == 1 && st[0]->weapon_entity() == "wpn-uav-001-02", "weapon id skips scenario id");
  const ParamMap* pm = ps.params("uav-001", "sta1");
  check(pm && need(*pm, "lethal_radius_m") == 15.0, "params() exposes resolved values");
}

// FPV 종말 유도: 이동 지상 표적
void tc_014() {
  const std::vector<v1::EntitySpec> sp = {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("fpv1", "fpv", 1)}),
                                          spec("gnd-001", v1::ENTITY_KIND_GROUND_TARGET)};
  PayloadSystem ps(ProfileLibrary::builtin(), sp, nullptr, nullptr);
  Geo start = kOrigin;
  start.alt_m = 150.0;
  Geo tpos = at(start, 30.0, 800.0);
  tpos.alt_m = 0.0;
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, start};
  const Ent t{"gnd-001", v1::ENTITY_KIND_GROUND_TARGET, v1::SIDE_RED, tpos, {0.0, 8.0, 0.0}};
  const auto r = fly(ps, {u, t}, strike_target("uav-001", "fpv1", "gnd-001"), 6000);
  check(r.launched, "fpv launched");
  check(r.ended && r.end_state == v1::STRIKE_STATE_IMPACT, "fpv impact");
  check(contains(r.killed, "gnd-001"), "fpv kills moving ground target");
  check(r.last_weapon.kind() == v1::ENTITY_KIND_FPV, "weapon kind FPV");
  std::fprintf(stderr, "  fpv end frame %llu reason %s\n", static_cast<unsigned long long>(r.end_frame),
               r.end_reason.c_str());
}

// ---- DEC-064: 비행 중 탐색기 가시선 ----

// 원점 기준 NED 상자(북 n0~n1, 동 e0~e1, 높이 h) 하나가 솟은 평지 DEM
swarm::dyn::GridTerrain tower_terrain(double n0, double n1, double e0, double e1, double h) {
  swarm::dyn::GridSpec g;
  g.lat0_deg = 37.49;
  g.lon0_deg = 126.99;
  g.dlat_deg = 0.0001;
  g.dlon_deg = 0.0001;
  g.rows = 601;
  g.cols = 301;
  std::vector<float> hv(g.rows * g.cols, 0.0f);
  const Geo base{kOrigin.lat_deg, kOrigin.lon_deg, 0.0};
  for (std::size_t r = 0; r < g.rows; ++r)
    for (std::size_t c = 0; c < g.cols; ++c) {
      const Vec3 d = ned_between(base, Geo{g.lat0_deg + r * g.dlat_deg, g.lon0_deg + c * g.dlon_deg, 0.0});
      if (d.x >= n0 && d.x <= n1 && d.y >= e0 && d.y <= e1) hv[r * g.cols + c] = static_cast<float>(h);
    }
  return swarm::dyn::GridTerrain(g, std::move(hv));
}

struct TrackLog {
  RunResult r;
  std::vector<std::optional<WeaponTrack>> track;  // 프레임별 step 뒤 유도 상태
  std::vector<Geo> target_pos;                    // 프레임별 표적 위치(step 입력)
  int lost_frames = 0, lose_events = 0, reacquire_events = 0;
  long long first_lost = -1, first_reacquire = -1;
};

TrackLog fly_track(PayloadSystem& ps, std::vector<Ent> ents, const Addressed<v1::StrikeCommand>& cmd,
                   std::uint64_t max_frames, const std::string& weapon, std::size_t target_index) {
  TrackLog L;
  bool prev_lost = false;
  for (std::uint64_t f = 0; f < max_frames; ++f) {
    FrameInput in = frame_in(f, ents);
    if (f == 0) in.strike_cmds.push_back(cmd);
    L.target_pos.push_back(ents[target_index].pos);
    const FrameOutput o = ps.step(in);
    for (const auto& e : o.events) L.r.events.push_back(e);
    for (const auto& k : o.killed) L.r.killed.push_back(k);
    const auto t = ps.weapon_track(weapon);
    L.track.push_back(t);
    if (t) {
      if (t->los_lost) ++L.lost_frames;
      if (t->los_lost && !prev_lost) {
        ++L.lose_events;
        if (L.first_lost < 0) L.first_lost = static_cast<long long>(f);
      }
      if (!t->los_lost && prev_lost) {
        ++L.reacquire_events;
        if (L.first_reacquire < 0) L.first_reacquire = static_cast<long long>(f);
      }
      prev_lost = t->los_lost;
    }
    for (const auto* a : strikes(o, cmd.entity)) {
      if (a->state() == v1::STRIKE_STATE_LAUNCHED) L.r.launched = true;
      if (a->state() == v1::STRIKE_STATE_IMPACT || a->state() == v1::STRIKE_STATE_MISSED ||
          a->state() == v1::STRIKE_STATE_REJECTED) {
        L.r.ended = true;
        L.r.end_state = a->state();
        L.r.end_reason = a->reason();
        L.r.end_frame = f;
      }
    }
    if (L.r.ended) break;
    for (auto& e : ents) {
      if (std::find(o.killed.begin(), o.killed.end(), e.id) != o.killed.end()) e.alive = false;
      e.pos = offset(e.pos, kDt * e.vel);
    }
  }
  return L;
}

std::vector<v1::EntitySpec> aam_specs() {
  return {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "aam_short", 2)}),
          spec("tgt-a", v1::ENTITY_KIND_AIR_TARGET)};
}

// 능선(탑) 뒤로 들어간 표적: 락 해제, 마지막으로 본 위치로 좌표 유도
void tc_015() {
  const auto tower = tower_terrain(2300.0, 2600.0, 150.0, 900.0, 1500.0);
  PayloadSystem ps(ProfileLibrary::builtin(), aam_specs(), make_terrain_los(tower), &tower);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {30.0, 0.0, 0.0}};
  const Ent t{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 3000.0, -900.0), {0.0, 60.0, 0.0}};
  const auto L = fly_track(ps, {u, t}, strike_target("uav-001", "sta1", "tgt-a"), 2000, "wpn-uav-001-01", 1);
  std::fprintf(stderr, "  launched %d lost@%lld lost_frames %d reacq %d end %d/%s @%llu\n", L.r.launched, L.first_lost,
               L.lost_frames, L.reacquire_events, L.r.end_state, L.r.end_reason.c_str(),
               static_cast<unsigned long long>(L.r.end_frame));
  check(L.r.launched, "launched (visible at launch)");
  check(L.first_lost > 0, "lock lost behind ridge");
  if (L.first_lost > 0) {
    const auto f = static_cast<std::size_t>(L.first_lost);
    const auto& before = L.track[f - 1];
    check(before && before->locked && !before->coordinate_mode, "locked before loss");
    const auto& lost = L.track[f];
    check(lost && lost->los_lost && lost->coordinate_mode && !lost->locked, "lost: coordinate guidance");
    // 좌표 유도 지점 = 마지막으로 본 표적 위치(상실 직전 프레임 입력)
    if (lost) check(distance_m(lost->guide_point, L.target_pos[f - 1]) < 1e-6, "guide point = last seen position");
    // 상실 동안 지점은 고정
    bool frozen = true;
    for (std::size_t k = f; k < L.track.size() && L.track[k] && L.track[k]->los_lost; ++k)
      frozen &= distance_m(L.track[k]->guide_point, L.track[f]->guide_point) < 1e-9;
    check(frozen, "guide point frozen while lost");
  }
  check(!contains(L.r.killed, "tgt-a"), "hidden target not hit");
}

// 다시 보이고 FOV·거리 안이면 재획득 → 도달
void tc_016() {
  // 표적 경로 바로 앞의 좁은 탑: 표적이 동쪽으로 지나가는 잠깐 동안만 가린다
  const auto tower = tower_terrain(2650.0, 2700.0, 60.0, 140.0, 1500.0);
  PayloadSystem ps(ProfileLibrary::builtin(), aam_specs(), make_terrain_los(tower), nullptr);
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {30.0, 0.0, 0.0}};
  const Ent t{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 0.0, 3000.0, -900.0), {0.0, 40.0, 0.0}};
  const auto L = fly_track(ps, {u, t}, strike_target("uav-001", "sta1", "tgt-a"), 2000, "wpn-uav-001-01", 1);
  std::fprintf(stderr, "  launched %d lost@%lld lost_frames %d reacq@%lld end %d/%s @%llu\n", L.r.launched, L.first_lost,
               L.lost_frames, L.first_reacquire, L.r.end_state, L.r.end_reason.c_str(),
               static_cast<unsigned long long>(L.r.end_frame));
  check(L.r.launched, "launched");
  check(L.lose_events >= 1, "lock lost while target behind tower");
  check(L.reacquire_events >= 1, "reacquired");
  if (L.first_reacquire > 0) {
    const auto& re = L.track[static_cast<std::size_t>(L.first_reacquire)];
    check(re && re->locked && !re->coordinate_mode && !re->los_lost, "reacquired: tracking again");
  }
  check(L.r.ended && L.r.end_state == v1::STRIKE_STATE_IMPACT && L.r.end_reason == "proximity", "hit after reacquire");
  check(contains(L.r.killed, "tgt-a"), "target killed after reacquire");
}

// 평지 회귀 없음: LosFn 없음 = 평지 LosFn. 조준점 발사는 비행 중 가시선을 보지 않는다. 비용 측정
void tc_017() {
  const swarm::dyn::FlatTerrain flat(0.0);
  const LosFn base = make_terrain_los(flat);
  long long calls = 0;
  const LosFn counted = [&](const Geo& a, const Geo& b) {
    ++calls;
    return base(a, b);
  };
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin, {30.0, 0.0, 0.0}};
  const Ent t{"tgt-a", v1::ENTITY_KIND_AIR_TARGET, v1::SIDE_RED, at(kOrigin, 10.0, 3000.0, 200.0), {0.0, 40.0, 0.0}};
  auto run = [&](LosFn los, TrackLog& L) {
    PayloadSystem ps(ProfileLibrary::builtin(), aam_specs(), std::move(los), nullptr);
    L = fly_track(ps, {u, t}, strike_target("uav-001", "sta1", "tgt-a"), 2000, "wpn-uav-001-01", 1);
  };
  TrackLog a, b;
  run(nullptr, a);
  calls = 0;
  run(counted, b);
  std::string sa, sb;
  for (const auto& e : a.r.events) sa += serialize(e);
  for (const auto& e : b.r.events) sb += serialize(e);
  check(!sa.empty() && sa == sb, "flat LosFn = no LosFn (events identical)");
  check(a.r.end_frame == b.r.end_frame && b.r.end_state == v1::STRIKE_STATE_IMPACT, "same hit frame");
  check(b.lose_events == 0 && b.lost_frames == 0, "flat: never lost");
  // 비행 중 프레임마다 1회 (발사 판정 1회 + 끝 프레임 포함 비행 프레임 수)
  const long long flight_frames = static_cast<long long>(b.r.end_frame) + 1;
  check(calls == 1 + flight_frames, "one LOS query per in-flight weapon per frame");
  std::fprintf(stderr, "  flight frames %lld, LOS calls %lld\n", flight_frames, calls);

  // 조준점 발사: 비행 중 가시선 판정 없음 (DEC-064)
  calls = 0;
  {
    PayloadSystem ps(ProfileLibrary::builtin(),
                     {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "agm_short", 1, {{"proximity_m", 0.0}})})},
                     counted, nullptr);
    Geo aim = at(kOrigin, 0.0, 1500.0);
    aim.alt_m = 0.0;
    const auto r = fly(ps, {u}, strike_point("uav-001", "sta1", aim), 3000);
    check(r.ended && r.end_state == v1::STRIKE_STATE_IMPACT, "aim point impact");
    check(calls == 0, "aim point launch: no LOS queries");
  }

  // 비용: 10 km 경로 1회 판정 시간 (표본 200개)
  const swarm::dyn::GridTerrain grid = tower_terrain(0.0, 0.0, 0.0, 0.0, 0.0);
  const LosFn gl = make_terrain_los(grid);
  const Geo p0 = kOrigin, p1 = at(kOrigin, 45.0, 10000.0, -500.0);
  const auto t0 = std::chrono::steady_clock::now();
  int vis = 0;
  for (int i = 0; i < 2000; ++i) vis += gl(p0, p1) ? 1 : 0;
  const double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count() / 2000.0;
  check(vis == 2000, "cost probe visible");
  std::fprintf(stderr, "  LOS 10 km grid query: %.2f us (Debug)\n", us);
}

// DEC-066: 조준점 발사도 발사 기체 기준 탐색 FOV 안이어야 한다
// agm_generic: seeker_fov 90°(반각 45°), 축은 기수에서 아래로 30°
std::string run_aim_fov(bool verbose) {
  PayloadSystem ps(ProfileLibrary::builtin(),
                   {spec("uav-001", v1::ENTITY_KIND_UAV, {pay("sta1", "agm_short", 10), pay("fpv1", "fpv", 1)})},
                   nullptr, nullptr);
  Geo hi = kOrigin;
  hi.alt_m = 5000.0;
  const Ent u{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, kOrigin};
  const Ent uh{"uav-001", v1::ENTITY_KIND_UAV, v1::SIDE_BLUE, hi};
  const double d = 1000.0;
  auto dz = [&](double elev_deg) { return d * std::tan(elev_deg * geo::kDegToRad); };  // 위 +
  std::string acc;
  std::uint64_t f = 0;
  std::uint32_t stores = 10;
  auto shoot = [&](const Ent& shooter, const std::string& pid, const Geo& aim, bool expect_launch, const char* what) {
    FrameInput in = frame_in(f, {shooter});
    in.strike_cmds.push_back(strike_point("uav-001", pid, aim));
    const auto o = ps.step(in);
    ++f;
    for (const auto& m : o.events) acc += serialize(m);
    for (const auto& m : o.spawned) acc += serialize(m);
    for (const auto& ob : o.onboard)
      for (const auto& m : ob.strike_activity) acc += serialize(m);
    const auto s = strikes(o, "uav-001");
    const v1::StrikeActivity* a = nullptr;
    for (const auto* x : s)
      if (x->state() == v1::STRIKE_STATE_LAUNCHED || x->state() == v1::STRIKE_STATE_REJECTED) a = x;
    if (!verbose) return;
    if (expect_launch) {
      check(a && a->state() == v1::STRIKE_STATE_LAUNCHED, what);
      if (pid == "sta1") --stores;
    } else {
      check(a && a->state() == v1::STRIKE_STATE_REJECTED && a->reason() == "out_of_fov", what);
      check(a && a->weapon_entity().empty(), "reject: no weapon id");
      check(o.spawned.empty() && events_of(o, "spawn").empty() && events_of(o, "launch").empty(),
            "reject: no entity spawned");
    }
    check(ps.loadout("uav-001")[1].count() == stores, "stores only drop on launch");
  };
  // 축 위(아래 30°) → 발사
  shoot(u, "sta1", at(kOrigin, 0.0, d, dz(-30.0)), true, "on axis: LAUNCHED");
  // 후방·측방 → 거부
  Geo behind = at(kOrigin, 180.0, 1500.0);
  behind.alt_m = 0.0;
  shoot(u, "sta1", behind, false, "behind: out_of_fov");
  Geo side = at(kOrigin, 90.0, 1500.0);
  side.alt_m = 0.0;  // 아래 33.7°, 방위 90° → 축과 약 66°
  shoot(u, "sta1", side, false, "abeam: out_of_fov");
  // 경계: 축 기준 위로 45° = 고각 +15°, 아래로 45° = 고각 −75°
  shoot(u, "sta1", at(kOrigin, 0.0, d, dz(14.8)), true, "elev +14.8: inside");
  shoot(u, "sta1", at(kOrigin, 0.0, d, dz(15.2)), false, "elev +15.2: out_of_fov");
  shoot(uh, "sta1", at(hi, 0.0, d, dz(-74.8)), true, "elev -74.8: inside");
  shoot(uh, "sta1", at(hi, 0.0, d, dz(-75.2)), false, "elev -75.2: out_of_fov");
  // 거리 초과가 FOV보다 먼저다
  Geo far_behind = at(kOrigin, 180.0, 7000.0);
  far_behind.alt_m = 0.0;
  {
    FrameInput in = frame_in(f++, {u});
    in.strike_cmds.push_back(strike_point("uav-001", "sta1", far_behind));
    const auto o = ps.step(in);
    const auto s = strikes(o, "uav-001");
    if (verbose)
      check(!s.empty() && s.back()->state() == v1::STRIKE_STATE_REJECTED && s.back()->reason() == "out_of_range",
            "out_of_range precedes out_of_fov");
  }
  // fpv(seeker_fov 360)는 후방 조준점도 발사
  {
    FrameInput in = frame_in(f++, {u});
    in.strike_cmds.push_back(strike_point("uav-001", "fpv1", behind));
    const auto o = ps.step(in);
    const auto s = strikes(o, "uav-001");
    bool launched = false;
    for (const auto* x : s) launched |= x->payload_id() == "fpv1" && x->state() == v1::STRIKE_STATE_LAUNCHED;
    if (verbose) check(launched, "fpv 360: behind aim point launched");
    for (const auto& m : o.events) acc += serialize(m);
  }
  return acc;
}

void tc_018() {
  const std::string a = run_aim_fov(true);
  const std::string b = run_aim_fov(false);
  check(!a.empty() && a == b, "same input twice: identical output");
}

struct Case {
  const char* id;
  void (*fn)();
};

}  // namespace

int main(int argc, char** argv) {
  const Case cases[] = {{"TC-PAY-001", tc_001}, {"TC-PAY-002", tc_002}, {"TC-PAY-003", tc_003},
                        {"TC-PAY-004", tc_004}, {"TC-PAY-005", tc_005}, {"TC-PAY-006", tc_006},
                        {"TC-PAY-007", tc_007}, {"TC-PAY-008", tc_008}, {"TC-PAY-009", tc_009},
                        {"TC-PAY-010", tc_010}, {"TC-PAY-011", tc_011}, {"TC-PAY-012", tc_012},
                        {"TC-PAY-013", tc_013}, {"TC-PAY-014", tc_014}, {"TC-PAY-015", tc_015},
                        {"TC-PAY-016", tc_016}, {"TC-PAY-017", tc_017}, {"TC-PAY-018", tc_018}};
  int ran = 0;
  for (const auto& c : cases) {
    if (argc > 1 && std::strcmp(argv[1], c.id) != 0) continue;
    const int before = g_failures;
    try {
      c.fn();
    } catch (const std::exception& e) {
      std::fprintf(stderr, "FAIL: %s threw: %s\n", c.id, e.what());
      ++g_failures;
    }
    std::fprintf(stderr, "%s %s\n", c.id, g_failures == before ? "PASS" : "FAIL");
    ++ran;
  }
  if (ran == 0) {
    std::fprintf(stderr, "unknown test %s\n", argc > 1 ? argv[1] : "");
    return 2;
  }
  return g_failures == 0 ? 0 : 1;
}
