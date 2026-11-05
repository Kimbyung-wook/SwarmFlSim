// IMP-DYN-005 (REQ-SIM-003, DEC-004, DEC-005, DEC-016)
// IMP-DYN-009 (DEC-053): int16 격자, RawDemLoader
#include "swarm/dyn/terrain.hpp"

#include <google/protobuf/struct.pb.h>
#include <google/protobuf/util/json_util.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace swarm::dyn {

GridTerrain::GridTerrain(GridSpec spec, std::vector<float> heights_m, double outside_m)
    : spec_(spec), h_(std::move(heights_m)), outside_m_(outside_m) {
  check();
  if (h_.size() != spec_.rows * spec_.cols) throw std::invalid_argument("GridTerrain: heights size != rows * cols");
}

GridTerrain::GridTerrain(Int16Heights, GridSpec spec, std::vector<std::int16_t> heights_m, double outside_m)
    : spec_(spec), h16_(std::move(heights_m)), outside_m_(outside_m) {
  check();
  if (h16_.size() != spec_.rows * spec_.cols) throw std::invalid_argument("GridTerrain: heights size != rows * cols");
}

void GridTerrain::check() const {
  if (spec_.rows < 2 || spec_.cols < 2) throw std::invalid_argument("GridTerrain: rows and cols must be >= 2");
  if (!(spec_.dlat_deg > 0.0) || !(spec_.dlon_deg > 0.0))
    throw std::invalid_argument("GridTerrain: spacing must be positive");
}

bool GridTerrain::contains(double lat_deg, double lon_deg) const {
  const double fr = (lat_deg - spec_.lat0_deg) / spec_.dlat_deg;
  const double fc = (lon_deg - spec_.lon0_deg) / spec_.dlon_deg;
  return fr >= 0.0 && fc >= 0.0 && fr <= static_cast<double>(spec_.rows - 1) &&
         fc <= static_cast<double>(spec_.cols - 1);
}

double GridTerrain::elevation_m(double lat_deg, double lon_deg) const {
  if (!contains(lat_deg, lon_deg)) return outside_m_;
  const double fr = (lat_deg - spec_.lat0_deg) / spec_.dlat_deg;
  const double fc = (lon_deg - spec_.lon0_deg) / spec_.dlon_deg;
  const std::size_t r = std::min(static_cast<std::size_t>(fr), spec_.rows - 2);
  const std::size_t c = std::min(static_cast<std::size_t>(fc), spec_.cols - 2);
  const double a = fr - static_cast<double>(r), b = fc - static_cast<double>(c);
  return (1 - a) * ((1 - b) * at(r, c) + b * at(r, c + 1)) + a * ((1 - b) * at(r + 1, c) + b * at(r + 1, c + 1));
}

// ---------------------------------------------------------------- RawDemLoader (IMP-DYN-009)
namespace {

using google::protobuf::Struct;
using google::protobuf::Value;

[[noreturn]] void bad(const std::string& why) { throw std::invalid_argument("RawDemLoader: " + why); }

const Value& field(const Struct& s, const char* key) {
  auto it = s.fields().find(key);
  if (it == s.fields().end()) bad(std::string("missing '") + key + "'");
  return it->second;
}

std::string str(const Struct& s, const char* key) {
  const Value& v = field(s, key);
  if (v.kind_case() != Value::kStringValue) bad(std::string("'") + key + "' must be a string");
  return v.string_value();
}

double num(const Struct& s, const char* key) {
  const Value& v = field(s, key);
  if (v.kind_case() != Value::kNumberValue || !std::isfinite(v.number_value()))
    bad(std::string("'") + key + "' must be a finite number");
  return v.number_value();
}

std::size_t count(const Struct& s, const char* key) {
  const double v = num(s, key);
  if (v < 2 || v > 1e6 || v != std::floor(v)) bad(std::string("'") + key + "' must be an integer in [2, 1e6]");
  return static_cast<std::size_t>(v);
}

void expect(const Struct& s, const char* key, const char* want) {
  if (str(s, key) != want) bad(std::string("'") + key + "' must be \"" + want + "\"");
}

}  // namespace

