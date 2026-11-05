// IMP-CORE-006: 최소 시나리오 파싱과 내장 시나리오
// IMP-CORE-025: 엔티티 ID 25자 이하, 엔티티당 재머 1개 적재 검증 (DEC-050, DEC-049)
#include "swarm/core/scenario.hpp"
#include "swarm/api/keys.hpp"
#include "swarm/lnk/profile.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <numbers>
#include <set>
#include <stdexcept>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/message.h>
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

// 설정된 모든 double·float 필드가 유한한지 본다. Struct 매개변수의 숫자도 포함한다
void check_finite(const pb::Message& m, const std::string& path) {
  const auto* r = m.GetReflection();
  std::vector<const pb::FieldDescriptor*> fields;
  r->ListFields(m, &fields);
  for (const auto* f : fields) {
    const std::string p = path + "." + std::string(f->name());
    const int n = f->is_repeated() ? r->FieldSize(m, f) : 1;
    for (int i = 0; i < n; ++i) {
      double v = 0.0;
      switch (f->cpp_type()) {
        case pb::FieldDescriptor::CPPTYPE_DOUBLE:
          v = f->is_repeated() ? r->GetRepeatedDouble(m, f, i) : r->GetDouble(m, f);
          break;
        case pb::FieldDescriptor::CPPTYPE_FLOAT:
          v = f->is_repeated() ? r->GetRepeatedFloat(m, f, i) : r->GetFloat(m, f);
          break;
        case pb::FieldDescriptor::CPPTYPE_MESSAGE:
          check_finite(f->is_repeated() ? r->GetRepeatedMessage(m, f, i) : r->GetMessage(m, f), p);
          continue;
        default:
          continue;
      }
      if (!std::isfinite(v)) throw std::invalid_argument("non-finite value at " + p);
    }
  }
}

void check_geodetic(const v1::Geodetic& g, const std::string& path) {
  if (g.lat_deg() < -90.0 || g.lat_deg() > 90.0)
    throw std::invalid_argument("latitude out of range at " + path + ": " + std::to_string(g.lat_deg()));
  if (g.lon_deg() < -180.0 || g.lon_deg() > 180.0)
    throw std::invalid_argument("longitude out of range at " + path + ": " + std::to_string(g.lon_deg()));
}

}  // namespace

bool valid_rate(double rate) { return std::isfinite(rate) && rate >= 0.0 && rate <= kMaxRate; }

void validate_scenario(const Scenario& sc) {
  if (sc.entities.empty()) throw std::invalid_argument("scenario has no entities");
  if (sc.frame_hz < 50 || sc.frame_hz > 100)  // REQ-DYN-003
    throw std::invalid_argument("frame_hz must be 50..100, got " + std::to_string(sc.frame_hz));
  if (!valid_rate(sc.rate))
    throw std::invalid_argument("rate must be finite and within 0.." + std::to_string(static_cast<int>(kMaxRate)));

  if (sc.source) check_finite(*sc.source, "scenario");
  for (const auto& e : sc.entities) {
    // IMP-CORE-025: 무장 ID wpn-<id>-NN이 엔티티 ID 상한 32자 안에 들게 한다 (DEC-050)
    if (e.id().size() > kMaxScenarioEntityId)
      throw std::invalid_argument("entity id longer than " + std::to_string(kMaxScenarioEntityId) +
                                  " chars: " + e.id());
    keys::check_entity_id(e.id());
    // JamZoneEvent.owner는 엔티티 ID다. 엔티티당 재머 1개 (DEC-049)
    int jammers = 0;
    for (const auto& p : e.payloads()) jammers += p.type() == "jammer";
    if (jammers > 1) throw std::invalid_argument("entity " + e.id() + " has " + std::to_string(jammers) + " jammers (max 1)");
    check_finite(e, "entity " + e.id());
    if (e.has_initial() && e.initial().has_position()) check_geodetic(e.initial().position(), e.id() + ".initial");
    for (const auto& g : e.script_path()) check_geodetic(g, e.id() + ".script_path");
  }

  std::set<std::string> profiles;
  if (sc.source)
    for (const auto& p : sc.source->link_profiles()) profiles.insert(p.name());
  for (const auto& e : sc.entities) {
    const auto& name = e.link_profile();
    if (name.empty() || profiles.count(name) || lnk::find_builtin_profile(name)) continue;
    throw std::invalid_argument("unknown link profile for " + e.id() + ": " + name);
  }
}

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

Scenario from_proto(const v1::Scenario& msg) {
  Scenario sc;
  sc.name = msg.name();
  const auto& run = msg.run();
  if (run.frame_hz() != 0) sc.frame_hz = run.frame_hz();
  if (run.mode() != v1::RUN_MODE_UNSPECIFIED) sc.mode = run.mode();
  if (run.rate() != 0.0) sc.rate = run.rate();
  sc.seed = run.seed();
  sc.participants.assign(run.participants().begin(), run.participants().end());
  sc.entities.assign(msg.entities().begin(), msg.entities().end());
  sc.source = msg;
  return sc;
}

void apply_run_override(Scenario& sc, const RunOverride& o) {
  if (o.mode == "realtime") sc.mode = v1::RUN_MODE_REALTIME;
  else if (o.mode == "lockstep") sc.mode = v1::RUN_MODE_LOCKSTEP;
  else if (o.mode == "freerun") sc.mode = v1::RUN_MODE_FREERUN;
  else if (!o.mode.empty()) throw std::invalid_argument("unknown mode: " + o.mode);
  if (!o.rate.empty()) sc.rate = std::stod(o.rate);
  if (!o.hz.empty()) sc.frame_hz = static_cast<std::uint32_t>(std::stoul(o.hz));
  if (!o.seed.empty()) sc.seed = std::stoull(o.seed);
  if (!sc.source) return;
  auto* run = sc.source->mutable_run();
  if (!o.mode.empty()) run->set_mode(sc.mode);
  if (!o.rate.empty()) run->set_rate(sc.rate);
  if (!o.hz.empty()) run->set_frame_hz(sc.frame_hz);
  if (!o.seed.empty()) run->set_seed(sc.seed);
}

v1::Scenario to_proto(const Scenario& sc) {
  if (sc.source) return *sc.source;
  v1::Scenario msg;
  msg.set_name(sc.name);
  auto* run = msg.mutable_run();
  run->set_mode(sc.mode);
  run->set_frame_hz(sc.frame_hz);
  run->set_seed(sc.seed);
  run->set_rate(sc.rate);
  for (const auto& p : sc.participants) run->add_participants(p);
  for (const auto& e : sc.entities) *msg.add_entities() = e;
  return msg;
}

Scenario read_scenario_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::invalid_argument("cannot open " + path);
  std::ostringstream ss;
  ss << in.rdbuf();
  const std::string text = ss.str();

  if (path.size() >= 3 && path.compare(path.size() - 3, 3, ".pb") == 0) {
    v1::Scenario msg;
    if (!msg.ParseFromString(text)) throw std::invalid_argument("scenario pb: parse failed: " + path);
    return from_proto(msg);
  }
  pb::Struct root;
  if (auto st = pb::util::JsonStringToMessage(text, &root); !st.ok())
    throw std::invalid_argument("scenario json: " + std::string(st.message()));
  if (const auto it = root.fields().find("run"); it != root.fields().end() && it->second.has_struct_value()) {
    v1::Scenario msg;
    if (auto st = pb::util::JsonStringToMessage(text, &msg); !st.ok())
      throw std::invalid_argument("scenario proto json: " + std::string(st.message()));
    return from_proto(msg);
  }
  return parse_scenario_json(text);
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
