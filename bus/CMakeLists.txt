# WP0 공용 버스 라이브러리 (DEC-026, PRP-NET-001)
# Zenoh(zenoh-c + zenoh-cpp)는 선택 의존성이다. 없으면 InMemoryBus만 들어간다.
# 설치 방법은 docs/10_contracts.md §7.2. 설치 경로는 CMAKE_PREFIX_PATH로 넘긴다.
option(SWARM_REQUIRE_ZENOH "Zenoh가 없으면 구성 실패" OFF)
find_package(zenohc CONFIG QUIET)
if(zenohc_FOUND)
  find_package(zenohcxx CONFIG QUIET)
endif()
if(zenohc_FOUND AND zenohcxx_FOUND)
  set(SWARM_BUS_WITH_ZENOH ON CACHE INTERNAL "")
  message(STATUS "bus: Zenoh ${zenohc_VERSION} found")
else()
  set(SWARM_BUS_WITH_ZENOH OFF CACHE INTERNAL "")
  # D-34: 메모리 버스만으로 빌드된 실행 파일은 프로세스 사이 통신이 안 돼 시작에서 멈춘다.
  if(SWARM_REQUIRE_ZENOH)
    message(FATAL_ERROR "bus: Zenoh not found (SWARM_REQUIRE_ZENOH=ON). CMAKE_PREFIX_PATH를 확인하라 (docs/10_contracts.md §7.2)")
  endif()
  message(WARNING "bus: Zenoh not found, memory backend only. 다중 프로세스 실행은 동작하지 않는다. 설치 경로를 CMAKE_PREFIX_PATH로 넘겨라 (docs/10_contracts.md §7.2)")
endif()

add_library(swarm_bus STATIC src/open_bus.cpp)
target_include_directories(swarm_bus PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(swarm_bus PUBLIC swarm_api)
if(SWARM_BUS_WITH_ZENOH)
  target_sources(swarm_bus PRIVATE src/zenoh_bus.cpp)
  target_link_libraries(swarm_bus PUBLIC zenohcxx::zenohc)
  target_compile_definitions(swarm_bus PRIVATE SWARM_BUS_WITH_ZENOH=1)
endif()

# swarm_bus를 쓰는 실행 파일 옆에 공유 라이브러리(zenohc.dll 등)를 둔다
function(swarm_copy_runtime_dlls target)
  if(WIN32 AND SWARM_BUS_WITH_ZENOH)
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_RUNTIME_DLLS:${target}> $<TARGET_FILE_DIR:${target}>
      COMMAND_EXPAND_LISTS)
  endif()
endfunction()

if(SWARM_BUILD_TESTS)
  add_executable(swarm_bus_tests tests/test_bus.cpp)
  target_link_libraries(swarm_bus_tests PRIVATE swarm_bus)
  swarm_copy_runtime_dlls(swarm_bus_tests)
  add_test(NAME swarm_bus_tests COMMAND swarm_bus_tests)
endif()

# TC-API-009: put 경로 측정 도구 (DEC-086). ctest에는 넣지 않는다
if(SWARM_BUILD_TESTS AND SWARM_BUS_WITH_ZENOH)
  add_executable(swarm_bus_bench bench/bench_put.cpp)
  target_link_libraries(swarm_bus_bench PRIVATE swarm_bus)
  swarm_copy_runtime_dlls(swarm_bus_bench)
endif()
