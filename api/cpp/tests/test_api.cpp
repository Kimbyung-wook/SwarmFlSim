// TC-API-003: C++ 키·InMemoryBus·생성 코드 링크 확인
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "swarm/api/bus.hpp"
#include "swarm/api/keys.hpp"
#include "swarm/api/plugin.hpp"
#include "swarm/v1/link.pb.h"

namespace {
int g_failures = 0;

void check(bool cond, const char* what) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}
}  // namespace

int main() {
  using namespace swarm;

  check(keys::tx("uav-001", keys::Iface::VI, "NavigationReport") == "swarm/uav-001/tx/vi/NavigationReport", "tx key");
  check(keys::link_state("uav-002", "uav-001") == "link/state/uav-001/uav-002", "link_state order");
  check(keys::is_valid_entity_id("gcs-01"), "valid id");
  check(!keys::is_valid_entity_id("UAV-001"), "uppercase id");
  check(!keys::is_valid_entity_id("uav"), "id without dash");
  check(!keys::is_valid_entity_id("uav--1"), "double dash");
  check(keys::keyexpr_matches("swarm/*/tx/**", "swarm/uav-001/tx/vi/FlightCommand"), "tx_all match");
  check(!keys::keyexpr_matches("swarm/*/tx/**", "swarm/uav-001/rx/vi/FlightCommand"), "tx_all no match");
  check(keys::keyexpr_matches("truth/**", "truth"), "** matches zero chunks");

  InMemoryBus bus;
  std::vector<std::string> got;
  {
    auto sub = bus.subscribe(keys::rx_all("uav-002"), [&](const Sample& s) { got.push_back(s.key); });

    v1::LinkEnvelope env;
    env.mutable_header()->set_source("uav-001");
    env.set_msg_type("swarm.v1.PeerStatus");
    std::string bytes = env.SerializeAsString();
    std::span<const std::uint8_t> payload(reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size());

    bus.put(keys::rx("uav-002", keys::Iface::P2P, "PeerStatus"), payload, protobuf_encoding("swarm.v1.LinkEnvelope"));
    bus.put(keys::rx("uav-003", keys::Iface::P2P, "PeerStatus"), payload, protobuf_encoding("swarm.v1.LinkEnvelope"));
  }
  bus.put(keys::rx("uav-002", keys::Iface::P2P, "PeerStatus"), {}, "");
  check(got.size() == 1, "bus delivers to matching subscriber only, and not after unsubscribe");

  if (g_failures == 0) std::puts("swarm_api_tests: ok");
  return g_failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
