cmake_minimum_required(VERSION 3.24)
project(swarm_flight VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(SWARM_BUILD_TESTS "Build tests" ON)

if(MSVC)
  add_compile_options(/W4 /permissive- /utf-8)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 의존성은 툴체인에 묶지 않는다 (DEC-022).
# vcpkg, MSYS2(pacman), 리눅스 배포판 패키지 모두 find_package로 찾는다.
# 배포판 패키지 중 CMake 설정 파일이 없는 경우를 위해 FindProtobuf 모듈로 한 번 더 찾는다.
find_package(Protobuf CONFIG QUIET)
if(NOT Protobuf_FOUND)
  find_package(Protobuf MODULE REQUIRED)
endif()
message(STATUS "Protobuf ${Protobuf_VERSION}")

if(SWARM_BUILD_TESTS)
  enable_testing()
endif()

# WP0 계약
add_subdirectory(proto)
add_subdirectory(api/cpp)

# WP별 C++ 모듈. 각 WP 세션이 디렉터리를 만들면 자동으로 포함된다 (DEC-021)
foreach(wp_dir core dynamics datalink logger payload agent)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${wp_dir}/CMakeLists.txt")
    add_subdirectory(${wp_dir})
  endif()
endforeach()
