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
  # 합성 DEM은 dynamics 시험 자료를 같이 쓴다 (TC-CORE-036~037, DEC-053)
  set(SWARM_TEST_DEM "${CMAKE_CURRENT_SOURCE_DIR}/../dynamics/tests/data/ridge.json")
  target_compile_definitions(swarm_core_tests PRIVATE SWARM_TEST_DEM="${SWARM_TEST_DEM}")
  add_test(NAME swarm_core_tests COMMAND swarm_core_tests)
  # TC-CORE-040: 실행 파일 --terrain-dem 적재와 잘못된 경로 종료 코드 (IMP-CORE-023)
  add_test(NAME core.TC-CORE-040.dem
           COMMAND swarm_core --bus memory --autostart --mode freerun --rate 0 --frames 20 --terrain-dem "${SWARM_TEST_DEM}")
  set_tests_properties(core.TC-CORE-040.dem PROPERTIES PASS_REGULAR_EXPRESSION "terrain=dem 101x101")
  add_test(NAME core.TC-CORE-040.dem_missing
           COMMAND swarm_core --bus memory --autostart --frames 1 --terrain-dem "${CMAKE_CURRENT_BINARY_DIR}/no_such_dem.json")
  set_tests_properties(core.TC-CORE-040.dem_missing PROPERTIES WILL_FAIL TRUE)

  if(SWARM_BUS_WITH_ZENOH)
    add_executable(swarm_core_zenoh_tests tests/test_zenoh_bus.cpp)
    target_link_libraries(swarm_core_zenoh_tests PRIVATE swarm_core_lib swarm_bus)
    swarm_copy_runtime_dlls(swarm_core_zenoh_tests)
    add_test(NAME swarm_core_zenoh_tests COMMAND swarm_core_zenoh_tests)
  endif()
endif()
