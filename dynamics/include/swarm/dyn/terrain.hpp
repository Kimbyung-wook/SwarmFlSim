// IMP-DYN-005: 평지, 격자 DEM 쌍선형 보간, DEM 로더 인터페이스, 지면 교차 이벤트
// IMP-DYN-009: int16 격자, 원시 격자 + JSON 머리글 DEM 로더
// REQ-SIM-003, DEC-004, DEC-005, DEC-016, DEC-053
#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <vector>

#include "swarm/api/dynamics.hpp"

namespace swarm::dyn {

class FlatTerrain final : public Terrain {
 public:
  explicit FlatTerrain(double elevation_m = 0.0) : elevation_m_(elevation_m) {}
  double elevation_m(double, double) const override { return elevation_m_; }

 private:
  double elevation_m_;
};

// 위경도 등간격 격자. 노드 (r, c)의 위치는 (lat0 + r·dlat, lon0 + c·dlon), r = 0이 남쪽 끝
struct GridSpec {
  double lat0_deg = 0.0;
  double lon0_deg = 0.0;
  double dlat_deg = 0.0;
  double dlon_deg = 0.0;
  std::size_t rows = 0;  // 위도 방향 노드 수 (≥ 2)
  std::size_t cols = 0;  // 경도 방향 노드 수 (≥ 2)
};

// int16 격자 생성자 구분 표지. 중괄호 목록 {0, 10, ...}은 float 생성자로만 간다
struct Int16Heights {};
inline constexpr Int16Heights kInt16Heights{};

class GridTerrain final : public Terrain {
 public:
  // heights_m: rows × cols, 행 우선(남→북, 서→동). 격자 밖 조회는 outside_m를 돌려준다.
  // 형식이 맞지 않으면 std::invalid_argument
  GridTerrain(GridSpec spec, std::vector<float> heights_m, double outside_m = 0.0);
  // 정수 m 격자 (IMP-DYN-009). 한반도 90 m DEM(약 1억 노드)을 float의 절반 메모리로 둔다
  GridTerrain(Int16Heights, GridSpec spec, std::vector<std::int16_t> heights_m, double outside_m = 0.0);
  double elevation_m(double lat_deg, double lon_deg) const override;
  bool contains(double lat_deg, double lon_deg) const;
  const GridSpec& spec() const { return spec_; }

 private:
  void check() const;
  double at(std::size_t r, std::size_t c) const {
    const std::size_t i = r * spec_.cols + c;
    return h16_.empty() ? static_cast<double>(h_[i]) : static_cast<double>(h16_[i]);
  }
  GridSpec spec_;
  std::vector<float> h_;           // float 격자 (둘 중 하나만 쓴다)
  std::vector<std::int16_t> h16_;  // int16 격자
  double outside_m_;
};

// DEM 로더 (DEC-016, DEC-053)
class DemLoader {
 public:
  virtual ~DemLoader() = default;
  virtual std::unique_ptr<GridTerrain> load(const std::filesystem::path& path) const = 0;
};

// IMP-DYN-009: int16 원시 격자 + JSON 머리글 (scripts/fetch_dem.py가 만든다). path는 JSON 머리글 경로
// 필수 키: format="swarm-dem-grid", version=1, data_file(머리글 기준 상대 경로), sample_type="int16",
//   byte_order="little", row_order="south_to_north", rows, cols(≥ 2), lat0_deg, lon0_deg(0행 0열 노드),
//   dlat_deg, dlon_deg(> 0), units="m". 선택: nodata(정수, 그 값의 노드는 nodata_fill_m). 그 밖의 키는 무시한다.
// 자료 파일 크기는 rows·cols·2 바이트여야 한다. 형식 오류는 std::invalid_argument, 파일을 못 열면 std::runtime_error
class RawDemLoader final : public DemLoader {
 public:
  // outside_m: 격자 밖 조회 고도. nodata_fill_m: nodata 노드에 넣을 고도(정수 m로 반올림)
  explicit RawDemLoader(double outside_m = 0.0, double nodata_fill_m = 0.0)
      : outside_m_(outside_m), nodata_fill_m_(nodata_fill_m) {}
  std::unique_ptr<GridTerrain> load(const std::filesystem::path& header_json) const override;

 private:
  double outside_m_, nodata_fill_m_;
};

// g = 고도 − (지형 고도 + clearance_m). 양수에서 0 이하로 넘어가면 지면 교차(탄착·충돌)
// model과 terrain은 반환된 함수보다 오래 살아야 한다
EventFn make_ground_event(const DynamicsModel& model, const Terrain& terrain, double clearance_m = 0.0);

}  // namespace swarm::dyn
