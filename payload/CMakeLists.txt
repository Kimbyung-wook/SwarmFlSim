# WP8 Payload (DEC-021, DEC-046)
# payload/profiles/*.json을 구성 시점에 C++ 원문 문자열로 넣는다 (ProfileLibrary::builtin)
file(GLOB SWARM_PAYLOAD_PROFILES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/profiles/*.json")
list(SORT SWARM_PAYLOAD_PROFILES)
set(_pay_gen "${CMAKE_CURRENT_BINARY_DIR}/gen/builtin_profiles.cpp")
set(_pay_src "// 자동 생성 파일: payload/CMakeLists.txt가 payload/profiles/*.json으로 만든다\n")
string(APPEND _pay_src "#include <string_view>\n#include <vector>\n\nnamespace swarm::payload {\n\n")
string(APPEND _pay_src "const std::vector<std::string_view>& builtin_profile_jsons() {\n")
string(APPEND _pay_src "  static const std::vector<std::string_view> v = {\n")
foreach(f ${SWARM_PAYLOAD_PROFILES})
  file(READ "${f}" _json)
  string(APPEND _pay_src "    R\"PAYLOADJSON(${_json})PAYLOADJSON\",\n")
endforeach()
string(APPEND _pay_src "  };\n  return v;\n}\n\n}  // namespace swarm::payload\n")
file(CONFIGURE OUTPUT "${_pay_gen}" CONTENT "${_pay_src}" @ONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${SWARM_PAYLOAD_PROFILES})

add_library(swarm_payload STATIC
  src/geometry.cpp
  src/profiles.cpp
  src/weapon.cpp
  src/payload_system.cpp
  "${_pay_gen}"
)
target_include_directories(swarm_payload PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_payload PUBLIC swarm_api swarm_dynamics)
target_compile_features(swarm_payload PUBLIC cxx_std_20)

if(SWARM_BUILD_TESTS)
  add_executable(swarm_payload_tests tests/test_payload.cpp)
  target_link_libraries(swarm_payload_tests PRIVATE swarm_payload)
  # 시험 케이스마다 CTest 항목 하나 (TC-PAY-NNN)
  foreach(tc
      TC-PAY-001 TC-PAY-002 TC-PAY-003 TC-PAY-004 TC-PAY-005 TC-PAY-006 TC-PAY-007
      TC-PAY-008 TC-PAY-009 TC-PAY-010 TC-PAY-011 TC-PAY-012 TC-PAY-013 TC-PAY-014
      TC-PAY-015 TC-PAY-016 TC-PAY-017 TC-PAY-018)
    add_test(NAME pay.${tc} COMMAND swarm_payload_tests ${tc})
  endforeach()
endif()
