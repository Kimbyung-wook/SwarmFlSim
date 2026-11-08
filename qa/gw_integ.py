"""QA 15차 P6 Gateway 통합 데모 (TC-QA-069~074, DEC-068).

Datalink·Agent(qa/strike_burst_agent.py: flocking_basic + 정해진 프레임 조준점 발사)·Core(realtime, 평지)를 띄우고
agra_lacal CAL Server, Gateway(qa/gw_wrap.py로 감싼 실제 진입점, --gcs gcs-01), 외부 CAL Client(qa/gw_ext_client.py)를
붙인다. 기체 5대(이동 4 + 정지 사수 1)와 gcs-01.

시간표(모의 s, realtime 1배속)
  30   외부 MA_TaskCommand: uav-001 hold(ext-hold-1), uav-002 return_to_base(ext-rtb-1)
  35~44 EXT 주입: uav-003 → gcs-01 PeerAlgorithmMessage·Detection·FormationCommand 각 1 Hz
  45   uav-005 조준점 발사(축 위) → StrikeActivity
  70   GCS_LINK_CUT uav-003·uav-004 15 s          (부분 차단)
  95   LINK_CUT gcs-01 15 s                         (GCS 전체 차단)
  120  Gateway 프로세스 강제 종료(PID), 130 다시 기동
  140  외부 hold uav-003(ext-hold-2), 145 외부 CANCEL ext-hold-1(uav-001)
  165  종료

uv run python qa/gw_integ.py --out qa/out/gw/r1
출력은 판정 요약뿐이다. 원자료는 <out>/result.json, ext/ext.json, gw*.json, stack/*.log.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from strike_burst import M_LAT, SCN, BurstStack, at  # noqa: E402

p0 = h.p0
QA = Path(__file__).resolve().parent
ROOT = QA.parent
GW_PY = ROOT / "gateway" / ".venv" / "Scripts" / "python.exe"
CAL_URL, CAL_ADMIN = "ws://127.0.0.1:18765", "127.0.0.1:18766"
NOLOSS = {"p_gb": 0.0, "p_bg": 1.0, "loss_good": 0.0, "loss_bad": 0.0}
GCS = "gcs-01"
MOVERS = ["uav-001", "uav-002", "uav-003", "uav-004"]
SHOOTER = "uav-005"

T_EXT, T_INJ, T_STRIKE = 30.0, (35, 44), 45.0
T_CUT1, T_CUT2, CUT_S = 70.0, 95.0, 15.0
T_GW_KILL, T_GW_UP = 120.0, 130.0
T_EXT2, T_CANCEL, T_END = 140.0, 145.0, 165.0
T_FAULT_ON, T_FAULT_OFF = 55.0, 62.0   # 16차: uav-004 SENSOR 고장 주입·해제 (SystemStatus 변화)

# 내부 STD 메시지 → UCI (gateway/README.md 교환 메시지 표)
STD_UCI = {"NavigationReport": "MA_NavigationReport", "SystemStatus": "SystemStatus",
           "FlightCommandStatus": "MA_FlightCommandStatus", "FlightCapability": "MA_FlightCapability",
           "TaskStatus": "MA_TaskStatus", "ApprovalRequest": "MA_ApprovalRequest",
           "PeerStatus": "MA_PackagePartnerStatusReport", "LeaderUpdate": "MA_LeaderUpdateRequest",
           "TrackShare": "MA_Entity", "SensorActivity": "PO_Activity", "JammerActivity": "EA_Activity",
           "StrikeActivity": "StrikeActivity", "StoreLoadout": "StoreLoadoutConfiguration"}
UCI_IFACE = {"MA_NavigationReport": "VI", "SystemStatus": "VI", "MA_FlightCommandStatus": "VI",
             "MA_FlightCapability": "VI", "MA_TaskStatus": "C2", "MA_ApprovalRequest": "C2",
             "MA_PackagePartnerStatusReport": "P2P", "MA_LeaderUpdateRequest": "P2P", "MA_Entity": "P2P",
             "PO_Activity": "MS", "EA_Activity": "MS", "StrikeActivity": "MS", "StoreLoadoutConfiguration": "MS",
             "MA_PositionReport": "POS"}  # 16차: uci_also (vi·p2p 토픽 둘 다)


def scenario(mover_ma: str = "flocking_basic") -> dict:
    agm = {"type": "agm_short", "profile": "agm_generic"}
    cam = {"id": "cam0", "type": "camera", "profile": "eo_wide"}
    ents = [{"id": GCS, "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(-2000, 0), "alt_m": 30.0}}, "link_profile": "gcs_default"}]
    for i, e in enumerate(MOVERS):
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(1000 * i, 0), "alt_m": 500.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 22.0, "z": 0.0}},
                     "payloads": [cam], "autonomy": {"ma_plugin": mover_ma,
                                                     "ma_params": {"group": f"g{i}"} if mover_ma == "flocking_basic" else {}},
                     "link_profile": "uav_default", "controlling_gcs": GCS})
    ents.append({"id": SHOOTER, "kind": "uav", "side": "blue", "dynamics": "static",
                 "initial": {"position": {**at(-1000, 0), "alt_m": 500.0}, "attitude": {"w": 1.0, "x": 0.0,
                                                                                    "y": 0.0, "z": 0.0}},
                 "payloads": [cam, {"id": "jam0", "type": "jammer", "profile": "ea_generic"},
                              {"id": "sta1", **agm, "count": 2}],
                 "autonomy": {"ma_plugin": "flocking_basic", "ma_params": {"group": "g5"}},
                 "link_profile": "uav_default", "controlling_gcs": GCS})
    ents.append({"id": "tgt-001", "kind": "ground_target", "side": "red", "dynamics": "static",
                 "initial": {"position": at(1500, 3000)}})
    dest = at(1500, 8000)
    return {"schema_version": "0.1", "name": "qa-gw-integ", "description": "QA 15차 P6 Gateway 통합 데모",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.4, "north_deg": 37.6, "west_deg": 127.9,
                                                   "east_deg": 128.2}},
            "run": {"mode": "realtime", "frame_hz": 50, "seed": 20261108, "rate": 1.0, "duration_s": 600.0},
            "link_profiles": [{"name": "uav_default", "ge": NOLOSS}, {"name": "gcs_default", "ge": NOLOSS}],
            "entities": ents,
            "mission_plan": {"plan_id": "plan-qa15", "tasks": [
                {"task_id": "task-001", "assignees": MOVERS,
                 "move_to": {"destination": {**dest, "alt_m": 500.0}, "speed_mps": 22.0}}]}}


class GwObserver(h.Observer):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints, jump_m=2000.0)
        self.keep_traj = True
        self.gcs_rx: list[tuple] = []     # (epoch, sim_s, short msg, source)
        self.gcs_tx: list[dict] = []      # swarm/gcs-01/tx/** (Gateway만 발행)
        self.lo: list[tuple] = []         # gcs 관련 link outcome (sim_s, src, dst, msg, outcome, reason)
        self.subs.append(self.bus.subscribe(f"swarm/{GCS}/tx/**", self._gtx))
        self.vi_rx: list[tuple] = []      # 16차: GCS가 받은 VI·PeerStatus 내용 (epoch, sim_s, msg, src, hdr_us, detail)
        from swarm.v1 import p2p_pb2, vi_pb2
        self.vi, self.p2p = vi_pb2, p2p_pb2

    def _rx(self, s) -> None:  # noqa: ANN001
        link = self.m[2]
        try:
            env = link.LinkEnvelope.FromString(s.payload)
            short = env.msg_type.rsplit(".", 1)[-1]
            with self.lock:
                self.gcs_rx.append((time.time(), self.sim_s(), short, env.header.source))
            det = None
            if short in ("NavigationReport", "PeerStatus"):
                m = (self.vi.NavigationReport if short == "NavigationReport" else self.p2p.PeerStatus).FromString(
                    env.payload)
                p = m.kinematics.position
                det = (m.header.sim_time_us, p.lat_deg, p.lon_deg, p.alt_m)
            elif short == "SystemStatus":
                m = self.vi.SystemStatus.FromString(env.payload)
                det = (m.header.sim_time_us, self.vi.Health.Name(m.health).removeprefix("HEALTH_"),
                       round(m.energy_frac, 4), [(x.name, self.vi.Health.Name(x.health).removeprefix("HEALTH_"))
                                                 for x in m.subsystems])
            elif short == "FlightCommandStatus":
                m = self.vi.FlightCommandStatus.FromString(env.payload)
                det = (m.header.sim_time_us, m.command_id,
                       self.m[4].CommandState.Name(m.state).removeprefix("COMMAND_STATE_"), m.reason)
            elif short == "FlightCapability":
                det = (0,)
            if det is not None:
                with self.lock:
                    self.vi_rx.append((time.time(), self.sim_s(), short, env.header.source, *det))
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.add("decode", f"gcs rx: {e}")
        super()._rx(s)

    def _outcome(self, s) -> None:  # noqa: ANN001
        super()._outcome(s)
        link = self.m[2]
        o = link.LinkOutcome.FromString(s.payload)
        if GCS in (o.src, o.dst):
            with self.lock:
                self.lo.append((o.tx_time_us * 1e-6, o.src, o.dst, o.msg_type.rsplit(".", 1)[-1],
                                link.LinkOutcomeKind.Name(o.outcome).removeprefix("LINK_OUTCOME_KIND_"),
                                link.DropReason.Name(o.reason).removeprefix("DROP_REASON_")
                                if o.outcome == link.LINK_OUTCOME_KIND_DROPPED else "", o.seq))

    def _gtx(self, s) -> None:  # noqa: ANN001
        link, c2 = self.m[2], self.m[3]
        env = link.LinkEnvelope.FromString(s.payload)
        row = {"epoch": time.time(), "sim_s": self.sim_s(), "key": s.key, "src": env.header.source,
               "seq": env.header.seq, "dst": list(env.dst), "msg": env.msg_type}
        if env.msg_type == "swarm.v1.TaskCommand":
            t = c2.TaskCommand.FromString(env.payload)
            row |= {"task_id": t.task_id, "kind": t.WhichOneof("task") or "", "cancel": t.cancel,
                    "assignees": list(t.assignees)}
        with self.lock:
            self.gcs_tx.append(row)

    def put_ext(self, src: str, iface: str, msg, dst: list[str]) -> None:  # noqa: ANN001
        sim, truth, link, c2, common = self.m
        from swarm.v1 import options_pb2
        with self.lock:
            t_us, frame = self.last_t_us or 0, self.last_frame or 0
        self.seq += 1
        hdr = common.Header(sim_time_us=t_us, frame=frame, source=src, seq=self.seq)
        msg.header.CopyFrom(hdr)
        env = link.LinkEnvelope(header=hdr, dst=dst, iface=getattr(options_pb2, f"L1_INTERFACE_{iface.upper()}"),
                                msg_type=msg.DESCRIPTOR.full_name, payload=msg.SerializeToString())
        name = msg.DESCRIPTOR.name
        self.bus.put(f"swarm/{src}/tx/{iface}/{name}", env.SerializeToString(), h.CT + "LinkEnvelope")


def wait_port(port: int, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def pos_ne(p: tuple, ref: tuple) -> tuple[float, float]:
    return ((p[0] - ref[0]) * M_LAT, (p[1] - ref[1]) * M_LAT * math.cos(math.radians(ref[0])))


def traj_at(tr: list, t: float) -> tuple | None:
    """frame/50 = 모의 s. t 이상인 첫 표본"""
    for fr, la, lo, al in tr:
        if fr / 50.0 >= t:
            return (la, lo, al)
    return None


def window(tr: list, t0: float, t1: float) -> list:
    return [(fr / 50.0, la, lo, al) for fr, la, lo, al in tr if t0 <= fr / 50.0 < t1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-port", type=int, default=48600)
    ap.add_argument("--mover-ma", default="flocking_basic",
                    help="uav-001~004 MA (16차 FlightCommandStatus 확인은 waypoint)")
    ap.add_argument("--gw-zenoh-config", action="store_true",
                    help="15차 방식: --no-multicast 대신 qa/scenarios/gw_zenoh_peer.json5로 멀티캐스트를 끈다")
    ap.add_argument("--no-wait-gw2", dest="wait_gw2", action="store_false",
                    help="재기동 Gateway의 LA-CAL 접속을 기다리지 않고 시간표대로 외부 명령을 보낸다 (r1·r2 방식)")
    a = ap.parse_args()
    out = (ROOT / a.out) if not Path(a.out).is_absolute() else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ext_dir = out / "ext"
    (ext_dir / "cmd").mkdir(parents=True, exist_ok=True)
    for f in [*ext_dir.glob("cmd/*.json"), ext_dir / "STOP", ext_dir / "ext.ready", ext_dir / "ext.json"]:
        f.unlink(missing_ok=True)
    sc = scenario(a.mover_ma)
    sp = SCN / "qa_gw_integ.json"
    sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
    sh_pos = next(e for e in sc["entities"] if e["id"] == SHOOTER)["initial"]["position"]
    aim = at(-1000 + 866.0, 0)  # 축 위: 북쪽 866 m 지면 = 아래 30°
    os.environ["BURST_OUT"] = str(out / "probe.json")
    os.environ["BURST_PLAN"] = json.dumps([{"f": int(T_STRIKE * 50), "e": SHOOTER, "pid": "sta1",
                                            "aim": [aim["lat_deg"], aim["lon_deg"], 0.0]}])
    os.environ["PYTHONIOENCODING"] = "utf-8"
    st = BurstStack(out / "stack", sp, base_port=a.base_port, lockstep=False, record=False,
                    core_extra=["--terrain-flat", "0"])
    extra: list = []
    gw_procs: list = []
    res: dict = {"scenario": str(sp.relative_to(ROOT)), "shooter": sh_pos, "aim": aim}
    marks: dict[str, float] = {}       # 동작 → epoch
    clock: list[tuple[float, float]] = []  # (epoch, sim_s)
    gw_port = a.base_port + 30

    def start_gw(gen: int):  # noqa: ANN202
        os.environ["GW_PROBE_OUT"] = str(out / f"gw{gen}.json")
        pr = p0.Proc(f"gateway.{gen}", [str(GW_PY), str(QA / "gw_wrap.py"), "--gcs", GCS, "--lacal", CAL_URL,
                                        *(["--zenoh-config", str(QA / "scenarios" / "gw_zenoh_peer.json5")]
                                          if a.gw_zenoh_config else ["--no-multicast"]),
                                        "--connect", st.endpoint(), "--listen", f"tcp/127.0.0.1:{gw_port + gen}",
                                        "--stats-s", "5"], st.out, cwd=ROOT)
        gw_procs.append(pr)
        return pr

    ncmd = [0]

    def ext_cmd(task_id: str, entities: list[str], kind: str, cancel: bool = False) -> None:
        ncmd[0] += 1
        (ext_dir / "cmd" / f"{ncmd[0]:03d}.json").write_text(json.dumps(
            {"task_id": task_id, "entities": entities, "kind": kind, "cancel": cancel}), encoding="utf-8")

    try:
        cal = p0.Proc("calsrv", [str(GW_PY), "-m", "swarm_gateway.lacal_server", "--config",
                                 str(QA / "scenarios" / "gw_lacal_server.yaml")], st.out, cwd=ROOT / "gateway")
        extra.append(cal)
        assert wait_port(18765), "CAL Server 기동 실패"
        st.start_one("datalink")
        st.start_one("agent")
        gw = start_gw(1)
        ext = p0.Proc("ext", [str(GW_PY), str(QA / "gw_ext_client.py"), "--url", CAL_URL, "--admin", CAL_ADMIN,
                              "--out", str(ext_dir)], st.out, cwd=ROOT)
        extra.append(ext)
        end = time.monotonic() + 40
        while not (ext_dir / "ext.ready").exists() and time.monotonic() < end:
            time.sleep(0.2)
        assert (ext_dir / "ext.ready").exists(), "외부 클라이언트 준비 실패"
        time.sleep(st.settle)
        ob = GwObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        from swarm.v1 import c2_pb2, ms_pb2, p2p_pb2
        done: set[str] = set()
        inj = Counter()
        t_wall0 = time.monotonic()

        def once(tag: str, t: float, fn) -> None:  # noqa: ANN001
            if tag not in done and ob.sim_s() >= t:
                done.add(tag)
                marks[tag] = time.time()
                fn()

        while time.monotonic() - t_wall0 < T_END * 1.5 + 60:
            time.sleep(0.1)
            s = ob.sim_s()
            clock.append((time.time(), s))
            once("ext1", T_EXT, lambda: (ext_cmd("ext-hold-1", ["uav-001"], "hold"),
                                         ext_cmd("ext-rtb-1", ["uav-002"], "return_to_base")))
            for k in range(T_INJ[0], T_INJ[1] + 1):
                def _inj() -> None:
                    ob.put_ext("uav-003", "p2p", p2p_pb2.PeerAlgorithmMessage(), [GCS])
                    ob.put_ext("uav-003", "ms", ms_pb2.Detection(), [GCS])
                    ob.put_ext("uav-003", "c2", c2_pb2.FormationCommand(), [GCS])
                    inj["n"] += 1
                once(f"inj{k}", float(k), _inj)
            once("fault_on", T_FAULT_ON, lambda: ob.fault("uav-004", "SENSOR"))
            once("fault_off", T_FAULT_OFF, lambda: ob.fault("uav-004", "SENSOR", clear=True))
            once("cut1", T_CUT1, lambda: [ob.fault(e, "GCS_LINK_CUT", CUT_S) for e in ("uav-003", "uav-004")])
            once("cut2", T_CUT2, lambda: ob.fault(GCS, "LINK_CUT", CUT_S))
            once("gw_kill", T_GW_KILL, lambda: (res.__setitem__("gw1_pid", gw.p.pid), gw.kill()))
            once("gw_up", T_GW_UP, lambda: res.__setitem__("gw2_pid", start_gw(2).p.pid))
            if "gw_up" in done and "gw2_ready_log" not in marks and (st.out / "gateway.2.log").exists():
                if "gateway: ready at" in (st.out / "gateway.2.log").read_text(encoding="utf-8", errors="replace"):
                    marks["gw2_ready_log"] = time.time()
            if "gw_up" in done and "gw2_connected" not in marks and (out / "gw2.json").exists():
                try:
                    if json.loads((out / "gw2.json").read_text(encoding="utf-8")).get("connected"):
                        marks["gw2_connected"] = time.time()
                except (ValueError, OSError):
                    pass
            # 재기동 Gateway가 LA-CAL 구독을 마친 뒤에 보낸다 (r1: 구독 전 PUB은 +OK이지만 받는 쪽이 없어 사라졌다)
            # 16차: 준비 완료 로그(O-13 대응)가 나오면 곧바로 보낸다
            ready = "gw2_ready_log" in marks or not a.wait_gw2
            once("ext2", (0.0 if ready else 1e9) if a.wait_gw2 else T_EXT2, lambda: ext_cmd("ext-hold-2", ["uav-003"], "hold"))
            once("cancel", (sim_at(clock, marks["ext2"]) + 5.0) if "ext2" in marks else 1e9,
                 lambda: ext_cmd("ext-hold-1", ["uav-001"], "hold", cancel=True))
            t_end = max(T_END, (sim_at(clock, marks["cancel"]) + 25.0) if "cancel" in marks else 1e9)
            if s >= t_end or "core" in "".join(st.dead()):
                break
        res["inject_rounds"] = inj["n"]
        res["dead_at_end"] = st.dead() + [p.name for p in extra + gw_procs[-1:] if not p.alive()]
        (ext_dir / "STOP").write_text("x", encoding="utf-8")
        time.sleep(2.5)
        res["log_issues"] = h.scan_logs(st)[:30]
        snap = ob.snapshot()  # snapshot()이 ob.lock을 잡으므로 밖에서 부른다
        with ob.lock:
            traj = {k: list(v) for k, v in ob.traj.items()}
            gcs_rx, gcs_tx, lo = list(ob.gcs_rx), list(ob.gcs_tx), list(ob.lo)
            taskstatus = {k: list(v) for k, v in ob.taskstatus.items()}
            status_hist = list(ob.status_hist)
            vi_rx = list(ob.vi_rx)
        ob.close()
    finally:
        st.down()
        p0.stop([*extra, *gw_procs])
    res["snapshot"] = snap
    res["marks"] = marks
    extj = json.loads((ext_dir / "ext.json").read_text(encoding="utf-8"))
    gwj = {g: json.loads((out / f"gw{g}.json").read_text(encoding="utf-8")) for g in (1, 2)
           if (out / f"gw{g}.json").exists()}
    probe = json.loads((out / "probe.json").read_text(encoding="utf-8")) if (out / "probe.json").exists() else {}
    import gzip
    import pickle
    with gzip.open(out / "raw.pkl.gz", "wb") as f:  # 분석 전에 원자료를 남긴다
        pickle.dump({"res": res, "traj": traj, "gcs_rx": gcs_rx, "gcs_tx": gcs_tx, "lo": lo, "taskstatus": taskstatus,
                     "status_hist": status_hist, "clock": clock, "vi_rx": vi_rx, "probe": probe}, f)
    analyse(res, extj, gwj, probe, traj, gcs_rx, gcs_tx, lo, taskstatus, status_hist, clock)
    import gw_vi
    res["summary"]["vi"] = gw_vi.analyse(res, extj, vi_rx, traj, clock, {g: (st.out / f"gateway.{g}.log")
                                                                     for g in (1, 2)})
    (out / "vi_rx.json").write_text(json.dumps(vi_rx, ensure_ascii=False), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1, default=str))


def sim_at(clock: list, epoch: float) -> float:
    for e, s in clock:
        if e >= epoch:
            return s
    return clock[-1][1] if clock else 0.0


def analyse(res, extj, gwj, probe, traj, gcs_rx, gcs_tx, lo, taskstatus, status_hist, clock) -> None:  # noqa: ANN001, C901, PLR0912, PLR0915
    S: dict = {}
    m = res["marks"]
    kill_e, start_e = m.get("gw_kill", 1e20), m.get("gw_up", 1e20)
    up_e = m.get("gw2_connected", start_e)  # 재기동 Gateway가 LA-CAL 구독을 마친 시각 (없으면 기동 시각)
    rx = extj["rx"]
    # (1) 종류별 수신, XSD
    by = Counter(r[1] for r in rx)
    ok = Counter(r[1] for r in rx if r[3])
    S["ext_rx_by_uci"] = {n: [by.get(n, 0), ok.get(n, 0), UCI_IFACE[n]] for n in UCI_IFACE}
    S["ext_rx_total"], S["ext_xsd_ok"] = len(rx), sum(ok.values())
    S["ext_xsd_fail"] = extj["xsd_fail"][:5]
    S["ext_mode"] = dict(Counter(r[5] for r in rx))
    S["ext_errors"] = extj["errors"][:5]
    S["tap"] = extj["tap"]
    # GCS rx 종류 (게이트웨이가 살아 있던 구간만 견준다)
    up = [(0, kill_e), (up_e, 1e20)]
    alive = lambda e: any(a <= e < b for a, b in up)  # noqa: E731
    gin = Counter(r[2] for r in gcs_rx)
    gin_up = Counter(r[2] for r in gcs_rx if alive(r[0]))
    S["gcs_rx_by_msg"] = dict(gin)
    S["gcs_rx_vs_ext"] = {k: {"gcs_rx_gw_up": gin_up[k], "uci": STD_UCI.get(k, "-"),
                              "ext": by.get(STD_UCI.get(k, ""), 0)} for k in sorted(gin)}
    S["gw_counters"] = {g: d["counters"] for g, d in gwj.items()}
    S["gw_rejections"] = {g: d["rejections"][:5] for g, d in gwj.items()}
    # 범위: 구독·발행·실제 수신 키
    S["gw_scope"] = {g: {"subscribe": d["subscribe"], "put": d["put"], "rx_prefix": d["rx_prefix"]}
                     for g, d in gwj.items()}
    # (2) EXT
    ext_names = ("PeerAlgorithmMessage", "Detection", "FormationCommand")
    S["ext_injected_rounds"] = res.get("inject_rounds")
    S["ext_at_gcs_rx"] = {n: gin.get(n, 0) for n in ext_names}
    S["ext_at_gw_rx"] = {g: {n: v for n, v in d["rx_keys"].items() if n.split("/")[-1] in ext_names}
                         for g, d in gwj.items()}
    tap_names = {t[0] for t in extj["tap"]}
    S["tap_non_std"] = sorted(tap_names - set(UCI_IFACE) - {"MA_TaskCommand"})
    # (3) 외부 명령 → tx → link/outcome → 기체
    S["ext_cmds"] = [{k: c.get(k) for k in ("file", "task_id", "entities", "kind", "cancel", "xsd_ok", "pub")}
                     for c in extj["cmds"]]
    S["gcs_tx"] = [{k: r.get(k) for k in ("sim_s", "key", "src", "seq", "dst", "task_id", "kind", "cancel")}
                   for r in gcs_tx]
    for r in S["gcs_tx"]:
        r["sim_s"] = round(r["sim_s"], 2)
    S["cmd_latency_s"] = []
    for c in extj["cmds"]:
        hit = [r for r in gcs_tx if r.get("task_id") == c["task_id"] and r.get("cancel") == c.get("cancel", False)]
        S["cmd_latency_s"].append(round(hit[0]["epoch"] - c["t"], 3) if hit else None)
    tc_lo = [x for x in lo if x[1] == GCS and x[3] == "TaskCommand"]
    S["taskcommand_outcomes"] = [{"sim_s": round(x[0], 2), "dst": x[2], "outcome": x[4], "reason": x[5],
                                  "seq": x[6]} for x in tc_lo]
    ext_tasks = ("ext-hold-1", "ext-rtb-1", "ext-hold-2")
    S["taskstatus_gcs"] = {e: [s for s in v if s.split(":")[0] in ext_tasks or "task-001" in s][:12]
                           for e, v in taskstatus.items() if e in MOVERS}
    ext_ts = defaultdict(list)
    for r in rx:
        if r[1] == "MA_TaskStatus" and r[6].get("task") in ext_tasks:
            st = f"{r[6]['task']}:{r[6]['state']}"
            if not ext_ts[r[6]["by"]] or ext_ts[r[6]["by"]][-1] != st:
                ext_ts[r[6]["by"]].append(st)
    S["taskstatus_ext"] = dict(ext_ts)
    # 기체 동작
    beh = {}
    home = {e: traj[e][0][1:3] for e in MOVERS if traj.get(e)}
    for e in MOVERS:
        tr = traj.get(e, [])
        if not tr:
            continue
        t2 = sim_at(clock, m["ext2"]) if "ext2" in m else T_EXT2
        t_last = tr[-1][0] / 50.0
        p30, p90, p140, p160 = (traj_at(tr, t) for t in (T_EXT, T_EXT + 60, t2, t_last - 1))
        row = {}
        if p30 and p90:
            row["east_30_90_m"] = round(pos_ne(p90, p30)[1], 0)
            w = window(tr, T_EXT + 20, min(t2, T_GW_KILL))
            row["max_from_p30_50_to_kill_m"] = round(max(math.hypot(*pos_ne(x[1:3], p30)) for x in w), 0) if w else None
            row["home_dist_30_m"] = round(math.hypot(*pos_ne(p30, home[e])), 0)
            row["home_dist_90_m"] = round(math.hypot(*pos_ne(p90, home[e])), 0)
        if p140 and p160:
            row["ext2_sim_s"], row["end_sim_s"] = round(t2, 1), round(t_last, 1)
            row["east_ext2_end_m"] = round(pos_ne(p160, p140)[1], 0)
            w = window(tr, t2 + 10, t_last)
            row["max_from_ext2pos_after10s_m"] = round(max(math.hypot(*pos_ne(x[1:3], p140)) for x in w), 0) if w else None
        beh[e] = row
    S["behaviour"] = beh
    # (4) 링크 차단 구간별 외부 수신률
    wins = {"base_50_70": (50, 70), "cut1_72_85": (T_CUT1 + 2, T_CUT1 + CUT_S), "mid_87_95": (87, 95),
            "cut2_97_110": (T_CUT2 + 2, T_CUT2 + CUT_S), "rec_112_120": (112, 120),
            "gw_down": (None, None), "after_up": (None, None)}
    rx_sim = [(sim_at(clock, r[0]), r) for r in rx]
    rate = {}
    for w, (a0, a1) in wins.items():
        if w == "after_up":
            a0, a1 = sim_at(clock, up_e) + 2.0, clock[-1][1] if clock else 0.0
        if w == "gw_down":
            ka, kb = sim_at(clock, kill_e), sim_at(clock, up_e)
            a0, a1 = ka + 0.5, kb
        dur = max(a1 - a0, 1e-6)
        sel = [r for s, r in rx_sim if a0 <= s < a1]
        c = Counter(UCI_IFACE[r[1]] for r in sel)
        gsel = [r for r in gcs_rx if a0 <= r[1] < a1]
        lsel = [x for x in lo if x[2] == GCS and a0 <= x[0] < a1]
        rate[w] = {"sim_s": [round(a0, 1), round(a1, 1)], "ext_per_s": round(len(sel) / dur, 2),
                   "ext_by_iface_per_s": {k: round(v / dur, 2) for k, v in sorted(c.items())},
                   "gcs_rx_per_s": round(len(gsel) / dur, 2),
                   "gcs_rx_sources": dict(Counter(r[3] for r in gsel)),
                   "to_gcs_outcomes": dict(Counter(x[4] + (("/" + x[5]) if x[5] else "") for x in lsel))}
    S["windows"] = rate
    # (5) Gateway 재시작: 그동안 모의 시각 진행
    ka, kb = sim_at(clock, kill_e), sim_at(clock, up_e)
    S["gw_down"] = {"wall_s": round(up_e - kill_e, 2), "restart_cmd_after_kill_s": round(start_e - kill_e, 2), "sim_progress_s": round(kb - ka, 2),
                    "gw1_pid": res.get("gw1_pid"), "gw2_pid": res.get("gw2_pid")}
    after = sorted(r[0] for r in rx if r[0] > up_e)
    if "gw2_connected" in m:
        S["gw_down"]["gw2_startup_wall_s"] = round(m["gw2_connected"] - start_e, 2)
    S["gw_down"]["first_ext_rx_after_up_s"] = round(after[0] - up_e, 2) if after else None
    S["gw_down"]["ext_rx_during_down"] = sum(1 for r in rx if kill_e + 0.5 <= r[0] < up_e)
    states = [x[1] for x in status_hist]
    S["sim_status_states"] = dict(Counter(states))
    S["strike"] = {"probe_cmds": len(probe.get("cmds", [])),
                   "acts": [{k: x.get(k) for k in ("f", "pid", "state", "reason", "weapon")} for x in probe.get("acts", [])][:6]}
    S["frames"] = {k: res["snapshot"].get(k) for k in ("last_frame", "sim_s", "gap_frames", "overruns", "findings")}
    S["dead_at_end"] = res.get("dead_at_end")
    S["log_issues"] = res.get("log_issues")
    res["summary"] = S


if __name__ == "__main__":
    try:
        main()
    finally:
        h.Stack.down_all()
