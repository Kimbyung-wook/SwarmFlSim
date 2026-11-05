# WP1 Sim Core (DEC-005, DEC-006, PRP-SIM-002)
# 동역학은 WP2 swarm_dynamics(dynamics/)의 팩토리로 만든다 (IMP-CORE-008). 목 모델은 시험용으로 남긴다.
# 버스는 공용 라이브러리 swarm_bus(bus/, DEC-026)로 연다. Zenoh 유무는 swarm_bus가 정한다.

add_library(swarm_core_lib STATIC
  src/entity_store.cpp
  src/scenario.cpp
  src/sim_core.cpp
  src/mock_dynamics.cpp
  src/scripted.cpp
  src/wp2_dynamics.cpp
)
target_include_directories(swarm_core_lib PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_core_lib PUBLIC swarm_api swarm_dynamics swarm_datalink_lib swarm_payload)

add_executable(swarm_core src/main.cpp)
target_link_libraries(swarm_core PRIVATE swarm_core_lib swarm_bus)
swarm_copy_runtime_dlls(swarm_core)

if(SWARM_BUILD_TESTS)
  add_executable(swarm_core_tests tests/test_core.cpp)
  target_link_libraries(swarm_core_tests PRIVATE swarm_core_lib)
  add_test(NAME swarm_core_tests COMMAND swarm_core_tests)

  if(SWARM_BUS_WITH_ZENOH)
    add_executable(swarm_core_zenoh_tests tests/test_zenoh_bus.cpp)
    target_link_libraries(swarm_core_zenoh_tests PRIVATE swarm_core_lib swarm_bus)
    swarm_copy_runtime_dlls(swarm_core_zenoh_tests)
    add_test(NAME swarm_core_zenoh_tests COMMAND swarm_core_zenoh_tests)
  endif()
endif()
