// IMP-CORE-006: 최소 시나리오 파싱과 내장 시나리오
#include "swarm/core/scenario.hpp"

#include <cmath>
#include <cstdio>
#include <numbers>
#include <stdexcept>

#include <google/protobuf/struct.pb.h>
#include <google/protobuf/util/json_util.h>

namespace swarm::core {

namespace {

namespace pb = google::protobuf;

v1::RunMode parse_mode(const std::string& s) {
  if (s == "realtime") return v1::RUN_MODE_REALTIME;
  if (s == "lockstep") return v1::RUN_MODE_LOCKSTEP;
  if (s == "freerun") return v1::RUN_MODE_FREERUN;
  v1::RunMode m{};
  if (v1::RunMode_Parse(s, &m)) return m;
  throw std::invalid_argument("unknown mode: " + s);
}

double number(const pb::Value& v, const char* what) {
  if (v.kind_case() != pb::Value::kNumberValue) throw std::invalid_argument(std::string(what) + " must be a number");
  return v.number_value();
}

}  // namespace

Scenario parse_scenario_json(const std::string& json) {
  pb::Struct root;
  if (auto st = pb::util::JsonStringToMessage(json, &root); !st.ok())
    throw std::invalid_argument("scenario json: " + std::string(st.message()));

  Scenario sc;
  const auto& f = root.fields();
  if (auto it = f.find("name"); it != f.end()) sc.name = it->second.string_value();
  if (auto it = f.find("frame_hz"); it != f.end()) sc.frame_hz = static_cast<std::uint32_t>(number(it->second, "frame_hz"));
  if (auto it = f.find("mode"); it != f.end()) sc.mode = parse_mode(it->second.string_value());
  if (auto it = f.find("rate"); it != f.end()) sc.rate = number(it->second, "rate");
  if (auto it = f.find("seed"); it != f.end()) sc.seed = static_cast<std::uint64_t>(number(it->second, "seed"));
  if (auto it = f.find("participants"); it != f.end())
    for (const auto& p : it->second.list_value().values()) sc.participants.push_back(p.string_value());

  const auto it = f.find("entities");
  if (it == f.end() || it->second.kind_case() != pb::Value::kListValue)
    throw std::invalid_argument("scenario json: entities list required");

  pb::util::JsonParseOptions opts;
  opts.ignore_unknown_fields = true;
  for (const auto& e : it->second.list_value().values()) {
    std::string ej;
    if (auto st = pb::util::MessageToJsonString(e, &ej); !st.ok())
      throw std::invalid_argument("scenario json: " + std::string(st.message()));
    v1::EntitySpec spec;
    if (auto st = pb::util::JsonStringToMessage(ej, &spec, opts); !st.ok())
      throw std::invalid_argument("entity: " + std::string(st.message()));
    sc.entities.push_back(std::move(spec));
  }
  return sc;
}

Scenario builtin_scenario(int uav_count) {
  Scenario sc;
  sc.name = "builtin";
  constexpr double kLat0 = 37.0, kLon0 = 127.5, kAlt = 1000.0, kSpeed = 25.0;

  v1::EntitySpec gcs;
  gcs.set_id("gcs-01");
  gcs.set_kind(v1::ENTITY_KIND_GCS);
  gcs.set_side(v1::SIDE_BLUE);
  gcs.set_dynamics(v1::DYNAMICS_KIND_STATIC);
  gcs.mutable_initial()->mutable_position()->set_lat_deg(kLat0 - 0.05);
  gcs.mutable_initial()->mutable_position()->set_lon_deg(kLon0);
  gcs.mutable_initial()->mutable_position()->set_alt_m(100.0);
  gcs.mutable_initial()->mutable_attitude()->set_w(1.0);
  sc.entities.push_back(gcs);

  // 5열 격자 대형, 북동쪽(45°)으로 비행
  const double psi = std::numbers::pi / 4;
  for (int i = 0; i < uav_count; ++i) {
    char id[16];
    std::snprintf(id, sizeof id, "uav-%03d", i + 1);
    v1::EntitySpec u;
    u.set_id(id);
    u.set_kind(v1::ENTITY_KIND_UAV);
    u.set_side(v1::SIDE_BLUE);
    u.set_dynamics(v1::DYNAMICS_KIND_DOF2);
    u.set_airframe("generic");
    u.set_controlling_gcs("gcs-01");
    auto* k = u.mutable_initial();
    k->mutable_position()->set_lat_deg(kLat0 + 0.002 * (i / 5));
    k->mutable_position()->set_lon_deg(kLon0 + 0.002 * (i % 5));
    k->mutable_position()->set_alt_m(kAlt + 10.0 * (i % 5));
    k->mutable_velocity_ned_mps()->set_x(kSpeed * std::cos(psi));
    k->mutable_velocity_ned_mps()->set_y(kSpeed * std::sin(psi));
    sc.entities.push_back(std::move(u));
  }
  return sc;
}

}  // namespace swarm::core
