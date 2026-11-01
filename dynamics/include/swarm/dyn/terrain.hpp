// IMP-DYN-005: 평지, 격자 DEM 쌍선형 보간, DEM 로더 인터페이스, 지면 교차 이벤트
// REQ-SIM-003, DEC-004, DEC-005, DEC-016
#pragma once

#include <cstddef>
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

class GridTerrain final : public Terrain {
 public:
  // heights_m: rows × cols, 행 우선(남→북, 서→동). 격자 밖 조회는 outside_m를 돌려준다.
  // 형식이 맞지 않으면 std::invalid_argument
  GridTerrain(GridSpec spec, std::vector<float> heights_m, double outside_m = 0.0);
  double elevation_m(double lat_deg, double lon_deg) const override;
  bool contains(double lat_deg, double lon_deg) const;
  const GridSpec& spec() const { return spec_; }

 private:
  GridSpec spec_;
  std::vector<float> h_;
  double outside_m_;
};

// 한반도 전역 저해상도 DEM 로더 자리 (DEC-016). 파일 형식이 정해지면 구현한다
class DemLoader {
 public:
  virtual ~DemLoader() = default;
  virtual std::unique_ptr<GridTerrain> load(const std::filesystem::path& path) const = 0;
};

// g = 고도 − (지형 고도 + clearance_m). 양수에서 0 이하로 넘어가면 지면 교차(탄착·충돌)
// model과 terrain은 반환된 함수보다 오래 살아야 한다
EventFn make_ground_event(const DynamicsModel& model, const Terrain& terrain, double clearance_m = 0.0);

}  // namespace swarm::dyn
