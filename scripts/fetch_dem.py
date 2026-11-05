# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26", "tifffile>=2024.1", "imagecodecs>=2024.1"]
# ///
"""한반도 DEM을 내려받아 하나의 격자로 합친다 (IMP-CORE-023, DEC-053, DEC-004).

자료: Copernicus DEM GLO-90 (3″, 약 90 m), AWS 공개 버킷 copernicus-dem-90m (HTTPS, 인증 없음).
범위: 위도 33~43°N, 경도 124~131°E (양 끝 포함). 바다라 타일이 없으면 0 m로 채운다.
출력 (저장소에 커밋하지 않는다. .gitignore의 data/dem/):
  data/dem/korea_glo90.bin   int16 little-endian, 행 우선, 0행 = 남쪽 끝, 서→동
  data/dem/korea_glo90.json  머리글 (형식은 dynamics/include/swarm/dyn/terrain.hpp의 RawDemLoader)
  data/dem/tiles/            내려받은 원본 타일 (다시 실행하면 재사용)

실행: uv run scripts/fetch_dem.py [--out data/dem] [--lat 33 43] [--lon 124 131]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import tifffile

ROOT = Path(__file__).resolve().parents[1]
BUCKET = "https://copernicus-dem-90m.s3.amazonaws.com"
PER_DEG = 1200  # 3″ 격자. 위도 50° 미만 타일은 가로·세로 1200 화소
NAME = "korea_glo90"
SOURCE = "Copernicus DEM GLO-90 (DGED/COG 30), s3://copernicus-dem-90m"
LICENSE = (
    "Copernicus DEM GLO-90, free and open licence. "
    "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 "
    "provided under COPERNICUS by the European Union and ESA; all rights reserved"
)


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_30_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def fetch_tile(lat: int, lon: int, tiles: Path) -> Path | None:
    """타일을 받아 경로를 돌려준다. 버킷에 없으면(바다) None."""
    name = tile_name(lat, lon)
    path = tiles / f"{name}.tif"
    missing = tiles / f"{name}.missing"
    if path.exists():
        return path
    if missing.exists():
        return None
    url = f"{BUCKET}/{name}/{name}.tif"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            missing.write_text(f"{e.code}\n")
            return None
        raise
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def read_tile(path: Path) -> tuple[np.ndarray, float, float]:
    """(고도, 0행 0열 화소 중심의 위도, 경도). 화소 중심 등록(PixelIsPoint)을 확인한다."""
    with tifffile.TiffFile(path) as t:
        p = t.pages[0]
        sx, sy, _ = p.tags["ModelPixelScaleTag"].value
        _, _, _, lon0, lat0, _ = p.tags["ModelTiepointTag"].value
        geokeys = p.tags["GeoKeyDirectoryTag"].value
        a = p.asarray()
    keys = {geokeys[i]: geokeys[i + 3] for i in range(4, len(geokeys), 4)}
    if keys.get(1025) != 2:  # GTRasterTypeGeoKey = RasterPixelIsPoint
        raise SystemExit(f"{path.name}: expected PixelIsPoint registration")
    if not (math.isclose(sx, 1 / PER_DEG) and math.isclose(sy, 1 / PER_DEG)):
        raise SystemExit(f"{path.name}: unexpected pixel scale {sx}, {sy}")
    return a, lat0, lon0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "dem")
    ap.add_argument("--lat", type=int, nargs=2, default=(33, 43), metavar=("S", "N"))
    ap.add_argument("--lon", type=int, nargs=2, default=(124, 131), metavar=("W", "E"))
    args = ap.parse_args()
    (s, n), (w, e) = args.lat, args.lon
    if not (s < n and w < e):
        ap.error("bad range")

    out: Path = args.out
    tiles = out / "tiles"
    tiles.mkdir(parents=True, exist_ok=True)
    rows, cols = (n - s) * PER_DEG + 1, (e - w) * PER_DEG + 1
    grid = np.zeros((rows, cols), dtype=np.int16)  # 0행 = 위도 s

    # 타일 (L, Lo)의 화소 (r, c) 중심은 위도 L+1 - r/1200, 경도 Lo + c/1200.
    # 남쪽 끝 행(위도 s)은 타일 L = s-1의 맨 위 행, 동쪽 끝 열(경도 e)은 타일 Lo = e의 맨 왼쪽 열이다.
    present, absent = [], []
    for lat in range(s - 1, n):
        for lon in range(w, e + 1):
            path = fetch_tile(lat, lon, tiles)
            if path is None:
                absent.append(tile_name(lat, lon))
                continue
            present.append(tile_name(lat, lon))
            a, lat0, lon0 = read_tile(path)
            i_top = round((lat0 - s) * PER_DEG)  # 타일 0행의 격자 행
            j_left = round((lon0 - w) * PER_DEG)
            th, tw = a.shape
            # 격자 행 i = i_top - r, 열 j = j_left + c
            r0, r1 = max(0, i_top - (rows - 1)), min(th, i_top + 1)
            c0, c1 = max(0, -j_left), min(tw, cols - j_left)
            if r0 >= r1 or c0 >= c1:
                continue
            block = np.rint(np.nan_to_num(a[r0:r1, c0:c1], nan=0.0)).clip(-32767, 32767).astype(np.int16)
            grid[i_top - r1 + 1 : i_top - r0 + 1, j_left + c0 : j_left + c1] = block[::-1]
            print(f"{tile_name(lat, lon)}: ok", file=sys.stderr)

    bin_path = out / f"{NAME}.bin"
    grid.astype("<i2").tofile(bin_path)
    header = {
        "format": "swarm-dem-grid",
        "version": 1,
        "data_file": bin_path.name,
        "sample_type": "int16",
        "byte_order": "little",
        "row_order": "south_to_north",
        "rows": rows,
        "cols": cols,
        "lat0_deg": float(s),
        "lon0_deg": float(w),
        "dlat_deg": 1 / PER_DEG,
        "dlon_deg": 1 / PER_DEG,
        "units": "m",
        "horizontal_datum": "WGS84",
        "vertical_datum": "EGM2008",
        "nodata": -32768,
        "source": SOURCE,
        "license": LICENSE,
        "tiles_present": len(present),
        "tiles_absent_filled_0m": absent,
    }
    (out / f"{NAME}.json").write_text(json.dumps(header, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"{bin_path} {rows}x{cols} int16 ({bin_path.stat().st_size} bytes), "
        f"tiles {len(present)} present / {len(absent)} absent, max {int(grid.max())} m",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
