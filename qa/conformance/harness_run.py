"""C2~C6 실행 점검: lockstep 고정 시드로 시뮬레이터 + Gateway + CAL Server + 외부 클라이언트를 띄우고 원자료를 모은다.

프로세스
  Logger(MCAP) · Datalink(participant datalink-0) · Agent(agent_probe.py로 감싼 실제 swarm_agent.cli, agent-0) · Core(lockstep
  1배속, 50 Hz, 평지) · CAL Server(gateway/config/lacal_server.yaml에서 포트·server_id만 바꿔 <out>/lacal_server.yaml로 쓴 것)
  · Gateway(qa/gw_wrap.py) · 외부 CAL Client(qa/gw_ext_client.py, external_c2. Gateway 변환기를 쓰지 않고 JSON을 직접 만든다)
포트: 기본 데모(8765/8766, P0 7447·48xxx)와 겹치지 않게 CAL 28765/28766, Zenoh 48900~.

입력은 모두 Core를 일시정지한 프레임에서 넣는다(StepFrames로 정확한 프레임까지 간 뒤). 유효 입력은 Gateway가 버스에 낸 것을
관측기가 본 뒤 재개하고, 부정 입력은 하나씩 보내 CAL Server 응답과 Gateway 거부 기록의 증가를 확인한다.

시간표(모의 s, 50 Hz)
  10  외부 hold ap-yes(uav-001, 승인)·ap-no(uav-002, 거부)·ap-to(uav-003, 응답 없음 → 15 s 뒤 시간 초과)
      외부 hold x-hold(uav-009), 외부 return_to_base x-rtb(uav-010), RoutePlan r-c1(uav-011, 3점)
  14  MissionPlan plan-c1(uav-011, r-c1)
  22  외부 CANCEL x-hold(uav-009)
  26  부정 입력 10종 (neg-*)
  30  StrikeActivity 자극: 관측기가 onboard/uav-005/StrikeCommand를 직접 낸다(시험 전용 주입. 기본 MA에는 무장 경로가 없다, O-45)
  70  일시정지 → /graph 스냅샷 → 종료
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
QA = HERE.parent
sys.path.insert(0, str(QA))
sys.path.insert(0, str(HERE))
import gw_integ as gi  # noqa: E402
import gw_plan as gp  # noqa: E402
import harness as h  # noqa: E402
from confcommon import GW_PY, ROOT, read_json, write_json  # noqa: E402
from strike_burst import at  # noqa: E402

p0 = h.p0
h.BUILD = ROOT / "build" / "msvc-release"
GCS = "gcs-01"
CAL_PORT, ADMIN_PORT = 28765, 28766
CAL_URL, CAL_ADMIN = f"ws://127.0.0.1:{CAL_PORT}", f"127.0.0.1:{ADMIN_PORT}"
BASE_PORT = 48900
HZ = 50
SEED = 20261117
T_CMD, T_MISSION, T_CANCEL, T_NEG, T_STRIKE, T_END = 10.0, 14.0, 22.0, 26.0, 30.0, 70.0
APPROVE = {"task-001": "APPROVED", "ap-yes": "APPROVED", "ap-no": "REJECTED"}
WP = ["uav-001", "uav-002", "uav-003", "uav-004"]
SHOOTER = "uav-005"
FORM = ["uav-006", "uav-007", "uav-008"]
XCMD = ["uav-009", "uav-010", "uav-011"]
FLK = ["uav-012", "uav-013", "uav-014"]
VEHICLES = [*WP, SHOOTER, *FORM, *XCMD, *FLK]


def route_pts() -> list[tuple[float, float, float]]:
    """uav-011(북 6 km) 앞쪽 3점"""
    out = []
    for i, (dn, de) in enumerate(((6200, 2000), (6600, 4000), (6200, 6000))):
        p = at(dn, de)
        out.append((p["lat_deg"], p["lon_deg"], 500.0 + 10.0 * i))
    return out


def scenario() -> dict:
    cam = {"id": "cam0", "type": "camera", "profile": "eo_wide"}
    uav_link = {"link_profile": "uav_default", "controlling_gcs": GCS}
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
                     "payloads": [cam], "autonomy": {"ma_plugin": "waypoint", "ma_params": mp}, **uav_link})
    ents.append({"id": SHOOTER, "kind": "uav", "side": "blue", "dynamics": "static",
                 "initial": {"position": {**at(-1000, 0), "alt_m": 500.0},
                             "attitude": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}},
                 "payloads": [cam, {"id": "jam0", "type": "jammer", "profile": "ea_generic"},
                              {"id": "sta1", "type": "agm_short", "profile": "agm_generic", "count": 2}],
                 "autonomy": {"ma_plugin": "waypoint", "ma_params": {}}, **uav_link})
    for i, e in enumerate(FORM):
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(-3000 - 150 * i, -1500 - 150 * i), "alt_m": 600.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 20.0, "z": 0.0}},
                     "autonomy": {"ma_plugin": "formation", "ma_params": {"group": "beta", "leader_speed_mps": 20.0}},
                     **uav_link})
    for i, e in enumerate(XCMD):
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(4000 + 1000 * i, 0), "alt_m": 500.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 22.0, "z": 0.0}},
                     "payloads": [cam], "autonomy": {"ma_plugin": "waypoint", "ma_params": {}}, **uav_link})
    for i, e in enumerate(FLK):
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(-5000 - 200 * i, 2000 + 200 * i), "alt_m": 550.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 20.0, "z": 0.0}},
                     "autonomy": {"ma_plugin": "flocking_basic", "ma_params": {"group": "flk"}}, **uav_link})
    ents.append({"id": "tgt-001", "kind": "ground_target", "side": "red", "dynamics": "static",
                 "initial": {"position": at(1500, 3000)}})
    dest = at(1500, 8000)
    return {"schema_version": "0.1", "name": "qa-std29", "description": "QA 29차 표준 적합성 점검 (DEC-092)",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9,
                                                   "east_deg": 128.2}},
            "run": {"mode": "lockstep", "frame_hz": HZ, "seed": SEED, "rate": 1.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": gi.NOLOSS}, {"name": "gcs_default", "ge": gi.NOLOSS}],
            "entities": ents,
            "mission_plan": {"plan_id": "plan-qa29", "tasks": [
                {"task_id": "task-001", "assignees": [*WP, *XCMD],
                 "move_to": {"destination": {**dest, "alt_m": 500.0}, "speed_mps": 22.0}},
                {"task_id": "task-002", "assignees": [FORM[0]],
                 "move_to": {"destination": {**at(-3000, 6000), "alt_m": 600.0}, "speed_mps": 20.0}},
                {"task_id": "task-003", "assignees": [SHOOTER],
                 "strike": {"target_id": "tgt-001", "weapon_type": "agm_short"}}],
                "formations": [{"group_id": "beta", "members": FORM, "leader": FORM[0], "shape": "wedge",
                                "spacing_m": 150.0}]},
            "engagement_criteria": {"hostile_sides": ["red"], "require_approval": True,
                                    "weapons_free": [{"circle": {"center": at(1500, 3000), "radius_m": 10000.0}}]}}


def negatives() -> list[dict]:
    """부정 입력. 모두 neg- 식별자. 'cmd'는 외부 클라이언트의 TaskCommand 작성기, 'raw'는 MessageData를 그대로 싣는다"""
    pts = route_pts()

    def cap(label_task: str, entity_label: str, state: str = "NEW") -> dict:
        return {"Command": [{"Capability": {
            "CommandID": {"UUID": gp.u(f"cmd:{label_task}"), "DescriptiveLabel": f"{label_task}/x"},
            "CommandState": state,
            "CapabilityID": {"UUID": gp.u(f"cap:{label_task}"), "DescriptiveLabel": entity_label},
            "Ranking": {"Rank": {"Priority": 0, "PrecedenceWithinPriority": 0}},
            "TaskID": {"UUID": gp.u(f"task:{label_task}"), "DescriptiveLabel": label_task}}}]}

    out: list[dict] = []
    out.append({"tag": "neg-xsd-cmdstate", "why": "XSD 위반 CommandState", "raw": "MA_TaskCommand", "topic": "swarm.c2",
                "data": cap("neg-xsd-cmdstate", "uav-001/hold", "BOGUS")})
    out.append({"tag": "neg-strike", "why": "가져오기 범위 밖 작업(strike)", "task_id": "neg-strike",
                "entities": ["uav-001"], "kind": "strike"})
    out.append({"tag": "neg-unknown", "why": "시나리오에 없는 기체 uav-999", "task_id": "neg-unknown",
                "entities": ["uav-999"], "kind": "hold"})
    out.append({"tag": "neg-caplabel", "why": "CapabilityID 표지가 '<엔티티>/<작업>' 형식이 아님", "raw": "MA_TaskCommand",
                "topic": "swarm.c2", "data": cap("neg-caplabel", "not an entity")})
    out.append({"tag": "neg-pending", "why": "최종 응답이 아닌 승인 상태(PENDING)", "raw": "MA_ApprovalRequestStatus",
                "topic": "swarm.c2", "data": gp.approval_data("neg-pending", "PENDING")})
    out.append({"tag": "neg-xsd-enum", "why": "XSD 위반 enum(RequestProcessingState DONE)", "raw": "MA_ApprovalRequestStatus",
                "topic": "swarm.c2", "data": {"RequestID": {"UUID": gp.u("neg-xsd-enum"), "DescriptiveLabel": "neg-xsd-enum"},
                                              "RequestProcessingState": "DONE", "ApprovalRequestProcessingState": "APPROVED"}})
    d = gp.route_data("neg-r-all", "uav-011", pts)
    d["Plan"]["Applicability"]["ApplicableToIDs"] = {"ALL": ""}
    out.append({"tag": "neg-route-all", "why": "적용 대상 ALL(기체 하나가 아님)", "raw": "MA_RoutePlan", "topic": "swarm.mp",
                "data": d})
    d = gp.route_data("neg-r-cycle", "uav-011", pts)
    d["Plan"]["Route"]["Path"][0]["PathSegment"][1]["NextPathSegment"] = {"PathSegmentID": {"UUID": gp.u("neg-r-cycle/seg0")}}
    out.append({"tag": "neg-route-cycle", "why": "경로 구간 순환", "raw": "MA_RoutePlan", "topic": "swarm.mp", "data": d})
    out.append({"tag": "neg-mission-unknown", "why": "받은 적 없는 RoutePlan을 가리키는 MissionPlan", "raw": "MA_MissionPlan",
                "topic": "swarm.mp", "data": gp.mission_data("neg-plan-unk", "uav-011", ["neg-r-none"])})
    out.append({"tag": "neg-xsd-route", "why": "XSD 위반(필수 요소 없음)", "raw": "MA_RoutePlan", "topic": "swarm.mp",
                "data": {"RoutePlanID": {"UUID": gp.u("neg-x1"), "DescriptiveLabel": "neg-xsd-route"}}})
    return out


def cal_config(out: Path) -> Path:
    src = (ROOT / "gateway" / "config" / "lacal_server.yaml").read_text(encoding="utf-8")
    txt = re.sub(r"^server_id: .*$", "server_id: calsrv-swarm-qa29", src, count=1, flags=re.M)
    txt = txt.replace("port: 8765}", f"port: {CAL_PORT}}}").replace("port: 8766}", f"port: {ADMIN_PORT}}}")
    assert f"port: {CAL_PORT}" in txt and f"port: {ADMIN_PORT}" in txt, "CAL 설정 포트 치환 실패"
    p = out / "lacal_server.yaml"
    p.write_text("# QA 29차: gateway/config/lacal_server.yaml에서 server_id·포트만 바꿨다 (harness_run.py가 만든다)\n" + txt,
                 encoding="utf-8")
    return p


class ConfObserver(gp.PlanObserver):
    """GCS 수신(= Gateway 입력)의 값, GCS 송신(= Gateway 출력)과 기체 수신 내용을 남긴다"""

    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        from swarm.v1 import common_pb2, ms_pb2, vi_pb2
        self.common, self.ms, self.vi2 = common_pb2, ms_pb2, vi_pb2
        self.bus_in: list[list] = []      # [sim_s, short, source, hdr_us, detail]

    def _state(self, v: int) -> str:
        return self.common.CommandState.Name(v).removeprefix("COMMAND_STATE_")

    def _detail(self, env) -> dict:  # noqa: ANN001
        row = super()._detail(env)
        if row["msg"] == "RoutePlan":
            m = self.mp.RoutePlan.FromString(env.payload)
            row["wps"] = [(w.position.lat_deg, w.position.lon_deg, w.position.alt_m) for w in m.waypoints]
        return row

    def _rx(self, s) -> None:  # noqa: ANN001
        super()._rx(s)
        try:
            env = self.m[2].LinkEnvelope.FromString(s.payload)
            short = env.msg_type.rsplit(".", 1)[-1]
            det: dict | None = None
            if short in ("NavigationReport", "PeerStatus"):
                m = (self.vi.NavigationReport if short == "NavigationReport" else self.p2p.PeerStatus).FromString(
                    env.payload)
                k = m.kinematics
                det = {"lat": k.position.lat_deg, "lon": k.position.lon_deg, "alt": k.position.alt_m,
                       "vel": [k.velocity_ned_mps.x, k.velocity_ned_mps.y, k.velocity_ned_mps.z]
                       if k.HasField("velocity_ned_mps") else None,
                       "q": [k.attitude.w, k.attitude.x, k.attitude.y, k.attitude.z] if k.HasField("attitude") else None,
                       "has_pos": m.HasField("kinematics") and k.HasField("position")}
            elif short == "TaskStatus":
                m = self.c2.TaskStatus.FromString(env.payload)
                det = {"task": m.task_id, "state": self._state(m.state), "reason": m.reason}
            elif short == "FlightCommandStatus":
                m = self.vi.FlightCommandStatus.FromString(env.payload)
                det = {"cmd": m.command_id, "state": self._state(m.state), "reason": m.reason}
            elif short == "ApprovalRequest":
                m = self.c2.ApprovalRequest.FromString(env.payload)
                det = {"req": m.request_id, "task": m.task_id}
            with self.lock:
                self.bus_in.append([round(self.sim_s(), 3), short, env.header.source, env.header.sim_time_us, det])
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.add("decode", f"conf rx: {e}")

    def strike(self, entity: str, payload_id: str, target: dict) -> None:
        with self.lock:
            t_us, frame = self.last_t_us or 0, self.last_frame or 0
        self.seq += 1
        cmd = self.ms.StrikeCommand(payload_id=payload_id, target_id="tgt-001")
        cmd.header.CopyFrom(self.common.Header(sim_time_us=t_us, frame=frame, source=entity, seq=self.seq))
        cmd.aim_point.lat_deg, cmd.aim_point.lon_deg, cmd.aim_point.alt_m = target["lat_deg"], target["lon_deg"], 0.0
        self.bus.put(f"onboard/{entity}/StrikeCommand", cmd.SerializeToString(), h.CT + "StrikeCommand")


class ConfStack(h.Stack):
    """Agent만 agent_probe.py로 띄운다(나머지는 harness.Stack 그대로)"""

    def _cmd(self, name: str) -> list[str]:
        if name == "agent":
            return [sys.executable, str(HERE / "agent_probe.py")]
        return super()._cmd(name)


def http_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310  로컬 관리 포트
        return json.loads(r.read().decode("utf-8"))


def run(out: Path, base_port: int = BASE_PORT, log=print) -> dict:  # noqa: ANN001, C901, PLR0915
    """원자료를 out에 쓰고 요약(marks, 진행 기록)을 돌려준다"""
    out.mkdir(parents=True, exist_ok=True)
    ext_dir = out / "ext"
    (ext_dir / "cmd").mkdir(parents=True, exist_ok=True)
    for f in [*ext_dir.glob("cmd/*.json"), ext_dir / "STOP", ext_dir / "ext.ready", ext_dir / "ext.json",
              ext_dir / "full.jsonl"]:
        f.unlink(missing_ok=True)
    sc = scenario()
    sp = out / "scenario.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    cfg = cal_config(out)
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["CONF_AGENT_PROBE"] = str(out / "agent_probe.json")
    os.environ["GW_PROBE_OUT"] = str(out / "gw1.json")
    st = ConfStack(out / "stack", sp, base_port=base_port, lockstep=True, rate=1.0, record=True, hz=HZ,
                   core_extra=["--terrain-flat", "0"])
    extra: list = []
    marks: dict = {"t0_epoch": time.time(), "events": []}
    ncmd = [0]
    pids: dict[str, int] = {}
    ob: ConfObserver | None = None

    def ev(tag: str, **kw) -> None:  # noqa: ANN003
        with ob.lock:
            fr, s = ob.last_frame, ob.sim_s()
        marks["events"].append({"tag": tag, "frame": fr, "sim_s": round(s, 3), "epoch": time.time(), **kw})
        log(f"[conf] {tag} frame={fr} {kw if kw else ''}")

    def put_cmd(c: dict) -> str:
        ncmd[0] += 1
        name = f"{ncmd[0]:03d}.json"
        write_json(ext_dir / "cmd" / name, c)
        return name

    def ext_state() -> dict:
        return read_json(ext_dir / "ext.json", default={"cmds": [], "rx": []}) or {"cmds": [], "rx": []}

    def wait_sent(fname: str, timeout: float = 10.0) -> dict | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for c in ext_state().get("cmds", []):
                if c.get("file") == fname:
                    return c
            time.sleep(0.2)
        return None

    def gw_rej() -> tuple[int, list[str]]:
        g = read_json(out / "gw1.json", default={}) or {}
        c = g.get("counters", {})
        n = sum(c.get(k, 0) for k in ("rejected", "unmapped"))   # ext_rejected는 같은 거부를 한 번 더 센다
        return n, list(g.get("rejections", []))

    def tx_after(n0: int, pred) -> list[dict]:  # noqa: ANN001
        with ob.lock:
            return [r for r in ob.tx[n0:] if pred(r)]

    def send_valid(items: list[tuple[str, dict, object]], timeout: float = 8.0) -> None:
        """items: (태그, 명령, 버스 확인 조건). 모두 보낸 뒤 각 조건의 GCS 송신을 관측기가 볼 때까지 기다린다"""
        with ob.lock:
            n0 = len(ob.tx)
        files = [(tag, put_cmd(c), pred) for tag, c, pred in items]
        for tag, f, pred in files:
            rec = wait_sent(f)
            end = time.monotonic() + timeout
            seen = []
            while time.monotonic() < end and not seen:
                seen = tx_after(n0, pred)
                time.sleep(0.1)
            ev(f"send {tag}", pub=(rec or {}).get("pub"), xsd_ok=(rec or {}).get("xsd_ok"),
               bus=[(r["msg"], r.get("id"), r.get("dst")) for r in seen][:4])

    def send_negatives() -> None:
        for c in negatives():
            with ob.lock:
                n0 = len(ob.tx)
            r0, _ = gw_rej()
            f = put_cmd({k: v for k, v in c.items() if k != "why"})
            rec = wait_sent(f) or {}
            time.sleep(1.6)            # gw1.json은 0.5 s마다 쓴다
            r1, rej = gw_rej()
            seen = tx_after(n0, lambda r: str(r.get("id", "")).startswith("neg-") or "uav-999" in r.get("dst", []))
            ev(f"neg {c['tag']}", pub=rec.get("pub"), xsd_ok=rec.get("xsd_ok"), xsd_err=rec.get("xsd_err"),
               gw_rej_delta=r1 - r0, gw_rej_new=rej[-(r1 - r0):] if r1 > r0 else [],
               bus=[{"msg": r["msg"], "id": r.get("id"), "dst": r.get("dst"), "key": r["key"]} for r in seen][:4],
               why=c["why"])

    try:
        cal = p0.Proc("calsrv", [str(GW_PY), "-m", "swarm_gateway.lacal_server", "--config", str(cfg)], st.out,
                      cwd=ROOT / "gateway")
        extra.append(cal)
        assert gi.wait_port(CAL_PORT), "CAL Server 기동 실패"
        st.start_one("logger")
        st.start_one("datalink")
        st.start_one("agent")
        gw = p0.Proc("gateway.1", [str(GW_PY), str(QA / "gw_wrap.py"), "--gcs", GCS, "--lacal", CAL_URL,
                                   "--lacal-admin", f"ws://{CAL_ADMIN}", "--no-multicast", "--connect", st.endpoint(),
                                   "--listen", f"tcp/127.0.0.1:{base_port + 30}", "--stats-s", "5"], st.out, cwd=ROOT)
        extra.append(gw)
        x = p0.Proc("ext", [str(GW_PY), str(QA / "gw_ext_client.py"), "--url", CAL_URL, "--admin", CAL_ADMIN,
                            "--out", str(ext_dir), "--approve", json.dumps(APPROVE),
                            "--full", str(ext_dir / "full.jsonl")], st.out, cwd=ROOT)
        extra.append(x)
        end = time.monotonic() + 60
        while not (ext_dir / "ext.ready").exists() and time.monotonic() < end:
            time.sleep(0.2)
        assert (ext_dir / "ext.ready").exists(), "외부 클라이언트 준비 실패"
        while "gateway: ready at" not in (st.out / "gateway.1.log").read_text(encoding="utf-8", errors="replace"):
            assert time.monotonic() < end, "Gateway 준비 실패"
            time.sleep(0.2)
        time.sleep(st.settle)
        ob = ConfObserver([st.endpoint()])
        ob.watch_onboard()
        time.sleep(1.0)
        st.start_one("core")
        pids = {n: p.p.pid for n, p in st.procs.items()} | {p.name: p.p.pid for p in extra}
        marks["pids"] = pids
        log(f"[conf] pids {pids}")
        assert gp.wait_frame(ob, 20, 90), "Core 시작 대기 실패"
        ob.pause()
        at_f = gp.wait_paused(ob)
        pts = route_pts()

        def goto(t_s: float) -> None:
            nonlocal at_f
            fr = int(round(t_s * HZ))
            ob.step(fr - at_f)
            assert gp.wait_frame(ob, fr, 240), f"프레임 {fr} 대기 실패"
            at_f = gp.wait_paused(ob, fr, 60)

        goto(T_CMD)
        is_tc = lambda tid: (lambda r: r["msg"] == "TaskCommand" and r.get("id") == tid)  # noqa: E731
        send_valid([
            ("ap-yes hold uav-001", {"task_id": "ap-yes", "entities": ["uav-001"], "kind": "hold"}, is_tc("ap-yes")),
            ("ap-no hold uav-002", {"task_id": "ap-no", "entities": ["uav-002"], "kind": "hold"}, is_tc("ap-no")),
            ("ap-to hold uav-003", {"task_id": "ap-to", "entities": ["uav-003"], "kind": "hold"}, is_tc("ap-to")),
            ("x-hold hold uav-009", {"task_id": "x-hold", "entities": ["uav-009"], "kind": "hold"}, is_tc("x-hold")),
            ("x-rtb return_to_base uav-010", {"task_id": "x-rtb", "entities": ["uav-010"], "kind": "return_to_base"},
             is_tc("x-rtb")),
            ("route r-c1 uav-011", {"raw": "MA_RoutePlan", "topic": "swarm.mp", "tag": "route r-c1",
                                    "data": gp.route_data("r-c1", "uav-011", pts)},
             lambda r: r["msg"] == "RoutePlan" and r.get("id") == "r-c1")])
        goto(T_MISSION)
        send_valid([("mission plan-c1 uav-011", {"raw": "MA_MissionPlan", "topic": "swarm.mp", "tag": "mission plan-c1",
                                                  "data": gp.mission_data("plan-c1", "uav-011", ["r-c1"])},
                     lambda r: r["msg"] == "MissionPlan" and r.get("id") == "plan-c1")])
        goto(T_CANCEL)
        send_valid([("cancel x-hold uav-009", {"task_id": "x-hold", "entities": ["uav-009"], "kind": "hold",
                                               "cancel": True},
                     lambda r: r["msg"] == "TaskCommand" and r.get("id") == "x-hold" and r.get("cancel"))])
        goto(T_NEG)
        send_negatives()
        goto(T_STRIKE)
        ob.strike(SHOOTER, "sta1", at(1500, 3000))
        ev("strike stimulus onboard/uav-005/StrikeCommand (시험 전용)")
        time.sleep(0.5)
        goto(T_END)
        ev("end paused")
        time.sleep(3.0)
        try:
            write_json(out / "graph.json", http_json(f"http://{CAL_ADMIN}/graph"))
        except Exception as e:  # noqa: BLE001
            marks["graph_error"] = str(e)
        (ext_dir / "STOP").write_text("x", encoding="utf-8")
        time.sleep(2.5)
        marks["dead_at_end"] = st.dead() + [p.name for p in extra if not p.alive()]
        marks["log_issues"] = h.scan_logs(st)[:40]
        marks["snapshot"] = ob.snapshot()
        with ob.lock:
            obs = {"bus_in": list(ob.bus_in), "tx": list(ob.tx), "rx": list(ob.rx), "ts": list(ob.ts),
                   "onboard": dict(ob.onboard), "status_hist": list(ob.status_hist)[-5:]}
        ob.close()
        write_json(out / "obs.json", obs)
    finally:
        st.down()          # Proc.kill은 자기가 띄운 PID만 taskkill /T /PID로 끝낸다
        p0.stop(extra)
    marks["t1_epoch"] = time.time()
    write_json(out / "marks.json", marks)
    return marks


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-port", type=int, default=BASE_PORT)
    a = ap.parse_args()
    try:
        run(Path(a.out).resolve(), a.base_port)
    finally:
        h.Stack.down_all()
