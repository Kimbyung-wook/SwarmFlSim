"""QA 36차 O-2 확인 (DEC-103, TC-QA-19x): 승인 흐름 시험용 MA approval_demo를 Gateway 외부 경로로 확인한다.

gw_agra.py(QA 28차 §36)와 같은 실제 스택: Datalink·Agent·Core(realtime 1배속, 평지)·CAL Server·Gateway(qa/gw_wrap.py)·
외부 CAL Client(qa/gw_ext_client.py, --approve 규칙). 외부 클라이언트가 MA_ApprovalRequest를 받으면 규칙대로
MA_ApprovalRequestStatus를 CAL로 보내고, Gateway가 그것을 ApprovalResponse로 바꿔 기체에 보낸다.

기체 (모두 정지, approval_demo, agm_short 2발, approval_timeout_s=15, 교전 기준 require_approval=true)
  uav-001  계획 strike st-yes → 외부 승인 → StrikeCommand → 유도 객체 도달이면 COMPLETED (표적은 북 1 km·동 0.5 km)
  uav-002  계획 strike st-no  → 외부 거부 → 발사 없이 REJECTED(approval denied)
  uav-003  계획 strike st-to  → 응답 없음 → 15 s 뒤 발사 없이 REJECTED(approval timeout)

uv run python qa/gw_approval36.py --out qa/out/qa36/approval/r1
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
import gw_agra as ga  # noqa: E402
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
T_END = 90.0
TIMEOUT_S = 15.0
CASES = {"uav-001": "st-yes", "uav-002": "st-no", "uav-003": "st-to"}
APPROVE = {"st-yes": "APPROVED", "st-no": "REJECTED"}
# r1(표적 북 2.5 km·동 3 km)은 탐색기 고정 실패(lock_failed)로 FAILED였다. r2부터 strike_burst와 같은 1 km 안팎에 둔다
TGT = (1000, 500)


def scenario() -> dict:
    cam = {"id": "cam0", "type": "camera", "profile": "eo_wide"}
    ents = [{"id": GCS, "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(-2000, 0), "alt_m": 30.0}}, "link_profile": "gcs_default"}]
    for i, e in enumerate(CASES):
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "static",
                     "initial": {"position": {**at(0, 500 * i), "alt_m": 500.0},
                                 "attitude": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}},
                     "payloads": [cam, {"id": "sta1", "type": "agm_short", "profile": "agm_generic", "count": 2}],
                     "autonomy": {"ma_plugin": "approval_demo", "ma_params": {"approval_timeout_s": TIMEOUT_S}},
                     "link_profile": "uav_default", "controlling_gcs": GCS})
    ents.append({"id": "tgt-001", "kind": "ground_target", "side": "red", "dynamics": "static",
                 "initial": {"position": at(*TGT)}})
    return {"schema_version": "0.1", "name": "qa-approval36", "description": "QA 36차 O-2 approval_demo 외부 경로",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9,
                                                   "east_deg": 128.2}},
            "run": {"mode": "realtime", "frame_hz": 50, "seed": 20261117, "rate": 1.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": gi.NOLOSS}, {"name": "gcs_default", "ge": gi.NOLOSS}],
            "entities": ents,
            "mission_plan": {"plan_id": "plan-qa36", "tasks": [
                {"task_id": t, "assignees": [e], "strike": {"target_id": "tgt-001", "weapon_type": "agm_short"}}
                for e, t in CASES.items()]},
            "engagement_criteria": {"hostile_sides": ["red"], "require_approval": True,
                                    "weapons_free": [{"circle": {"center": at(*TGT), "radius_m": 10000.0}}]}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-port", type=int, default=48700)
    a = ap.parse_args()
    out = (ROOT / a.out) if not Path(a.out).is_absolute() else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    e1 = out / "ext1"
    sp = SCN / "qa_approval36.json"
    sp.write_text(json.dumps(scenario(), ensure_ascii=False, indent=1), encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    st = h.Stack(out / "stack", sp, base_port=a.base_port, lockstep=False, record=False,
                 core_extra=["--terrain-flat", "0"])
    extra: list = []
    res: dict = {"scenario": str(sp.relative_to(ROOT))}
    clock: list[tuple[float, float]] = []
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
        extra.append(ga.start_ext("ext1", e1, st, APPROVE))
        end = time.monotonic() + 40
        while not (e1 / "ext.ready").exists() and time.monotonic() < end:
            time.sleep(0.2)
        assert (e1 / "ext.ready").exists(), "외부 클라이언트 준비 실패"
        time.sleep(st.settle)
        ob = gi.GwObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        t0 = time.monotonic()
        while time.monotonic() - t0 < T_END * 1.5 + 60:
            time.sleep(0.1)
            s = ob.sim_s()
            clock.append((time.time(), s))
            if s >= T_END or "core" in "".join(st.dead()):
                break
        res["dead_at_end"] = st.dead() + [p.name for p in extra if not p.alive()]
        (e1 / "STOP").write_text("x", encoding="utf-8")
        time.sleep(2.5)
        res["log_issues"] = h.scan_logs(st)[:30]
        snap = ob.snapshot()
        with ob.lock:
            gcs_rx, gcs_tx = list(ob.gcs_rx), list(ob.gcs_tx)
            taskstatus = {k: list(v) for k, v in ob.taskstatus.items()}
        ob.close()
    finally:
        st.down()
        p0.stop(extra)
    res["snapshot"] = {k: snap.get(k) for k in ("last_frame", "sim_s", "gap_frames", "overruns", "findings")}
    x1 = json.loads((e1 / "ext.json").read_text(encoding="utf-8")) if (e1 / "ext.json").exists() else \
        {"rx": [], "cmds": [], "xsd_fail": [], "errors": []}
    gwj = json.loads((out / "gw1.json").read_text(encoding="utf-8")) if (out / "gw1.json").exists() else {}
    with gzip.open(out / "raw.pkl.gz", "wb") as f:
        pickle.dump({"res": res, "gcs_rx": gcs_rx, "gcs_tx": gcs_tx, "taskstatus": taskstatus, "clock": clock,
                     "ext": x1, "gw": gwj}, f)
    res["summary"] = analyse(res, x1, gwj, gcs_rx, gcs_tx, taskstatus, clock)
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1, default=str))


def analyse(res, x1, gwj, gcs_rx, gcs_tx, taskstatus, clock) -> dict:  # noqa: ANN001
    sim_at = ga.sim_at
    S: dict = {}
    S["approval_requests_ext"] = [{"t_sim": round(sim_at(clock, r[0]), 2), "xsd_ok": r[3],
                                   **{k: r[6].get(k) for k in ("req", "task", "state")}}
                                  for r in x1["rx"] if r[1] == "MA_ApprovalRequest"]
    S["approval_replies"] = [{k: c.get(k) for k in ("tag", "xsd_ok", "pub", "xsd_err")} | {"t_sim": round(sim_at(clock, c["t"]), 2)}
                             for c in x1["cmds"] if c.get("name") == "MA_ApprovalRequestStatus"]
    S["gw_tx"] = [{"sim_s": round(r["sim_s"], 2), "key": r["key"].split("/tx/")[-1], "dst": r["dst"]} for r in gcs_tx]
    # GCS가 받은 TaskStatus(모의 시각 포함)
    S["taskstatus_gcs"] = {e: v[:12] for e, v in sorted(taskstatus.items())}
    ts_t = defaultdict(list)
    for r in gcs_rx:
        if r[2] == "TaskStatus":
            ts_t[r[3]].append(round(r[1], 2))
    S["taskstatus_rx_t"] = {e: v[:12] for e, v in sorted(ts_t.items())}
    ext_ts = defaultdict(list)
    for r in x1["rx"]:
        if r[1] == "MA_TaskStatus":
            s = f"{r[6]['task']}:{r[6]['state']}@{round(sim_at(clock, r[0]), 2)}"
            if not ext_ts[r[6]["by"]] or ext_ts[r[6]["by"]][-1].split("@")[0] != s.split("@")[0]:
                ext_ts[r[6]["by"]].append(s)
    S["taskstatus_ext"] = dict(sorted(ext_ts.items()))
    # 발사 여부: GCS가 받은 StrikeActivity·StoreLoadout (기체별 모의 시각)
    act = defaultdict(list)
    for r in gcs_rx:
        if r[2] in ("StrikeActivity", "StoreLoadout"):
            act[f"{r[3]}/{r[2]}"].append(round(r[1], 2))
    S["strike_rx"] = {k: v[:10] for k, v in sorted(act.items())}
    S["ext_rx_by_uci"] = dict(Counter(r[1] for r in x1["rx"]))
    S["ext1_xsd_fail"], S["ext1_errors"] = x1["xsd_fail"][:5], x1["errors"][:5]
    S["gw_counters"] = gwj.get("counters")
    S["gw_rejections"] = gwj.get("rejections", [])[:5]
    S["gcs_rx_by_msg"] = dict(Counter(r[2] for r in gcs_rx))
    S["frames"] = res["snapshot"]
    S["dead_at_end"] = res.get("dead_at_end")
    S["log_issues"] = res.get("log_issues")
    return S


if __name__ == "__main__":
    try:
        main()
    finally:
        h.Stack.down_all()