std::unique_ptr<GridTerrain> RawDemLoader::load(const std::filesystem::path& header_json) const {
  std::ifstream hf(header_json, std::ios::binary);
  if (!hf) throw std::runtime_error("RawDemLoader: cannot open " + header_json.string());
  std::ostringstream text;
  text << hf.rdbuf();
  Struct h;
  if (const auto st = google::protobuf::util::JsonStringToMessage(text.str(), &h); !st.ok())
    bad("bad json: " + std::string(st.message()));

  expect(h, "format", "swarm-dem-grid");
  if (num(h, "version") != 1.0) bad("unsupported version");
  expect(h, "sample_type", "int16");
  expect(h, "byte_order", "little");
  expect(h, "row_order", "south_to_north");
  expect(h, "units", "m");
  GridSpec g;
  g.rows = count(h, "rows");
  g.cols = count(h, "cols");
  if (g.rows * g.cols > 400'000'000) bad("grid too large");
  g.lat0_deg = num(h, "lat0_deg");
  g.lon0_deg = num(h, "lon0_deg");
  g.dlat_deg = num(h, "dlat_deg");
  g.dlon_deg = num(h, "dlon_deg");
  if (!(g.dlat_deg > 0) || !(g.dlon_deg > 0)) bad("spacing must be positive");
  const double lat1 = g.lat0_deg + static_cast<double>(g.rows - 1) * g.dlat_deg;
  const double lon1 = g.lon0_deg + static_cast<double>(g.cols - 1) * g.dlon_deg;
  if (g.lat0_deg < -90 || lat1 > 90 + 1e-9 || g.lon0_deg < -180 || lon1 > 360 + 1e-9) bad("grid outside lat/lon range");
  bool has_nodata = false;
  std::int16_t nodata = 0;
  if (h.fields().count("nodata")) {
    const double v = num(h, "nodata");
    if (v != std::floor(v) || v < -32768 || v > 32767) bad("'nodata' must be an int16");
    has_nodata = true;
    nodata = static_cast<std::int16_t>(v);
  }
  const std::string rel_s = str(h, "data_file");
  const std::filesystem::path rel{std::u8string(rel_s.begin(), rel_s.end())};
  if (rel.empty() || rel.is_absolute()) bad("'data_file' must be a relative path");
  const std::filesystem::path data = header_json.parent_path() / rel;

  const std::size_t n = g.rows * g.cols;
  std::error_code ec;
  const auto size = std::filesystem::file_size(data, ec);
  if (ec) throw std::runtime_error("RawDemLoader: cannot open " + data.string());
  if (size != n * 2) bad("data file size " + std::to_string(size) + " != rows*cols*2 = " + std::to_string(n * 2));
  std::ifstream df(data, std::ios::binary);
  if (!df) throw std::runtime_error("RawDemLoader: cannot open " + data.string());
  std::vector<std::int16_t> v(n);
  std::vector<unsigned char> buf(1 << 20);
  std::size_t i = 0;
  while (i < n) {
    const std::size_t want = std::min(buf.size(), (n - i) * 2);
    if (!df.read(reinterpret_cast<char*>(buf.data()), static_cast<std::streamsize>(want)))
      throw std::runtime_error("RawDemLoader: read failed " + data.string());
    for (std::size_t k = 0; k < want; k += 2, ++i)  // little-endian, 호스트 바이트 순서와 무관
      v[i] = static_cast<std::int16_t>(static_cast<std::uint16_t>(buf[k] | (buf[k + 1] << 8)));
  }
  if (has_nodata) {
    const double fill = std::clamp(std::round(nodata_fill_m_), -32767.0, 32767.0);
    for (auto& x : v)
      if (x == nodata) x = static_cast<std::int16_t>(fill);
  }
  return std::make_unique<GridTerrain>(kInt16Heights, g, std::move(v), outside_m_);
}

EventFn make_ground_event(const DynamicsModel& model, const Terrain& terrain, double clearance_m) {
  return [&model, &terrain, clearance_m](double, std::span<const double> x) {
    KinematicSample k;
    model.to_kinematic(x, Environment{}, k);  // 위치만 쓰므로 바람과 무관
    return k.alt_m - (terrain.elevation_m(k.lat_deg, k.lon_deg) + clearance_m);
  };
}

}  // namespace swarm::dyn
