"""QA 22차 P2 판정: GCS Heartbeat와 링크 상실 행동을 실제 스택으로 확인한다 (TC-QA-119~, DEC-078, REQ-LNK-003).

Datalink·Agent·Core(release, 평지, lockstep). 판정 입력: swarm/<기체>/tx/vi/FlightCommandStatus(command_id <기체>-lost-link-<n>),
GCS가 받은 같은 메시지, LinkOutcome(GcsHeartbeat), truth 궤적, GCS가 받은 TaskStatus.

uv run python qa/p2_lostlink.py --case cut --out qa/out/p2/cut      정책별 동작 (GCS_LINK_CUT)
uv run python qa/p2_lostlink.py --case jam --out qa/out/p2/jam      정책별 동작 (재밍 구역 진입)
uv run python qa/p2_lostlink.py --case iso --out qa/out/p2/iso      한 기체 두절이 다른 기체에 주는 영향
uv run python qa/p2_lostlink.py --case iso2 --out qa/out/p2/iso2    같은 무리·편대의 한 기체 두절
uv run python qa/p2_lostlink.py --case det --out qa/out/p2/det      lockstep 같은 시드 재현
uv run python qa/p2_lostlink.py --case regress --out qa/out/p2/reg  기존 시나리오 영향 (Heartbeat 끔·기본·continue)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gw_plan as gp  # noqa: E402
import harness as h  # noqa: E402
from gw_integ import GCS, NOLOSS  # noqa: E402
from strike_burst import M_LAT, SCN, at  # noqa: E402

h.BUILD = Path(__file__).resolve().parent.parent / "build" / "msvc-release"
ALT = 500.0
V = 20.0
LATC = math.cos(math.radians(37.5))
HEAVY = ({"p_gb": 0.2, "p_bg": 0.2, "loss_good": 0.05, "loss_bad": 0.9}, None, None)


def uav(i: int) -> str:
    return f"uav-{i:03d}"


def pos(n: float, e: float, alt: float = ALT) -> dict:
    return {**at(n, e), "alt_m": alt}


def ne(lat: float, lon: float) -> tuple[float, float]:
    a = at(0, 0)
    return (lat - a["lat_deg"]) * M_LAT, (lon - a["lon_deg"]) * M_LAT * LATC


def veh(i: int, ma: str = "waypoint", params: dict | None = None, east: float | None = None) -> dict:
    e = 1000.0 * (i - 1) if east is None else east
    return {"id": uav(i), "kind": "uav", "side": "blue", "dynamics": "dof3", "airframe": "skywalker_x8",
            "initial": {"position": pos(0, e), "velocity_ned_mps": {"x": V, "y": 0.0, "z": 0.0}},
            "autonomy": {"ma_plugin": ma, "ma_params": params or {}}, "link_profile": "uav_default",
            "controlling_gcs": GCS}


def far(task: str, who: list[str], east: float, policy: str | None = None) -> dict:
    t = {"task_id": task, "assignees": who, "move_to": {"destination": pos(20000, east), "speed_mps": V}}
    return {**t, "lost_link_policy": policy} if policy else t


def scenario(name: str, ents: list[dict], tasks: list[dict], ge: dict | None = None, gcs_e: float = 0.0,
             formations: list[dict] | None = None) -> dict:
    gcs = {"id": GCS, "kind": "gcs", "side": "blue", "dynamics": "static",
           "initial": {"position": pos(-2000, gcs_e, 30.0)}, "link_profile": "gcs_default"}
    mp: dict = {"plan_id": "plan-p2", "tasks": tasks}
    if formations:
        mp["formations"] = formations
    return {"schema_version": "0.1", "name": name, "description": "QA 22차 P2 링크 상실",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.3, "north_deg": 37.8, "west_deg": 127.8, "east_deg": 128.5}},
            "run": {"mode": "lockstep", "frame_hz": 50, "seed": 20261110, "rate": 1.0, "duration_s": 1800.0},
            "link_profiles": [{"name": n, "ge": ge or NOLOSS} for n in ("uav_default", "gcs_default")],
            "entities": [gcs, *ents], "mission_plan": mp}


class Obs(gp.PlanObserver):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        self.fcs_tx: list[tuple] = []      # (hdr_us, 기체, command_id, 상태)
        self.fcs_rx: list[tuple] = []      # (hdr_us, rx_us, 기체, command_id, 상태)
        self.subs.append(self.bus.subscribe("swarm/*/tx/vi/FlightCommandStatus", self._ftx))
        self.subs.append(self.bus.subscribe(f"swarm/{GCS}/rx/vi/FlightCommandStatus", self._frx))

    def _dec(self, s):  # noqa: ANN001, ANN202
        env = self.m[2].LinkEnvelope.FromString(s.payload)
        st = self.vi.FlightCommandStatus.FromString(env.payload)
        return env, st, self.m[4].CommandState.Name(st.state).removeprefix("COMMAND_STATE_")

    def _ftx(self, s) -> None:  # noqa: ANN001
        env, st, name = self._dec(s)
        with self.lock:
            self.fcs_tx.append((env.header.sim_time_us, env.header.source, st.command_id, name))

    def _frx(self, s) -> None:  # noqa: ANN001
        env, st, name = self._dec(s)
        with self.lock:
            self.fcs_rx.append((env.header.sim_time_us, env.rx_time_us, env.header.source, st.command_id, name))


def inject(ob: Obs, events: list[tuple]) -> list[int]:
    """gw_plan.inject_at_frames에 재밍 구역 켜기·끄기를 더했다. ev = (frame, 기체|구역 소유자, 종류, 지속|(n,e,r))"""
    assert gp.wait_frame(ob, 20, 60), "시작 대기 실패"
    ob.pause()
    at_f = gp.wait_still(ob)
    done = []
    for frame, who, kind, arg in events:
        if frame != at_f:
            ob.step(frame - at_f)
            assert gp.wait_frame(ob, frame, 180), f"프레임 {frame} 대기 실패"
            at_f = gp.wait_still(ob)
            assert at_f == frame, f"프레임 불일치 {at_f} != {frame}"
        if kind in ("JAM_ON", "JAM_OFF"):
            n, e, r = arg
            p = at(n, e)
            ob.jam_zone(who, p["lat_deg"], p["lon_deg"], r, kind == "JAM_ON")
        else:
            ob.fault(who, kind, arg)
        time.sleep(0.3)
        done.append(at_f)
    ob.resume()
    return done


def stack(out: Path, sc: dict | Path, port: int, rate: float, hb_off: bool = False) -> tuple[h.Stack, Obs]:
    out.mkdir(parents=True, exist_ok=True)
    if isinstance(sc, dict):
        p = out / "scn.json"
        p.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        p = sc
    st = h.Stack(out, p, base_port=port, lockstep=True, rate=rate, record=False, core_extra=["--terrain-flat", "0"])
    st.start_one("datalink", ["--heartbeat-hz", "0"] if hb_off else None)
    st.start_one("agent")
    time.sleep(st.settle)
    ob = Obs([st.endpoint()])
    time.sleep(1.0)
    st.start_one("core")
    return st, ob


def grab(ob: Obs, st: h.Stack) -> dict:
    with ob.lock:
        d = {"lo": list(ob.all_lo), "hdr": list(ob.gcs_hdr), "traj": {k: list(x) for k, x in ob.traj.items()},
             "ts": list(ob.ts), "fcs_tx": list(ob.fcs_tx), "fcs_rx": list(ob.fcs_rx),
             "events": Counter(k for k, _ in ob.events), "frames": ob.last_frame, "gap": ob.gap_frames}
    d["dead"], d["issues"] = st.dead(), h.scan_logs(st)[:10]
    return d


# ---- 행동 판정 ----------------------------------------------------------------------------------

def bnd(traj: list[tuple], t0: float, t1: float) -> list[tuple[float, float, float]]:
    out = []
    for f, la, lo, _ in traj:
        t = f / 50.0
        if t0 <= t <= t1:
            n, e = ne(la, lo)
            out.append((t, n, e))
    return out


def shape(traj: list[tuple], t0: float, t1: float, c: tuple[float, float] | None = None) -> dict:
    """구간의 비행 모양: 순이동(직선 진행), c 중심 거리의 최소·최대"""
    r = bnd(traj, t0, t1)
    if len(r) < 2:
        return {"n": len(r)}
    net = math.hypot(r[-1][1] - r[0][1], r[-1][2] - r[0][2])
    res = {"t": [round(t0, 1), round(t1, 1)], "net_m": round(net), "north_m": round(r[-1][1] - r[0][1]),
           "net_speed": round(net / max(r[-1][0] - r[0][0], 0.02), 1)}
    if c:
        d = [math.hypot(x[1] - c[0], x[2] - c[1]) for x in r]
        res |= {"rmin": round(min(d)), "rmax": round(max(d))}
    return res


def timeline(d: dict, e: str) -> dict:
    """기체별 상실·재개 시각. tx의 FlightCommandStatus를 쓰고 GCS 수신은 따로 적는다"""
    tx = sorted(x for x in d["fcs_tx"] if x[1] == e)
    lost = [x for x in tx if "-lost-link-" in x[2]]
    first: dict[str, float] = {}
    for x in lost:
        first.setdefault(x[2], x[0] * 1e-6)
    hb = sorted((x[0], x[1], x[5]) for x in d["lo"] if x[4] == "GcsHeartbeat" and x[3] == e)
    out: dict = {"lost_cmds": first, "lost_t": min(first.values(), default=None)}
    out["fcs_rx_lost"] = sorted({(round(x[0] * 1e-6, 2), round(x[1] * 1e-6, 2), x[3], x[4]) for x in d["fcs_rx"]
                                 if x[2] == e and "-lost-link-" in x[3]})
    out["hb"] = dict(Counter(x[2] for x in hb))
    if out["lost_t"] is not None:
        t = out["lost_t"]
        heard = [x[1] * 1e-6 for x in hb if x[2] == "DELIVERED" and x[1] * 1e-6 <= t]
        out["last_hb_rx"] = round(max(heard), 3) if heard else None
        out["lost_after_last_hb"] = round(t - max(heard), 3) if heard else None
        after = [x[1] * 1e-6 for x in hb if x[2] == "DELIVERED" and x[1] * 1e-6 > t]
        out["first_hb_after"] = round(min(after), 3) if after else None
        task_after = sorted({(x[0] * 1e-6, x[2]) for x in tx if "-task-" in x[2] and x[0] * 1e-6 > t})
        out["next_task_cmd"] = (round(task_after[0][0], 3), task_after[0][1]) if task_after else None
        r = [p for p in d["traj"].get(e, []) if p[0] / 50.0 >= t]
        if r:
            out["center"] = tuple(round(v) for v in ne(r[0][1], r[0][2]))
    out["task"] = [f"{round(x[0], 1)}:{x[2]}:{x[3]}" + (f"({x[4]})" if x[4] else "") for x in d["ts"] if x[1] == e]
    return out


def task_cmd(ob: Obs, e: str, n: float, east: float, tid: str, policy: int = 0) -> None:
    t = ob.m[3].TaskCommand()
    p = pos(n, east)
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg, t.move_to.destination.alt_m = p["lat_deg"], p["lon_deg"], ALT
    t.move_to.speed_mps = V
    t.lost_link_policy = policy
    ob.task(t, [e], tid)


def run_timeline(out: Path, sc: dict, port: int, rate: float, plan: list[tuple], end: float, ids: list[str]) -> tuple[dict, dict]:
    st, ob = stack(out, sc, port, rate)
    t0 = time.monotonic()
    marks = {}
    try:
        for t, name, fn in sorted(plan, key=lambda x: x[0]):
            while ob.sim_s() < t and time.monotonic() - t0 < 400 and not st.dead():
                time.sleep(0.005)
            fn(ob)
            marks[name] = ob.sim_s()
        while ob.sim_s() < end and time.monotonic() - t0 < 500 and not st.dead():
            time.sleep(0.05)
        d = grab(ob, st)
        ob.close()
    finally:
        st.down()
    res = {"marks": marks, "frames": d["frames"], "gap": d["gap"], "dead": d["dead"], "issues": d["issues"],
           "drop": dict(Counter((x[4], x[5]) .__str__() for x in d["lo"] if x[4] == "GcsHeartbeat"))}
    res["veh"] = {e: timeline(d, e) for e in ids}
    return res, d


# ---- case: cut ----------------------------------------------------------------------------------

P = {"resume": "resume_on_recovery", "cont": "continue", "hold": "hold_until_command"}


def case_cut(base: Path, port: int) -> None:
    C2 = h.pb()[3]
    res_p, cont_p = C2.LOST_LINK_POLICY_RESUME_ON_RECOVERY, C2.LOST_LINK_POLICY_CONTINUE
    ents = [veh(1), veh(2), veh(3), veh(4, params={"lost_link_policy": P["resume"]}), veh(5), veh(6),
            veh(7, params={"lost_link_policy": P["cont"]}), veh(8), veh(9), veh(10, params={"lost_link_policy": P["cont"]}),
            veh(11), veh(12, "flocking_basic", {"group": "gx"}), veh(13, "hold"),
            veh(14, "formation", {"group": "fg"}), veh(15, "formation", {"group": "fg"}), veh(16),
            veh(17, params={"lost_link_policy": P["resume"]}),
            veh(18, "flocking_basic", {"group": "gy", "lost_link_policy": P["resume"]}),
            veh(19, "flocking_basic", {"group": "gz", "lost_link_policy": P["cont"]})]
    route = {"task_id": "t-011", "assignees": [uav(11)], "lost_link_policy": P["resume"],
             "route": {"waypoints": [{"position": pos(1000, 10000), "speed_mps": V, "acceptance_radius_m": 100.0},
                                     {"position": pos(2000, 10000), "speed_mps": V, "acceptance_radius_m": 100.0},
                                     {"position": pos(2800, 10000), "speed_mps": V, "acceptance_radius_m": 100.0}]}}
    tasks = [far("t-001", [uav(1)], 0), far("t-002", [uav(2)], 1000, P["resume"]), far("t-004", [uav(4)], 3000),
             far("t-005", [uav(5)], 4000, P["cont"]), far("t-007", [uav(7)], 6000), far("t-008", [uav(8)], 7000),
             far("t-009", [uav(9)], 8000), far("t-010", [uav(10)], 9000, P["hold"]), route,
             far("t-012", [uav(12)], 11000), far("t-014", [uav(14)], 13000),
             far("t-018", [uav(18)], 17000), far("t-019", [uav(19)], 18000)]
    fm = [{"group_id": "fg", "members": [uav(14), uav(15)], "leader": uav(14), "shape": "line", "spacing_m": 150.0}]
    sc = scenario("qa-p2-cut", ents, tasks, formations=fm)
    cuts = [uav(i) for i in (1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 15, 16, 17, 18, 19)]
    plan: list[tuple] = [
        (2.0, "bus3", lambda o: task_cmd(o, uav(3), 20000, 2000, "t-003", res_p)),
        (2.0, "bus6", lambda o: task_cmd(o, uav(6), 20000, 5000, "t-006", cont_p)),
        (20.0, "cut", lambda o: [o.fault(e, "GCS_LINK_CUT", 60.0) for e in cuts] and o.fault(uav(8), "GCS_LINK_CUT", 3.0)),
        (130.0, "newcmd", lambda o: task_cmd(o, uav(1), 3000, -5000, "t-new-1")),
        (130.0, "newcmd16", lambda o: task_cmd(o, uav(16), 3000, 16000, "t-new-16")),
    ]
    ids = [uav(i) for i in range(1, 20)]
    res, d = run_timeline(base, sc, port, 2.0, plan, 215.0, ids)
    t_cut, t_rec = res["marks"]["cut"], res["marks"]["cut"] + 60.0
    for e in ids:
        v = res["veh"][e]
        tr = d["traj"].get(e, [])
        c = v.get("center")
        if c is None and e in (uav(12), uav(18)):   # flocking은 FlightCommand를 쓰지 않아 상실 시각의 궤적 위치를 쓴다
            r = bnd(tr, t_cut + 4.1, t_cut + 4.2)
            c = v["center"] = (round(r[0][1]), round(r[0][2]))
        v["before"] = shape(tr, 5, t_cut, None)
        v["during"] = shape(tr, t_cut + 15, t_rec - 2, tuple(c) if c else None)
        v["after_rec"] = shape(tr, t_rec + 5, 128, tuple(c) if c else None)
        v["after_cmd"] = shape(tr, 135, 214, tuple(c) if c else None)
    (base / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("FINISHED")


# ---- case: jam ----------------------------------------------------------------------------------

def case_jam(base: Path, port: int) -> None:
    zone = (6300.0, 1500.0, 6000.0)
    gcs_e = 1500.0
    ents = [veh(1), veh(2), veh(3), veh(4, east=9000.0), veh(5, east=-9000.0),
            veh(6, east=500.0, params={"hold_radius_m": 50}), veh(7, east=2500.0, params={"hold_radius_m": 50})]
    tasks = [far("t-001", [uav(1)], 0), far("t-002", [uav(2)], 1000, P["resume"]), far("t-003", [uav(3)], 2000, P["cont"]),
             far("t-004", [uav(4)], 9000), far("t-005", [uav(5)], -9000),
             far("t-006", [uav(6)], 500), far("t-007", [uav(7)], 2500, P["resume"])]
    sc = scenario("qa-p2-jam", ents, tasks, gcs_e=gcs_e)
    g = at(-2000, gcs_e)
    a = at(zone[0], zone[1])
    plan: list[tuple] = [
        (0.5, "gcsjam_on", lambda o: o.jam_zone("jam-qa2", g["lat_deg"], g["lon_deg"], 300.0, True)),
        (0.6, "zone_on", lambda o: o.jam_zone("jam-qa", a["lat_deg"], a["lon_deg"], zone[2], True)),
        (15.0, "gcsjam_off", lambda o: o.jam_zone("jam-qa2", g["lat_deg"], g["lon_deg"], 300.0, False)),
        (100.0, "zone_off", lambda o: o.jam_zone("jam-qa", a["lat_deg"], a["lon_deg"], zone[2], False)),
        (130.0, "newcmd", lambda o: task_cmd(o, uav(1), 3000, -5000, "t-new-1")),
    ]
    ids = [uav(i) for i in range(1, 8)]
    res, d = run_timeline(base, sc, port, 2.0, plan, 215.0, ids)
    off = res["marks"]["zone_off"]
    for e in ids:
        v = res["veh"][e]
        tr = d["traj"].get(e, [])
        c = v.get("center")
        ent = [p[0] / 50.0 for p in tr if math.hypot(ne(p[1], p[2])[0] - zone[0], ne(p[1], p[2])[1] - zone[1]) < zone[2]]
        v["zone_entry_t"] = round(min(ent), 2) if ent else None
        v["zone_exit_t"] = round(max(ent), 2) if ent else None
        v["during"] = shape(tr, 55, off - 2, tuple(c) if c else None)
        v["after_off"] = shape(tr, off + 5, 128, tuple(c) if c else None)
        v["after_cmd"] = shape(tr, 135, 214, tuple(c) if c else None)
    (base / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("FINISHED")


# ---- case: iso·det ------------------------------------------------------------------------------

def run_ls(out: Path, sc, port: int, rate: float, events: list[tuple], end: float, wall: float = 300.0) -> dict:
    st, ob = stack(out, sc, port, rate)
    t0 = time.monotonic()
    try:
        injected = inject(ob, events) if events else []
        while ob.sim_s() < end + 1.0 and time.monotonic() - t0 < wall and not st.dead():
            time.sleep(0.05)
        d = grab(ob, st)
        ob.close()
    finally:
        st.down()
    lim_us, lim_fr = int(end * 1e6), int(end * 50)
    # 지연이 긴 프로파일(qa_slow)은 끝 무렵 송신의 수신이 종료 뒤로 넘어가 실행마다 잘린다. 비교는 끝 5 s의 송신을 뺀다
    cmp_us = lim_us - 5_000_000
    d["lo"] = sorted(x for x in d["lo"] if x[0] < cmp_us)
    d["hdr"] = sorted(x for x in d["hdr"] if x[3] < cmp_us)
    d["traj"] = {k: [x for x in r if x[0] <= lim_fr] for k, r in d["traj"].items()}
    d["fcs"] = sorted(x for x in d["fcs_tx"] if x[0] < lim_us)
    d["injected"], d["wall"] = injected, round(time.monotonic() - t0, 1)
    return d


def compare(a: dict, b: dict) -> dict:
    c = {"lo_same": a["lo"] == b["lo"], "hdr_same": a["hdr"] == b["hdr"], "fcs_same": a["fcs"] == b["fcs"]}
    c |= gp.traj_common(a["traj"], b["traj"])
    for k in ("lo", "hdr", "fcs"):
        if not c[f"{k}_same"]:
            c[f"{k}_diff"] = gp.diff_sets(a[k], b[k])
    return c


def info(d: dict) -> dict:
    return {"frames": d["frames"], "gap": d["gap"], "dead": d["dead"], "issues": d["issues"], "wall": d["wall"],
            "injected": d["injected"], "lo": len(d["lo"]), "hdr": len(d["hdr"]),
            "hb": dict(Counter(x[5] for x in d["lo"] if x[4] == "GcsHeartbeat")),
            "lost_cmds": sorted({(x[1], x[2], x[0]) for x in d["fcs"] if "-lost-link-" in x[2]})}


def case_iso(base: Path, port: int) -> None:
    def sc(ge):  # noqa: ANN001, ANN202
        ents = [veh(1), veh(2), veh(3), veh(4, "flocking_basic", {"group": "fa"}), veh(5, "flocking_basic", {"group": "fa"}), veh(6)]
        return scenario("qa-p2-iso", ents, [far("t", [uav(i) for i in range(1, 7)], 1000)], ge=ge)
    report = {}
    ev = [(1000, uav(1), "GCS_LINK_CUT", 30.0)]
    for name, ge in (("noloss", None), ("loss", gp.LOSS[0])):
        base_d = run_ls(base / name / "none", sc(ge), port, 0.0, [], 75.0)
        cut_d = run_ls(base / name / "cut", sc(ge), port, 0.0, ev, 75.0)
        others = [uav(i) for i in range(2, 7)]
        a = {"lo": [x for x in base_d["lo"] if uav(1) not in x[2:4]], "hdr": [x for x in base_d["hdr"] if x[0] != uav(1)],
             "fcs": [x for x in base_d["fcs"] if x[1] != uav(1)], "traj": {k: base_d["traj"][k] for k in others}}
        b = {"lo": [x for x in cut_d["lo"] if uav(1) not in x[2:4]], "hdr": [x for x in cut_d["hdr"] if x[0] != uav(1)],
             "fcs": [x for x in cut_d["fcs"] if x[1] != uav(1)], "traj": {k: cut_d["traj"][k] for k in others}}
        tc = gp.traj_common(a["traj"], b["traj"])
        report[name] = {"none": info(base_d), "cut": info(cut_d), "others": {
            "lo_same": a["lo"] == b["lo"], "lo": len(a["lo"]), "hdr_same": a["hdr"] == b["hdr"], "fcs_same": a["fcs"] == b["fcs"], **tc}}
        (base / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("FINISHED")


def case_iso2(base: Path, port: int) -> None:
    """같은 flocking 무리·편대의 한 기체(리더 포함)만 두절했을 때 동료의 비행이 달라지는 양"""
    def sc():  # noqa: ANN202
        ents = [*[veh(i, "flocking_basic", {"group": "fa"}, east=200.0 * (i - 1)) for i in range(1, 5)],
                veh(5, "formation", {"group": "fg"}, east=4000.0), veh(6, "formation", {"group": "fg"}, east=4200.0),
                veh(7, east=9000.0)]
        fm = [{"group_id": "fg", "members": [uav(5), uav(6)], "leader": uav(5), "shape": "line", "spacing_m": 150.0}]
        tasks = [far("t-a", [uav(i) for i in range(1, 5)], 300), far("t-f", [uav(5)], 4000), far("t-c", [uav(7)], 9000)]
        return scenario("qa-p2-iso2", ents, tasks, formations=fm)
    none = run_ls(base / "none", sc(), port, 0.0, [], 135.0)
    cut = run_ls(base / "cut", sc(), port, 0.0, [(1000, uav(1), "GCS_LINK_CUT", 60.0), (1000, uav(5), "GCS_LINK_CUT", 60.0)], 135.0)
    report: dict = {"none": info(none), "cut": info(cut), "veh": {}}
    for e in sorted(none["traj"]):
        if not e.startswith("uav-"):
            continue
        a, b = ({x[0]: ne(x[1], x[2]) for x in d["traj"][e]} for d in (none, cut))
        row = {}
        for t in (20, 30, 40, 60, 80, 100, 130):
            f = t * 50
            if f in a and f in b:
                row[t] = round(math.hypot(a[f][0] - b[f][0], a[f][1] - b[f][1]))
        report["veh"][e] = {"diff_m_at_t": row, "hb": dict(Counter(x[5] for x in cut["lo"] if x[4] == "GcsHeartbeat" and x[3] == e))}
    (base / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("FINISHED")


def det_fleet(ge: dict | None) -> dict:
    ents = [veh(1), veh(2), veh(3), veh(4, "flocking_basic", {"group": "fa"}), veh(5, "flocking_basic", {"group": "fa"}),
            veh(6, params={"lost_link_policy": P["cont"]})]
    tasks = [far("t-1", [uav(1), uav(4), uav(5), uav(6)], 1000), far("t-2", [uav(2)], 1000, P["resume"]), far("t-3", [uav(3)], 2000, P["cont"])]
    return scenario("qa-p2-det", ents, tasks, ge=ge)


def case_det(base: Path, port: int, runs: int, only: str) -> None:
    Z = (1500.0, 2500.0, 1400.0)
    ev_cut = [(500, uav(1), "GCS_LINK_CUT", 20.0), (900, uav(2), "GCS_LINK_CUT", 20.0)]
    ev_all = [*ev_cut, (2200, "jam-qa", "JAM_ON", Z), (3400, "jam-qa", "JAM_OFF", Z)]
    V_ = {"noloss_cut_jam": (det_fleet(None), ev_all, 80.0), "loss_cut": (det_fleet(gp.LOSS[0]), ev_cut, 80.0),
          "heavy": (det_fleet(HEAVY[0]), [], 80.0), "s3_link": (SCN / "qa_s3_link.json", [], 60.0),
          "p5_near": (SCN / "qa_p5_near.json", [], 60.0)}
    report: dict = {}
    if only:
        V_ = {k: x for k, x in V_.items() if k in only.split(",")}
    for name, (sc, ev, end) in V_.items():
        ds = [run_ls(base / name / f"run{i}", sc, port, 0.0, ev, end) for i in range(1, runs + 1)]
        extra = {}
        if name == "noloss_cut_jam":
            d2 = run_ls(base / name / "rate2", sc, port, 2.0, ev, end, 300.0)
            extra["rate2"] = {"cmp": compare(ds[0], d2), "info": info(d2)}
        report[name] = {"cmp": {f"1v{i + 1}": compare(ds[0], d) for i, d in enumerate(ds) if i},
                        "info": [info(d) for d in ds], **extra}
        (base / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("FINISHED")


# ---- case: regress ------------------------------------------------------------------------------

REG = {"qa_s3_link": 300.0, "qa_p5_near": 640.0, "qa_p5_noloss": 640.0, "qa_p5_nopayload": 640.0, "qa_p5_nosensor": 640.0,
       "qa_p5_range": 640.0}


def reg_one(out: Path, name: str, mode: str, port: int) -> dict:
    src = SCN / f"{name}.json"
    sc: dict | Path = src
    j = json.loads(src.read_text(encoding="utf-8"))
    for e in j["entities"]:
        if e.get("kind") == "uav":  # 시나리오 파일의 지정(§30.8 뒤 continue)과 무관하게 모드대로 비교한다
            params = e["autonomy"].setdefault("ma_params", {})
            params.pop("lost_link_policy", None)
            if mode == "cont":
                params["lost_link_policy"] = "continue"
    sc = j
    st, ob = stack(out, sc, port, 0.0, hb_off=mode == "off")
    t0, end = time.monotonic(), REG[name]
    try:
        while ob.sim_s() < end and time.monotonic() - t0 < 500 and not st.dead():
            time.sleep(0.1)
        d = grab(ob, st)
        ob.close()
    finally:
        st.down()
    res: dict = {"wall": round(time.monotonic() - t0, 1), "frames": d["frames"], "gap": d["gap"], "dead": d["dead"], "issues": d["issues"][:6],
                 "events": dict(d["events"]), "hb": dict(Counter(x[5] for x in d["lo"] if x[4] == "GcsHeartbeat")),
                 "outcomes": dict(Counter(x[5] for x in d["lo"])), "veh": {}}
    uavs = sorted(k for k in d["traj"] if k.startswith("uav-"))
    for e in uavs:
        t = timeline(d, e)
        tr = d["traj"][e]
        la, lo, alt = tr[-1][1:]
        res["veh"][e] = {"lost_t": t["lost_t"], "lost_n": len(t["lost_cmds"]), "after": t.get("lost_after_last_hb"), "hb": t["hb"], "first_hb_after": t.get("first_hb_after"),
                         "final": (round(la, 5), round(lo, 5), round(alt)), "last100": shape(tr, tr[-1][0] / 50.0 - 100, tr[-1][0] / 50.0),
                         "task": t["task"][-6:]}
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return res


def case_regress(base: Path, port: int, only: str) -> None:
    names = only.split(",") if only else list(REG)
    for name in names:
        for mode in ("off", "default", "cont"):
            out = base / name / mode
            if (out / "result.json").exists():
                continue
            reg_one(out, name, mode, port)
            print(name, mode, flush=True)
    print("FINISHED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-port", type=int, default=49300)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    base = Path(a.out)
    base.mkdir(parents=True, exist_ok=True)
    try:
        if a.case == "cut":
            case_cut(base, a.base_port)
        elif a.case == "jam":
            case_jam(base, a.base_port)
        elif a.case == "iso":
            case_iso(base, a.base_port)
        elif a.case == "iso2":
            case_iso2(base, a.base_port)
        elif a.case == "det":
            case_det(base, a.base_port, a.runs, a.only)
        elif a.case == "regress":
            case_regress(base, a.base_port, a.only)
    finally:
        h.Stack.down_all()


if __name__ == "__main__":
    main()
