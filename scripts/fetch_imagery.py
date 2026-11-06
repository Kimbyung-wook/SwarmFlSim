# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""한반도 영상 타일을 내려받아 로컬 TMS로 저장한다 (IMP-UI-069, DEC-057, REQ-SIM-003).

기본 자료: EOxCloudless (Sentinel-2 cloudless) 최신판 WMTS, Web Mercator(GoogleMapsCompatible).
  라이선스 CC BY-NC-SA 4.0 (비상업). 표기:
  "Sentinel-2 cloudless by EOX IT Services GmbH (Contains modified Copernicus Sentinel data <year>)"

!! 약관 주의 !!
  EOX는 공개 엔드포인트의 비상업적 직접 사용을 허용하지만, 요청을 분산하고 큰 묶음을 한꺼번에
  보내지 말라고 하며, 오프라인 일괄 제공은 유료 상품·문의(cloudless@eox.at)로 안내한다.
  z13까지 약 6.2만 장(62,214) 일괄 받기가 허용되는지는 약관에 명시되어 있지 않다(2026-11 확인).
  그래서 EOX 원본에서 받으려면 EOX에서 서면 허가를 받은 뒤 --eox-permission 을 주어야 한다.
  허가가 없으면 타일 수만 계산하고 끝낸다. 다른 출처(자체 타일 서버 등)는 --template 으로 준다.

범위: 위도 33~43°N, 경도 124~131°E, 줌 0~13 (기본).
출력 (저장소에 커밋하지 않는다. .gitignore의 data/tiles/):
  data/tiles/imagery/{z}/{x}/{y}.jpg   TMS 행 번호(남쪽이 0)
  data/tiles/imagery/tilemapresource.xml  Cesium TileMapServiceImageryProvider가 읽는다
  data/tiles/imagery/fetch_state.json  실패 목록 (다시 실행하면 있는 타일은 건너뛰고 이어 받는다)

실행:
  uv run scripts/fetch_imagery.py --count                       # 타일 수만
  uv run scripts/fetch_imagery.py --eox-permission [--rate 2]   # EOX 허가를 받은 경우
  uv run scripts/fetch_imagery.py --template "https://my.server/{z}/{x}/{y}.jpg" --year 2025
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2025
EOX_TEMPLATE = (
    "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-{year}_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg"
)
USER_AGENT = "swarm-flight-offline-tiles/1.0 (non-commercial research)"


def lon_to_x(lon: float, z: int) -> int:
    n = 1 << z
    return min(n - 1, max(0, int((lon + 180.0) / 360.0 * n)))


def lat_to_y(lat: float, z: int) -> int:
    """XYZ 행 번호 (북쪽이 0)"""
    n = 1 << z
    r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n
    return min(n - 1, max(0, int(y)))


def tile_ranges(s: float, n: float, w: float, e: float, zmin: int, zmax: int):
    for z in range(zmin, zmax + 1):
        yield z, lon_to_x(w, z), lon_to_x(e, z), lat_to_y(n, z), lat_to_y(s, z)


def count_tiles(ranges) -> int:
    return sum((x1 - x0 + 1) * (y1 - y0 + 1) for _, x0, x1, y0, y1 in ranges)


def write_tilemap(out: Path, s: float, n: float, w: float, e: float, zmin: int, zmax: int, title: str) -> None:
    """gdal2tiles 'mercator' 프로파일: BoundingBox는 위경도(도). Cesium이 이 범위 안 타일만 요청한다."""
    sets = "\n".join(
        f'      <TileSet href="{z}" units-per-pixel="{156543.03392804097 / (1 << z):.10f}" order="{z}"/>'
        for z in range(zmin, zmax + 1)
    )
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<TileMap version="1.0.0" tilemapservice="http://tms.osgeo.org/1.0.0">
  <Title>{title}</Title>
  <Abstract></Abstract>
  <SRS>EPSG:3857</SRS>
  <BoundingBox minx="{w}" miny="{s}" maxx="{e}" maxy="{n}"/>
  <Origin x="{w}" y="{s}"/>
  <TileFormat width="256" height="256" mime-type="image/jpeg" extension="jpg"/>
  <TileSets profile="mercator">
{sets}
  </TileSets>
