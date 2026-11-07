"""QA 15차 TC-QA-065~068: 합성 언덕 DEM으로 비행 중 가시선 상태 전환 검증 (DEC-064, IMP-PAY-008).

실제 DEM 대신 해석식 언덕 하나(가우스형, int16 반올림)를 `data/dem/korea_glo90.json`과 같은 머리글 형식
(format=swarm-dem-grid)으로 만들어 Core `--terrain-dem`에 준다. 유도 상태는 버스로 보고되지 않으므로(OPN-055)
`qa/los_track.py`와 같은 방식으로 truth 궤적에서 프레임마다 유도 가설(T: 표적 추적, C: 고정점 좌표 유도)을
한 프레임 재계산으로 분류하고, Python 가시선(`qa/los_check.py` los(), make_terrain_los와 같은 식)과 견준다.

판정 규칙(payload_system.cpp run_weapons): truth 프레임 k(프레임 시작 상태)의 유도 객체–표적 가시선이
  막힘 → 그 프레임은 C(고정점 = 마지막 T 프레임의 표적 위치), 트임 → T(FOV 360°, 거리 ≤ lock_range).
기대 상태열과 관측 상태열이 프레임 단위로 같은지 본다.

출력은 판정 요약(전환 프레임, 일치/불일치)만 낸다. 원자료는 결과 폴더의 traj.json·result.json에 남는다.

uv run python qa/los_synth.py dem                                   # qa/out/los_synth/dem/synth_hill.json
uv run python qa/los_synth.py design                                # Python 사전 비행으로 예상 상태열
uv run python qa/los_synth.py run --case hill --out qa/out/los_synth/hill_a
uv run python qa/los_synth.py analyse qa/out/los_synth/hill_a
uv run python qa/los_synth.py same qa/out/los_synth/hill_a qa/out/los_synth/hill_b   # 결정성
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
import los_check as lc  # noqa: E402
import los_track as lt  # noqa: E402
from dem_check import Dem  # noqa: E402
from strike_burst import SCN, BurstStack  # noqa: E402
from strike_cases import F0, aim_quat, base, uav  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM_DIR = ROOT / "qa/out/los_synth/dem"
DEM_JSON = DEM_DIR / "synth_hill.json"
M_LAT = 111_320.0
DT = 0.02

# 합성 격자: 0.0003° 간격 401×401 (약 13.4 km × 10.5 km), 0행 0열 = 남서 모서리
GRID = {"lat0_deg": 38.0, "lon0_deg": 128.0, "dlat_deg": 0.0003, "dlon_deg": 0.0003, "rows": 401, "cols": 401}
# 언덕: 중심(격자 가운데), 높이 H, 표준편차 σ (m). 고도 z = H·exp(−r²/2σ²), 평지 0 m
HILL = {"lat_deg": 38.06, "lon_deg": 128.06, "h_m": 150.0, "sigma_m": 80.0}


def at(dn: float, de: float) -> tuple[float, float]:
    """언덕 중심 기준 북·동 거리(m) → 위경도 (시나리오 배치용 근사)"""
    lat = HILL["lat_deg"] + dn / M_LAT
    return lat, HILL["lon_deg"] + de / (M_LAT * math.cos(math.radians(HILL["lat_deg"])))


def hill_z(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    dn = (lat - HILL["lat_deg"]) * M_LAT
    de = (lon - HILL["lon_deg"]) * M_LAT * math.cos(math.radians(HILL["lat_deg"]))
    return HILL["h_m"] * np.exp(-(dn * dn + de * de) / (2.0 * HILL["sigma_m"] ** 2))


def write_dem(path: Path = DEM_JSON) -> Path:
    g = GRID
    lat = g["lat0_deg"] + np.arange(g["rows"]) * g["dlat_deg"]
    lon = g["lon0_deg"] + np.arange(g["cols"]) * g["dlon_deg"]
    z = np.rint(hill_z(lat[:, None], lon[None, :])).astype("<i2")  # south_to_north 행 순서
    path.parent.mkdir(parents=True, exist_ok=True)
    data = path.with_suffix(".bin")
    z.tofile(data)
    hd = {"format": "swarm-dem-grid", "version": 1, "data_file": data.name, "sample_type": "int16",
          "byte_order": "little", "row_order": "south_to_north", "units": "m", **g,
          "source": "QA 합성 언덕 (los_synth.py)", "hill": HILL}
    path.write_text(json.dumps(hd, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# 배치 ------------------------------------------------------------------------
# 사수: 언덕 서쪽 정지. 표적: 언덕 동쪽 평지에서 북쪽으로 이동(지상 2 m). 이동 중 언덕 그늘로 들어갔다가 나온다.
# 값은 design(사전 비행)으로 골랐다. hill: 상실 1회 후 재획득. edge: 재획득 직후 그늘 가장자리에서 한 번 더 깜박인다
GEOM = {"shooter_ne": (-150.0, -2600.0), "shooter_alt": 450.0,
        "tgt_e": 900.0, "tgt_n0": -180.0, "tgt_n1": 1600.0, "tgt_speed": 50.0}
CASE_GEOM = {"hill": {}, "edge": {"tgt_n0": -270.0}, "flat": {}, "coord": {}}
OV = {"seeker_fov_deg": 360.0}  # FOV는 판정에서 뺀다(가시선만 본다)


def scenario(case: str) -> tuple[dict, list[dict], dict]:
    g = {**GEOM, **CASE_GEOM[case]}
    sl, so = at(*g["shooter_ne"])
    salt = g["shooter_alt"]
    p0 = at(g["tgt_n0"], g["tgt_e"])
    path, n = [], g["tgt_n0"] + 25.0
    while n <= g["tgt_n1"] + 1e-9:
        la, lo = at(n, g["tgt_e"])
        path.append({"lat_deg": round(la, 7), "lon_deg": round(lo, 7), "alt_m": 2.0})
        n += 25.0
    tgt = {"id": "tgt-m", "kind": "ground_target", "side": "red", "dynamics": "scripted",
           "initial": {"position": {"lat_deg": round(p0[0], 7), "lon_deg": round(p0[1], 7), "alt_m": 2.0},
                       "velocity_ned_mps": {"x": g["tgt_speed"], "y": 0.0, "z": 0.0}},
           "script_path": path}
    wp = {"type": "agm_short", "profile": "agm_generic", "overrides": OV}
    ents = [{"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {"lat_deg": sl, "lon_deg": so, "alt_m": 30.0}}, "link_profile": "gcs_default"},
            tgt]
    tl = at(g["tgt_n0"] + g["tgt_speed"] * F0 * DT, g["tgt_e"]) + (2.0,)  # 발사 프레임의 표적 위치
    ents.append(uav("uav-s", {"lat_deg": sl, "lon_deg": so, "alt_m": salt},
                    [{"id": "sta1", **wp, "count": 1}, {"id": "sta2", **wp, "count": 1}]))
    ents[-1]["initial"]["attitude"] = aim_quat((sl, so, salt), tl)
    if case == "coord":  # 고정 좌표(조준점) 모드: 표적 지정 없이 같은 지점을 겨눈다
        pl = [{"f": F0, "e": "uav-s", "pid": "sta1", "aim": [tl[0], tl[1], 0.0]}]
    else:
        pl = [{"f": F0, "e": "uav-s", "pid": "sta1", "tgt": "tgt-m"}]
    sc = base(f"qa-los-synth-{case}", ents, False,
              {"south_deg": 38.0, "north_deg": 38.12, "west_deg": 128.0, "east_deg": 128.12},
              {"lat_deg": HILL["lat_deg"], "lon_deg": HILL["lon_deg"], "alt_m": 0.0})
    sc["description"] = "QA 15차 합성 언덕 가시선 전환 (DEC-064)"
    terrain = ["--terrain-flat", "0"] if case == "flat" else ["--terrain-dem", str(DEM_JSON)]
    return sc, pl, {"terrain": terrain, "geom": g, "hill": HILL, "aim_at_launch": tl}


# Python 사전 비행 (배치 고르기용, 판정에는 쓰지 않는다) -------------------------
def design(a: argparse.Namespace) -> dict:
    dem = a.dem if getattr(a, "dem", None) else Dem(write_dem())
    g = dict(GEOM)
    for kv in a.set:
        k, v = kv.split("=")
        g[k] = float(v)
    p = dict(lt.AGM, **OV)
    sl, so = at(*g["shooter_ne"])
    pos = (sl, so, g["shooter_alt"])
    tl = at(g["tgt_n0"] + g["tgt_speed"] * F0 * DT, g["tgt_e"]) + (2.0,)
    vel = lt.mul(p["launch_speed_mps"], lt.unit(lt.ned_between(pos, tl)))
    t_fl, last, lost, seq = 0.0, None, False, []
    for k in range(3000):
        n = g["tgt_n0"] + g["tgt_speed"] * (F0 + 1 + k) * DT
        tp = at(n, g["tgt_e"]) + (2.0,)
        tv = (g["tgt_speed"], 0.0, 0.0)
        vis = lc.los(dem, pos, tp, 50.0)[0]
        lost = not vis and last is not None
        if not lost:
            last = tp
        seq.append("T" if not lost else "C")
        pos, vel = lt.step_weapon(p, pos, vel, t_fl, tp if not lost else last, tv if not lost else (0, 0, 0))
        t_fl += DT
        if pos[2] - dem.el(pos[0], pos[1]) <= 0 or lt.pos_err(pos, tp) < 3.0:
            break
    runs = []
    for i, c in enumerate(seq):
        if runs and runs[-1][2] == c:
            runs[-1][1] = i
        else:
            runs.append([i, i, c])
    end = {"runs": runs, "clear_m": round(pos[2] - dem.el(pos[0], pos[1]), 1),
           "miss_m": round(lt.pos_err(pos, tp), 1)}
    if not getattr(a, "quiet", False):
        print("geom", g)
        print("runs(flight frame)", end)
    return end


# 실행 ------------------------------------------------------------------------
def run(a: argparse.Namespace) -> None:
    write_dem()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc, pl, info = scenario(a.case)
    if a.seed is not None:
        sc["run"]["seed"] = a.seed
    sp = SCN / f"qa_los_synth_{a.case}.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.environ["BURST_OUT"] = str(out / "probe.json")
    os.environ["BURST_PLAN"] = json.dumps(pl)
    st = BurstStack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                    core_extra=[*info["terrain"], "--frames", str(a.frames)])
    res: dict = {"case": a.case, "scenario": str(sp), "seed": sc["run"]["seed"], "plan": pl, **info}
    try:
        st.start_one("datalink")
        st.start_one("agent", ["--activity-max-hz", "10"])
        time.sleep(st.settle)
        ob = lt.TrackObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 600:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.5)
        with ob.lock:
            tr = {k: list(v) for k, v in ob.tr.items()}
            res["core"] = list(ob.core)
            res["truth_gap_frames"] = ob.gap_frames
        evs = []
        for _, e, _ in ob.parsed_events():
            w = e.WhichOneof("event")
            x = getattr(e, w)
            row = {"f": e.header.frame, "t_us": e.header.sim_time_us, "kind": w}
            if w == "launch":
                row |= {"weapon": x.weapon_entity, "target": x.target_id}
            elif w == "impact":
                p = x.position
                row |= {"weapon": x.weapon_entity, "killed": list(x.killed), "lat": p.lat_deg, "lon": p.lon_deg,
                        "alt": p.alt_m}
            elif w == "kill":
                row |= {"entity": x.entity_id, "cause": x.cause}
            elif w == "spawn":
                row |= {"entity": x.entity.id}
            evs.append(row)
        res["events"] = evs
        res["last_frame"] = ob.last_frame
        res["log_issues"] = h.scan_logs(st)
        ob.close()
    finally:
        st.down()
    log = (out / "stack" / "core.log").read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"overruns (\d+)", log)
    res["overruns"] = int(m[-1]) if m else None
    (out / "traj.json").write_text(json.dumps(tr), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"run {a.case}: last_frame={res['last_frame']} gaps={len(res['truth_gap_frames'] or [])} "
          f"overruns={res['overruns']} log_issues={len(res['log_issues'] or [])} weapons="
          f"{sum(1 for k in tr if k.startswith('wpn-'))}")


# 판정 ------------------------------------------------------------------------
def runs_of(d: dict) -> list[list]:
    seq = []
    for f in sorted(d):
        if seq and seq[-1][2] == d[f] and seq[-1][1] == f - 1:
            seq[-1][1] = f
        else:
            seq.append([f, f, d[f]])
    return seq


def judge(d: Path, tol: float) -> dict:
    """유도 객체마다 기대 상태(가시선) 대 관측 상태(한 프레임 재계산)를 견준다"""
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    tr = json.loads((d / "traj.json").read_text(encoding="utf-8"))
    dem = None if "--terrain-flat" in res["terrain"] else Dem(Path(res["terrain"][1]))
    launches = {e["weapon"]: e for e in res["events"] if e["kind"] == "launch"}
    impacts = {e["weapon"]: e for e in res["events"] if e["kind"] == "impact"}
    aim = next((tuple(p["aim"]) for p in res["plan"] if "aim" in p), None)
    p = dict(lt.AGM, **OV)
    out: dict = {"case": res["case"], "weapons": {}}
    for wid, rows in sorted(tr.items()):
        if not wid.startswith("wpn-"):
            continue
        tid = launches.get(wid, {}).get("target", "")
        fr = {r[0]: r for r in rows}
        live = sorted(f for f, r in fr.items() if r[7])
        tg = {r[0]: r for r in tr.get(tid, [])} if tid else {}
        l0 = live[0]
        exp, obs, margin, skipped = {}, {}, {}, []
        last_t = None  # 마지막 T 프레임의 표적 위치 = 고정점
        for f in live[:-1]:
            if f + 1 not in fr or not fr[f + 1][7]:
                continue
            t_fl = (f - l0 + 1) * DT
            pos, vel, nxt = tuple(fr[f][1:4]), tuple(fr[f][4:7]), tuple(fr[f + 1][1:4])
            if tid:
                if f not in tg:
                    continue
                ok, w = lc.los(dem, pos, tuple(tg[f][1:4]), 50.0)
                margin[f] = w["margin_m"]
                exp[f] = "T" if ok else "C"
            else:
                exp[f] = "A"  # 조준점 좌표 유도
            if abs(t_fl - p["burn_time_s"]) < 1.5 * DT:
                skipped.append(f)  # 연소 종료가 걸친 프레임은 재계산 식이 부 스텝 경계와 어긋날 수 있다
                continue
            if tid:
                eT = lt.pos_err(lt.step_weapon(p, pos, vel, t_fl, tuple(tg[f][1:4]), tuple(tg[f][4:7]))[0], nxt)
                eC = (lt.pos_err(lt.step_weapon(p, pos, vel, t_fl, last_t, (0.0, 0.0, 0.0))[0], nxt)
                      if last_t else math.inf)
                c = "T" if eT <= tol and eT <= eC else ("C" if eC <= tol else "?")
                if c == "T":
                    last_t = tuple(tg[f][1:4])
            else:
                eA = lt.pos_err(lt.step_weapon(p, pos, vel, t_fl, aim, (0.0, 0.0, 0.0))[0], nxt)
                c = "A" if eA <= tol else "?"
            obs[f] = c
        mism = [f for f in obs if obs[f] != exp[f]]
        W = {"target": tid or None, "flight_frames": [l0, live[-1]],
             "expected": [f"{s}:{a}-{b}" for a, b, s in runs_of(exp)],
             "observed": [f"{s}:{a}-{b}" for a, b, s in runs_of(obs)],
             "compared": len(obs), "skipped": skipped, "mismatch_n": len(mism), "mismatch_frames": mism[:20],
             "verdict": "일치" if obs and not mism else "불일치"}
        trans = [b for a, b, _ in runs_of(exp)][:-1]
        if trans and margin:
            W["los_margin_at_transitions_m"] = {f"{f}->{f + 1}": [margin.get(f), margin.get(f + 1)] for f in trans}
        im = impacts.get(wid)
        if im:
            ref = tuple(tg[max(k for k in tg if k <= im["f"])][1:4]) if tg else aim
            W["impact"] = {"f": im["f"], "to_ref_m": round(lt.pos_err((im["lat"], im["lon"], im["alt"]), ref), 2),
                           "killed": im["killed"]}
        else:
            W["impact"] = None
        out["weapons"][wid] = W
    return out


def analyse(a: argparse.Namespace) -> None:
    r = judge(Path(a.dir), a.tol)
    (Path(a.dir) / "analysis.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    for wid, W in r["weapons"].items():
        print(f"[{r['case']}] {wid} target={W['target']} 비행 {W['flight_frames'][0]}-{W['flight_frames'][1]}")
        print(f"  기대 {' '.join(W['expected'])}")
        print(f"  관측 {' '.join(W['observed'])}")
        print(f"  비교 {W['compared']} 프레임, 제외 {W['skipped']}, 불일치 {W['mismatch_n']} {W['mismatch_frames']}"
              f" → {W['verdict']}")
        if "los_margin_at_transitions_m" in W:
            print(f"  전환 프레임 가시선 여유(m) {W['los_margin_at_transitions_m']}")
        im = W["impact"]
        print("  종료 " + (f"impact f={im['f']} 기준점까지 {im['to_ref_m']} m, killed={im['killed']}" if im
                         else "impact 없음"))


def same(a: argparse.Namespace) -> None:
    ra, rb = (json.loads((Path(x) / "result.json").read_text(encoding="utf-8")) for x in (a.a, a.b))
    ta, tb = (json.loads((Path(x) / "traj.json").read_text(encoding="utf-8")) for x in (a.a, a.b))
    keys = sorted(set(ta) | set(tb))
    first = {}
    for k in keys:
        fa, fb = {r[0]: r for r in ta.get(k, [])}, {r[0]: r for r in tb.get(k, [])}
        d = [f for f in sorted(set(fa) | set(fb)) if fa.get(f) != fb.get(f)]
        if d:
            first[k] = d[0]
    ev = ([(e["f"], e["t_us"], e["kind"], e.get("weapon"), e.get("entity")) for e in r["events"]] for r in (ra, rb))
    ev_same = next(ev) == next(ev)
    core_same = ra["core"] == rb["core"]
    ok = not first and ev_same and core_same
    print(f"same {Path(a.a).name} vs {Path(a.b).name}: 궤적 {'일치' if not first else '불일치 ' + str(first)}, "
          f"이벤트 {'일치' if ev_same else '불일치'}, StrikeActivity {'일치' if core_same else '불일치'}"
          f" ({len(keys)} 엔티티) → {'결정적' if ok else '비결정'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("dem").set_defaults(fn=lambda a: print(write_dem()))
    d = sp.add_parser("design")
    d.add_argument("--set", nargs="*", default=[])
    d.set_defaults(fn=design)
    r = sp.add_parser("run")
    r.add_argument("--case", choices=tuple(CASE_GEOM), required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--frames", type=int, default=900)
    r.add_argument("--seed", type=int)
    r.add_argument("--base-port", type=int, default=48800)
    r.set_defaults(fn=run)
    n = sp.add_parser("analyse")
    n.add_argument("dir")
    n.add_argument("--tol", type=float, default=1e-4)
    n.set_defaults(fn=analyse)
    s = sp.add_parser("same")
    s.add_argument("a")
    s.add_argument("b")
    s.set_defaults(fn=same)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
