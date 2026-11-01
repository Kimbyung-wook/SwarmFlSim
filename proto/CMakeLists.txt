file(GLOB SWARM_PROTO_FILES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/swarm/v1/*.proto")

set(SWARM_PROTO_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/gen")
file(MAKE_DIRECTORY "${SWARM_PROTO_GEN_DIR}")

add_library(swarm_proto STATIC ${SWARM_PROTO_FILES})
target_link_libraries(swarm_proto PUBLIC protobuf::libprotobuf)
target_include_directories(swarm_proto PUBLIC "${SWARM_PROTO_GEN_DIR}")

protobuf_generate(
  TARGET swarm_proto
  LANGUAGE cpp
  IMPORT_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
  PROTOC_OUT_DIR "${SWARM_PROTO_GEN_DIR}"
)