</TileMap>
"""
    (out / "tilemapresource.xml").write_text(xml, encoding="utf-8")


class Fetcher:
    """요청 간격 제한 + 재시도(지수 백오프, Retry-After 존중). HTML 응답(차단·안내 페이지)은 실패로 본다."""

    def __init__(self, rate: float, retries: int):
        self.interval = 1.0 / rate
        self.retries = retries
        self.next_at = 0.0

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self.next_at:
            time.sleep(self.next_at - now)
        self.next_at = max(now, self.next_at) + self.interval

    def get(self, url: str) -> bytes | None:
        """타일 바이트. 404(타일 없음)면 None. 끝내 실패하면 예외."""
        delay = 2.0
        for attempt in range(self.retries + 1):
            self._wait()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=60) as r:
                    ctype = r.headers.get("Content-Type", "")
                    data = r.read()
                if not ctype.startswith("image/"):
                    raise RuntimeError(f"not an image ({ctype}), probably rate-limited")
                return data
            except urllib.error.HTTPError as ex:
                if ex.code == 404:
                    return None
                if ex.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise
                ra = ex.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else delay
            except (urllib.error.URLError, TimeoutError, RuntimeError):
                if attempt == self.retries:
                    raise
                wait = delay
            # 서버가 느려지라는 신호: 간격도 늘린다
            self.interval = min(self.interval * 1.5, 10.0)
            time.sleep(wait + random.uniform(0, 1))
            delay = min(delay * 2, 300.0)
        raise RuntimeError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "tiles" / "imagery")
    ap.add_argument("--lat", type=float, nargs=2, default=(33.0, 43.0), metavar=("S", "N"))
    ap.add_argument("--lon", type=float, nargs=2, default=(124.0, 131.0), metavar=("W", "E"))
    ap.add_argument("--zoom", type=int, nargs=2, default=(0, 13), metavar=("MIN", "MAX"))
    ap.add_argument("--year", type=int, default=YEAR, help="EOxCloudless 연도판 (기본 %(default)s)")
    ap.add_argument("--template", help="XYZ 타일 URL 템플릿 ({z},{x},{y}; y는 북쪽이 0). 주면 EOX 대신 쓴다")
    ap.add_argument("--eox-permission", action="store_true", help="EOX에서 일괄 받기 허가를 받았음 (기본 출처에 필요)")
    ap.add_argument("--rate", type=float, default=2.0, help="초당 요청 수 상한 (기본 %(default)s)")
    ap.add_argument("--retries", type=int, default=6)
    ap.add_argument("--count", action="store_true", help="타일 수만 출력")
    args = ap.parse_args()
    (s, n), (w, e), (zmin, zmax) = args.lat, args.lon, args.zoom
    if not (s < n and w < e and 0 <= zmin <= zmax <= 18):
        ap.error("bad range")

    ranges = list(tile_ranges(s, n, w, e, zmin, zmax))
    total = count_tiles(ranges)
    print(f"tiles z{zmin}-z{zmax}: {total}", file=sys.stderr)
    for z, x0, x1, y0, y1 in ranges:
        print(f"  z{z}: x {x0}-{x1}, y {y0}-{y1} ({(x1 - x0 + 1) * (y1 - y0 + 1)})", file=sys.stderr)
    if args.count:
        return 0
    if not args.template and not args.eox_permission:
        print(
            "Bulk download from EOX needs written permission from EOX (cloudless@eox.at).\n"
            "Pass --eox-permission once granted, or --template for another source. Nothing was downloaded.",
            file=sys.stderr,
        )
        return 2

    template = args.template or EOX_TEMPLATE.replace("{year}", str(args.year))
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_tilemap(out, s, n, w, e, zmin, zmax, f"Sentinel-2 cloudless {args.year} (EOX)")
    fetcher = Fetcher(args.rate, args.retries)
    state_path = out / "fetch_state.json"
    failed: list[str] = []
    done = skipped = missing = 0
    nbytes = 0
    t0 = time.monotonic()
    try:
        for z, x0, x1, y0, y1 in ranges:
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    tms_y = (1 << z) - 1 - y
                    path = out / str(z) / str(x) / f"{tms_y}.jpg"
                    if path.exists() and path.stat().st_size > 0:
                        skipped += 1
                        continue
                    url = template.format(z=z, x=x, y=y)
                    try:
                        data = fetcher.get(url)
                    except Exception as ex:  # noqa: BLE001 - 실패는 기록하고 다음 실행에서 이어 받는다
                        failed.append(f"{z}/{x}/{y}: {ex}")
                        continue
                    if data is None:
                        missing += 1
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(".part")
                    tmp.write_bytes(data)
                    tmp.replace(path)
                    done += 1
                    nbytes += len(data)
                    if done % 500 == 0:
                        el = time.monotonic() - t0
                        print(f"  {done + skipped}/{total} ({nbytes / 1e6:.1f} MB, {el:.0f} s)", file=sys.stderr)
    finally:
        state = {
            "template": template,
            "total": total,
            "downloaded": done,
            "skipped_existing": skipped,
            "missing_404": missing,
            "failed": failed,
            "bytes": nbytes,
            "seconds": round(time.monotonic() - t0, 1),
        }
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"downloaded {done}, existing {skipped}, 404 {missing}, failed {len(failed)}, "
        f"{nbytes / 1e6:.1f} MB in {state['seconds']} s",
        file=sys.stderr,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
