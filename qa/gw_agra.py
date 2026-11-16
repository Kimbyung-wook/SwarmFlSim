"""QA 28차 DEC-088~091 통합 확인 (TC-QA-158~). agra_lacal을 거친 실제 스택.

Datalink·Agent(기본 swarm_agent)·Core(realtime 1배속, 평지)와 CAL Server(qa/scenarios/gw_lacal_server_28.yaml =
gateway/config/lacal_server.yaml의 포트만 바꾼 것), Gateway(qa/gw_wrap.py, --lacal-admin), 외부 CAL Client 둘
(qa/gw_ext_client.py: ext1은 시작부터, ext2는 실행 중간에 붙는 늦은 구독자)을 띄운다.

기체
  uav-001~003  waypoint, approval_tasks=hold, approval_timeout_s=15. 외부 hold 명령의 승인·거부·시간 초과
  uav-004      waypoint, approval_tasks=move_to. 계획 작업 task-001을 승인 뒤 시작. track_share_hz=1
  uav-003      track_share_hz=1 (표적 tgt-001 쪽으로 비행)
  uav-005      정지, agm_short 2발(StoreLoadout). 계획 strike(task-003, engagement_criteria.require_approval=true)
  uav-006~008  formation(beta, 리더 uav-006). LeaderUpdate
시간표(모의 s)
  20   외부 hold: ap-yes(uav-001, 승인), ap-no(uav-002, 거부), ap-to(uav-003, 응답 없음 → 15 s 뒤 시간 초과)
  50   GCS_LINK_CUT uav-001·uav-005 12 s(> lost_link_timeout_s 5 s), uav-002 3 s(< 5 s)
  80   ext2 접속(늦은 구독자)
  105  종료

uv run python qa/gw_agra.py --out qa/out/qa28/r1
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gw_integ as gi  # noqa: E402
import harness as h  # noqa: E402
from strike_burst import SCN, at  # noqa: E402

p0 = h.p0
h.BUILD = Path(__file__).resolve().parent.parent / "build" / "msvc-release"
QA = Path(__file__).resolve().parent
ROOT = QA.parent
GW_PY = gi.GW_PY
CAL_URL, CAL_ADMIN = gi.CAL_URL, gi.CAL_ADMIN
GCS = gi.GCS
T_CMD, T_CUT, CUT_LONG, CUT_SHORT, T_LATE, T_END = 20.0, 50.0, 12.0, 3.0, 80.0, 105.0
APPROVE = {"task-001": "APPROVED", "ap-yes": "APPROVED", "ap-no": "REJECTED"}
WP = ["uav-001", "uav-002", "uav-003", "uav-004"]
SHOOTER = "uav-005"
FORM = ["uav-006", "uav-007", "uav-008"]
ALL = [*WP, SHOOTER, *FORM]
CHANGE = ("SystemStatus", "FlightCapability", "FlightCommandStatus", "StoreLoadout", "SensorActivity",
          "JammerActivity", "StrikeActivity")


def scenario() -> dict:
    cam = {"id": "cam0", "type": "camera", "profile": "eo_wide"}
    ents = [{"id": GCS, "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(-2000, 0), "alt_m": 30.0}}, "link_profile": "gcs_default"}]
    for i, e in enumerate(WP):
        mp = {"approval_tasks": "hold", "approval_timeout_s": 15.0}
        if e == "uav-004":
            mp = {"approval_tasks": "move_to"}
        if e in ("uav-003", "uav-004"):
            mp["track_share_hz"] = 1.0
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(1000 * i, 0), "alt_m": 500.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 22.0, "z": 0.0}},
                     "payloads": [cam], "autonomy": {"ma_plugin": "waypoint", "ma_params": mp},
                     "link_profile": "uav_default", "controlling_gcs": GCS})
    ents.append({"id": SHOOTER, "kind": "uav", "side": "blue", "dynamics": "static",
                 "initial": {"position": {**at(-1000, 0), "alt_m": 500.0},
                             "attitude": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}},
                 "payloads": [cam, {"id": "sta1", "type": "agm_short", "profile": "agm_generic", "count": 2}],
                 "autonomy": {"ma_plugin": "waypoint", "ma_params": {}},
                 "link_profile": "uav_default", "controlling_gcs": GCS})
    for i, e in enumerate(FORM):
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(-3000 - 150 * i, -1500 - 150 * i), "alt_m": 600.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 20.0, "z": 0.0}},
                     "autonomy": {"ma_plugin": "formation", "ma_params": {"group": "beta", "leader_speed_mps": 20.0}},
                     "link_profile": "uav_default", "controlling_gcs": GCS})
    ents.append({"id": "tgt-001", "kind": "ground_target", "side": "red", "dynamics": "static",
                 "initial": {"position": at(1500, 3000)}})
    dest = at(1500, 8000)
    return {"schema_version": "0.1", "name": "qa-agra28", "description": "QA 28차 DEC-088~091 통합 확인",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9,
                                                   "east_deg": 128.2}},
            "run": {"mode": "realtime", "frame_hz": 50, "seed": 20261116, "rate": 1.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": gi.NOLOSS}, {"name": "gcs_default", "ge": gi.NOLOSS}],
            "entities": ents,
            "mission_plan": {"plan_id": "plan-qa28", "tasks": [
                {"task_id": "task-001", "assignees": WP,
                 "move_to": {"destination": {**dest, "alt_m": 500.0}, "speed_mps": 22.0}},
                {"task_id": "task-002", "assignees": [FORM[0]],
                 "move_to": {"destination": {**at(-3000, 6000), "alt_m": 600.0}, "speed_mps": 20.0}},
                {"task_id": "task-003", "assignees": [SHOOTER],
                 "strike": {"target_id": "tgt-001", "weapon_type": "agm_short"}}],
                "formations": [{"group_id": "beta", "members": FORM, "leader": FORM[0], "shape": "wedge",
                                "spacing_m": 150.0}]},
            "engagement_criteria": {"hostile_sides": ["red"], "require_approval": True,
                                    "weapons_free": [{"circle": {"center": at(1500, 3000), "radius_m": 10000.0}}]}}


def start_ext(name: str, ext_dir: Path, st, approve: dict | None) -> "p0.Proc":  # noqa: ANN001
    (ext_dir / "cmd").mkdir(parents=True, exist_ok=True)
    for f in [*ext_dir.glob("cmd/*.json"), ext_dir / "STOP", ext_dir / "ext.ready", ext_dir / "ext.json"]:
        f.unlink(missing_ok=True)
    return p0.Proc(name, [str(GW_PY), str(QA / "gw_ext_client.py"), "--url", CAL_URL, "--admin", CAL_ADMIN,
                          "--out", str(ext_dir), *(["--approve", json.dumps(approve)] if approve else [])],
                   st.out, cwd=ROOT)


def main() -> None:  # noqa: PLR0915
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-port", type=int, default=48700)
    a = ap.parse_args()
    out = (ROOT / a.out) if not Path(a.out).is_absolute() else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    e1, e2 = out / "ext1", out / "ext2"
    sc = scenario()
    sp = SCN / "qa_agra28.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    st = h.Stack(out / "stack", sp, base_port=a.base_port, lockstep=False, record=False,
                 core_extra=["--terrain-flat", "0"])
    extra: list = []
    res: dict = {"scenario": str(sp.relative_to(ROOT))}
    marks: dict[str, float] = {}
    clock: list[tuple[float, float]] = []
    ncmd = [0]

    def ext_cmd(task_id: str, entities: list[str], kind: str) -> None:
        ncmd[0] += 1
        (e1 / "cmd" / f"{ncmd[0]:03d}.json").write_text(json.dumps(
            {"task_id": task_id, "entities": entities, "kind": kind}), encoding="utf-8")

    try:
        cal = p0.Proc("calsrv", [str(GW_PY), "-m", "swarm_gateway.lacal_server", "--config",
                                 str(QA / "scenarios" / "gw_lacal_server_28.yaml")], st.out, cwd=ROOT / "gateway")
        extra.append(cal)
        assert gi.wait_port(18765), "CAL Server 기동 실패"
        st.start_one("datalink")
        st.start_one("agent")
        os.environ["GW_PROBE_OUT"] = str(out / "gw1.json")
        gw = p0.Proc("gateway.1", [str(GW_PY), str(QA / "gw_wrap.py"), "--gcs", GCS, "--lacal", CAL_URL,
                                   "--lacal-admin", f"ws://{CAL_ADMIN}", "--no-multicast", "--connect", st.endpoint(),
                                   "--listen", f"tcp/127.0.0.1:{a.base_port + 30}", "--stats-s", "5"], st.out, cwd=ROOT)
        extra.append(gw)
        x1 = start_ext("ext1", e1, st, APPROVE)
        extra.append(x1)
        end = time.monotonic() + 40
        while not (e1 / "ext.ready").exists() and time.monotonic() < end:
            time.sleep(0.2)
        assert (e1 / "ext.ready").exists(), "외부 클라이언트 준비 실패"
        time.sleep(st.settle)
        ob = gi.GwObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        done: set[str] = set()
        t0 = time.monotonic()

        def once(tag: str, t: float, fn) -> None:  # noqa: ANN001
            if tag not in done and ob.sim_s() >= t:
                done.add(tag)
                marks[tag] = time.time()
                fn()

        while time.monotonic() - t0 < T_END * 1.5 + 60:
            time.sleep(0.1)
            s = ob.sim_s()
            clock.append((time.time(), s))
            once("cmd", T_CMD, lambda: (ext_cmd("ap-yes", ["uav-001"], "hold"), ext_cmd("ap-no", ["uav-002"], "hold"),
                                        ext_cmd("ap-to", ["uav-003"], "hold")))
            once("cut", T_CUT, lambda: (ob.fault("uav-001", "GCS_LINK_CUT", CUT_LONG),
                                        ob.fault(SHOOTER, "GCS_LINK_CUT", CUT_LONG),
                                        ob.fault("uav-002", "GCS_LINK_CUT", CUT_SHORT)))
            once("late", T_LATE, lambda: extra.append(start_ext("ext2", e2, st, None)))
            if s >= T_END or "core" in "".join(st.dead()):
                break
        res["dead_at_end"] = st.dead() + [p.name for p in extra if not p.alive()]
        for d in (e1, e2):
            (d / "STOP").write_text("x", encoding="utf-8")
        time.sleep(2.5)
        res["log_issues"] = h.scan_logs(st)[:30]
        snap = ob.snapshot()
        with ob.lock:
            gcs_rx, gcs_tx, lo = list(ob.gcs_rx), list(ob.gcs_tx), list(ob.lo)
            taskstatus = {k: list(v) for k, v in ob.taskstatus.items()}
            vi_rx = list(ob.vi_rx)
        ob.close()
    finally:
        st.down()
        p0.stop(extra)
    res["snapshot"] = {k: snap.get(k) for k in ("last_frame", "sim_s", "gap_frames", "overruns", "findings")}
    res["marks"] = marks
    ext = {n: json.loads((d / "ext.json").read_text(encoding="utf-8")) for n, d in (("ext1", e1), ("ext2", e2))
           if (d / "ext.json").exists()}
    gwj = json.loads((out / "gw1.json").read_text(encoding="utf-8")) if (out / "gw1.json").exists() else {}
    with gzip.open(out / "raw.pkl.gz", "wb") as f:
        pickle.dump({"res": res, "gcs_rx": gcs_rx, "gcs_tx": gcs_tx, "lo": lo, "taskstatus": taskstatus,
                     "clock": clock, "vi_rx": vi_rx, "ext": ext, "gw": gwj}, f)
    gw_log = (st.out / "gateway.1.log").read_text(encoding="utf-8", errors="replace")
    res["summary"] = analyse(res, ext, gwj, gcs_rx, gcs_tx, taskstatus, clock, gw_log)
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1, default=str))


def sim_at(clock: list, epoch: float) -> float:
    for e, s in clock:
        if e >= epoch:
            return s
    return clock[-1][1] if clock else 0.0


def analyse(res, ext, gwj, gcs_rx, gcs_tx, taskstatus, clock, gw_log) -> dict:  # noqa: ANN001, C901, PLR0912, PLR0915
    S: dict = {}
    x1 = ext.get("ext1", {"rx": [], "cmds": [], "xsd_fail": [], "errors": []})
    x2 = ext.get("ext2", {"rx": [], "cmds": [], "xsd_fail": [], "errors": [], "sub_t": None})
    # 1. 4종: GCS rx → 외부(ext1) 도달, XSD
    four = {"ApprovalRequest": "MA_ApprovalRequest", "LeaderUpdate": "MA_LeaderUpdateRequest",
            "TrackShare": "MA_Entity", "StoreLoadout": "StoreLoadoutConfiguration"}
    gin = Counter(r[2] for r in gcs_rx)
    gsrc = defaultdict(Counter)
    for r in gcs_rx:
        gsrc[r[2]][r[3]] += 1
    S["four"] = {}
    for k, u in four.items():
        rows = [r for r in x1["rx"] if r[1] == u]
        S["four"][k] = {"gcs_rx": gin.get(k, 0), "gcs_rx_by_src": dict(sorted(gsrc[k].items())), "ext1": len(rows),
                        "ext1_xsd_ok": sum(1 for r in rows if r[3]), "topic": sorted({r[2] for r in rows}),
                        "sample": rows[0][6] if rows else None}
    S["ext1_xsd_fail"], S["ext1_errors"] = x1["xsd_fail"][:5], x1["errors"][:5]
    S["ext2_xsd_fail"], S["ext2_errors"] = x2["xsd_fail"][:5], x2["errors"][:5]
    # 승인 흐름
    S["approval_requests_ext"] = [{"t_sim": round(sim_at(clock, r[0]), 2), **{k: r[6].get(k) for k in ("req", "task", "state")}}
                                  for r in x1["rx"] if r[1] == "MA_ApprovalRequest"]
    S["approval_replies"] = [{k: c.get(k) for k in ("tag", "xsd_ok", "pub", "xsd_err")} | {"t_sim": round(sim_at(clock, c["t"]), 2)}
                             for c in x1["cmds"] if c.get("name") == "MA_ApprovalRequestStatus"]
    S["ext_cmds"] = [{k: c.get(k) for k in ("task_id", "entities", "kind", "xsd_ok", "pub")} for c in x1["cmds"] if "task_id" in c]
    S["gw_tx"] = [{"sim_s": round(r["sim_s"], 2), "key": r["key"].split("/tx/")[-1], "dst": r["dst"],
                   **({"task_id": r["task_id"], "kind": r["kind"]} if "task_id" in r else {})} for r in gcs_tx]
    S["taskstatus_gcs"] = {e: v[:12] for e, v in sorted(taskstatus.items())}
    ext_ts = defaultdict(list)
    for r in x1["rx"]:
        if r[1] == "MA_TaskStatus":
            s = f"{r[6]['task']}:{r[6]['state']}"
            if not ext_ts[r[6]["by"]] or ext_ts[r[6]["by"]][-1] != s:
                ext_ts[r[6]["by"]].append(s)
    S["taskstatus_ext"] = dict(sorted(ext_ts.items()))
    # 2. 복구 재송신: GCS가 받은 변화 보고 (기체, 종류)별 모의 시각
    ch = defaultdict(list)
    for r in gcs_rx:
        if r[2] in CHANGE:
            ch[(r[3], r[2])].append(round(r[1], 2))
    S["change_rx_times"] = {f"{e}/{k}": v[:20] for (e, k), v in sorted(ch.items())}
    rec = {}
    for e, dur in (("uav-001", CUT_LONG), (SHOOTER, CUT_LONG), ("uav-002", CUT_SHORT)):
        a0, a1 = T_CUT + dur, T_CUT + dur + 3.0
        rec[e] = {"cut_s": dur, "window": [a0, a1],
                  "in_window": {k: sum(1 for t in v if a0 <= t < a1) for (ee, k), v in ch.items() if ee == e}}
    S["recovery"] = rec
    # 평소 보고량: 끊김 영향이 없는 구간(25~50 s, 65~80 s, 85~105 s)의 GCS 수신 종류별 초당
    wins = {"w25_50": (25, 50), "w65_80": (65, 80), "w85_105": (85, T_END)}
    S["rates"] = {}
    for w, (a0, a1) in wins.items():
        c = Counter(r[2] for r in gcs_rx if a0 <= r[1] < a1)
        S["rates"][w] = {k: round(v / (a1 - a0), 2) for k, v in sorted(c.items())}
    # 3. 늦은 구독자
    sub_t = x2.get("sub_t")
    S["late"] = {"sub_t_sim": round(sim_at(clock, sub_t), 2) if sub_t else None}
    if sub_t:
        first = {}
        for r in x2["rx"]:
            key = f"{r[1]}@{r[2]}"
            first.setdefault(key, round(r[0] - sub_t, 3))
        S["late"]["first_rx_after_sub_s"] = dict(sorted(first.items()))
        w2 = [r for r in x2["rx"] if r[0] - sub_t < 2.0]
        S["late"]["within_2s"] = dict(Counter(f"{r[1]}" for r in w2))
        S["late"]["within_2s_who"] = {n: sorted({(r[6].get("who") or r[6].get("by") or r[4][:8]) for r in w2 if r[1] == n})
                                      for n in sorted({r[1] for r in w2})}
        S["late"]["xsd_ok"] = [sum(1 for r in x2["rx"] if r[3]), len(x2["rx"])]
        # ext1이 같은 순간 받은 중복 (README: 기존 구독자에게도 한 번 더 간다)
        d1 = [r for r in x1["rx"] if 0 <= r[0] - sub_t < 2.0 and r[1] not in ("MA_NavigationReport", "MA_PositionReport",
                                                                              "MA_PackagePartnerStatusReport")]
        S["late"]["ext1_same_2s"] = dict(Counter(r[1] for r in d1))
    S["gw_replay_log"] = [ln.strip()[-160:] for ln in gw_log.splitlines() if "DEC-089" in ln or "late subscriber" in ln][:30]
    S["gw_counters"] = gwj.get("counters")
    S["gw_rejections"] = gwj.get("rejections", [])[:5]
    S["ext_rx_by_uci"] = {n: dict(Counter(r[1] for r in x["rx"])) for n, x in (("ext1", x1), ("ext2", x2))}
    S["gcs_rx_by_msg"] = dict(gin)
    S["frames"] = res["snapshot"]
    S["dead_at_end"] = res.get("dead_at_end")
    S["log_issues"] = res.get("log_issues")
    return S


if __name__ == "__main__":
    try:
        main()
    finally:
        h.Stack.down_all()
