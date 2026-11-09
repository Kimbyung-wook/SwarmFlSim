# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26"]
# ///
"""GLO-90 DEM 격자를 Cesium 지형 타일(heightmap-1.0)로 바꾼다 (IMP-UI-070, DEC-057, REQ-SIM-003).

입력: data/dem/korea_glo90.{json,bin} (scripts/fetch_dem.py가 만든다. 형식은 계약 §6)
출력 (저장소에 커밋하지 않는다. .gitignore의 data/tiles/):
  data/tiles/terrain/layer.json
  data/tiles/terrain/{z}/{x}/{y}.terrain   gzip 압축 heightmap-1.0 (Vite 개발 서버가 Content-Encoding을 붙인다)

형식: Cesium heightmap-1.0, EPSG:4326 지리 좌표 타일링(0레벨 2×1장), TMS 행 번호(남쪽이 0).
  타일마다 65×65 표본(가장자리 공유), uint16 LE = (높이 m + 1000) × 5, 북→남 행, 서→동 열,
  다음 1바이트 자식 마스크(bit0 남서, bit1 남동, bit2 북서, bit3 북동), 1바이트 물 마스크(0 = 육지).
  높이는 DEM 값(EGM2008 정표고) 그대로 쓴다. 동역학 지형(RawDemLoader)과 같은 높이를 보이기 위함이다.
  DEM 범위 밖과 바다는 0 m.
레벨: 기본 0~12 (12레벨 표본 간격 ≈ 0.00069° ≈ 77 m, GLO-90 3″ ≈ 0.00083°).
  표본 간격이 DEM보다 넓은 레벨은 2배씩 평균한 피라미드에서 뽑아 산 봉우리 깜빡임을 줄인다.
외부 바이너리는 필요 없다 (numpy만).

실행: uv run scripts/make_terrain_tiles.py [--dem data/dem/korea_glo90.json] [--out data/tiles/terrain] [--max-level 12]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
N = 65  # 타일 한 변 표본 수
OFFSET, SCALE = 1000.0, 5.0  # heightmap-1.0 기본 부호화


class Grid:
    """한 피라미드 단계. (lat0, lon0)은 0행 0열 표본 위치, d는 간격(도)"""

    def __init__(self, z: np.ndarray, lat0: float, lon0: float, dlat: float, dlon: float):
        self.z, self.lat0, self.lon0, self.dlat, self.dlon = z, lat0, lon0, dlat, dlon

    def half(self) -> "Grid":
        r, c = (self.z.shape[0] // 2) * 2, (self.z.shape[1] // 2) * 2
        a = self.z[:r, :c]
        m = (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]) * 0.25
        return Grid(m, self.lat0 + self.dlat / 2, self.lon0 + self.dlon / 2, self.dlat * 2, self.dlon * 2)

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """쌍선형 보간. 격자 밖은 0"""
        fi = (lat - self.lat0) / self.dlat
        fj = (lon - self.lon0) / self.dlon
        rows, cols = self.z.shape
        inside = (fi >= 0) & (fi <= rows - 1) & (fj >= 0) & (fj <= cols - 1)
        fi = np.clip(fi, 0, rows - 1)
        fj = np.clip(fj, 0, cols - 1)
        i0 = np.minimum(np.floor(fi).astype(np.int64), rows - 2)
        j0 = np.minimum(np.floor(fj).astype(np.int64), cols - 2)
        ti, tj = fi - i0, fj - j0
        z = self.z
        v = (
            z[i0, j0] * (1 - ti) * (1 - tj)
            + z[i0 + 1, j0] * ti * (1 - tj)
            + z[i0, j0 + 1] * (1 - ti) * tj
            + z[i0 + 1, j0 + 1] * ti * tj
        )
        return np.where(inside, v, 0.0)


def load_dem(path: Path) -> tuple[Grid, dict]:
    h = json.loads(path.read_text(encoding="utf-8"))
    if h.get("format") != "swarm-dem-grid" or h.get("row_order") != "south_to_north":
        raise SystemExit(f"{path}: unsupported DEM header")
    raw = np.fromfile(path.with_name(h["data_file"]), dtype="<i2").reshape(h["rows"], h["cols"])
    z = raw.astype(np.float32)
    z[raw == h.get("nodata", -32768)] = 0.0
    return Grid(z, h["lat0_deg"], h["lon0_deg"], h["dlat_deg"], h["dlon_deg"]), h


def tile_rect(level: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(서, 남, 동, 북) 도. TMS y(남쪽이 0)"""
    span = 180.0 / (1 << level)
    w, s = -180.0 + x * span, -90.0 + y * span
    return w, s, w + span, s + span


