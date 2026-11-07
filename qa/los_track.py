"""QA 14차 TC-QA-065~: 표적 지정 무장의 비행 중 DEM 가시선 추적 (DEC-064, IMP-PAY-008).

무장 유도 상태는 버스로 보고되지 않는다(OPN-055). 그래서 truth/state의 무장·표적 궤적과 종료 이벤트로 판정한다.

관찰 방법
- 실행: `qa/strike_cases.py`와 같은 묶음(Datalink + 명령 Agent + Core, 링크 손실 0, lockstep)을 띄우고
  truth/state의 무장·표적 상태(위치·속도)를 프레임마다 기록한다(traj.json). `--build`로 다른 빌드를 고를 수 있다.
  DEC-064 이전 빌드(가시선을 보지 않고 계속 추적)를 기준으로 같은 시나리오를 돌려 궤적이 갈라지는 프레임을 잰다.
- 가시선: truth 프레임 k는 Core 프레임 k의 시작 상태다(Payload가 같은 값으로 계산한다). 무장(k)–표적(k) 가시선을
  `qa/los_check.py` `los()`(make_terrain_los와 같은 식, 50 m 표본, 끝점 0.5 m 허용)로 계산한다.
- 한 프레임 재계산: truth k의 무장 상태에서 `payload/src/weapon.cpp` advance_weapon(agm, 부 스텝 5 ms)을 Python으로
  다시 돌려 truth k+1과 견준다. 유도 대상 가설 두 가지
    T(추적): 표적의 프레임 k 위치·속도
    C(좌표): 고정점(마지막으로 본 표적 위치), 속도 0
  어느 가설이 truth k+1을 재현하는지로 프레임마다 유도 상태를 분류한다. 고정점은 T가 처음 어긋난 프레임의 직전
  프레임 표적 위치다(Payload는 추적하는 프레임마다 그 프레임 표적 위치를 저장한다).

케이스
- ridge: 기존 `qa/scenarios/qa_ridge.json`(§21 TC-QA-060, 정지 표적). 계획은 strike_cases.case_ridge(point=True).
- move:  같은 설악 배치. 표적이 동쪽 사면을 따라 내려가며(지상 2 m, 스크립트 경로) 능선 그늘로 들어간다.
         사수 고도 여러 개(th50 + 30·80·150·300 m), 모두 표적 지정 발사. 저고도 사수 1기는 조준점 발사도 한다.

uv run python qa/los_track.py run --case ridge --out qa/out/los_track/ridge_new
uv run python qa/los_track.py run --case ridge --out qa/out/los_track/ridge_old --build <DEC-064 이전 build/msvc-debug>
uv run python qa/los_track.py analyse qa/out/los_track/ridge_new --ref qa/out/los_track/ridge_old
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

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
import los_check as lc  # noqa: E402
from dem_check import DEM_JSON, Dem  # noqa: E402
from strike_burst import SCN, BurstStack  # noqa: E402
from strike_cases import F0, CaseObserver, aim_quat, base, case_cases, case_ridge, uav  # noqa: E402

DT = 0.02
G = 9.80665
A_WGS, F_WGS = 6378137.0, 1.0 / 298.257223563
E2 = F_WGS * (2.0 - F_WGS)
D2R, R2D = math.pi / 180.0, 180.0 / math.pi
AGM = {"max_range_m": 6000.0, "lock_range_m": 6000.0, "seeker_fov_deg": 90.0, "launch_speed_mps": 20.0,
       "thrust_accel_mps2": 80.0, "burn_time_s": 4.0, "drag_k_per_m": 0.00005, "max_g": 15.0, "nav_gain": 3.0,
       "max_flight_time_s": 60.0}


# 시나리오 ------------------------------------------------------------------
def east_m(lat: float, lon: float, m: float) -> float:
    return lon + m / (lc.M_LAT * math.cos(lat * D2R))


def case_move(dem: Dem, speed: float, start_e: float, end_e: float, dalts: tuple, fov: float | None) -> tuple:
    """설악 능선 동쪽 사면을 동쪽으로 내려가는 표적, 서쪽 같은 지점의 사수 여러 기"""
    lc.SITES = {"seorak": lc.SITES["seorak"]}
    dz = lc.design(dem)["seorak"]
    peak = lc.SITES["seorak"]["peak"]
    sl, so = dz["sensor"]
    th50 = dz["threshold_alt_m"]["step50"]
    lat = peak[0]
    path = []
    e = start_e
    while e <= end_e + 1e-9:
        lo = east_m(lat, peak[1], e)
        path.append({"lat_deg": lat, "lon_deg": round(lo, 7), "alt_m": round(dem.el(lat, lo) + 2.0, 2)})
        e += 25.0
    t0 = path[0]
    # 스크립트 경로: 속도 크기만 쓴다(방향은 경로). 첫 점은 initial.position
    tgt_ent = {"id": "tgt-m", "kind": "ground_target", "side": "red", "dynamics": "scripted",
               "initial": {"position": t0, "velocity_ned_mps": {"x": 0.0, "y": speed, "z": 0.0}},
               "script_path": path[1:]}
    ov = {} if fov is None else {"seeker_fov_deg": fov}
    wp = {"type": "agm_short", "profile": "agm_generic", **({"overrides": ov} if ov else {})}
    ents = [{"id": "gcs-01", "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {"lat_deg": sl, "lon_deg": so, "alt_m": round(dem.el(sl, so) + 30.0, 1)}},
             "link_profile": "gcs_default"}, tgt_ent]
    # 발사 시점(프레임 100) 표적 위치를 겨눈다
    s_launch = speed * F0 * DT
    tl = interp_path([(t0["lat_deg"], t0["lon_deg"], t0["alt_m"])] +
                     [(p["lat_deg"], p["lon_deg"], p["alt_m"]) for p in path[1:]], s_launch)
    shooters = {}
    for d in dalts:
        eid = f"uav-{'p' if d >= 0 else 'm'}{abs(int(d)):03d}"
        alt = round(th50 + d, 1)
        shooters[eid] = alt
        ents.append(uav(eid, {"lat_deg": sl, "lon_deg": so, "alt_m": alt},
                        [{"id": "sta1", **wp, "count": 1}, {"id": "sta2", **wp, "count": 1}]))
        ents[-1]["initial"]["attitude"] = aim_quat((sl, so, alt), tl)
    pl = [{"f": F0, "e": e, "pid": "sta1", "tgt": "tgt-m"} for e in shooters]
    low = next(iter(shooters))
    pl.append({"f": F0 + 50, "e": low, "pid": "sta2", "aim": [tl[0], tl[1], tl[2] - 2.0]})  # 1 s 늦게: 같은 사수의 표적 지정 무장과 겹치지 않게
    sc = base("qa-los-track", ents, False, {"south_deg": 38.0, "north_deg": 38.25, "west_deg": 128.3,
                                             "east_deg": 128.6}, {"lat_deg": sl, "lon_deg": so, "alt_m": 0.0})
    sc["description"] = "QA 14차 비행 중 가시선 추적 (DEC-064)"
    info = {"terrain": ["--terrain-dem", str(DEM_JSON)], "design": dz, "shooters": shooters,
            "target_speed_mps": speed, "path_e_m": [start_e, end_e], "aim_at_launch": tl, "fov": fov}
    return sc, pl, info


def interp_path(pts: list[tuple], s: float) -> tuple:
    """스크립트 경로 길이 s 지점(근사: 수평·수직 직선 거리)"""
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = lc.norm(lc.ned(a, b))
        if acc + d >= s:
            f = (s - acc) / d
            return tuple(a[i] + f * (b[i] - a[i]) for i in range(3))
        acc += d
    return pts[-1]


# 실행 ------------------------------------------------------------------------
class TrackObserver(CaseObserver):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        self.tr: dict[str, list] = {}

    def _truth(self, s) -> None:  # noqa: ANN001
        h.Observer._truth(self, s)
        sim, truth, *_ = self.m
        f = truth.TruthFrame.FromString(s.payload)
        fr = f.header.frame
        with self.lock:
            for e in f.entities:
                if e.id.startswith("wpn-") or e.id.startswith("tgt-"):
                    p, v = e.kinematics.position, e.kinematics.velocity_ned_mps
                    self.tr.setdefault(e.id, []).append([fr, p.lat_deg, p.lon_deg, p.alt_m, v.x, v.y, v.z,
                                                         bool(e.alive)])


def run(a: argparse.Namespace) -> None:
    if a.build:
        h.BUILD = Path(a.build)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dem = None
    if a.case == "ridge":
        _, pl, info = case_ridge(False, True)
        info.pop("dem", None)
        sp = SCN / "qa_ridge.json"  # 기존 파일 그대로
    elif a.case == "cases":
        _, pl, info = case_cases(False)
        sp = SCN / "qa_cases.json"
    else:
        dem = Dem()
        sc, pl, info = case_move(dem, a.speed, a.start_e, a.end_e, tuple(a.dalts), a.fov)
        sp = SCN / f"qa_{a.case}.json"
        sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    probe_out = out / "probe.json"
    os.environ["BURST_OUT"] = str(probe_out)
    os.environ["BURST_PLAN"] = json.dumps(pl)
    st = BurstStack(out / "stack", sp, base_port=a.base_port, lockstep=True, rate=20.0, record=False,
                    core_extra=[*info["terrain"], "--frames", str(a.frames)])
    res: dict = {"case": a.case, "build": str(h.BUILD), "scenario": str(sp), "plan": pl,
                 **{k: v for k, v in info.items() if k != "terrain"}, "terrain": info["terrain"]}
    t_wall = time.monotonic()
    try:
        st.start_one("datalink")
        st.start_one("agent", ["--activity-max-hz", "10"])
        time.sleep(st.settle)
        ob = TrackObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 600:
            time.sleep(1.0)
            if (ob.last_frame or 0) >= a.frames - 1 or "core" in "".join(st.dead()):
                break
        time.sleep(1.5)
        with ob.lock:
            core, tr = list(ob.core), {k: list(v) for k, v in ob.tr.items()}
            gaps, frames = ob.gap_frames, ob.frames
        evs = []
        for k, e, _ in ob.parsed_events():
            w = e.WhichOneof("event")
            x = getattr(e, w)
            row = {"f": e.header.frame, "t_us": e.header.sim_time_us, "kind": w}
            if w == "launch":
                row |= {"shooter": x.shooter, "weapon": x.weapon_entity, "target": x.target_id}
            elif w == "impact":
                p = x.position
                row |= {"weapon": x.weapon_entity, "killed": list(x.killed), "lat": p.lat_deg, "lon": p.lon_deg,
                        "alt": p.alt_m}
            elif w == "kill":
                row |= {"entity": x.entity_id, "cause": x.cause}
            elif w == "spawn":
                row |= {"entity": x.entity.id}
            evs.append(row)
        res["wall_s"] = round(time.monotonic() - t_wall, 1)
        res["last_frame"] = ob.last_frame
        res["truth_frames"] = frames
        res["truth_gap_frames"] = gaps
        res["core"] = core
        res["events"] = evs
        res["log_issues"] = h.scan_logs(st)
        ob.close()
    finally:
        st.down()
    log = (out / "stack" / "core.log").read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"overruns (\d+)", log)
    res["overruns"] = int(m[-1]) if m else None
    (out / "traj.json").write_text(json.dumps(tr), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res.get(k) for k in ("case", "build", "wall_s", "last_frame", "truth_gap_frames",
                                              "overruns", "log_issues")}, ensure_ascii=False, indent=1))
    for c in core:
        print("  core", c["f"], c["e"], c["pid"], c["state"], c["reason"], c["weapon"])
    for r in evs:
        if r["kind"] != "spawn":
            print("  ev", r)


# 무장 한 프레임 재계산 (weapon.cpp advance_weapon, agm, 비행 중 구간) ---------------
def m_rad(lat):  # noqa: ANN001, ANN201
    s = math.sin(lat)
    w = 1.0 - E2 * s * s
    return A_WGS * (1.0 - E2) / (w * math.sqrt(w))


def n_rad(lat):  # noqa: ANN001, ANN201
    s = math.sin(lat)
    return A_WGS / math.sqrt(1.0 - E2 * s * s)


def ned_between(a, b):  # noqa: ANN001, ANN201
    lat_mid = 0.5 * (a[0] + b[0]) * D2R
    h_mid = 0.5 * (a[2] + b[2])
    m = m_rad(lat_mid) + h_mid
    n = (n_rad(lat_mid) + h_mid) * math.cos(lat_mid)
    return ((b[0] - a[0]) * D2R * m, (b[1] - a[1]) * D2R * n, -(b[2] - a[2]))


def offset(a, d):  # noqa: ANN001, ANN201
    lat0 = a[0] * D2R
    h_mid = a[2] - 0.5 * d[2]
    m = m_rad(lat0) + h_mid
    dlat1 = d[0] / m
    lat_mid = lat0 + 0.5 * dlat1
    m = m_rad(lat_mid) + h_mid
    n = (n_rad(lat_mid) + h_mid) * max(math.cos(lat_mid), 1e-9)
    return (a[0] + d[0] / m * R2D, a[1] + d[1] / n * R2D, a[2] - d[2])


def add(a, b):  # noqa: ANN001, ANN201
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):  # noqa: ANN001, ANN201
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(k, a):  # noqa: ANN001, ANN201
    return (k * a[0], k * a[1], k * a[2])


def dot(a, b):  # noqa: ANN001, ANN201
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):  # noqa: ANN001, ANN201
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def nrm(a):  # noqa: ANN001, ANN201
    return math.sqrt(dot(a, a))


def unit(a):  # noqa: ANN001, ANN201
    n = nrm(a)
    return mul(1.0 / n, a) if n > 1e-12 else (1.0, 0.0, 0.0)


def limit(a, mx):  # noqa: ANN001, ANN201
    n = nrm(a)
    return mul(mx / n, a) if n > mx and n > 0.0 else a


def pn_accel(N, r, v_rel, vm):  # noqa: ANN001, ANN201, N803
    r2 = dot(r, r)
    if r2 < 1e-6:
        return (0.0, 0.0, 0.0)
    omega = mul(1.0 / r2, cross(r, v_rel))
    vc = -dot(r, v_rel) / math.sqrt(r2)
    a = mul(N * vc, cross(omega, unit(r)))
    um = unit(vm)
    return sub(a, mul(dot(a, um), um))


def step_weapon(p: dict, pos, vel, t_fl: float, tgt_pos, tgt_vel):  # noqa: ANN001, ANN201
    n = max(1, math.ceil(DT / 0.005 - 1e-9))
    hh = DT / n
    for k in range(n):
        tau0 = k * hh
        r = add(ned_between(pos, tgt_pos), mul(tau0, tgt_vel))
        v = nrm(vel)
        u = unit(vel)
        a = (0.0, 0.0, G)
        if t_fl < p["burn_time_s"]:
            a = add(a, mul(p["thrust_accel_mps2"], u))
        a = sub(a, mul(p["drag_k_per_m"] * v * v, u))
        up = (0.0, 0.0, -G)
        gcomp = sub(up, mul(dot(up, u), u))
        a = add(a, limit(add(pn_accel(p["nav_gain"], r, sub(tgt_vel, vel), vel), gcomp), p["max_g"] * G))
        disp = add(mul(hh, vel), mul(0.5 * hh * hh, a))
        pos = offset(pos, disp)
        vel = add(vel, mul(hh, a))
        t_fl += hh
    return pos, vel


def pos_err(a, b) -> float:  # noqa: ANN001
    return nrm(ned_between(a, b))


# 분석 ------------------------------------------------------------------------
def analyse(a: argparse.Namespace) -> None:
    d = Path(a.dir)
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    tr = json.loads((d / "traj.json").read_text(encoding="utf-8"))
    ref = json.loads((Path(a.ref) / "traj.json").read_text(encoding="utf-8")) if a.ref else None
    ref_res = json.loads((Path(a.ref) / "result.json").read_text(encoding="utf-8")) if a.ref else None
    flat = "--terrain-flat" in res["terrain"]
    dem = None if flat else Dem()
    launches = {e["weapon"]: e for e in res["events"] if e["kind"] == "launch"}
    impacts = {e["weapon"]: e for e in res["events"] if e["kind"] == "impact"}
    plan_ov = {}
    out: dict = {"dir": str(d), "ref": a.ref, "weapons": {}}
    for wid, rows in sorted(tr.items()):
        if not wid.startswith("wpn-"):
            continue
        lau = launches.get(wid, {})
        tid = lau.get("target", "")
        fr = {r[0]: r for r in rows}
        live = sorted(f for f, r in fr.items() if r[7])
        tg = {r[0]: r for r in tr.get(tid, [])} if tid else {}
        W: dict = {"target": tid, "launch_f": lau.get("f"), "first_truth_f": live[0] if live else None,
                   "last_alive_f": live[-1] if live else None, "impact": impacts.get(wid)}
        if tid and dem is not None or (tid and flat):
            # 프레임별 가시선 (truth k 무장, truth k 표적)
            vis = {}
            for f in live:
                if f in tg and tg[f][7]:
                    ok, worst = lc.los(dem, tuple(fr[f][1:4]), tuple(tg[f][1:4]), 50.0)
                    vis[f] = (ok, worst["margin_m"])
            blocked = [f for f, (ok, _) in vis.items() if not ok]
            runs, prev = [], None
            for f in sorted(blocked):
                if prev is not None and f == prev + 1:
                    runs[-1][1] = f
                else:
                    runs.append([f, f])
                prev = f
            W["los_blocked_runs"] = runs
            W["los_min_margin"] = min((m for _, m in vis.values()), default=None)
        # 한 프레임 재계산: 가설 T, C
        if tid and len(live) > 2:
            p = dict(AGM)
            for ov in a.override:
                k, v = ov.split("=")
                p[k] = float(v)
            l0 = live[0]
            # t_flight: truth 첫 프레임 f0(발사 프레임 + 1)에 한 프레임(DT) 비행했다
            cls, frozen, errs = {}, None, []
            for f in live[:-1]:
                if f + 1 not in fr or not fr[f + 1][7] or f not in tg:
                    continue
                t_fl = (f - l0 + 1) * DT
                if abs(t_fl - p["burn_time_s"]) < 1.5 * DT:
                    continue
                pos, vel = tuple(fr[f][1:4]), tuple(fr[f][4:7])
                nxt = tuple(fr[f + 1][1:4])
                eT = pos_err(step_weapon(p, pos, vel, t_fl, tuple(tg[f][1:4]), tuple(tg[f][4:7]))[0], nxt)
                if frozen is None and eT > a.tol:
                    frozen = (f, tuple(tg[f - 1][1:4]))
                eC = pos_err(step_weapon(p, pos, vel, t_fl, frozen[1], (0.0, 0.0, 0.0))[0], nxt) if frozen else None
                c = "T" if eT <= a.tol else ("C" if eC is not None and eC <= a.tol else "?")
                if c == "T" and eC is not None and eC <= a.tol:
                    c = "TC"
                cls[f] = c
                errs.append((f, eT, eC))
            seq, prev = [], None
            for f in sorted(cls):
                if cls[f] != prev:
                    seq.append([f, f, cls[f]])
                else:
                    seq[-1][1] = f
                prev = cls[f]
            W["mode_runs"] = seq
            W["frozen"] = {"first_C_frame": frozen[0], "point": frozen[1],
                           "target_frame": frozen[0] - 1} if frozen else None
            W["max_err_T_when_T"] = max((e for f, e, _ in errs if cls[f] in ("T", "TC")), default=None)
            W["max_err_C_when_C"] = max((e for f, _, e in errs if cls[f] == "C"), default=None)
            W["unknown_frames"] = [f for f, c in cls.items() if c == "?"][:20]
            if frozen:
                W["frozen_point_ground_m"] = round(dem.el(frozen[1][0], frozen[1][1]), 2) if dem else 0.0
        if ref is not None and wid in ref:
            rr = {r[0]: r for r in ref[wid]}
            common = sorted(set(fr) & set(rr))
            diff = [f for f in common if fr[f][1:7] != rr[f][1:7] or fr[f][7] != rr[f][7]]
            W["ref_first_diff_frame"] = diff[0] if diff else None
            W["ref_frames_common"] = len(common)
            W["ref_frames_only_new"] = len(set(fr) - set(rr))
            W["ref_frames_only_ref"] = len(set(rr) - set(fr))
            if diff:
                f = diff[0]
                W["ref_diff_at_first_m"] = pos_err(tuple(fr[f][1:4]), tuple(rr[f][1:4]))
            rimp = {e["weapon"]: e for e in ref_res["events"] if e["kind"] == "impact"}.get(wid)
            W["ref_impact"] = rimp
        if W.get("impact") and tg:
            im = W["impact"]
            W["impact_to_target_m"] = round(pos_err((im["lat"], im["lon"], im["alt"]),
                                                    tuple(tg[max(f for f in tg if f <= im["f"])][1:4])), 2)
            if W.get("frozen"):
                W["impact_to_frozen_m"] = round(pos_err((im["lat"], im["lon"], im["alt"]), W["frozen"]["point"]), 2)
        out["weapons"][wid] = W
    if ref is not None:
        tgt_ids = [k for k in tr if k.startswith("tgt-")]
        out["targets_same_as_ref"] = {k: tr[k] == ref.get(k) for k in tgt_ids}
        evn = [(e["f"], e["kind"], e.get("weapon"), e.get("entity"), e.get("killed")) for e in res["events"]]
        evr = [(e["f"], e["kind"], e.get("weapon"), e.get("entity"), e.get("killed")) for e in ref_res["events"]]
        out["events_same_as_ref"] = evn == evr
        out["core_strike_same_as_ref"] = res["core"] == ref_res["core"]
    out["overruns"] = res.get("overruns")
    out["ref_overruns"] = ref_res.get("overruns") if ref_res else None
    (d / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--case", choices=("ridge", "cases", "move", "move2", "move3"), required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--build")
    r.add_argument("--frames", type=int, default=1200)
    r.add_argument("--base-port", type=int, default=48600)
    r.add_argument("--speed", type=float, default=15.0)
    r.add_argument("--start-e", type=float, default=900.0)
    r.add_argument("--end-e", type=float, default=2500.0)
    r.add_argument("--dalts", type=float, nargs="+", default=[30.0, 80.0, 150.0, 300.0])
    r.add_argument("--fov", type=float, default=360.0)
    r.set_defaults(fn=run)
    n = sp.add_parser("analyse")
    n.add_argument("dir")
    n.add_argument("--ref")
    n.add_argument("--tol", type=float, default=1e-4)
    n.add_argument("--override", nargs="*", default=["seeker_fov_deg=360"])
    n.set_defaults(fn=analyse)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
