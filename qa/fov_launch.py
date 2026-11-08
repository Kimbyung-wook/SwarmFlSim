"""QA 15차 TC-QA-075~077: 조준점 StrikeCommand의 발사 시점 FOV 판정 (DEC-066, IMP-PAY-009).

평지(--terrain-flat 0), lockstep. 정지 사수 uav-001(고도 500 m, 기수 북쪽·수평, agm_short FOV 90°·축 고각 −30°)이
케이스마다 다른 스테이션(각 2발)으로 조준점 1발을 쏜다. `qa/strike_burst_agent.py`가 정해진 MA 프레임에 명령을 낸다.
발사 시점 응답만 본다: Core onboard StrikeActivity(상태·사유·weapon_entity), GCS 수신 StrikeActivity,
onboard StoreLoadout 잔량, truth/event launch·spawn, truth/state 엔티티 수. 비행·도달은 보지 않는다.

uv run python qa/fov_launch.py --out qa/out/fov/r1
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from strike_burst import M_LAT, SCN, BurstObserver, BurstStack, SH  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOLOSS = {"p_gb": 0.0, "p_bg": 1.0, "loss_good": 0.0, "loss_bad": 0.0}
ALT = 500.0
HALF = 45.0
EL_AXIS = -30.0


def ned_to_geo(n: float, e: float, alt: float) -> list[float]:
    return [round(SH[0] + n / M_LAT, 8), round(SH[1] + e / (M_LAT * math.cos(math.radians(SH[0]))), 8), alt]


def axis_angle(n: float, e: float, alt: float) -> float:
    """사수(원점, ALT)에서 본 조준점과 탐색 축(북쪽, 고각 −30°) 사이 각 (평면 근사)"""
    d = (n, e, ALT - alt)  # NED down +
    ax = (math.cos(math.radians(EL_AXIS)), 0.0, -math.sin(math.radians(EL_AXIS)))
    c = sum(x * y for x, y in zip(d, ax)) / math.sqrt(sum(x * x for x in d))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def at_dir(rng: float, az_deg: float, el_deg: float) -> tuple[float, float, float]:
    """사수 기준 수평 거리 rng, 방위 az, 고각 el인 점의 (n, e, alt)"""
    return (rng * math.cos(math.radians(az_deg)), rng * math.sin(math.radians(az_deg)),
            ALT + rng * math.tan(math.radians(el_deg)))


def az_boundary() -> float:
    """고각 −30°에서 축과 45°가 되는 방위"""
    c = (math.cos(math.radians(HALF)) - math.sin(math.radians(30)) ** 2) / math.cos(math.radians(30)) ** 2
    return math.degrees(math.acos(c))


def cases() -> list[dict]:
    azb = az_boundary()
    pts = {
        "on_axis": (866.0, 0.0, 0.0, "LAUNCHED"),
        "behind": (-1500.0, 0.0, 0.0, "REJECTED"),
        "abeam": (0.0, 1500.0, 0.0, "REJECTED"),
        "el_up_in": (*at_dir(1000.0, 0.0, 14.7)[:2], at_dir(1000.0, 0.0, 14.7)[2], "LAUNCHED"),
        "el_up_out": (*at_dir(1000.0, 0.0, 15.3)[:2], at_dir(1000.0, 0.0, 15.3)[2], "REJECTED"),
        "az_in": (*at_dir(800.0, azb - 0.5, -30.0)[:2], at_dir(800.0, azb - 0.5, -30.0)[2], "LAUNCHED"),
        "az_out": (*at_dir(800.0, azb + 0.5, -30.0)[:2], at_dir(800.0, azb + 0.5, -30.0)[2], "REJECTED"),
    }
    out = []
    for i, (name, (n, e, alt, exp)) in enumerate(pts.items()):
        out.append({"case": name, "pid": f"sta{i + 1}", "f": 100 + 20 * i, "n": round(n, 2), "e": round(e, 2),
                    "alt": round(alt, 2), "angle_deg": round(axis_angle(n, e, alt), 3), "expect": exp,
                    "aim": ned_to_geo(n, e, alt)})
    return out


def scenario(cs: list[dict]) -> dict:
    stations = [{"id": c["pid"], "type": "agm_short", "profile": "agm_generic", "count": 2} for c in cs]
    ents = [{"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {"lat_deg": SH[0] - 2000 / M_LAT, "lon_deg": SH[1], "alt_m": 30.0}},
             "link_profile": "gcs_default"},
            {"id": "uav-001", "kind": "uav", "side": "blue", "dynamics": "static",
             "initial": {"position": {"lat_deg": SH[0], "lon_deg": SH[1], "alt_m": ALT},
                         "attitude": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}},
             "payloads": stations, "autonomy": {"ma_plugin": "flocking_basic", "ma_params": {"group": "alpha"}},
             "link_profile": "uav_default", "controlling_gcs": "gcs-01"}]
    return {"schema_version": "0.1", "name": "qa-fov-launch", "description": "QA 15차 조준점 FOV 판정 (DEC-066)",
            "map": {"origin": {"lat_deg": SH[0], "lon_deg": SH[1], "alt_m": 0.0},
                    "extent": {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9, "east_deg": 128.1}},
            "run": {"mode": "lockstep", "frame_hz": 50, "seed": 20261108, "rate": 20.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": NOLOSS}, {"name": "gcs_default", "ge": NOLOSS}],
            "entities": ents, "mission_plan": {"plan_id": "plan-qa15-fov", "tasks": []}}


class FovObserver(BurstObserver):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        self.loadout: list[tuple[int, dict]] = []
        self.ent_n: list[tuple[int, int]] = []
        self.subs.append(self.bus.subscribe("onboard/uav-001/StoreLoadout", self._lo))

    def _lo(self, s) -> None:  # noqa: ANN001
        m = self.ms.StoreLoadout.FromString(s.payload)
        with self.lock:
            self.loadout.append((m.header.frame, {p.id: p.count for p in m.stores}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=400)
    ap.add_argument("--base-port", type=int, default=48700)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cs = cases()
    sp = SCN / "qa_fov_launch.json"
    sp.write_text(json.dumps(scenario(cs), ensure_ascii=False, indent=1), encoding="utf-8")
    os.environ["BURST_OUT"] = str(out / "probe.json")
    os.environ["BURST_PLAN"] = json.dumps([{"f": c["f"], "e": "uav-001", "pid": c["pid"], "aim": c["aim"]} for c in cs])
    st = BurstStack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                    core_extra=["--terrain-flat", "0", "--frames", str(a.frames)])
    try:
        st.start_one("datalink")
        st.start_one("agent")
        time.sleep(st.settle)
        ob = FovObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 300:
            time.sleep(0.5)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.5)
        with ob.lock:
            core, rx, lo, ent_n = list(ob.core), list(ob.rx), list(ob.loadout), list(ob.entity_n)
        evs = ob.parsed_events()
        last_frame = ob.last_frame
        issues = h.scan_logs(st)
        ob.close()
    finally:
        st.down()
    probe = json.loads((out / "probe.json").read_text(encoding="utf-8")) if (out / "probe.json").exists() else {}
    ev = Counter()
    ev_rows = []
    for _, e, _ in evs:
        w = e.WhichOneof("event")
        if w in ("launch", "spawn"):
            ev[w] += 1
            x = getattr(e, w)
            ev_rows.append({"f": e.header.frame, "kind": w,
                            "weapon": x.weapon_entity if w == "launch" else x.entity.id})
    rows = []
    for c in cs:
        mine = [r for r in core if r["pid"] == c["pid"]]
        first = next((r for r in mine if r["state"] in ("LAUNCHED", "REJECTED")), None)
        g = next((r for r in rx if r["pid"] == c["pid"] and r["state"] in ("LAUNCHED", "REJECTED")), None)
        before = [l for f, l in lo if f < c["f"]]
        after = [l for f, l in lo if f >= c["f"]]
        cnt_before = before[-1].get(c["pid"]) if before else None
        cnt_end = lo[-1][1].get(c["pid"]) if lo else None
        launch_ev = [r for r in ev_rows if r["kind"] == "launch" and first and r["weapon"] == first["weapon"]
                     and first["weapon"]]
        exp_cnt = 1 if c["expect"] == "LAUNCHED" else 2
        state = first["state"] if first else None
        reason = first["reason"] if first else None
        ok = (state == c["expect"] and (reason == "out_of_fov" if c["expect"] == "REJECTED" else reason == "")
              and cnt_end == exp_cnt
              and ((not first["weapon"] and not launch_ev) if c["expect"] == "REJECTED" else bool(launch_ev))
              and g is not None and g["state"] == state and g["reason"] == reason)
        rows.append({"case": c["case"], "angle_deg": c["angle_deg"], "aim_alt_m": c["alt"], "cmd_f": c["f"],
                     "expect": c["expect"], "state": state, "reason": reason,
                     "core_f": first["f"] if first else None, "weapon": first["weapon"] if first else None,
                     "launch_event": len(launch_ev), "count_before": cnt_before, "count_end": cnt_end,
                     "gcs_rx": f"{g['state']}/{g['reason']}" if g else None, "pass": ok,
                     "loadout_msgs_after": len(after)})
    res = {"last_frame": last_frame, "cmds": len(probe.get("cmds", [])), "events": dict(ev),
           "launched_expected": sum(c["expect"] == "LAUNCHED" for c in cs),
           "entity_count_min_max": [min(ent_n), max(ent_n)] if ent_n else None,
           "loadout_frames": [f for f, _ in lo], "az_boundary_deg": round(az_boundary(), 3), "cases": rows,
           "log_issues": issues[:20]}
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "cases"}, ensure_ascii=False, default=str))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    finally:
        h.Stack.down_all()
