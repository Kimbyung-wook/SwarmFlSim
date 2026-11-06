# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26", "rasterio>=1.4", "pillow>=10", "psutil>=5.9"]
# ///
"""AWS 공개 Sentinel-2 L2A 장면을 자체 합성해 한반도 영상 타일을 만든다 (IMP-UI-072, DEC-059, REQ-SIM-003).

자료: Earth Search(Element 84) STAC 컬렉션 sentinel-2-c1-l2a — AWS 공개 버킷의 Copernicus Sentinel-2
  L2A COG. 계정·키 없이 HTTPS로 읽는다. 밴드 B04/B03/B02(10 m)와 SCL(장면 분류, 20 m)만 쓴다.
  반사율 = 화소값(DN) × scale + offset (STAC raster:bands의 scale·offset을 그대로 적용).
이용 조건: Copernicus Sentinel 데이터 법적 고지(Regulation (EU) No 1159/2013) — 자유·완전·공개 이용,
  수정본을 배포하면 "Contains modified Copernicus Sentinel data [Year]". UI 표기는 mapCredits.ts.

단계 (다시 실행하면 이미 만든 합성·타일은 건너뛰고 이어 한다):
  1. 장면 찾기: 기간(--start~--end, 기본 최근 1년) 중 --months(기본 9~11월, 가을) 안에서
     장면 구름 비율 --max-cloud 이하인 장면을 MGRS 타일별로 모은다.
  2. 합성(MGRS 타일마다): 구름·결측이 적은 순으로 --candidates 장면의 SCL만 먼저 읽어(장당 약 3 MB)
     유효 화소(--scl-valid, 기본 식생·나지·물·눈)를 센다.
     --method best(기본): 유효 화소를 가장 많이 더하는 장면부터 고르고, 새로 메우는 화소가 --min-gain
       미만이면 멈춘다(최대 --max-scenes). 먼저 고른 장면의 화소가 우선이다.
     --method median: 유효 화소가 많은 --max-scenes 장면을 모두 읽어 화소별 중앙값.
     둘 다 끝까지 빈 화소는 고른 장면에서 구름(8·9·10)·포화(1)만 아니면 채운다.
     밴드는 COG 개관으로 --src-res(기본 20 m)만 읽는다. z13은 한반도에서 14~16 m/px라 10 m 원본이 필요 없다.
     결과: data/s2composite/<기간태그>/<MGRS>.tif (3밴드 int16 = 반사율 × 10000, 결측 -32768).
  3. 타일: z13 Web Mercator 타일을 재투영·합성해 8비트 RGB로 바꾸고, z12~z0은 아래 레벨 4장을 줄여 만든다.
     data/tiles/imagery/{z}/{x}/{y}.jpg (TMS 행 번호) + tilemapresource.xml + source.json.
색 보정: v = clip((반사율 - black) / (white - black), 0, 1) ** (1 / gamma) × 255, 세 밴드 공통.
결측(먼 바다·남은 구멍): --nodata-rgb로 채운다. z > --keep-empty-below 인데 전부 결측인 타일은 쓰지 않는다
  (Cesium은 없는 타일 대신 상위 타일을 늘려 보인다).

실행:
  uv run scripts/make_s2_composite_tiles.py --list           # MGRS 타일·장면 수만
  uv run scripts/make_s2_composite_tiles.py                  # 찾기 → 합성 → 타일
  uv run scripts/make_s2_composite_tiles.py --months 4 5 --method median --white 0.28 --gamma 1.6
  uv run scripts/make_s2_composite_tiles.py --tiles-only     # 합성은 그대로 두고 색·타일만 다시
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_imagery import tile_ranges, write_tilemap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STAC = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-c1-l2a"
BANDS = ("red", "green", "blue")  # B04, B03, B02
NODATA = -32768
SCL_BAD = (0, 1, 8, 9, 10)  # 결측, 포화, 구름(중·고), 권운 — 마지막 채움에서도 쓰지 않음
WEB_MERC_HALF = 20037508.342789244
UA = "swarm-flight-s2-composite/1.0 (non-commercial research)"
GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MULTIRANGE="YES",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MAX_RETRY="8",
    GDAL_HTTP_RETRY_DELAY="3",
    GDAL_HTTP_USERAGENT=UA,
    GDAL_CACHEMAX=256,
)


# ---------------------------------------------------------------- 장면 찾기

def date_windows(start: dt.date, end: dt.date, months: list[int]) -> list[tuple[dt.date, dt.date]]:
    """[start, end] 중 months에 드는 연속 구간들"""
    out: list[tuple[dt.date, dt.date]] = []
    d = start
    while d <= end:
        if d.month in months:
            s = d
            while d <= end and d.month in months:
                d += dt.timedelta(days=1)
            out.append((s, d - dt.timedelta(days=1)))
        else:
            d += dt.timedelta(days=1)
    return out


def stac_search(bbox, win: tuple[dt.date, dt.date], max_cloud: float) -> list[dict]:
    body = {
        "collections": [COLLECTION], "bbox": list(bbox), "limit": 200,
        "datetime": f"{win[0].isoformat()}T00:00:00Z/{win[1].isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
    }
    items: list[dict] = []
    while True:
        req = urllib.request.Request(STAC, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    page = json.load(r)
                break
            except Exception:  # noqa: BLE001
                if attempt == 4:
                    raise
                time.sleep(5 * (attempt + 1))
        items += page["features"]
        nxt = next((ln for ln in page.get("links", []) if ln.get("rel") == "next"), None)
        if not nxt or not page["features"]:
            return items
        body = nxt.get("body", body)


def scene_record(it: dict) -> dict:
    p = it["properties"]
    rec = {"id": it["id"], "datetime": p["datetime"], "cloud": p.get("eo:cloud_cover", 100.0),
           "nodata_pct": p.get("s2:nodata_pixel_percentage", 0.0), "bbox": it["bbox"]}
    for k in (*BANDS, "scl"):
        a = it["assets"][k]
        rb = (a.get("raster:bands") or [{}])[0]
        rec[k] = {"href": a["href"], "scale": rb.get("scale", 1.0), "offset": rb.get("offset", 0.0)}
    return rec


def find_scenes(args) -> dict[str, list[dict]]:
    (s, n), (w, e) = args.lat, args.lon
    by_grid: dict[str, list[dict]] = {}
    seen = set()
    for win in date_windows(args.start, args.end, args.months):
        for it in stac_search((w, s, e, n), win, args.max_cloud):
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            g = it["properties"].get("grid:code", it["id"].split("_")[1])
            by_grid.setdefault(g.replace("MGRS-", ""), []).append(scene_record(it))
    for g in by_grid:
        by_grid[g].sort(key=lambda r: (r["cloud"] + r["nodata_pct"], r["datetime"]))
    return dict(sorted(by_grid.items()))


# ---------------------------------------------------------------- 합성

def _open_level(href: str, native_m: int, want_m: int):
    """want_m 해상도 개관을 연다. 원본보다 거칠게만 (개관 배율 2, 4, 8...)"""
    import rasterio

    f = want_m // native_m
    if f <= 1:
        return rasterio.open(href)
    return rasterio.open(href, overview_level=int(math.log2(f)) - 1)


def _read_scl(rec: dict, res: int) -> np.ndarray:
    with _open_level(rec["scl"]["href"], 20, res) as ds:
        a = ds.read(1)
    if res < 20:  # 10 m 요청이면 20 m SCL을 2배로
        a = np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
    return a


def _read_rgb(rec: dict, res: int):
    """(3, H, W) int16 반사율 × 10000, 원본 결측은 NODATA. 그리고 프로파일"""
    def one(k):
        with _open_level(rec[k]["href"], 10, res) as ds:
            return ds.read(1), dict(crs=ds.crs, transform=ds.transform, width=ds.width, height=ds.height)

    with ThreadPoolExecutor(3) as ex:
        parts = list(ex.map(one, BANDS))
    out = np.empty((3, *parts[0][0].shape), dtype=np.int16)
    for i, (k, (dn, _)) in enumerate(zip(BANDS, parts)):
        sc, of = rec[k]["scale"], rec[k]["offset"]
        v = np.rint((dn.astype(np.float32) * sc + of) * 10000.0)
        out[i] = np.where(dn == 0, NODATA, np.clip(v, -1000, 32767)).astype(np.int16)
    return out, parts[0][1]


def composite_grid(grid: str, scenes: list[dict], cfg: dict) -> dict:
    import rasterio
    from rasterio.warp import transform_bounds

    dst = Path(cfg["comp_dir"]) / f"{grid}.tif"
    info_path = dst.with_suffix(".json")
    if dst.exists() and info_path.exists():
        return json.loads(info_path.read_text(encoding="utf-8"))
    res = cfg["src_res"]
    valid_cls = np.array(cfg["scl_valid"], dtype=np.uint8)
    t0 = time.monotonic()
    with rasterio.Env(**GDAL_ENV):
        cands = scenes[: cfg["candidates"]]
        scls = []
        for rec in cands:
            try:
                scls.append(_read_scl(rec, res))
            except Exception as ex:  # noqa: BLE001 - 깨진 장면은 건너뛴다
                print(f"    {grid}: skip {rec['id']} ({ex})", file=sys.stderr)
                scls.append(None)
        shape = next((a.shape for a in scls if a is not None), None)
        if shape is None:
            return {"grid": grid, "error": "no readable scene"}
        good = [(rec, a) for rec, a in zip(cands, scls) if a is not None and a.shape == shape]
        masks = [np.isin(a, valid_cls) for _, a in good]
        npx = shape[0] * shape[1]

        if cfg["method"] == "median":
            order = sorted(range(len(good)), key=lambda i: -int(masks[i].sum()))[: cfg["max_scenes"]]
        else:
            order, cover = [], np.zeros(shape, dtype=bool)
            while len(order) < cfg["max_scenes"]:
                gains = [(int((m & ~cover).sum()), i) for i, m in enumerate(masks) if i not in order]
                if not gains:
                    break
                gain, i = max(gains)
                if order and gain < cfg["min_gain"] * npx:
                    break
                order.append(i)
                cover |= masks[i]

        stack, prof = [], None
        for i in order:
            rgb, p = _read_rgb(good[i][0], res)
            if rgb.shape[1:] != shape:
                continue
            prof = prof or p
            stack.append((i, rgb))
    if not stack:
        return {"grid": grid, "error": "no scene read"}

    acc = np.full((3, *shape), NODATA, dtype=np.int16)
    if cfg["method"] == "median":
        # 행 띠 단위로 중앙값 (메모리 절약)
        for r0 in range(0, shape[0], 512):
            r1 = min(shape[0], r0 + 512)
            vals = np.stack([rgb[:, r0:r1].astype(np.float32) for _, rgb in stack])  # (S, 3, h, w)
            ok = np.stack([masks[i][r0:r1] for i, _ in stack])[:, None] & (vals != NODATA)
            vals[~np.broadcast_to(ok, vals.shape)] = np.nan
            with np.errstate(all="ignore"):
                med = np.nanmedian(vals, axis=0)
            acc[:, r0:r1] = np.where(np.isnan(med), NODATA, np.rint(med)).astype(np.int16)
    else:
        for i, rgb in stack:
            fill = (acc[0] == NODATA) & masks[i] & (rgb[0] != NODATA)
            acc[:, fill] = rgb[:, fill]
    # 마지막 채움: 구름·포화만 아니면
    for i, rgb in stack:
        hole = acc[0] == NODATA
        if not hole.any():
            break
        ok = hole & ~np.isin(good[i][1], SCL_BAD) & (rgb[0] != NODATA)
        acc[:, ok] = rgb[:, ok]

    tmp = dst.with_suffix(".part")
    with rasterio.open(tmp, "w", driver="GTiff", count=3, dtype="int16", nodata=NODATA, tiled=True,
                       blockxsize=512, blockysize=512, compress="deflate", predictor=2, **prof) as wds:
        wds.write(acc)
    tmp.replace(dst)
    bounds = rasterio.transform.array_bounds(prof["height"], prof["width"], prof["transform"])
    info = {
        "grid": grid, "path": str(dst),
        "bbox": list(transform_bounds(prof["crs"], "EPSG:4326", *bounds, densify_pts=21)),
        "scenes": [good[i][0]["id"] for i, _ in stack],
        "coverage": round(float((acc[0] != NODATA).mean()), 4),
        "seconds": round(time.monotonic() - t0, 1),
    }
    info_path.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return info


# ---------------------------------------------------------------- 타일

def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """XYZ(북쪽 0) 타일의 (minx, miny, maxx, maxy) m"""
    span = 2 * WEB_MERC_HALF / (1 << z)
    minx = -WEB_MERC_HALF + x * span
    maxy = WEB_MERC_HALF - y * span
    return minx, maxy - span, minx + span, maxy


def tile_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 1 << z
    w = x / n * 360.0 - 180.0
    e = (x + 1) / n * 360.0 - 180.0
    nl = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    sl = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return w, sl, e, nl


def to_rgb(refl10k: np.ndarray, black: float, white: float, gamma: float) -> np.ndarray:
    refl = refl10k.astype(np.float32) / 10000.0
    v = np.clip((refl - black) / (white - black), 0.0, 1.0) ** (1.0 / gamma)
    return np.rint(v * 255.0).astype(np.uint8)


_W: dict = {}


def _init_worker(cfg: dict) -> None:
    import rasterio

    _W.clear()
    _W.update(cfg)
    _W["ds"] = {}  # 최근에 연 합성 파일 몇 개만 열어 둔다 (프로세스마다 메모리 제한)
    _W["rasterio"] = rasterio
    _W["env"] = rasterio.Env(GDAL_CACHEMAX=64)  # 기본은 RAM의 5 %라 프로세스가 많으면 메모리가 모자란다
    _W["env"].__enter__()
    import atexit

    atexit.register(_close_worker)


def _close_worker() -> None:
    for ds in _W.get("ds", {}).values():
        ds.close()
    _W.get("ds", {}).clear()
    if "env" in _W:
        _W.pop("env").__exit__(None, None, None)


def _open_src(path: str):
    ds = _W["ds"].pop(path, None)
    if ds is None:
        ds = _W["rasterio"].open(path)
        while len(_W["ds"]) >= 4:
            _W["ds"].pop(next(iter(_W["ds"]))).close()
    _W["ds"][path] = ds  # 맨 뒤 = 가장 최근
    return ds


def _render_top(job: tuple[int, int, int]) -> bool:
    """최상위 레벨 타일 하나. 데이터가 있으면 쓰고 True"""
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    z, x, y = job
    path = Path(_W["out"]) / str(z) / str(x) / f"{(1 << z) - 1 - y}.jpg"
    if path.exists():
        return True
    w, s, e, n = tile_lonlat(z, x, y)
    acc = np.full((3, 256, 256), NODATA, dtype=np.int16)
    for src in _W["sources"]:
        bw, bs, be, bn = src["bbox"]
        if be < w or bw > e or bn < s or bs > n:
            continue
        ds = _open_src(src["path"])
        tmp = np.full((3, 256, 256), NODATA, dtype=np.int16)
        reproject(
            source=_W["rasterio"].band(ds, [1, 2, 3]), destination=tmp,
            dst_transform=from_bounds(*tile_bounds_3857(z, x, y), 256, 256), dst_crs="EPSG:3857",
            src_nodata=NODATA, dst_nodata=NODATA, resampling=Resampling[_W["resampling"]],
        )
        hole = acc[0] == NODATA
        acc[:, hole] = tmp[:, hole]
        if not (acc[0] == NODATA).any():
            break
    valid = acc[0] != NODATA
    if not valid.any():
        return False
    rgb = to_rgb(acc, _W["black"], _W["white"], _W["gamma"])
    rgb[:, ~valid] = np.array(_W["nodata_rgb"], dtype=np.uint8)[:, None]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmpf = path.with_suffix(".part")
    Image.fromarray(np.ascontiguousarray(np.moveaxis(rgb, 0, -1))).save(tmpf, "JPEG", quality=_W["quality"])
    tmpf.replace(path)
    return True


def _build_parent(job) -> bool:
    from PIL import Image

    out, z, x, y, nodata_rgb, quality, keep_empty = job
    out = Path(out)
    path = out / str(z) / str(x) / f"{(1 << z) - 1 - y}.jpg"
    n1 = 1 << (z + 1)
    canvas = Image.new("RGB", (512, 512), tuple(nodata_rgb))
    any_child = False
    for dx in (0, 1):
        for dy in (0, 1):
            p = out / str(z + 1) / str(2 * x + dx) / f"{n1 - 1 - (2 * y + dy)}.jpg"
            if p.exists():
                with Image.open(p) as im:
                    canvas.paste(im.convert("RGB"), (dx * 256, dy * 256))
                any_child = True
    if not any_child and not keep_empty:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.resize((256, 256), Image.Resampling.LANCZOS).save(path, "JPEG", quality=quality)
    return True


def make_tiles(sources: list[dict], args) -> int:
    out: Path = args.out
    (s, n), (w, e), (zmin, zmax) = args.lat, args.lon, args.zoom
    ranges = {z: r for z, *r in tile_ranges(s, n, w, e, zmin, zmax)}
    x0, x1, y0, y1 = ranges[zmax]
    jobs = [(zmax, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    cfg = dict(out=str(out), sources=sources, black=args.black, white=args.white, gamma=args.gamma,
               nodata_rgb=list(args.nodata_rgb), quality=args.quality, resampling=args.resampling)
    t0 = time.monotonic()
    total = 0
    with ProcessPoolExecutor(args.workers, initializer=_init_worker, initargs=(cfg,)) as ex:
        for i, ok in enumerate(ex.map(_render_top, jobs, chunksize=32), 1):
            total += ok
            if i % 5000 == 0:
                print(f"  z{zmax}: {i}/{len(jobs)} ({time.monotonic() - t0:.0f} s)", file=sys.stderr)
        print(f"  z{zmax}: {total}/{len(jobs)} tiles with data", file=sys.stderr)
        for z in range(zmax - 1, zmin - 1, -1):
            px0, px1, py0, py1 = ranges[z]
            pj = [(str(out), z, x, y, list(args.nodata_rgb), args.quality, z <= args.keep_empty_below)
                  for x in range(px0, px1 + 1) for y in range(py0, py1 + 1)]
            cnt = sum(ex.map(_build_parent, pj, chunksize=16))
            total += cnt
            print(f"  z{z}: {cnt} tiles", file=sys.stderr)
    return total


# ---------------------------------------------------------------- main

def main() -> int:
    today = dt.date.today()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "tiles" / "imagery")
    ap.add_argument("--comp-dir", type=Path, default=ROOT / "data" / "s2composite")
    ap.add_argument("--lat", type=float, nargs=2, default=(33.0, 43.0), metavar=("S", "N"))
    ap.add_argument("--lon", type=float, nargs=2, default=(124.0, 131.0), metavar=("W", "E"))
    ap.add_argument("--zoom", type=int, nargs=2, default=(0, 13), metavar=("MIN", "MAX"))
    ap.add_argument("--start", type=dt.date.fromisoformat, default=today - dt.timedelta(days=365))
    ap.add_argument("--end", type=dt.date.fromisoformat, default=today)
    ap.add_argument("--months", type=int, nargs="+", default=[9, 10, 11], help="계절(월). 기본 가을 9 10 11")
    ap.add_argument("--max-cloud", type=float, default=30.0, help="장면 구름 비율 상한 %% (기본 %(default)s)")
    ap.add_argument("--candidates", type=int, default=8, help="타일마다 SCL을 볼 장면 수 (기본 %(default)s)")
    ap.add_argument("--max-scenes", type=int, default=3, help="타일마다 밴드를 받을 장면 수 상한 (기본 %(default)s)")
    ap.add_argument("--min-gain", type=float, default=0.003, help="best: 새로 메우는 화소 비율이 이보다 작으면 멈춤")
    ap.add_argument("--method", choices=["best", "median"], default="best")
    ap.add_argument("--scl-valid", type=int, nargs="+", default=[4, 5, 6, 11],
                    help="쓸 SCL 분류 (기본 4 식생, 5 나지, 6 물, 11 눈)")
    ap.add_argument("--src-res", type=int, choices=[10, 20, 40], default=20, help="받을 해상도 m (COG 개관)")
    ap.add_argument("--black", type=float, default=0.0, help="검정으로 둘 반사율 (기본 %(default)s)")
    ap.add_argument("--white", type=float, default=0.25, help="흰색으로 둘 반사율 (기본 %(default)s)")
    ap.add_argument("--gamma", type=float, default=1.4, help="감마 (1보다 크면 어두운 곳을 밝힘, 기본 %(default)s)")
    ap.add_argument("--nodata-rgb", type=int, nargs=3, default=(14, 32, 56), metavar=("R", "G", "B"))
    ap.add_argument("--quality", type=int, default=85, help="JPEG 품질")
    ap.add_argument("--resampling", default="bilinear", choices=["nearest", "bilinear", "cubic", "average", "lanczos"])
    ap.add_argument("--keep-empty-below", type=int, default=8, help="이 레벨 이하는 전부 결측이어도 타일을 쓴다")
    ap.add_argument("--workers", type=int, default=min(12, max(1, (os.cpu_count() or 2) - 1)),
                    help="타일 프로세스 수 (기본 CPU-1, 최대 12)")
    ap.add_argument("--fetch-workers", type=int, default=4, help="동시에 합성할 MGRS 타일 수 (기본 %(default)s)")
    ap.add_argument("--grids", nargs="+", help="이 MGRS 타일만 (시험용, 예: 52SCG)")
    ap.add_argument("--list", action="store_true", help="MGRS 타일·장면 수만 출력")
    ap.add_argument("--tiles-only", action="store_true", help="합성(index.json)으로 타일만 다시 만든다")
    args = ap.parse_args()
    (s, n), (w, e) = args.lat, args.lon
    if not (s < n and w < e and args.white > args.black and args.gamma > 0 and args.start <= args.end):
        ap.error("bad range, dates or colour parameters")
    months = sorted(set(args.months))
    tag = f"{args.start.isoformat()}_{args.end.isoformat()}_m{'-'.join(map(str, months))}_{args.method}_{args.src_res}m"
    comp_dir: Path = args.comp_dir / tag
    t_all = time.monotonic()

    if args.tiles_only:
        dirs = sorted(args.comp_dir.glob("*/index.json"), key=lambda p: p.stat().st_mtime)
        if not dirs:
            ap.error(f"no composite under {args.comp_dir}")
        index = json.loads(dirs[-1].read_text(encoding="utf-8"))
    else:
        by_grid = find_scenes(args)
        if args.grids:
            by_grid = {g: v for g, v in by_grid.items() if g in set(args.grids)}
        nsc = sum(len(v) for v in by_grid.values())
        print(f"{len(by_grid)} MGRS tiles, {nsc} scenes (cloud <= {args.max_cloud} %, months {months}, "
              f"{args.start}..{args.end})", file=sys.stderr)
        thin = [g for g, v in by_grid.items() if len(v) < 2]
        if thin:
            print(f"  tiles with < 2 scenes: {' '.join(thin)}", file=sys.stderr)
        if args.list:
            for g, v in by_grid.items():
                print(f"  {g}: {len(v)} scenes, best {v[0]['id']} cloud {v[0]['cloud']:.1f} %", file=sys.stderr)
            return 0
        comp_dir.mkdir(parents=True, exist_ok=True)
        cfg = dict(comp_dir=str(comp_dir), src_res=args.src_res, scl_valid=args.scl_valid, method=args.method,
                   candidates=args.candidates, max_scenes=args.max_scenes, min_gain=args.min_gain)
        import psutil

        t0 = time.monotonic()
        net0 = psutil.net_io_counters().bytes_recv  # 시스템 전체 수신량(근사). 받은 용량 보고용
        infos, failed = [], []
        with ProcessPoolExecutor(max(1, args.fetch_workers)) as ex:
            futs = {ex.submit(composite_grid, g, v, cfg): g for g, v in by_grid.items()}
            for i, f in enumerate(as_completed(futs), 1):
                g = futs[f]
                try:
                    info = f.result()
                except Exception as ex_:  # noqa: BLE001 - 다음 실행에서 이어 한다
                    failed.append(f"{g}: {ex_}")
                    continue
                if "error" in info:
                    failed.append(f"{g}: {info['error']}")
                    continue
                infos.append(info)
                print(f"  [{i}/{len(by_grid)}] {g}: {len(info['scenes'])} scenes, coverage "
                      f"{info['coverage'] * 100:.1f} %, {time.monotonic() - t0:.0f} s", file=sys.stderr)
        infos.sort(key=lambda r: -r["coverage"])
        comp_bytes = sum(Path(r["path"]).stat().st_size for r in infos)
        index = {"tag": tag, "args": {k: (str(v) if isinstance(v, (Path, dt.date)) else v)
                                      for k, v in vars(args).items()},
                 "items": infos, "failed": failed, "seconds": round(time.monotonic() - t0, 1),
                 "composite_bytes": comp_bytes,
                 "net_bytes_approx": psutil.net_io_counters().bytes_recv - net0,
                 "scenes_read": sum(len(r["scenes"]) for r in infos)}
        (comp_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
        print(f"composite: {len(infos)} tiles, {index['scenes_read']} scenes read, "
              f"{comp_bytes / 1e9:.2f} GB on disk, ~{index['net_bytes_approx'] / 1e9:.2f} GB received, "
              f"{index['seconds']:.0f} s", file=sys.stderr)
        if failed:
            print(f"{len(failed)} tiles failed (run again to resume):\n  " + "\n  ".join(failed), file=sys.stderr)

    dates = sorted({sid.split("_")[2][:4] for r in index["items"] for sid in r["scenes"]})
    args.out.mkdir(parents=True, exist_ok=True)
    write_tilemap(args.out, s, n, w, e, args.zoom[0], args.zoom[1],
                  f"Copernicus Sentinel-2 L2A composite {index['tag']}")
    (args.out / "source.json").write_text(json.dumps({
        "collection": COLLECTION, "composite": index["tag"], "black": args.black, "white": args.white,
        "gamma": args.gamma, "credit": f"Contains modified Copernicus Sentinel data {'-'.join(dates[::max(1, len(dates) - 1)])}",
    }, indent=1) + "\n", encoding="utf-8")
    t0 = time.monotonic()
    total = make_tiles(index["items"], args)
    size = sum(p.stat().st_size for p in args.out.rglob("*.jpg"))
    print(f"{args.out}: {total} tiles, {size / 1e6:.1f} MB, tiles {time.monotonic() - t0:.0f} s, "
          f"all {time.monotonic() - t_all:.0f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