def tiles_over(level: int, w: float, s: float, e: float, n: float) -> tuple[int, int, int, int]:
    """DEM 사각형과 겹치는 타일 범위 (x0, y0, x1, y1), 끝 포함"""
    span = 180.0 / (1 << level)
    nx, ny = 2 << level, 1 << level
    x0 = max(0, int(math.floor((w + 180.0) / span)))
    x1 = min(nx - 1, int(math.floor((e + 180.0) / span - 1e-12)))
    y0 = max(0, int(math.floor((s + 90.0) / span)))
    y1 = min(ny - 1, int(math.floor((n + 90.0) / span - 1e-12)))
    return x0, y0, x1, y1


def encode(heights: np.ndarray, child_mask: int) -> bytes:
    q = np.clip(np.rint((heights + OFFSET) * SCALE), 0, 65535).astype("<u2")
    # 물 마스크 1바이트(0 = 전부 육지). Cesium은 자식 마스크 뒤 바이트를 늘 물 마스크로 읽어 비면 렌더가 멈춘다
    return gzip.compress(q.tobytes() + bytes([child_mask, 0]), compresslevel=6, mtime=0)


def main() -> int:
    # cp949 콘솔에서 --help의 비 cp949 문자로 끝나지 않게 한다
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dem", type=Path, default=ROOT / "data" / "dem" / "korea_glo90.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "tiles" / "terrain")
    ap.add_argument("--max-level", type=int, default=12)
    args = ap.parse_args()
    if not args.dem.exists():
        print(f"{args.dem} not found: run `uv run scripts/fetch_dem.py` first", file=sys.stderr)
        return 2

    t0 = time.monotonic()
    base, hdr = load_dem(args.dem)
    rows, cols = base.z.shape
    w, s = base.lon0, base.lat0
    e, n = w + (cols - 1) * base.dlon, s + (rows - 1) * base.dlat
    pyramid = [base]
    while min(pyramid[-1].z.shape) >= 4:
        pyramid.append(pyramid[-1].half())

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    maxl = args.max_level
    ranges = [tiles_over(L, w, s, e, n) for L in range(maxl + 1)]
    available: list[list[dict]] = []
    count = nbytes = 0
    k = np.arange(N) / (N - 1)
    for L in range(maxl + 1):
        span = 180.0 / (1 << L)
        step = span / (N - 1)
        # 표본 간격 이하로 가장 거친 피라미드 단계
        g = pyramid[0]
        for p in pyramid:
            if p.dlat <= step:
                g = p
        if L == 0:
            # 0레벨은 지구 전체 2장이 있어야 한다
            xs, ys = range(2), range(1)
            available.append([{"startX": 0, "startY": 0, "endX": 1, "endY": 0}])
        else:
            x0, y0, x1, y1 = ranges[L]
            xs, ys = range(x0, x1 + 1), range(y0, y1 + 1)
            available.append([{"startX": x0, "startY": y0, "endX": x1, "endY": y1}])
        nxt = ranges[L + 1] if L < maxl else None
        for x in xs:
            for y in ys:
                tw, ts, te, tn = tile_rect(L, x, y)
                lat = tn - k * span  # 북→남
                lon = tw + k * span
                hgt = g.sample(lat[:, None], lon[None, :])
                mask = 0
                if nxt:
                    cx0, cy0, cx1, cy1 = nxt
                    for bit, (cx, cy) in enumerate(((2 * x, 2 * y), (2 * x + 1, 2 * y), (2 * x, 2 * y + 1), (2 * x + 1, 2 * y + 1))):
                        if cx0 <= cx <= cx1 and cy0 <= cy <= cy1:
                            mask |= 1 << bit
                data = encode(hgt, mask)
                p = out / str(L) / str(x) / f"{y}.terrain"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                count += 1
                nbytes += len(data)
        print(f"  level {L}: {len(xs) * len(ys)} tiles", file=sys.stderr)

    layer = {
        "tilejson": "2.1.0",
        "name": "korea_glo90",
        "description": hdr.get("source", ""),
        "license": hdr.get("license", ""),  # 화면 표기는 UI가 붙인다 (attribution이면 Cesium이 겹쳐 띄움)
        "format": "heightmap-1.0",
        "version": "1.0.0",
        "scheme": "tms",
        "projection": "EPSG:4326",
        "tiles": ["{z}/{x}/{y}.terrain?v={version}"],
        "minzoom": 0,
        "maxzoom": maxl,
        "bounds": [w, s, e, n],
        "available": available,
    }
    (out / "layer.json").write_text(json.dumps(layer, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"{out}: {count} tiles, {nbytes / 1e6:.1f} MB, levels 0-{maxl}, {time.monotonic() - t0:.0f} s",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
