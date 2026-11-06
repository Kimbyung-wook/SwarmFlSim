"""TC-QA-044: DEM 지형 (QA-022, DEC-053, IMP-CORE-023, IMP-DYN-009).

산악(설악산·한라산)과 격자 북쪽 끝 바깥에 기체를 두고 lockstep으로 돌린다. Core `--terrain-dem`.
- truth 궤적의 각 프레임에서 DEM 쌍선형 보간 고도(Python, data/dem/korea_glo90.bin)를 계산해
  처음 지면 아래로 내려간 프레임을 기대값으로 삼고, Core가 낸 kill(cause=ground) 프레임·위치와 비교한다.
- 격자 밖(43.0°N 북쪽)은 0 m여야 한다. 같은 경도의 격자 안 북쪽 끝 고도보다 낮게 날린다.

uv run python qa/dem_check.py --out qa/out/dem/mtn --case mtn [--flat]   # --flat: DEM 대신 --terrain-flat 0
uv run python qa/dem_check.py --out qa/out/dem/north --case north
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM_JSON = ROOT / "data/dem/korea_glo90.json"
SCN = Path(__file__).resolve().parent / "scenarios"
M_LAT = 111_320.0


class Dem:
    def __init__(self, path: Path = DEM_JSON) -> None:
        hd = json.loads(path.read_text(encoding="utf-8"))
        self.h = hd
        self.z = np.fromfile(path.parent / hd["data_file"], dtype="<i2").reshape(hd["rows"], hd["cols"])

    def el(self, lat: float, lon: float) -> float:
        hd = self.h
        fr = (lat - hd["lat0_deg"]) / hd["dlat_deg"]
        fc = (lon - hd["lon0_deg"]) / hd["dlon_deg"]
        if not (0 <= fr <= hd["rows"] - 1 and 0 <= fc <= hd["cols"] - 1):
            return 0.0
        r, c = min(int(fr), hd["rows"] - 2), min(int(fc), hd["cols"] - 2)
        a, b = fr - r, fc - c
        z = self.z
        return float((1 - a) * ((1 - b) * z[r, c] + b * z[r, c + 1]) + a * ((1 - b) * z[r + 1, c] + b * z[r + 1, c + 1]))


def uav(i: str, lat: float, lon: float, alt: float, vn: float, ve: float) -> dict:
    return {"id": i, "kind": "uav", "side": "blue", "dynamics": "dof2", "airframe": "skywalker_x8",
            "initial": {"position": {"lat_deg": lat, "lon_deg": lon, "alt_m": alt},
                        "velocity_ned_mps": {"x": vn, "y": ve, "z": 0.0}},
            "autonomy": {"ma_plugin": "waypoint", "ma_params": {"hold_radius_m": 300, "acceptance_m": 80}},
            "link_profile": "uav_default", "controlling_gcs": "gcs-01"}


def scenario(case: str, dem: Dem) -> dict:
    ents, tasks = [], []
    if case == "mtn":
        # 설악산 대청봉(38.1192, 128.4650, DEM 1,694 m), 한라산(33.3617, 126.5358, DEM 1,921 m)를 서→동으로 넘는다
        olat, olon = 38.119, 128.43
        legs = [("uav-001", 38.11917, 128.465, 1500.0), ("uav-002", 38.11917, 128.465, 1650.0),
                ("uav-003", 38.11917, 128.465, 1850.0), ("uav-004", 33.36167, 126.53583, 1800.0),
                ("uav-005", 33.36167, 126.53583, 2050.0)]
        dx = 0.0135  # 경도 약 1.2 km
        for i, la, lo, alt in legs:
            ents.append(uav(i, la, lo - dx, alt, 0.0, 22.0))
            tasks.append({"task_id": f"t-{i}", "assignees": [i],
                          "move_to": {"destination": {"lat_deg": la, "lon_deg": lo + dx, "alt_m": alt},
                                      "speed_mps": 22.0}})
    else:
        # 격자 북쪽 끝은 43.0°N. 127.5°E 근처 북쪽 끝 고도는 약 900 m
        olat, olon = 42.98, 127.5
        # uav-001·003: 격자 밖에서 선회(0 m 위). uav-002: 격자 밖 400 m에서 남쪽으로 들어온다(북쪽 끝 고도 약 900 m).
        # 격자 밖이 0 m면 시작 때 지면 위이므로 지면 이벤트가 걸리고 경계를 넘을 때 kill 된다.
        # uav-004: 격자 안 지면 아래(DEM 약 980 m)에서 400 m로 시작 (QA-024)
        for i, la, alt in [("uav-001", 43.03, 400.0), ("uav-003", 43.03, 30.0), ("uav-004", 42.985, 400.0)]:
            ents.append(uav(i, la, 127.5, alt, 0.0, 20.0))
            tasks.append({"task_id": f"t-{i}", "assignees": [i],
                          "hold": {"center": {"lat_deg": la, "lon_deg": 127.5 + 0.004, "alt_m": alt},
                                   "radius_m": 300.0, "direction": "cw"}})
        ents.append(uav("uav-002", 43.006, 127.52, 400.0, -20.0, 0.0))
        tasks.append({"task_id": "t-uav-002", "assignees": ["uav-002"],
                      "move_to": {"destination": {"lat_deg": 42.98, "lon_deg": 127.52, "alt_m": 400.0},
                                  "speed_mps": 20.0}})
    g_alt = dem.el(olat - 0.03, olon) + 30.0
    ents.insert(0, {"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
                    "initial": {"position": {"lat_deg": olat - 0.03, "lon_deg": olon, "alt_m": round(g_alt, 1)}},
                    "link_profile": "gcs_default"})
    # 지도 범위는 한반도 범위(33.0~43.1°N, 124.0~131.9°E, DEC-016) 안이어야 한다
    ext = ({"south_deg": 33.2, "north_deg": 38.3, "west_deg": 126.3, "east_deg": 128.7} if case == "mtn"
           else {"south_deg": 42.8, "north_deg": 43.1, "west_deg": 127.3, "east_deg": 127.7})
    return {"schema_version": "0.1", "name": f"qa-dem-{case}", "description": "TC-QA-044 DEM 지형 (QA-022)",
            "map": {"origin": {"lat_deg": olat, "lon_deg": olon, "alt_m": round(g_alt, 1)},
                    "extent": ext},
            "run": {"mode": "lockstep", "frame_hz": 50, "seed": 20261106, "rate": 20.0, "duration_s": 600.0},
            "entities": ents, "mission_plan": {"plan_id": "plan-dem", "tasks": tasks}}


def analyse(traj: dict, kills: list, dem: Dem) -> dict:
    out = {}
    for eid, rows in sorted(traj.items()):
        if not eid.startswith("uav"):
            continue
        rows = sorted(rows)
        clr = [(fr, alt - dem.el(la, lo), la, lo, alt) for fr, la, lo, alt in rows]
        below = next((c for c in clr if c[1] < 0), None)
        k = next((x for x in kills if x["entity"] == eid), None)
        live = [c for c in clr if k is None or c[0] < k["frame"]]
        mn = min(live, key=lambda c: c[1]) if live else None
        d = {"frames": [rows[0][0], rows[-1][0]], "start_alt": round(rows[0][3], 1),
             "start_dem_m": round(rows[0][3] - clr[0][1], 1), "start_clearance_m": round(clr[0][1], 1),
             "min_clearance_m": round(mn[1], 2) if mn else None,
             "min_clearance_frame": mn[0] if mn else None,
             "max_terrain_m": round(max(dem.el(la, lo) for _, la, lo, _ in rows), 1),
             "expected_first_below_frame": below[0] if below else None, "kill": k}
        if k:
            last = [c for c in clr if c[0] <= k["frame"]][-1]
            d["at_kill"] = {"frame": last[0], "alt_m": round(last[4], 2), "dem_m": round(last[4] - last[1], 2),
                            "clearance_m": round(last[1], 2)}
        out[eid] = d
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--case", choices=["mtn", "north"], default="mtn")
    ap.add_argument("--base-port", type=int, default=48400)
    ap.add_argument("--frames", type=int, default=7000)
    ap.add_argument("--flat", action="store_true", help="DEM 대신 --terrain-flat 0 (대조)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dem = Dem()
    sc = scenario(a.case, dem)
    sp = SCN / f"qa_dem_{a.case}.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    terr = ["--terrain-flat", "0"] if a.flat else ["--terrain-dem", str(DEM_JSON)]
    st = h.Stack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                 core_extra=[*terr, "--frames", str(a.frames)])
    res: dict = {"case": a.case, "terrain": terr}
    try:
        st.start_one("datalink")
        st.start_one("agent")
        time.sleep(st.settle)
        ob = h.Observer([st.endpoint()])
        ob.keep_traj = True
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 900:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.0)
        from swarm.v1 import truth_pb2
        kills = []
        for k, p in ob.events:
            if not k.endswith("kill"):
                continue
            e = truth_pb2.TruthEvent.FromString(bytes(p))
            kills.append({"entity": e.kill.entity_id, "cause": e.kill.cause, "frame": e.header.frame})
        res["last_frame"] = ob.last_frame
        res["kills"] = kills
        res["uav"] = analyse(dict(ob.traj), kills, dem)
        res["core_log_head"] = [ln for ln in st.log_text().get("core", "").splitlines() if any(w in ln.lower() for w in ("terrain", "dem", "warn", "경고"))][:8]
        res["log_issues"] = h.scan_logs(st)
        ob.bus.close()
    finally:
        st.down()
    txt = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    (out / "result.json").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
