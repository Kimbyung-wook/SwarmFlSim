# WP1 Sim Core (DEC-005, DEC-006, PRP-SIM-002)

# Zenoh(zenoh-c + zenoh-cpp)는 선택 의존성이다. 없으면 ZenohBus 없이 InMemoryBus로만 빌드한다.
# 설치 방법은 docs/10_contracts.md §7.2. 설치 경로는 CMAKE_PREFIX_PATH로 넘긴다.
find_package(zenohc CONFIG QUIET)
if(zenohc_FOUND)
  find_package(zenohcxx CONFIG QUIET)
endif()
if(zenohc_FOUND AND zenohcxx_FOUND)
  set(SWARM_CORE_WITH_ZENOH ON)
  message(STATUS "core: Zenoh ${zenohc_VERSION} found, building ZenohBus")
else()
  set(SWARM_CORE_WITH_ZENOH OFF)
  message(STATUS "core: Zenoh not found, ZenohBus disabled")
endif()

add_library(swarm_core_lib STATIC
  src/entity_store.cpp
  src/scenario.cpp
  src/sim_core.cpp
  src/mock_dynamics.cpp
)
target_include_directories(swarm_core_lib PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_core_lib PUBLIC swarm_api)

if(SWARM_CORE_WITH_ZENOH)
  add_library(swarm_core_zenoh STATIC src/zenoh_bus.cpp)
  target_include_directories(swarm_core_zenoh PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
  target_link_libraries(swarm_core_zenoh PUBLIC swarm_api zenohcxx::zenohc)
  target_compile_definitions(swarm_core_zenoh PUBLIC SWARM_CORE_WITH_ZENOH=1)
endif()

# 공유 라이브러리(zenohc.dll 등)를 실행 파일 옆에 둔다
function(swarm_core_copy_runtime_dlls target)
  if(WIN32)
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_RUNTIME_DLLS:${target}> $<TARGET_FILE_DIR:${target}>
      COMMAND_EXPAND_LISTS)
  endif()
endfunction()

add_executable(swarm_core src/main.cpp)
target_link_libraries(swarm_core PRIVATE swarm_core_lib)
if(SWARM_CORE_WITH_ZENOH)
  target_link_libraries(swarm_core PRIVATE swarm_core_zenoh)
  swarm_core_copy_runtime_dlls(swarm_core)
endif()

if(SWARM_BUILD_TESTS)
  add_executable(swarm_core_tests tests/test_core.cpp)
  target_link_libraries(swarm_core_tests PRIVATE swarm_core_lib)
  add_test(NAME swarm_core_tests COMMAND swarm_core_tests)

  if(SWARM_CORE_WITH_ZENOH)
    add_executable(swarm_core_zenoh_tests tests/test_zenoh_bus.cpp)
    target_link_libraries(swarm_core_zenoh_tests PRIVATE swarm_core_lib swarm_core_zenoh)
    swarm_core_copy_runtime_dlls(swarm_core_zenoh_tests)
    add_test(NAME swarm_core_zenoh_tests COMMAND swarm_core_zenoh_tests)
  endif()
endif()
