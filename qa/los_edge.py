"""TC-QA-063·064: 가시선 끝점 0.5 m 허용이 판정을 가르는 배치 (DEC-018, IMP-PAY-003).

make_terrain_los는 50 m 표본에서 시선 높이가 지면보다 낮으면 가린다고 보되, 양 끝점에서 50 m 안 표본은
지면을 0.5 m 낮춰 본다(`qa/los_check.py` `los()`와 같은 식). 이 허용이 결과를 바꾸는 배치를 놓고 Core 탐지를
허용 0.5 m 기대값과 허용 0 m 기대값 양쪽에 견준다.

--terrain dem (설악 일대, DEM에서 고른 고정 좌표)
- A 묶음: 지면에 붙은 표적(AGL 0). 표적 앞 마지막 표본(50 m 안)만 0~0.5 m 가리고 나머지는 1 m 넘게 트였다.
  허용 0.5 m면 보이고, 허용이 없으면 안 보인다.
- B 묶음: 표적 바로 앞(50 m 안) 지면이 시선을 0.5 m 넘게 가린다. 허용이 있어도 안 보인다.
- B1 자리에 표적 높이만 바꾼 변형(AGL 0.6, 2)을 더 둔다(같은 언덕, 높이로 판정이 바뀌는 경계).
--terrain flat (평지 0 m)
- 표적 고도 0, 7.9 km 동쪽 센서 고도 세 가지. 곡률 처짐만으로 끝점 표본 하나가 가리는 구간을 만든다.
  허용 0.5 m 경계 고도와 허용 0 m 경계 고도를 이분 탐색으로 구해 그 아래·사이·위에 둔다.

uv run python qa/los_edge.py --terrain dem --out qa/out/los_edge/dem
uv run python qa/los_edge.py --terrain flat --out qa/out/los_edge/flat
uv run python qa/los_edge.py --terrain dem --design   # 실행 없이 기대값만
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
import los_check as lc  # noqa: E402
from dem_check import DEM_JSON, Dem  # noqa: E402

# 이름: (센서 위도, 경도, 고도 m), (표적 위도, 경도), 표적 AGL 목록
DEM_PAIRS = {
    "A1": ((38.095, 128.604244, 369.43), (38.095, 128.57), (0.0, 2.0)),
    "A2": ((38.215, 128.5043, 416.68), (38.215, 128.47), (0.0,)),
    "A3": ((38.08, 128.503763, 577.65), (38.08, 128.538), (0.0,)),
    "B1": ((38.164, 128.392276, 1013.66), (38.164, 128.358), (0.0, 0.6, 2.0)),
    "B2": ((38.068, 128.519769, 678.9), (38.068, 128.554), (0.0,)),
    "B3": ((38.143, 128.488266, 1321.17), (38.143, 128.454), (0.0,)),
}
FLAT_TGT = (37.5, 128.0)
FLAT_D_E = 7900.0


def end_split(dem: Dem | None, a: tuple, b: tuple) -> dict:
    """끝점 50 m 안 표본과 그 밖 표본의 최소 여유(허용 없이, 시선 − 지면)"""
    d = lc.norm(lc.ned(a, b))
    n = min(max(math.ceil(d / 50.0), 2), 4000)
    we, wm, k_end = math.inf, math.inf, None
    for k in range(1, n):
        s = k / n
        ray = a[2] + s * (b[2] - a[2]) - s * (1.0 - s) * d * d / (2.0 * lc.A)
        g = dem.el(a[0] + s * (b[0] - a[0]), a[1] + s * (b[1] - a[1])) if dem is not None else 0.0
        if min(s, 1.0 - s) * d <= 50.0:
            if ray - g < we:
                we, k_end = ray - g, round((1.0 - s) * d, 1)
        else:
            wm = min(wm, ray - g)
    return {"end_margin_m": round(we, 3), "end_dist_to_target_m": k_end, "mid_margin_m": round(wm, 3),
            "d_m": round(d, 1), "n_samples": n - 1}


def flat_alts() -> dict:
    m_lon = lc.M_LAT * math.cos(FLAT_TGT[0] * lc.D2R)
    sl, so = FLAT_TGT[0], round(FLAT_TGT[1] - FLAT_D_E / m_lon, 6)
    tgt = (FLAT_TGT[0], FLAT_TGT[1], 0.0)

    def thr(tol: float) -> float:
        lo, hi = 0.0, 20.0
        assert not lc.los(None, (sl, so, lo), tgt, 50.0, tol)[0] and lc.los(None, (sl, so, hi), tgt, 50.0, tol)[0]
        while hi - lo > 1e-4:
            mid = 0.5 * (lo + hi)
            if lc.los(None, (sl, so, mid), tgt, 50.0, tol)[0]:
                hi = mid
            else:
                lo = mid
        return hi

    h05, h0 = thr(0.5), thr(0.0)
    return {"sensor": (sl, so), "target": tgt, "thr_tol05_m": round(h05, 4), "thr_tol0_m": round(h0, 4),
            "alts": {"F-below": round(h05 - 0.01, 3), "F-between": round(0.5 * (h05 + h0), 3),
                     "F-above": round(h0 + 0.01, 3)}}


def layout(dem: Dem | None, terrain: str) -> tuple[list[dict], list[dict], dict]:
    """(센서 목록, 표적 목록, 설계 정보)"""
    sensors, tgts, info = [], [], {}
    if terrain == "dem":
        for name, (sp, tp, agls) in DEM_PAIRS.items():
            g = dem.el(*tp)
            for agl in agls:
                tid = f"tgt-{name.lower()}-agl{round(agl * 10):d}"
                tgts.append({"id": tid, "pos": (tp[0], tp[1], round(g + agl, 3)), "pair": name, "agl": agl})
            sensors.append({"name": name, "pos": sp, "aim": f"tgt-{name.lower()}-agl0"})
    else:
        fz = flat_alts()
        info["flat"] = fz
        tgts.append({"id": "tgt-flat", "pos": fz["target"], "pair": "F", "agl": 0.0})
        for k, alt in fz["alts"].items():
            sensors.append({"name": k, "pos": (*fz["sensor"], alt), "aim": "tgt-flat"})
    tpos = {t["id"]: t["pos"] for t in tgts}
    for i, s in enumerate(sensors, 1):
        s["id"] = f"uav-{i:03d}"
        az, el = lc.az_el(s["pos"], tpos[s["aim"]])
        s["az"], s["el"] = round(az, 6), round(el, 6)
    return sensors, tgts, info


def scenario(sensors: list[dict], tgts: list[dict], dem: Dem | None) -> dict:
    ents = []
    for t in tgts:
        ents.append({"id": t["id"], "kind": "ground_target", "side": "red", "dynamics": "static",
                     "initial": {"position": {"lat_deg": t["pos"][0], "lon_deg": t["pos"][1], "alt_m": t["pos"][2]}}})
    for s in sensors:
        ents.append({"id": s["id"], "kind": "uav", "side": "blue", "dynamics": "static",
                     "initial": {"position": {"lat_deg": s["pos"][0], "lon_deg": s["pos"][1], "alt_m": s["pos"][2]}},
                     "payloads": [{"id": "cam0", "type": "camera", "profile": "eo_wide",
                                   "overrides": {**lc.CAM, "default_az_deg": s["az"], "default_el_deg": s["el"]}}],
                     "autonomy": {"ma_plugin": "flocking_basic", "ma_params": {"group": "alpha"}},
                     "link_profile": "uav_default", "controlling_gcs": "gcs-01"})
    s0 = sensors[0]["pos"]
    gl = round((dem.el(s0[0], s0[1]) if dem is not None else 0.0) + 30.0, 1)
    ents.insert(0, {"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
                    "initial": {"position": {"lat_deg": s0[0], "lon_deg": s0[1], "alt_m": gl}},
                    "link_profile": "gcs_default"})
    lat = [p for e in ents for p in [e["initial"]["position"]["lat_deg"]]]
    lon = [p for e in ents for p in [e["initial"]["position"]["lon_deg"]]]
    return {"schema_version": "0.1", "name": "qa-los-edge", "description": "TC-QA-063·064 가시선 끝점 허용 (DEC-018)",
            "map": {"origin": {"lat_deg": s0[0], "lon_deg": s0[1], "alt_m": 0.0},
                    "extent": {"south_deg": min(lat) - 0.05, "north_deg": max(lat) + 0.05,
                               "west_deg": min(lon) - 0.05, "east_deg": max(lon) + 0.05}},
            "run": {"mode": "lockstep", "frame_hz": 50, "seed": 20261107, "rate": 20.0, "duration_s": 600.0},
            "entities": ents, "mission_plan": {"plan_id": "plan-los-edge", "tasks": []}}


def expect(dem: Dem | None, sensors: list[dict], tgts: list[dict]) -> dict:
    """FOV·거리 안 (센서, 표적) 쌍마다 허용 0.5 m / 0 m 기대 탐지와 여유"""
    out = {}
    for s in sensors:
        for t in tgts:
            ok, rng, hh, ee = lc.fov_ok(s, t["pos"])
            if not ok:
                continue
            v05, w05 = lc.los(dem, s["pos"], t["pos"], 50.0, 0.5)
            v0, _ = lc.los(dem, s["pos"], t["pos"], 50.0, 0.0)
            out[f"{s['id']}>{t['id']}"] = {"sensor": s["name"], "target": t["id"], "agl": t["agl"],
                                           "range_m": round(rng, 1), "los_tol05": v05, "los_tol0": v0,
                                           "worst_tol05": w05, **end_split(dem, s["pos"], t["pos"])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", choices=("dem", "flat"), required=True)
    ap.add_argument("--out")
    ap.add_argument("--design", action="store_true")
    ap.add_argument("--base-port", type=int, default=48400)
    ap.add_argument("--frames", type=int, default=300)
    a = ap.parse_args()
    dem = Dem() if a.terrain == "dem" else None
    sensors, tgts, info = layout(dem, a.terrain)
    sc = scenario(sensors, tgts, dem)
    exp = expect(dem, sensors, tgts)
    res: dict = {"terrain": a.terrain, "info": info, "sensors": sensors, "targets": tgts, "expect": exp}
    if a.design:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        return
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sp = lc.SCN / f"qa_los_edge_{a.terrain}.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    terr = ["--terrain-dem", str(DEM_JSON)] if dem is not None else ["--terrain-flat", "0"]
    from p5_e2e import P5Observer
    st = h.Stack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                 core_extra=[*terr, "--frames", str(a.frames)])
    try:
        st.start_one("datalink")
        st.start_one("agent")
        time.sleep(st.settle)
        ob = P5Observer([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 300:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.0)
        with ob.lock:
            det = list(ob.det)
        cnt = Counter(f"{e}>{t}" for _, e, t, _ in det)
        rows, bad05, diff0 = [], [], []
        for k in sorted(set(exp) | set(cnt)):
            e = exp.get(k)
            w05, w0 = bool(e and e["los_tol05"]), bool(e and e["los_tol0"])
            got = cnt.get(k, 0)
            rows.append({"pair": k, "sensor": e["sensor"] if e else "-", "agl": e["agl"] if e else None,
                         "expect_tol05": w05, "expect_tol0": w0, "n_det": got,
                         "end_margin_m": e["end_margin_m"] if e else None,
                         "end_dist_to_target_m": e["end_dist_to_target_m"] if e else None,
                         "mid_margin_m": e["mid_margin_m"] if e else None})
            if w05 != (got > 0):
                bad05.append(k)
            if w0 != (got > 0):
                diff0.append(k)
        res.update({"terrain_args": terr, "last_frame": ob.last_frame, "rows": rows,
                    "mismatch_tol05": bad05, "differs_from_tol0": diff0, "log_issues": h.scan_logs(st)})
        ob.close()
    finally:
        st.down()
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"terrain": a.terrain, "info": info, "last_frame": res["last_frame"],
                      "mismatch_tol05": bad05, "differs_from_tol0": diff0, "rows": rows,
                      "log_issues": res["log_issues"]}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
