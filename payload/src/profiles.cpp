// IMP-PAY-002: 공개 일반값 프로파일과 PayloadSpec.overrides 재정의 (DEC-019)
#include "swarm/payload/profiles.hpp"

#include <algorithm>
#include <fstream>
#include <sstream>
#include <stdexcept>

#include <google/protobuf/struct.pb.h>
#include <google/protobuf/util/json_util.h>

namespace swarm::payload {

// builtin_profiles.cpp (CMake가 payload/profiles/*.json으로 만든다)
const std::vector<std::string_view>& builtin_profile_jsons();

namespace {

using google::protobuf::Struct;
using google::protobuf::Value;

double to_number(const Value& v, const std::string& where) {
  if (v.kind_case() == Value::kNumberValue) return v.number_value();
  if (v.kind_case() == Value::kBoolValue) return v.bool_value() ? 1.0 : 0.0;
  throw std::invalid_argument("payload profile: '" + where + "' must be a number or bool");
}

std::string str_field(const Struct& s, const char* key) {
  auto it = s.fields().find(key);
  if (it == s.fields().end() || it->second.kind_case() != Value::kStringValue)
    throw std::invalid_argument(std::string("payload profile: missing string '") + key + "'");
  return it->second.string_value();
}

}  // namespace

const ProfileLibrary& ProfileLibrary::builtin() {
  static const ProfileLibrary lib = [] {
    ProfileLibrary l;
    for (auto j : builtin_profile_jsons()) l.add_json(j);
    return l;
  }();
  return lib;
}

void ProfileLibrary::add_json(std::string_view json) {
  Struct root;
  auto st = google::protobuf::util::JsonStringToMessage(std::string(json), &root);
  if (!st.ok()) throw std::invalid_argument("payload profile: bad json: " + std::string(st.message()));
  const std::string type = str_field(root, "type");
  TypeEntry entry;
  entry.default_profile = str_field(root, "default");
  auto pit = root.fields().find("profiles");
  if (pit == root.fields().end() || pit->second.kind_case() != Value::kStructValue)
    throw std::invalid_argument("payload profile " + type + ": missing 'profiles'");
  for (const auto& [name, v] : pit->second.struct_value().fields()) {
    if (v.kind_case() != Value::kStructValue)
      throw std::invalid_argument("payload profile " + type + "/" + name + ": not an object");
    ParamMap m;
    for (const auto& [k, x] : v.struct_value().fields()) m[k] = to_number(x, type + "/" + name + "/" + k);
    entry.profiles[name] = std::move(m);
  }
  auto dit = entry.profiles.find(entry.default_profile);
  if (dit == entry.profiles.end())
    throw std::invalid_argument("payload profile " + type + ": default '" + entry.default_profile + "' not found");
  for (const auto& [name, m] : entry.profiles) {
    const ParamMap& def = dit->second;
    const bool same = m.size() == def.size() &&
                      std::equal(m.begin(), m.end(), def.begin(), [](const auto& a, const auto& b) { return a.first == b.first; });
    if (!same)
      throw std::invalid_argument("payload profile " + type + "/" + name + ": keys differ from default profile");
  }
  types_[type] = std::move(entry);
}

void ProfileLibrary::load_dir(const std::filesystem::path& dir) {
  std::vector<std::filesystem::path> files;
  for (const auto& e : std::filesystem::directory_iterator(dir))
    if (e.is_regular_file() && e.path().extension() == ".json") files.push_back(e.path());
  std::sort(files.begin(), files.end());
  for (const auto& f : files) {
    std::ifstream in(f, std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    add_json(ss.str());
  }
}

std::vector<std::string> ProfileLibrary::types() const {
  std::vector<std::string> out;
  for (const auto& [t, e] : types_) out.push_back(t);
  return out;
}

bool ProfileLibrary::has(const std::string& type, const std::string& profile) const {
  auto it = types_.find(type);
  return it != types_.end() && it->second.profiles.count(profile.empty() ? it->second.default_profile : profile);
}

ParamMap ProfileLibrary::resolve(const v1::PayloadSpec& spec) const {
  auto it = types_.find(spec.type());
  if (it == types_.end()) throw std::invalid_argument("payload " + spec.id() + ": unknown type '" + spec.type() + "'");
  const std::string& name = spec.profile().empty() ? it->second.default_profile : spec.profile();
  auto pit = it->second.profiles.find(name);
  if (pit == it->second.profiles.end())
    throw std::invalid_argument("payload " + spec.id() + ": unknown " + spec.type() + " profile '" + name + "'");
  ParamMap m = pit->second;
  // 재정의는 키 이름순으로 적용한다 (protobuf map 순서에 의존하지 않는다)
  std::map<std::string, const Value*> ov;
  for (const auto& [k, v] : spec.overrides().fields()) ov[k] = &v;
  for (const auto& [k, v] : ov) {
    auto mit = m.find(k);
    if (mit == m.end())
      throw std::invalid_argument("payload " + spec.id() + ": unknown override '" + k + "' for " + spec.type());
    mit->second = to_number(*v, spec.id() + "/" + k);
  }
  return m;
}

double need(const ParamMap& m, const std::string& key) {
  auto it = m.find(key);
  if (it == m.end()) throw std::invalid_argument("payload param '" + key + "' missing");
  return it->second;
}

}  // namespace swarm::payload
