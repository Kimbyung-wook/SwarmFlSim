// IMP-API-007: open_bus (DEC-026)
#include "swarm/bus/open_bus.hpp"

#include <stdexcept>

#ifdef SWARM_BUS_WITH_ZENOH
#include "swarm/bus/zenoh_bus.hpp"
#endif

namespace swarm::bus {

bool zenoh_available() {
#ifdef SWARM_BUS_WITH_ZENOH
  return true;
#else
  return false;
#endif
}

std::string default_backend() { return zenoh_available() ? "zenoh" : "memory"; }

std::unique_ptr<Bus> open_bus(const BusConfig& config) {
  const std::string backend = config.backend.empty() ? default_backend() : config.backend;
  if (backend == "memory") return std::make_unique<InMemoryBus>();
#ifdef SWARM_BUS_WITH_ZENOH
  if (backend == "zenoh") {
    ZenohOptions o;
    o.config_file = config.zenoh_config_file;
    o.mode = config.zenoh_mode;
    o.connect = config.connect;
    o.listen = config.listen;
    o.multicast_scouting = config.multicast_scouting;
    return std::make_unique<ZenohBus>(o);
  }
#endif
  throw std::invalid_argument("unsupported bus backend: " + backend + " (available: " +
                              (zenoh_available() ? "zenoh, memory" : "memory") + ")");
}

bool parse_bus_arg(BusConfig& config, std::string_view flag, const std::function<std::string()>& next) {
  if (flag == "--bus") config.backend = next();
  else if (flag == "--zenoh-config") config.zenoh_config_file = next();
  else if (flag == "--zenoh-mode") config.zenoh_mode = next();
  else if (flag == "--connect") config.connect.push_back(next());
  else if (flag == "--listen") config.listen.push_back(next());
  else if (flag == "--no-multicast") config.multicast_scouting = false;
  else return false;
  return true;
}

}  // namespace swarm::bus
