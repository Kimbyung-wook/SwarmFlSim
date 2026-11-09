# WP4 Datalink Emulator (DEC-021, PRP-LNK-001, PRP-LNK-002)
# 버스는 swarm_bus(open_bus, DEC-026), 지형은 swarm_dynamics의 Terrain 구현을 쓴다.
add_library(swarm_datalink_lib STATIC
  src/profile.cpp
  src/channel.cpp
  src/emulator.cpp
)
target_include_directories(swarm_datalink_lib PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_datalink_lib PUBLIC swarm_api)
target_compile_features(swarm_datalink_lib PUBLIC cxx_std_20)

add_executable(swarm_datalink src/main.cpp)
target_link_libraries(swarm_datalink PRIVATE swarm_datalink_lib swarm_dynamics swarm_bus)
swarm_copy_runtime_dlls(swarm_datalink)

if(SWARM_BUILD_TESTS)
  add_executable(swarm_datalink_tests tests/test_datalink.cpp)
  target_link_libraries(swarm_datalink_tests PRIVATE swarm_datalink_lib swarm_dynamics)
  # 시험 케이스마다 CTest 항목 하나 (TC-LNK-NNN)
  foreach(tc
      TC-LNK-001 TC-LNK-002 TC-LNK-003 TC-LNK-004 TC-LNK-005 TC-LNK-006
      TC-LNK-007 TC-LNK-008 TC-LNK-009 TC-LNK-010 TC-LNK-011 TC-LNK-012
      TC-LNK-013 TC-LNK-014 TC-LNK-015 TC-LNK-016 TC-LNK-017 TC-LNK-018 TC-LNK-019 TC-LNK-020 TC-LNK-021 TC-LNK-022 TC-LNK-023 TC-LNK-024 TC-LNK-025 TC-LNK-026)
    add_test(NAME lnk.${tc} COMMAND swarm_datalink_tests ${tc})
  endforeach()
endif()
