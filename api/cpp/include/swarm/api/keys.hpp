// Zenoh 키 체계 (docs/10_contracts.md §3). Python 쪽은 api/python/src/swarm_api/keys.py
#pragma once

#include <algorithm>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace swarm::keys {

enum class Iface { C2, VI, MS, MP, MD, P2P };

constexpr std::string_view to_string(Iface i) {
  switch (i) {
    case Iface::C2: return "c2";
    case Iface::VI: return "vi";
    case Iface::MS: return "ms";
    case Iface::MP: return "mp";
    case Iface::MD: return "md";
    case Iface::P2P: return "p2p";
  }
  return "";
}

// ^[a-z][a-z0-9]*(-[a-z0-9]+)+$, 길이 32 이하
inline bool is_valid_entity_id(std::string_view id) {
  if (id.empty() || id.size() > 32 || id.front() < 'a' || id.front() > 'z') return false;
  bool has_dash = false;
  char prev = '\0';
  for (char c : id) {
    const bool alnum = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
    if (c == '-') {
      if (prev == '-') return false;
      has_dash = true;
    } else if (!alnum) {
      return false;
    }
    prev = c;
  }
  return has_dash && prev != '-';
}

inline const std::string& check_entity_id(const std::string& id) {
  if (!is_valid_entity_id(id)) throw std::invalid_argument("invalid entity id: " + id);
  return id;
}

inline constexpr std::string_view kClockTick = "sim/clock/tick";
inline constexpr std::string_view kSimCtrlCmd = "sim/ctrl/cmd";
inline constexpr std::string_view kSimCtrlStatus = "sim/ctrl/status";
inline constexpr std::string_view kSimCtrlScenario = "sim/ctrl/scenario";
inline constexpr std::string_view kTxAll = "swarm/*/tx/**";
inline constexpr std::string_view kTruthState = "truth/state";

inline std::string clock_done(const std::string& participant) {
  return "sim/clock/done/" + check_entity_id(participant);
}

// 매개변수 (DEC-035). owner: dynamics | fa | ma
inline constexpr std::string_view kSimParamAll = "sim/param/**";

inline std::string sim_param(const std::string& id, std::string_view owner) {
  if (owner != "dynamics" && owner != "fa" && owner != "ma") throw std::invalid_argument("invalid param owner");
  return "sim/param/" + check_entity_id(id) + "/" + std::string(owner);
}

inline std::string tx(const std::string& src, Iface iface, std::string_view msg) {
  return "swarm/" + check_entity_id(src) + "/tx/" + std::string(to_string(iface)) + "/" + std::string(msg);
}

inline std::string rx(const std::string& dst, Iface iface, std::string_view msg) {
  return "swarm/" + check_entity_id(dst) + "/rx/" + std::string(to_string(iface)) + "/" + std::string(msg);
}

inline std::string rx_all(const std::string& dst) { return "swarm/" + check_entity_id(dst) + "/rx/**"; }

inline std::string onboard(const std::string& id, std::string_view msg) {
  return "onboard/" + check_entity_id(id) + "/" + std::string(msg);
}

// 항법·제어 일괄 (DEC-081). Core·Agent 런타임 전용
inline constexpr std::string_view kNavigationBatch = "onboard_batch/NavigationBatch";
inline constexpr std::string_view kControlBatchAll = "onboard_batch/ControlBatch/*";

inline std::string control_batch(std::string_view participant) {
  return "onboard_batch/ControlBatch/" + std::string(participant);
}

inline std::string link_outcome(const std::string& src, const std::string& dst) {
  return "link/outcome/" + check_entity_id(src) + "/" + check_entity_id(dst);
}

inline std::string link_state(const std::string& a, const std::string& b) {
  check_entity_id(a);
  check_entity_id(b);
  return a < b ? "link/state/" + a + "/" + b : "link/state/" + b + "/" + a;
}

inline std::string truth_event(std::string_view kind) { return "truth/event/" + std::string(kind); }

namespace detail {
inline std::vector<std::string_view> split(std::string_view s) {
  std::vector<std::string_view> out;
  std::size_t start = 0;
  for (std::size_t i = 0; i <= s.size(); ++i) {
    if (i == s.size() || s[i] == '/') {
      out.push_back(s.substr(start, i - start));
      start = i + 1;
    }
  }
  return out;
}

inline bool match(const std::vector<std::string_view>& e, std::size_t i,
                  const std::vector<std::string_view>& k, std::size_t j) {
  if (i == e.size()) return j == k.size();
  if (e[i] == "**") {
    for (std::size_t jj = j; jj <= k.size(); ++jj)
      if (match(e, i + 1, k, jj)) return true;
    return false;
  }
  if (j == k.size()) return false;
  if (e[i] == "*" || e[i] == k[j]) return match(e, i + 1, k, j + 1);
  return false;
}
}  // namespace detail

// Zenoh 키 표현식 일치 판정. `*`는 한 마디, `**`는 0개 이상 마디
inline bool keyexpr_matches(std::string_view expr, std::string_view key) {
  return detail::match(detail::split(expr), 0, detail::split(key), 0);
}

}  // namespace swarm::keys
