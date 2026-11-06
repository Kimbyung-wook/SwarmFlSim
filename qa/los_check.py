"""TC-QA-052~054: DEM 가시선 차폐 (DEC-018, IMP-PAY-001·003).

설악산 대청봉·한라산 백록담 능선을 사이에 두고 정지(static) 센서 기체와 지상 표적을 놓는다.
- 센서는 카메라 기본 방위·고각(overrides default_az_deg/default_el_deg)을 표적 쪽으로 맞춘다. 정지 기체의 자세는
  항등 쿼터니언(기수 북쪽, 수평)이므로 FRD = NED 이다.
- 같은 위치에서 고도만 바꾼 센서(차폐 → 트임 경계 위·아래)와 옆으로 옮긴 센서를 둔다.
- Python으로 Core와 같은 판정(50 m 표본, 지구 곡률 처짐, 끝점 50 m 안 0.5 m 허용, DEM 쌍선형 보간)을 따로 계산해
  모든 (센서, 대상) 쌍의 기대 탐지 여부를 만든다. 거리·FOV 판정도 같은 식(ned_between, 카메라 좌표)으로 계산한다.
- 5 m 표본(세밀)으로도 다시 계산해 50 m 표본이 능선 꼭대기를 건너뛰는 경계 효과를 기록한다.
- Core `--terrain-dem`과 `--terrain-flat 0` 두 번 돌려 onboard/*/Detection을 센서·대상별로 센다.

uv run python qa/los_check.py --out qa/out/los/dem
uv run python qa/los_check.py --out qa/out/los/flat --flat
uv run python qa/los_check.py --design      # 실행 없이 기대값·경계만 출력
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from dem_check import DEM_JSON, Dem  # noqa: E402

SCN = Path(__file__).resolve().parent / "scenarios"
A, F = 6378137.0, 1.0 / 298.257223563
E2 = F * (2.0 - F)
D2R = math.pi / 180.0
CAM = {"hfov_deg": 30.0, "vfov_deg": 30.0, "max_range_m": 8000.0}
TGT_AGL = 2.0


def m_rad(lat: float) -> float:
    s = math.sin(lat)
    w = 1.0 - E2 * s * s
    return A * (1.0 - E2) / (w * math.sqrt(w))


def n_rad(lat: float) -> float:
    s = math.sin(lat)
    return A / math.sqrt(1.0 - E2 * s * s)


def ned(a: tuple, b: tuple) -> tuple[float, float, float]:
    """payload ned_between과 같은 식"""
    lat_mid = 0.5 * (a[0] + b[0]) * D2R
    h_mid = 0.5 * (a[2] + b[2])
    m = m_rad(lat_mid) + h_mid
    n = (n_rad(lat_mid) + h_mid) * math.cos(lat_mid)
    return ((b[0] - a[0]) * D2R * m, (b[1] - a[1]) * D2R * n, -(b[2] - a[2]))


def norm(v) -> float:  # noqa: ANN001
    return math.sqrt(sum(x * x for x in v))


def los(dem: Dem | None, a: tuple, b: tuple, step: float = 50.0, tol: float = 0.5) -> tuple[bool, dict]:
    """make_terrain_los와 같은 판정. dem=None이면 평지 0 m. 가장 깊게 가린(또는 가장 아슬한) 표본을 돌려준다"""
    d = norm(ned(a, b))
    worst = {"margin_m": math.inf}
    if d < 1e-6:
        return True, worst
    n = min(max(math.ceil(d / step), 2), 4000)
    ok = True
    for k in range(1, n):
        s = k / n
        lat = a[0] + s * (b[0] - a[0])
        lon = a[1] + s * (b[1] - a[1])
        ray = a[2] + s * (b[2] - a[2]) - s * (1.0 - s) * d * d / (2.0 * A)
        g = dem.el(lat, lon) if dem is not None else 0.0
        t = tol if min(s, 1.0 - s) * d <= step else 0.0
        margin = ray - (g - t)
        if margin < worst["margin_m"]:
            worst = {"margin_m": round(margin, 3), "s": round(s, 4), "dist_from_sensor_m": round(s * d, 1),
                     "ray_m": round(ray, 2), "ground_m": round(g, 2), "lat": round(lat, 6), "lon": round(lon, 6)}
        if margin < 0:
            ok = False
    worst["n_samples"] = n - 1
    worst["d_m"] = round(d, 1)
    return ok, worst


def az_el(a: tuple, b: tuple) -> tuple[float, float]:
    v = ned(a, b)
    return math.degrees(math.atan2(v[1], v[0])), math.degrees(math.atan2(-v[2], math.hypot(v[0], v[1])))


def boresight(az: float, el: float) -> tuple[float, float, float]:
    """항등 자세에서 az_el_to_frd = NED"""
    az, el = az * D2R, el * D2R
    return (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), -math.sin(el))


def cross(a, b):  # noqa: ANN001, ANN201
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b) -> float:  # noqa: ANN001
    return sum(x * y for x, y in zip(a, b))


def fov_ok(s: dict, t: tuple) -> tuple[bool, float, float, float]:
    """run_sensors와 같은 거리·FOV 판정. (통과, 거리, h, e)"""
    p = s["pos"]
    f = boresight(s["az"], s["el"])
    right = cross((0.0, 0.0, 1.0), f)
    nr = norm(right)
    right = tuple(x / nr for x in right)
    rd = dot(right, f)
    right = tuple(r - rd * x for r, x in zip(right, f))
    nr = norm(right)
    right = tuple(x / nr for x in right)
    down = cross(f, right)
    v = ned(p, t)
    rng = norm(v)
    fx = dot(v, f)
    if rng > CAM["max_range_m"] or rng < 1e-6 or fx <= 0:
        return False, rng, math.nan, math.nan
    hh = math.degrees(math.atan2(dot(v, right), fx))
    ee = math.degrees(math.atan2(dot(v, down), fx))
    return abs(hh) <= CAM["hfov_deg"] / 2 and abs(ee) <= CAM["vfov_deg"] / 2, rng, hh, ee


def threshold(dem: Dem, lat: float, lon: float, tgt: tuple, step: float, lo: float, hi: float) -> float:
    """센서 고도를 이분 탐색해 가시선이 트이는 최저 고도(0.01 m)를 찾는다"""
    assert not los(dem, (lat, lon, lo), tgt, step)[0] and los(dem, (lat, lon, hi), tgt, step)[0]
    while hi - lo > 0.01:
        mid = 0.5 * (lo + hi)
        if los(dem, (lat, lon, mid), tgt, step)[0]:
            hi = mid
        else:
            lo = mid
    return hi


# 능선별 배치: 봉우리에서 동서로 떨어진 거리(m). 센서는 서쪽, 표적은 동쪽 사면, 옮긴 센서는 표적 동쪽(같은 쪽)
M_LAT = 111_320.0
SITES = {
    "seorak": {"peak": (38.1192, 128.4650), "sensor_w_m": 1500.0, "target_e_m": 1000.0, "moved_e_m": 2500.0},
    "halla": {"peak": (33.3617, 126.5358), "sensor_w_m": 1500.0, "target_e_m": 1200.0, "moved_e_m": 2700.0},
}
DALT = 150.0


def east(p: tuple, m: float) -> tuple[float, float]:
    return (p[0], round(p[1] + m / (M_LAT * math.cos(p[0] * D2R)), 6))


def design(dem: Dem) -> dict:
    """센서·표적 배치와 Python 경계값"""
    out = {}
    for site, g in SITES.items():
        tl, to = east(g["peak"], g["target_e_m"])
        tgt = (tl, to, round(dem.el(tl, to) + TGT_AGL, 2))
        sl, so = east(g["peak"], -g["sensor_w_m"])
        gnd = dem.el(sl, so)
        th = {f"step{st:g}": round(threshold(dem, sl, so, tgt, st, gnd + 20, 6000), 2) for st in (50.0, 5.0, 1.0)}
        th50 = th["step50"]
        alts = {"low": round(th50 - DALT, 1), "edge_lo": round(th50 - 1.0, 1), "edge_hi": round(th50 + 1.0, 1),
                "high": round(th50 + DALT, 1)}
        ml, mo = east(g["peak"], g["moved_e_m"])
        _, crest = los(dem, (sl, so, th50 - 0.01), tgt, 50.0)
        out[site] = {"peak_dem_m": round(dem.el(*g["peak"]), 1), "target": tgt, "sensor": (sl, so),
                     "sensor_ground_m": round(gnd, 1), "threshold_alt_m": th, "crest_at_threshold": crest,
                     "sensor_alts": alts, "moved": (ml, mo, alts["low"]), "moved_ground_m": round(dem.el(ml, mo), 1)}
    return out


def build(dem: Dem, dz: dict) -> tuple[dict, list[dict]]:
    ents, sensors, tasks = [], [], []
    for site, g in dz.items():
        tid = f"tgt-{site}"
        ents.append({"id": tid, "kind": "ground_target", "side": "red", "dynamics": "static",
                     "initial": {"position": {"lat_deg": g["target"][0], "lon_deg": g["target"][1],
                                              "alt_m": g["target"][2]}}})
        sl, so = g["sensor"]
        spots = [(f"{site}-{k}", (sl, so, v)) for k, v in g["sensor_alts"].items()]
        spots.append((f"{site}-moved", tuple(g["moved"])))
        for name, pos in spots:
            az, el = az_el(pos, tuple(g["target"]))
            sensors.append({"name": name, "site": site, "pos": pos, "az": az, "el": el, "aim": tid})
    for i, s in enumerate(sensors, 1):
        s["id"] = f"uav-{i:03d}"
        ents.append({"id": s["id"], "kind": "uav", "side": "blue", "dynamics": "static",
                     "initial": {"position": {"lat_deg": s["pos"][0], "lon_deg": s["pos"][1], "alt_m": s["pos"][2]}},
                     "payloads": [{"id": "cam0", "type": "camera", "profile": "eo_wide",
                                   "overrides": {**CAM, "default_az_deg": round(s["az"], 6),
                                                 "default_el_deg": round(s["el"], 6)}}],
                     "autonomy": {"ma_plugin": "waypoint", "ma_params": {"hold_radius_m": 300, "acceptance_m": 80}},
                     "link_profile": "uav_default", "controlling_gcs": "gcs-01"})
        s["az"], s["el"] = round(s["az"], 6), round(s["el"], 6)
        tasks.append({"task_id": f"t-{s['id']}", "assignees": [s["id"]],
                      "hold": {"center": {"lat_deg": s["pos"][0], "lon_deg": s["pos"][1], "alt_m": s["pos"][2]},
                               "radius_m": 300.0, "direction": "cw"}})
    olat, olon = 38.0, 128.3
    ents.insert(0, {"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
                    "initial": {"position": {"lat_deg": olat, "lon_deg": olon,
                                             "alt_m": round(dem.el(olat, olon) + 30.0, 1)}},
                    "link_profile": "gcs_default"})
    sc = {"schema_version": "0.1", "name": "qa-los", "description": "TC-QA-052~054 DEM 가시선 차폐 (DEC-018)",
          "map": {"origin": {"lat_deg": olat, "lon_deg": olon, "alt_m": 0.0},
                  "extent": {"south_deg": 33.2, "north_deg": 38.3, "west_deg": 126.3, "east_deg": 128.7}},
          "run": {"mode": "lockstep", "frame_hz": 50, "seed": 20261106, "rate": 20.0, "duration_s": 600.0},
          "entities": ents, "mission_plan": {"plan_id": "plan-los", "tasks": tasks}}
    return sc, sensors


def expect(dem: Dem | None, sensors: list[dict], ents: list[dict]) -> dict:
    """모든 (센서, 대상) 쌍의 기대 탐지 여부"""
    pos = {e["id"]: (e["initial"]["position"]["lat_deg"], e["initial"]["position"]["lon_deg"],
                     e["initial"]["position"]["alt_m"]) for e in ents}
    out = {}
    for s in sensors:
        for tid, t in pos.items():
            if tid == s["id"]:
                continue
            ok, rng, hh, ee = fov_ok(s, t)
            if not ok:
                continue
            v50, w50 = los(dem, s["pos"], t, 50.0)
            v5, w5 = los(dem, s["pos"], t, 5.0)
            out[f"{s['id']}>{tid}"] = {"name": s["name"], "range_m": round(rng, 1), "h_deg": round(hh, 3),
                                       "e_deg": round(ee, 3), "los50": v50, "los5": v5,
                                       "worst50": w50, "worst5": w5}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--flat", action="store_true")
    ap.add_argument("--design", action="store_true")
    ap.add_argument("--base-port", type=int, default=48400)
    ap.add_argument("--frames", type=int, default=300)
    a = ap.parse_args()
    dem = Dem()
    dz = design(dem)
    sc, sensors = build(dem, dz)
    exp_dem = expect(dem, sensors, sc["entities"])
    exp_flat = expect(None, sensors, sc["entities"])
    res: dict = {"design": dz, "sensors": sensors, "expect_dem": exp_dem, "expect_flat": exp_flat}
    if a.design:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        return
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sp = SCN / "qa_los.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    terr = ["--terrain-flat", "0"] if a.flat else ["--terrain-dem", str(DEM_JSON)]
    from p5_e2e import P5Observer
    st = h.Stack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                 core_extra=[*terr, "--frames", str(a.frames)])
    res["terrain"] = terr
    try:
        st.start_one("datalink")
        st.start_one("agent")
        time.sleep(st.settle)
        ob = P5Observer([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 600:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.0)
        with ob.lock:
            det = list(ob.det)
            sact = list(ob.sact)
        frames = sorted({f for f, *_ in det})
        cnt = Counter(f"{e}>{t}" for _, e, t, _ in det)
        rng = {}
        for _, e, t, r in det:
            rng[f"{e}>{t}"] = round(r, 1)
        exp = exp_flat if a.flat else exp_dem
        n_obs_frames = (ob.last_frame or 0)
        rows, bad = [], []
        for k in sorted(set(exp) | set(cnt)):
            e = exp.get(k)
            want = bool(e and e["los50"])
            got = cnt.get(k, 0)
            rows.append({"pair": k, "name": e["name"] if e else "-", "expect": want, "n_det": got,
                         "range_core": rng.get(k), "range_py": e["range_m"] if e else None,
                         "margin50": e["worst50"]["margin_m"] if e else None,
                         "margin5": e["worst5"]["margin_m"] if e else None})
            if want != (got > 0):
                bad.append(k)
        res["last_frame"] = ob.last_frame
        res["det_frames"] = [frames[0], frames[-1], len(frames)] if frames else None
        res["sensor_activity"] = Counter(f"{e}:{act}" for _, e, _, act in sact)
        res["rows"] = rows
        res["mismatch"] = bad
        res["core_log_head"] = [ln for ln in st.log_text().get("core", "").splitlines()
                                if any(w in ln.lower() for w in ("terrain", "dem", "warn", "경고", "reject"))][:10]
        res["log_issues"] = h.scan_logs(st)
        ob.close()
    finally:
        st.down()
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    (out / "result.json").write_text(txt, encoding="utf-8")
    print(json.dumps({"terrain": terr, "last_frame": res["last_frame"], "det_frames": res["det_frames"],
                      "mismatch": bad, "rows": rows}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
