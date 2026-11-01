# WP2 동역학 (DEC-021)
add_library(swarm_dynamics STATIC
  src/models.cpp
  src/integrators.cpp
  src/terrain.cpp
  src/factory.cpp
)
target_include_directories(swarm_dynamics PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_dynamics PUBLIC swarm_api)
target_compile_features(swarm_dynamics PUBLIC cxx_std_20)

if(SWARM_BUILD_TESTS)
  add_executable(swarm_dynamics_tests tests/test_dynamics.cpp)
  target_link_libraries(swarm_dynamics_tests PRIVATE swarm_dynamics)
  # 시험 케이스마다 CTest 항목 하나 (TC-DYN-NNN)
  foreach(tc
      TC-DYN-001 TC-DYN-002 TC-DYN-003 TC-DYN-004 TC-DYN-005 TC-DYN-006
      TC-DYN-007 TC-DYN-008 TC-DYN-009 TC-DYN-010 TC-DYN-011 TC-DYN-012)
    add_test(NAME dyn.${tc} COMMAND swarm_dynamics_tests ${tc})
  endforeach()
endif()
