# WP7 Logger/Replay (DEC-011, PRP-LOG-001)
# MCAP C++ 라이브러리(헤더 전용)는 vcpkg 포트 unofficial-mcap을 찾고,
# 없으면 MCAP_INCLUDE_DIR(mcap/mcap.hpp가 있는 include 디렉터리)에서 찾는다.
find_package(unofficial-mcap CONFIG QUIET)
if(TARGET unofficial::mcap::mcap)
  set(SWARM_MCAP_TARGET unofficial::mcap::mcap)
else()
  find_path(MCAP_INCLUDE_DIR mcap/mcap.hpp)
  if(NOT MCAP_INCLUDE_DIR)
    message(WARNING "mcap not found: logger/ is skipped. Set MCAP_INCLUDE_DIR to <mcap>/cpp/mcap/include")
    return()
  endif()
  add_library(swarm_mcap INTERFACE)
  target_include_directories(swarm_mcap INTERFACE "${MCAP_INCLUDE_DIR}")
  target_compile_definitions(swarm_mcap INTERFACE MCAP_COMPRESSION_NO_LZ4 MCAP_COMPRESSION_NO_ZSTD)
  set(SWARM_MCAP_TARGET swarm_mcap)
endif()

add_library(swarm_logger STATIC src/mcap_log.cpp)
# 실행 파일 swarm_logger의 import 라이브러리(swarm_logger.lib)와 이름이 겹치지 않게 한다
set_target_properties(swarm_logger PROPERTIES OUTPUT_NAME swarm_logger_static)
target_include_directories(swarm_logger PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_logger PUBLIC swarm_api PRIVATE ${SWARM_MCAP_TARGET})

add_executable(swarm_logger_cli src/main.cpp)
set_target_properties(swarm_logger_cli PROPERTIES OUTPUT_NAME swarm_logger)
target_link_libraries(swarm_logger_cli PRIVATE swarm_logger)

if(SWARM_BUILD_TESTS)
  add_executable(swarm_logger_tests tests/test_logger.cpp)
  target_link_libraries(swarm_logger_tests PRIVATE swarm_logger ${SWARM_MCAP_TARGET})
  add_test(NAME swarm_logger_tests COMMAND swarm_logger_tests WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
endif()
