"""QA 13차 TC-QA-058~062: MISSED 종료, 능선 뒤 표적 Strike, realtime 상한, Sensor·Jammer 상한.

`qa/strike_burst.py`와 같은 관찰 방식(Core onboard/<id>/StrikeActivity = 진실, GCS swarm/gcs-01/rx/ms/*Activity = 수신)을
쓰고, `qa/strike_burst_agent.py`(정해진 MA 프레임에 명령을 내는 Agent)로 명령을 낸다. 링크 손실은 0이다.
결과 폴더의 result.json·rx.json은 `qa/strike_burst_keys.py`로 키별 분석을 할 수 있는 형식이다.

--case cases (평지 0 m)
  uav-001 (500 m, 정지) agm_short 세 스테이션
  - sta1: max_flight_time_s 3 s로 재정의, 5 km 표적에 발사 → MISSED expired
  - sta2: 같은 표적(tgt-a)에 20 ms 간격 2발 → 앞 무장 IMPACT, 뒤 무장은 그 살상반경 안 → MISSED destroyed
  - sta3: 1 s 뒤 같은 표적에 1발 → 비행 중 표적 소멸, 마지막 위치로 좌표 유도
  uav-002 (500 m, 정지) 카메라 cam0, 재머 jam0(반경 10 m로 재정의)
  - 프레임 600~649 매 프레임 SensorCommand enable 토글, 700~749 매 프레임 JammerCommand enable 토글
--case ridge (DEM, 설악 대청봉 능선, `qa/los_check.py` 배치)
  능선 서쪽 같은 지점에 고도만 다른 사수 4기(차폐 −150 m, 경계 −1 m, 경계 +1 m, 트임 +150 m), 표적은 동쪽 사면 지상 2 m.
  seeker_fov_deg를 360으로 재정의해 FOV는 판정에서 뺀다. 모두 같은 프레임에 표적 지정 발사, 차폐 사수는 조준점 발사도 한다.
  --point: 사수 초기 자세를 표적 방향(방위·내림각)으로 맞춘다. 없으면 기수가 북쪽이다(첫 실행 qa/out/ridge/h10_north).

uv run python qa/strike_cases.py --case cases --out qa/out/cases/h10 --hz 10
uv run python qa/strike_cases.py --case cases --out qa/out/cases/h0 --hz 0
uv run python qa/strike_cases.py --case cases --out qa/out/cases/rt10 --hz 10 --realtime
uv run python qa/strike_cases.py --case ridge --point --out qa/out/ridge/h10 --hz 10 --frames 3300
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from p5_e2e import P5Observer  # noqa: E402
from strike_burst import M_LAT, SCN, BurstObserver, BurstStack, at  # noqa: E402

FRAME_US = 20_000
F0 = 100
NOLOSS = {"p_gb": 0.0, "p_bg": 1.0, "loss_good": 0.0, "loss_bad": 0.0}


def base(name: str, ents: list[dict], realtime: bool, extent: dict, origin: dict) -> dict:
    return {"schema_version": "0.1", "name": name, "description": "QA 13차 StrikeActivity·임무장비 보고",
            "map": {"origin": origin, "extent": extent},
            "run": {"mode": "realtime" if realtime else "lockstep", "frame_hz": 50, "seed": 20261107,
                    "rate": 1.0 if realtime else 20.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": NOLOSS}, {"name": "gcs_default", "ge": NOLOSS}],
            "entities": ents, "mission_plan": {"plan_id": "plan-qa13", "tasks": []}}


def uav(eid: str, pos: dict, payloads: list[dict]) -> dict:
    return {"id": eid, "kind": "uav", "side": "blue", "dynamics": "static", "initial": {"position": pos},
            "payloads": payloads, "autonomy": {"ma_plugin": "flocking_basic", "ma_params": {"group": "alpha"}},
            "link_profile": "uav_default", "controlling_gcs": "gcs-01"}


def case_cases(realtime: bool) -> tuple[dict, list[dict], dict]:
    agm = {"type": "agm_short", "profile": "agm_generic"}
    ents = [{"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(-2000, 0), "alt_m": 30.0}}, "link_profile": "gcs_default"},
            uav("uav-001", {**at(0, 0), "alt_m": 500.0},
                [{"id": "sta1", **agm, "count": 1, "overrides": {"max_flight_time_s": 3.0}},
                 {"id": "sta2", **agm, "count": 2}, {"id": "sta3", **agm, "count": 1}]),
            uav("uav-002", {**at(0, 500), "alt_m": 500.0},
                [{"id": "cam0", "type": "camera", "profile": "eo_wide"},
                 {"id": "jam0", "type": "jammer", "profile": "ea_generic",
                  "overrides": {"radius_m": 10.0, "max_radius_m": 20.0}}])]
    for tid, (dn, de) in {"tgt-a": (1000, 0), "tgt-far": (5000, 0)}.items():
        ents.append({"id": tid, "kind": "ground_target", "side": "red", "dynamics": "static",
                     "initial": {"position": at(dn, de)}})
    pl = [{"f": F0, "e": "uav-001", "pid": "sta1", "tgt": "tgt-far"},
          {"f": F0, "e": "uav-001", "pid": "sta2", "tgt": "tgt-a"},
          {"f": F0 + 1, "e": "uav-001", "pid": "sta2", "tgt": "tgt-a"},
          {"f": F0 + 50, "e": "uav-001", "pid": "sta3", "tgt": "tgt-a"}]
    pl += [{"f": f, "e": "uav-002", "pid": "cam0", "kind": "sensor", "en": f % 2 == 1} for f in range(600, 650)]
    pl += [{"f": f, "e": "uav-002", "pid": "jam0", "kind": "jam", "en": f % 2 == 0} for f in range(700, 750)]
    sc = base("qa-cases", ents, realtime, {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9,
                                           "east_deg": 128.1}, at(0, 0))
    return sc, pl, {"terrain": ["--terrain-flat", "0"]}


def aim_quat(src: tuple, dst: tuple) -> dict:
    """src에서 dst를 보는 기수(요·피치, 롤 0) 쿼터니언. NED 기준 FRD 동체."""
    m_lon = M_LAT * math.cos(math.radians(src[0]))
    dn, de, dd = (dst[0] - src[0]) * M_LAT, (dst[1] - src[1]) * m_lon, src[2] - dst[2]
    yaw, pitch = math.atan2(de, dn), -math.atan2(dd, math.hypot(dn, de))
    cy, sy, cp, sp = math.cos(yaw / 2), math.sin(yaw / 2), math.cos(pitch / 2), math.sin(pitch / 2)
    return {"w": cy * cp, "x": -sy * sp, "y": cy * sp, "z": sy * cp}


def case_ridge(realtime: bool, point: bool = False) -> tuple[dict, list[dict], dict]:
    import los_check as lc
    from dem_check import DEM_JSON, Dem
    dem = Dem()
    lc.SITES = {"seorak": lc.SITES["seorak"]}
    dz = lc.design(dem)["seorak"]
    tgt = dz["target"]
    sl, so = dz["sensor"]
    alts = dz["sensor_alts"]
    wp = {"type": "agm_short", "profile": "agm_generic", "overrides": {"seeker_fov_deg": 360.0}}
    ents = [{"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {"lat_deg": sl, "lon_deg": so, "alt_m": round(dem.el(sl, so) + 30.0, 1)}},
             "link_profile": "gcs_default"},
            {"id": "tgt-r", "kind": "ground_target", "side": "red", "dynamics": "static",
             "initial": {"position": {"lat_deg": tgt[0], "lon_deg": tgt[1], "alt_m": tgt[2]}}}]
    shooters = {"uav-low": alts["low"], "uav-elo": alts["edge_lo"], "uav-ehi": alts["edge_hi"],
                "uav-high": alts["high"]}
    los = {}
    for eid, alt in shooters.items():
        ents.append(uav(eid, {"lat_deg": sl, "lon_deg": so, "alt_m": alt},
                        [{"id": "sta1", **wp, "count": 1}, {"id": "sta2", **wp, "count": 1}]))
        if point:  # 기수를 표적 쪽으로 (초기 자세)
            ents[-1]["initial"]["attitude"] = aim_quat((sl, so, alt), tuple(tgt))
        ok, worst = lc.los(dem, (sl, so, alt), tuple(tgt), 50.0)
        los[eid] = {"alt_m": alt, "los50": ok, "margin50_m": worst["margin_m"]}
    pl = [{"f": F0, "e": e, "pid": "sta1", "tgt": "tgt-r"} for e in shooters]
    pl.append({"f": F0, "e": "uav-low", "pid": "sta2", "aim": [tgt[0], tgt[1], tgt[2] - 2.0]})
    sc = base("qa-ridge", ents, realtime, {"south_deg": 38.0, "north_deg": 38.25, "west_deg": 128.3,
                                           "east_deg": 128.6}, {"lat_deg": sl, "lon_deg": so, "alt_m": 0.0})
    return sc, pl, {"terrain": ["--terrain-dem", str(DEM_JSON)], "design": dz, "shooter_los": los,
                    "dem": dem}


class CaseObserver(BurstObserver):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        self.jact: list[tuple] = []
        self.sact2: list[tuple] = []
        self.subs.append(self.bus.subscribe("onboard/*/JammerActivity", self._jact))

    def _jact(self, s) -> None:  # noqa: ANN001
        a = self.ms.JammerActivity.FromString(s.payload)
        with self.lock:
            self.jact.append((a.header.frame, s.key.split("/")[1], a.payload_id, a.active))

    def _gact(self, s) -> None:  # noqa: ANN001
        BurstObserver._gact(self, s)
        P5Observer._gact(self, s)  # 모든 *Activity 수신 (gact)


def other_activity(core_s: list[tuple], core_j: list[tuple], gact: list[tuple]) -> dict:
    """Sensor·Jammer: Core 변화 수, GCS가 받은 서로 다른 본문 변화 수, 주기 틱 밖 송신 간격"""
    out = {}
    for name, core in (("SensorActivity", core_s), ("JammerActivity", core_j)):
        rows = sorted([g for g in gact if g[2] == name and g[3] == "uav-002"], key=lambda g: (g[6], g[4]))
        ch_core, prev = [], None
        for f, e, pid, act in sorted(core):
            if e == "uav-002" and act != prev:
                ch_core.append((f, act))
                prev = act
        rx_ch, prev = [], None
        for g in rows:
            if g[9] != prev:
                rx_ch.append(g)
                prev = g[9]
        sends = sorted({g[5] for g in rows if g[5] % 50})
        gaps = [(b - a) * FRAME_US / 1e3 for a, b in zip(sends, sends[1:])]
        win = [g for g in rows if (600 if name == "SensorActivity" else 700) <= g[5] <= 760]
        wsend = sorted({g[5] for g in win})
        out[name] = {"core_msgs": len([c for c in core if c[1] == "uav-002"]), "core_changes": len(ch_core),
                     "rx_msgs": len(rows), "rx_distinct_changes": len(rx_ch),
                     "window_send_frames": wsend,
                     "window_min_gap_ms": min([(b - a) * FRAME_US / 1e3 for a, b in zip(wsend, wsend[1:])],
                                              default=None),
                     "nonperiod_min_gap_ms": min(gaps, default=None),
                     "last_core_active": ch_core[-1][1] if ch_core else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=("cases", "ridge"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--frames", type=int, default=1100)
    ap.add_argument("--base-port", type=int, default=48400)
    ap.add_argument("--point", action="store_true", help="ridge: 사수 기수를 표적 쪽으로")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc, pl, info = case_cases(a.realtime) if a.case == "cases" else case_ridge(a.realtime, a.point)
    dem = info.pop("dem", None)
    sp = SCN / f"qa_{a.case}.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    probe_out = out / "probe.json"
    os.environ["BURST_OUT"] = str(probe_out)
    os.environ["BURST_PLAN"] = json.dumps(pl)
    st = BurstStack(out / "stack", sp, base_port=a.base_port, lockstep=not a.realtime,
                    rate=1.0 if a.realtime else 20.0, record=False,
                    core_extra=[*info["terrain"], "--frames", str(a.frames)])
    res: dict = {"case": a.case, "hz": a.hz, "realtime": a.realtime, "plan_n": len(pl), **info}
    t_wall = time.monotonic()
    try:
        st.start_one("datalink")
        st.start_one("agent", ["--activity-max-hz", str(a.hz)])
        time.sleep(st.settle)
        ob = CaseObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 600:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.5)
        with ob.lock:
            core, rx, gact = list(ob.core), list(ob.rx), list(ob.gact)
            sact, jact, act_lo = list(ob.sact), list(ob.jact), list(ob.act_lo)
        evs = ob.parsed_events()
        probe = json.loads(probe_out.read_text(encoding="utf-8")) if probe_out.exists() else {}
        res["wall_s"] = round(time.monotonic() - t_wall, 1)
        res["last_frame"] = ob.last_frame
        res["core"] = core
        res["rx_n"] = len(rx)
        res["drops"] = [x for x in act_lo if x[4] != "DELIVERED"]
        res["probe_cmds"] = len(probe.get("cmds", []))
        cmd_f = defaultdict(list)
        for c in probe.get("cmds", []):
            cmd_f[(c["e"], c["pid"])].append(c["f"])
        res["cmd_frames_first"] = {f"{k[0]}/{k[1]}": v[0] for k, v in cmd_f.items()}
        ev_rows = []
        for k, e, _ in evs:
            w = e.WhichOneof("event")
            x = getattr(e, w)
            row = {"f": e.header.frame, "t_us": e.header.sim_time_us, "kind": w}
            if w == "launch":
                row |= {"shooter": x.shooter, "weapon": x.weapon_entity, "target": x.target_id}
            elif w == "impact":
                p = x.position
                row |= {"weapon": x.weapon_entity, "killed": list(x.killed), "lat": round(p.lat_deg, 6),
                        "lon": round(p.lon_deg, 6), "alt": round(p.alt_m, 1)}
                if dem is not None:
                    row["ground_m"] = round(dem.el(p.lat_deg, p.lon_deg), 1)
                    tg = info["design"]["target"]
                    row["to_target_m"] = round(h.dist_m((p.lat_deg, p.lon_deg), (tg[0], tg[1])), 1)
            elif w == "kill":
                row |= {"entity": x.entity_id, "cause": x.cause}
            elif w == "spawn":
                row |= {"entity": x.entity.id}
            ev_rows.append(row)
        res["events"] = ev_rows
        if a.case == "cases":
            res["other_activity"] = other_activity(sact, jact, gact)
        res["log_issues"] = h.scan_logs(st)
        with open(out / "rx.json", "w", encoding="utf-8") as f:
            json.dump(rx, f, ensure_ascii=False)
        with open(out / "gact.json", "w", encoding="utf-8") as f:
            json.dump(gact, f, ensure_ascii=False)
        ob.close()
    finally:
        st.down()
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res.get(k) for k in ("case", "hz", "realtime", "wall_s", "last_frame", "rx_n", "drops",
                                              "shooter_los", "other_activity", "log_issues")},
                     ensure_ascii=False, indent=1, default=str))
    for c in core:
        print("  core", c["f"], c["e"], c["pid"], c["state"], c["reason"], c["weapon"])
    for r in ev_rows:
        if r["kind"] != "spawn":
            print("  ev", r)


if __name__ == "__main__":
    main()
