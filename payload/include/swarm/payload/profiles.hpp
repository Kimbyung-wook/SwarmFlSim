// IMP-PAY-002: 공개 일반값 프로파일과 PayloadSpec.overrides 재정의 (DEC-019, REQ-PAY-001, REQ-PAY-005)
#pragma once

#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/v1/entity.pb.h"

namespace swarm::payload {

using ParamMap = std::map<std::string, double>;

// 형식별 프로파일 묶음. JSON 한 파일이 형식 하나다:
// { "type": "camera", "default": "eo_wide", "note": "...", "profiles": { "eo_wide": { "hfov_deg": 60, ... } } }
// 같은 형식의 프로파일은 모두 기본 프로파일과 같은 키를 가져야 한다
class ProfileLibrary {
 public:
  // payload/profiles/*.json을 빌드 시점에 넣어 둔 기본 라이브러리
  static const ProfileLibrary& builtin();

  // 형식 하나를 더한다(같은 형식이 있으면 바꾼다). 형식 오류면 std::invalid_argument
  void add_json(std::string_view json);
  // 디렉터리의 *.json을 이름순으로 add_json 한다
  void load_dir(const std::filesystem::path& dir);

  std::vector<std::string> types() const;
  bool has(const std::string& type, const std::string& profile) const;

  // 프로파일 값에 overrides를 덮어쓴 값. profile이 비면 그 형식의 기본 프로파일.
  // 모르는 형식·프로파일, 프로파일에 없는 재정의 키, 숫자·불이 아닌 값이면 std::invalid_argument
  ParamMap resolve(const v1::PayloadSpec& spec) const;

 private:
  struct TypeEntry {
    std::string default_profile;
    std::map<std::string, ParamMap> profiles;
  };
  std::map<std::string, TypeEntry> types_;
};

// 값이 없으면 std::invalid_argument
double need(const ParamMap& m, const std::string& key);

}  // namespace swarm::payload
