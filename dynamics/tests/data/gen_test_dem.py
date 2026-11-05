"""시험용 합성 DEM ridge.{json,bin}을 만든다 (TC-DYN-015, TC-CORE-036~037, DEC-053).
형식은 scripts/fetch_dem.py의 결과와 같다 (int16 little-endian, 0행 = 남쪽, JSON 머리글).
격자: 위도 36.9..37.1, 경도 126.9..127.1, 간격 0.002도(약 220 m), 101 x 101.
지형: 위도 37.008을 중심으로 동서로 뻗은 능선. 반폭 0.004도 삼각 단면, 정점 1200 m, 그 밖은 0 m.
남서 모서리 노드 하나는 nodata(-32768)다.
실행: python gen_test_dem.py  (이 파일 옆에 쓴다. 표준 라이브러리만 쓴다)
"""

import json
import pathlib
import struct

N, D, LAT0, LON0 = 101, 0.002, 36.9, 126.9
NODATA = -32768
here = pathlib.Path(__file__).parent


def ridge(lat: float) -> int:
    return max(0, round(1200 * (1 - abs(lat - 37.008) / 0.004)))


values = []
for r in range(N):  # 남 → 북
    h = ridge(LAT0 + r * D)
    values.extend([h] * N)
values[0] = NODATA
(here / "ridge.bin").write_bytes(struct.pack(f"<{len(values)}h", *values))
header = {
    "format": "swarm-dem-grid",
    "version": 1,
    "data_file": "ridge.bin",
    "sample_type": "int16",
    "byte_order": "little",
    "row_order": "south_to_north",
    "rows": N,
    "cols": N,
    "lat0_deg": LAT0,
    "lon0_deg": LON0,
    "dlat_deg": D,
    "dlon_deg": D,
    "units": "m",
    "nodata": NODATA,
    "source": "synthetic (dynamics/tests/data/gen_test_dem.py)",
}
(here / "ridge.json").write_text(json.dumps(header, indent=2) + "\n", encoding="utf-8", newline="\n")
