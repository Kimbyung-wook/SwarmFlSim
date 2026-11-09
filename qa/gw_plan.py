"""QA 18·19차 외부 임무 계획·승인 응답 통합 시험 (TC-QA-089~, DEC-075~077, D-29, O-23, O-26).

Logger·Datalink·Agent·Bridge·Core(realtime, 평지) + agra_lacal CAL Server + Gateway(qa/gw_wrap.py) + 외부 CAL Client.
기체 7대: uav-001·002·003·007은 waypoint MA, uav-004·005·006은 flocking_basic. 모두 동쪽 8 km move_to(task-001)로 시작한다.
uav-003·006은 어떤 계획도 받지 않는 대조 기체다. 시뮬레이터에 ApprovalRequest 발신자가 없어(DEC-075) QA가 uav → gcs로 주입한다.

시간표(모의 s)
  15  RoutePlan만: uav-001 r-a(3점)                                    TC-QA-089
  70  RoutePlan+MissionPlan: uav-002 r-w1(1점), uav-004 r-f1(1점), uav-005 r-f2(2점, flocking은 route 미지원)
 100  RoutePlan+MissionPlan: uav-001 r-w2(2점)                         TC-QA-090
 125  uav-002 r-w3, uav-004 r-f3 / 135 같은 plan_id 재전송 / 145 새 plan_id   TC-QA-091
 155  지원 범위 밖·XSD 위반 입력 / 165 유효 계획 uav-001 r-v1           TC-QA-093
 170~182 승인: 요청 주입 → APPROVED·REJECTED·모르는 요청·rx 되돌림     TC-QA-094
 184~193 UI(브리지)와 Gateway가 uav-007에 번갈아 TaskCommand          TC-QA-095
 195  GCS_LINK_CUT uav-002 15 s / 198 계획 전송 / 213 RoutePlan·MissionPlan 재전송   TC-QA-096
 222  GCS_LINK_CUT uav-001 15 s / 225 단독 RoutePlan / 240 재전송       19차
 275  종료

uv run python qa/gw_plan.py --out qa/out/gw18/r1
uv run python qa/gw_plan.py --out qa/out/gw18/order --order-trial   (D-29: RoutePlan·MissionPlan 도착 순서 대조)
uv run python qa/gw_plan.py --out qa/out/gw19/ls_order --order-trial --lockstep --rounds 4
uv run python qa/gw_plan.py --lockstep-det qa/out/gw19/det    (Gateway 없이 lockstep 2회 비교, 손실 없음·있음)
uv run --with mcap python qa/gw_plan.py --mcap qa/out/gw18/r1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
import uuid
import zlib
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as h  # noqa: E402
from gw_integ import CAL_ADMIN, CAL_URL, GCS, GW_PY, NOLOSS, ROOT, GwObserver, sim_at, wait_port  # noqa: E402
from strike_burst import M_LAT, SCN, at  # noqa: E402

p0 = h.p0
QA = Path(__file__).resolve().parent
WP = ["uav-001", "uav-002", "uav-003", "uav-007"]
FL = ["uav-004", "uav-005", "uav-006"]
ALL = sorted(WP + FL)
CONTROL = ["uav-003", "uav-006"]
BRIDGE_PORT = 48865
UI_ID = "ui-qa"
NS = uuid.UUID("9a7e2f6d-1c5b-4d0b-8f8a-5d1c6b0e7c11")
T_END = 275.0
LS_END_S = 60.0     # --lockstep-det 비교 구간


def u(s: str) -> str:
    return str(uuid.uuid5(NS, s))


def scenario(ge: dict | None = None, latency_ms: float | None = None, jitter_ms: float | None = None) -> dict:
    ents = [{"id": GCS, "kind": "gcs", "side": "blue", "dynamics": "static",
             "initial": {"position": {**at(-2000, 0), "alt_m": 30.0}}, "link_profile": "gcs_default"}]
    for i, e in enumerate(ALL):
        ma = "waypoint" if e in WP else "flocking_basic"
        ents.append({"id": e, "kind": "uav", "side": "blue", "dynamics": "dof2",
                     "initial": {"position": {**at(1000 * i, 0), "alt_m": 500.0},
                                 "velocity_ned_mps": {"x": 0.0, "y": 22.0, "z": 0.0}},
                     "payloads": [{"id": "cam0", "type": "camera", "profile": "eo_wide"}],
                     "autonomy": {"ma_plugin": ma, "ma_params": {"group": f"g{i}"} if e in FL else {}},
                     "link_profile": "uav_default", "controlling_gcs": GCS})
    lat = {} if latency_ms is None else {"latency_ms": latency_ms, "jitter_ms": jitter_ms or 0.0}
    tasks = [{"task_id": "task-001", "assignees": ALL,
              "move_to": {"destination": {**at(3000, 8000), "alt_m": 500.0}, "speed_mps": 22.0}}]
    return {"schema_version": "0.1", "name": "qa-gw-plan", "description": "QA 18차 외부 임무 계획·승인 응답",
            "map": {"origin": at(0, 0), "extent": {"south_deg": 37.4, "north_deg": 37.7, "west_deg": 127.9,
                                                   "east_deg": 128.2}},
            "run": {"mode": "realtime", "frame_hz": 50, "seed": 20261109, "rate": 1.0, "duration_s": 900.0},
            "link_profiles": [{"name": n, "ge": ge or NOLOSS, **lat} for n in ("uav_default", "gcs_default")],
            "entities": ents, "mission_plan": {"plan_id": "plan-qa18", "tasks": tasks}}


# ---- 공개 XSD 구조대로 직접 만든 외부 메시지 (Gateway 변환기를 쓰지 않는다) ----------------------------------

def segment(route: str, i: int, pt: tuple, last: bool) -> dict:
    seg: dict = {"PathSegmentID": {"UUID": u(f"{route}/seg{i}")}, "Source": "OPERATOR_DEFINED",
                 "EndPoint": {"WayPoint": {"PointChoice": {"Point2D": {
                     "Latitude": math.radians(pt[0]), "Longitude": math.radians(pt[1]), "Altitude": float(pt[2]),
                     "AltitudeReference": "MSL"}}, "WaypointType": "NAV_ONLY"}}}
    if not last:
        seg["NextPathSegment"] = {"PathSegmentID": {"UUID": u(f"{route}/seg{i + 1}")}}
    return seg


def route_data(route: str, entity: str, pts: list[tuple]) -> dict:
    path_id = u(f"{route}/path")
    segs = [segment(route, i, p, i == len(pts) - 1) for i, p in enumerate(pts)]
    return {"RoutePlanID": {"UUID": u(f"route:{route}"), "DescriptiveLabel": route},
            "Plan": {"Applicability": {"ApplicableToIDs": {"SystemID": {"UUID": u(f"sys:{entity}"),
                                                                        "DescriptiveLabel": entity}}},
                     "Parts": {"RouteType": ["PRIMARY"]},
                     "Route": {"Detailed": True, "FirstInRoutePathID": {"UUID": path_id},
                               "RouteProjection": "GREAT_CIRCLE",
                               "Path": [{"PathID": {"UUID": path_id}, "PathType": "PRIMARY",
                                         "FirstInPathSegmentID": {"UUID": u(f"{route}/seg0")}, "PathSegment": segs}]}},
            "ForPlanningUseOnly": False}


def mission_data(plan: str, entity: str, routes: list[str]) -> dict:
    return {"MissionPlanID": {"UUID": u(f"plan:{plan}"), "DescriptiveLabel": plan},
            "Applicability": {"ApplicableToIDs": {"SystemID": {"UUID": u(f"sys:{entity}"), "DescriptiveLabel": entity}}},
            "SubPlans": {"RoutePlanID": [{"UUID": u(f"route:{r}")} for r in routes]},
            "ForPlanningUseOnly": False}


def approval_data(request: str, state: str, processing: str = "COMPLETED") -> dict:
    return {"RequestID": {"UUID": u(f"req:{request}"), "DescriptiveLabel": request},
            "RequestProcessingState": processing, "ApprovalRequestProcessingState": state}


def task_cmd(system_task: str, entity: str, kind: str) -> dict:
    return {"Command": [{"Capability": {
        "CommandID": {"UUID": str(uuid.uuid4()), "DescriptiveLabel": f"{system_task}/{entity}"}, "CommandState": "NEW",
        "CapabilityID": {"UUID": str(uuid.uuid4()), "DescriptiveLabel": f"{entity}/{kind}"},
        "Ranking": {"Rank": {"Priority": 0, "PrecedenceWithinPriority": 0}},
        "TaskID": {"UUID": str(uuid.uuid4()), "DescriptiveLabel": system_task}}}]}


def bad_inputs(pos_pts: list[tuple]) -> list[tuple[str, str, str, dict]]:
    """(태그, 메시지, 토픽, MessageData). 앞 9개는 XSD는 통과하지만 지원 범위 밖, 뒤 3개는 XSD 위반"""
    base = lambda: route_data("r-bad", "uav-001", pos_pts)  # noqa: E731
    out: list[tuple[str, str, str, dict]] = []
    d = base(); d["Plan"]["Applicability"]["ApplicableToIDs"] = {"ALL": ""}
    out.append(("route_all", "MA_RoutePlan", "swarm.mp", d))
    d = base(); d["Plan"]["Applicability"]["ApplicableToIDs"] = {"PackageID": {"UUID": u("pkg")}}
    out.append(("route_package", "MA_RoutePlan", "swarm.mp", d))
    d = base(); d["ForPlanningUseOnly"] = True
    out.append(("route_planning_only", "MA_RoutePlan", "swarm.mp", d))
    d = base(); d["Plan"]["Route"]["Path"][0]["PathSegment"][1]["NextPathSegment"] = {
        "PathSegmentID": {"UUID": u("r-bad/seg0")}}
    out.append(("route_cycle", "MA_RoutePlan", "swarm.mp", d))
    d = base(); d["Plan"]["Window"] = {"Begin": "2026-11-09T00:00:00Z"}
    out.append(("route_window", "MA_RoutePlan", "swarm.mp", d))
    d = mission_data("plan-bad", "uav-001", ["r-a"]); d["SubPlans"]["TaskPlanID"] = [{"UUID": u("taskplan")}]
    out.append(("mission_taskplan", "MA_MissionPlan", "swarm.mp", d))
    out.append(("mission_unknown_route", "MA_MissionPlan", "swarm.mp", mission_data("plan-bad2", "uav-001", ["r-none"])))
    out.append(("mission_other_vehicle", "MA_MissionPlan", "swarm.mp", mission_data("plan-bad3", "uav-002", ["r-a"])))
    out.append(("approval_pending", "MA_ApprovalRequestStatus", "swarm.c2", approval_data("apr-p", "PENDING")))
    out.append(("xsd_route_missing", "MA_RoutePlan", "swarm.mp", {"RoutePlanID": {"UUID": u("x1")}}))
    out.append(("xsd_mission_baduuid", "MA_MissionPlan", "swarm.mp",
                {"MissionPlanID": {"UUID": "not-a-uuid"}, "ForPlanningUseOnly": False}))
    out.append(("xsd_approval_enum", "MA_ApprovalRequestStatus", "swarm.c2",
                {"RequestID": {"UUID": u("x3")}, "RequestProcessingState": "DONE",
                 "ApprovalRequestProcessingState": "APPROVED"}))
    return out


class PlanObserver(GwObserver):
    def __init__(self, endpoints: list[str]) -> None:
        super().__init__(endpoints)
        from swarm.v1 import c2_pb2, mp_pb2
        self.c2, self.mp = c2_pb2, mp_pb2
        self.tx: list[dict] = []
        self.rx: list[dict] = []
        self.ts: list[tuple] = []
        self.all_lo: list[tuple] = []      # (tx_us, rx_us, src, dst, msg, outcome, seq)
        self.gcs_hdr: list[tuple] = []     # GCS 수신 (source, msg, seq, hdr_us, crc)
        self.subs.append(self.bus.subscribe(f"swarm/{GCS}/tx/**", self._ptx))
        for pat in ("swarm/*/rx/mp/*", "swarm/*/rx/c2/*"):
            self.subs.append(self.bus.subscribe(pat, self._prx))

    def _detail(self, env) -> dict:  # noqa: ANN001
        name = env.msg_type.rsplit(".", 1)[-1]
        row: dict = {"msg": name, "publisher": env.publisher, "seq": env.header.seq, "dst": list(env.dst),
                     "source": env.header.source}
        if name == "RoutePlan":
            m = self.mp.RoutePlan.FromString(env.payload)
            row |= {"id": m.route_id, "n": len(m.waypoints), "entity": m.entity_id}
        elif name == "MissionPlan":
            m = self.mp.MissionPlan.FromString(env.payload)
            row |= {"id": m.plan_id, "tasks": [(t.task_id, t.WhichOneof("task")) for t in m.tasks]}
        elif name == "TaskCommand":
            m = self.c2.TaskCommand.FromString(env.payload)
            row |= {"id": m.task_id, "kind": m.WhichOneof("task") or "", "cancel": m.cancel}
        elif name == "ApprovalResponse":
            m = self.c2.ApprovalResponse.FromString(env.payload)
            row |= {"id": m.request_id, "approved": m.approved}
        return row

    def _ptx(self, s) -> None:  # noqa: ANN001
        env = self.m[2].LinkEnvelope.FromString(s.payload)
        row = {"sim_s": round(self.sim_s(), 2), "key": s.key, **self._detail(env)}
        with self.lock:
            self.tx.append(row)

    def _prx(self, s) -> None:  # noqa: ANN001
        env = self.m[2].LinkEnvelope.FromString(s.payload)
        if env.header.source != GCS:
            return
        row = {"sim_s": round(self.sim_s(), 2), "to": s.key.split("/")[1], "key": s.key, **self._detail(env)}
        with self.lock:
            self.rx.append(row)

    def _outcome(self, s) -> None:  # noqa: ANN001
        super()._outcome(s)
        link = self.m[2]
        o = link.LinkOutcome.FromString(s.payload)
        with self.lock:
            self.all_lo.append((o.tx_time_us, o.rx_time_us, o.src, o.dst, o.msg_type.rsplit(".", 1)[-1],
                                link.LinkOutcomeKind.Name(o.outcome).removeprefix("LINK_OUTCOME_KIND_"), o.seq))

    def _rx(self, s) -> None:  # noqa: ANN001
        super()._rx(s)
        env = self.m[2].LinkEnvelope.FromString(s.payload)
        with self.lock:
            self.gcs_hdr.append((env.header.source, env.msg_type.rsplit(".", 1)[-1], env.header.seq,
                                 env.header.sim_time_us, zlib.crc32(env.payload)))
        if env.msg_type == "swarm.v1.TaskStatus":
            st = self.c2.TaskStatus.FromString(env.payload)
            with self.lock:
                self.ts.append((round(self.sim_s(), 2), env.header.source, st.task_id,
                                self.m[4].CommandState.Name(st.state).removeprefix("COMMAND_STATE_"), st.reason))


async def ui_send(frames: list[tuple[str, str, bytes]]) -> str:
    from swarm_bridge.frame import encode_frame
    from websockets.asyncio.client import connect
    async with connect(f"ws://127.0.0.1:{BRIDGE_PORT}/bus", max_size=2**24) as ws:
        await ws.send(json.dumps({"op": "hello", "client": UI_ID, "role": "control", "gcs": GCS}))
        hello = await asyncio.wait_for(ws.recv(), 5)
        for k, e, b in frames:
            await ws.send(encode_frame(k, e, b))
        await asyncio.sleep(0.3)
        return str(hello)[:120]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--base-port", type=int, default=48800)
    ap.add_argument("--order-trial", action="store_true", help="간격 0 / 2 s로 RoutePlan·MissionPlan을 보내 작업 완료를 대조한다")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--lockstep", action="store_true", help="Gateway·외부 입력을 둔 채 lockstep(rate 1)으로 돌린다")
    ap.add_argument("--lockstep-det", help="Gateway 없이 lockstep 같은 시드 반복 비교 (결과 폴더)")
    ap.add_argument("--det-runs", type=int, default=2)
    ap.add_argument("--mcap", help="결과 폴더의 rec.mcap에서 publisher를 집계한다 (uv run --with mcap)")
    a = ap.parse_args()
    if a.mcap:
        mcap_check(Path(a.mcap))
        return
    if a.lockstep_det:
        lockstep_det(ROOT / a.lockstep_det, a.base_port, a.det_runs)
        return
    out = (ROOT / a.out) if not Path(a.out).is_absolute() else Path(a.out)
    ext_dir = out / "ext"
    (ext_dir / "cmd").mkdir(parents=True, exist_ok=True)
    for f in [*ext_dir.glob("cmd/*.json"), ext_dir / "STOP", ext_dir / "ext.ready", ext_dir / "ext.json"]:
        f.unlink(missing_ok=True)
    sp = SCN / "qa_gw_plan.json"
    sp.write_text(json.dumps(scenario(), ensure_ascii=False, indent=1), encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    st = h.Stack(out / "stack", sp, base_port=a.base_port, lockstep=a.lockstep, rate=1.0, record=True, bridge=True,
                 bridge_port=BRIDGE_PORT, core_extra=["--terrain-flat", "0"])
    n = [0]
    extra: list = []
    clock: list[tuple[float, float]] = []
    events: list[dict] = []        # 계획 전송 기록
    ui_seq = Counter()
    res: dict = {}

    def send(tag: str, name: str, topic: str, data: dict) -> None:
        n[0] += 1
        f = ext_dir / "cmd" / f"{n[0]:03d}"
        f.with_suffix(".tmp").write_text(json.dumps({"raw": name, "topic": topic, "data": data, "tag": tag}),
                                         encoding="utf-8")
        f.with_suffix(".tmp").replace(f.with_suffix(".json"))

    try:
        cal = p0.Proc("calsrv", [str(GW_PY), "-m", "swarm_gateway.lacal_server", "--config",
                                 str(QA / "scenarios" / "gw_lacal_server.yaml")], st.out, cwd=ROOT / "gateway")
        extra.append(cal)
        assert wait_port(18765), "CAL Server 기동 실패"
        st.start_one("logger")
        st.start_one("datalink")
        st.start_one("agent")
        st.start_one("bridge")
        os.environ["GW_PROBE_OUT"] = str(out / "gw1.json")
        extra.append(p0.Proc("gateway.1", [str(GW_PY), str(QA / "gw_wrap.py"), "--gcs", GCS, "--lacal", CAL_URL,
                                           "--no-multicast", "--connect", st.endpoint(), "--listen",
                                           f"tcp/127.0.0.1:{a.base_port + 31}", "--stats-s", "10"], st.out, cwd=ROOT))
        extra.append(p0.Proc("ext", [str(GW_PY), str(QA / "gw_ext_client.py"), "--url", CAL_URL, "--admin", CAL_ADMIN,
                                     "--out", str(ext_dir)], st.out, cwd=ROOT))
        end = time.monotonic() + 40
        while not (ext_dir / "ext.ready").exists() and time.monotonic() < end:
            time.sleep(0.2)
        assert (ext_dir / "ext.ready").exists(), "외부 클라이언트 준비 실패"
        end = time.monotonic() + 40
        while "gateway: ready at" not in (st.out / "gateway.1.log").read_text(encoding="utf-8", errors="replace"):
            assert time.monotonic() < end, "Gateway 준비 실패"
            time.sleep(0.2)
        time.sleep(st.settle)
        ob = PlanObserver([st.endpoint()])
        time.sleep(1.0)
        st.start_one("core")
        from swarm.v1 import c2_pb2, link_pb2, options_pb2

        def offs(e: str, rel: list[tuple[float, float]]) -> list[tuple]:
            p = ob.pos[e]
            return [(p[0] + dn / M_LAT, p[1] + de / (M_LAT * math.cos(math.radians(p[0]))), 500.0) for dn, de in rel]

        def plan(entity: str, route: str, plan_id: str | None, rel: list[tuple[float, float]], label: str) -> None:
            pts = offs(entity, rel)
            send(f"route:{route}", "MA_RoutePlan", "swarm.mp", route_data(route, entity, pts))
            if plan_id:
                send(f"plan:{plan_id}", "MA_MissionPlan", "swarm.mp", mission_data(plan_id, entity, [route]))
            events.append({"sim_s": round(ob.sim_s(), 2), "entity": entity, "route": route, "plan": plan_id,
                           "label": label, "pts": pts})

        def resend(entity: str, plan_id: str, route: str, label: str) -> None:
            send(f"plan:{plan_id}", "MA_MissionPlan", "swarm.mp", mission_data(plan_id, entity, [route]))
            events.append({"sim_s": round(ob.sim_s(), 2), "entity": entity, "route": route, "plan": plan_id,
                           "label": label, "resend": True})

        def replan(entity: str, route: str, plan_id: str | None, label: str) -> None:
            ev = next(x for x in events if x["route"] == route and "pts" in x)
            send(f"route:{route}", "MA_RoutePlan", "swarm.mp", route_data(route, entity, ev["pts"]))
            if plan_id:
                send(f"plan:{plan_id}", "MA_MissionPlan", "swarm.mp", mission_data(plan_id, entity, [route]))
            events.append({"sim_s": round(ob.sim_s(), 2), "entity": entity, "route": route, "plan": plan_id,
                           "label": label, "resend": True})

        def approve_inject(src: str, req: str) -> None:
            ob.put_ext(src, "c2", c2_pb2.ApprovalRequest(request_id=req, task_id="task-001", description="qa"), [GCS])

        def ui_task(task_id: str, kind: str, entity: str = "uav-007") -> None:
            key = f"swarm/{GCS}/tx/c2/TaskCommand"
            ui_seq[key] += 1
            t = c2_pb2.TaskCommand(task_id=task_id, assignees=[entity])
            getattr(t, kind).SetInParent()
            t.header.source, t.header.seq = GCS, ui_seq[key]
            env = link_pb2.LinkEnvelope(dst=[entity], iface=options_pb2.L1_INTERFACE_C2, publisher=UI_ID,
                                        msg_type="swarm.v1.TaskCommand", payload=t.SerializeToString(), priority=0)
            env.header.source, env.header.seq = GCS, ui_seq[key]
            res.setdefault("ui_hello", asyncio.run(ui_send([(key, h.CT + "LinkEnvelope", env.SerializeToString())])))

        bad_sent = [False]

        def bad() -> None:
            p = ob.pos["uav-001"]
            pts = [(p[0] + 0.002, p[1], 500.0), (p[0] + 0.004, p[1], 500.0)]
            for tag, name, topic, data in bad_inputs(pts):
                send(tag, name, topic, data)
            bad_sent[0] = True

        schedule = [
            (15, "r-a", lambda: plan("uav-001", "r-a", None, [(400, 500), (800, 200), (400, -200)], "route_only")),
            (70, "w1", lambda: plan("uav-002", "r-w1", "plan-w1", [(300, 600)], "wp_move_to")),
            (70.5, "f1", lambda: plan("uav-004", "r-f1", "plan-f1", [(300, 800)], "fl_move_to")),
            (71, "f2", lambda: plan("uav-005", "r-f2", "plan-f2", [(300, 800), (600, 1200)], "fl_route")),
            (100, "w2", lambda: plan("uav-001", "r-w2", "plan-w2", [(400, 500), (800, 200)], "wp_route")),
            (125, "w3", lambda: plan("uav-002", "r-w3", "plan-w3", [(0, 3000), (0, 6000)], "wp_long")),
            (125.5, "f3", lambda: plan("uav-004", "r-f3", "plan-f3", [(0, 5000)], "fl_long")),
            (135, "w3r", lambda: resend("uav-002", "plan-w3", "r-w3", "wp_dup")),
            (135.5, "f3r", lambda: resend("uav-004", "plan-f3", "r-f3", "fl_dup")),
            (145, "w4", lambda: plan("uav-002", "r-w4", "plan-w4", [(1000, 2000), (2000, 2000)], "wp_new")),
            (145.5, "f4", lambda: plan("uav-004", "r-f4", "plan-f4", [(1000, 3000)], "fl_new")),
            (155, "bad", bad),
            (165, "v1", lambda: plan("uav-001", "r-v1", "plan-v1", [(300, 300)], "after_reject")),
            (170, "ap1i", lambda: approve_inject("uav-003", "apr-1")),
            (172, "ap1", lambda: send("apr-1", "MA_ApprovalRequestStatus", "swarm.c2", approval_data("apr-1", "APPROVED"))),
            (175, "ap2i", lambda: approve_inject("uav-006", "apr-2")),
            (177, "ap2", lambda: send("apr-2", "MA_ApprovalRequestStatus", "swarm.c2", approval_data("apr-2", "REJECTED"))),
            (180, "ap3", lambda: send("apr-x", "MA_ApprovalRequestStatus", "swarm.c2", approval_data("apr-x", "APPROVED"))),
            (182, "echo", lambda: ob.put_ext("uav-003", "c2", c2_pb2.ApprovalResponse(request_id="apr-echo", approved=True),
                                             [GCS])),
            (184, "ui1", lambda: ui_task("ui-qa-1", "hold")),
            (187, "g1", lambda: send("gw-t1", "MA_TaskCommand", "swarm.c2", task_cmd("gw-t1", "uav-007", "hold"))),
            (190, "ui2", lambda: ui_task("ui-qa-2", "return_to_base")),
            (193, "g2", lambda: send("gw-t2", "MA_TaskCommand", "swarm.c2", task_cmd("gw-t2", "uav-007", "hold"))),
            (195, "cut", lambda: ob.fault("uav-002", "GCS_LINK_CUT", 15.0)),
            (198, "c1", lambda: plan("uav-002", "r-c1", "plan-c1", [(-1000, 3000)], "during_cut")),
            (213, "c1r", lambda: replan("uav-002", "r-c1", "plan-c1", "after_cut")),
            (222, "cut2", lambda: ob.fault("uav-001", "GCS_LINK_CUT", 15.0)),
            (225, "c2", lambda: plan("uav-001", "r-c2", None, [(1200, 600), (1200, 1500)], "solo_during_cut")),
            (240, "c2r", lambda: replan("uav-001", "r-c2", None, "solo_after_cut")),
        ]
        t_end = T_END
        if a.order_trial:
            # 라운드마다 4개 조건(간격 0·2 s × 항로점 1·2개)을 waypoint 4대에 돌려 가며 배정한다
            schedule, t_end = [], 20.0 + 40.0 * a.rounds + 5.0
            vehicles = ["uav-001", "uav-002", "uav-003", "uav-007"]
            conds = [("gap0", 1), ("gap0", 2), ("gap2", 1), ("gap2", 2)]
            for k in range(a.rounds):
                t = 20.0 + 40.0 * k
                for j, e in enumerate(vehicles):
                    gap, wps = conds[(j + k) % 4]
                    r, pl, rel = f"r-z{k}-{e}", f"p-z{k}-{e}", [(200.0, 250.0), (400.0, 0.0)][:wps]
                    lab = f"{gap}_{wps}"
                    if gap == "gap0":
                        schedule.append((t, r, (lambda e=e, r=r, pl=pl, rel=rel, lab=lab: plan(e, r, pl, rel, lab))))
                    else:
                        schedule.append((t, r, (lambda e=e, r=r, rel=rel, lab=lab: plan(e, r, None, rel, lab))))
                        schedule.append((t + 2.0, pl, (lambda e=e, r=r, pl=pl: resend(e, pl, r, "gap2_plan"))))
        done: set[str] = set()
        marks: dict[str, float] = {}
        t0 = time.monotonic()
        while time.monotonic() - t0 < t_end + 90:
            time.sleep(0.05)
            s = ob.sim_s()
            clock.append((time.time(), s))
            for t, tag, fn in schedule:
                if tag not in done and s >= t:
                    done.add(tag)
                    marks[tag] = round(s, 2)
                    fn()
            if s >= t_end or "core" in "".join(st.dead()):
                break
        res["wall_over"] = round(time.monotonic() - t0 - ob.sim_s(), 1)
        res["dead_at_end"] = st.dead() + [p.name for p in extra if not p.alive()]
        (ext_dir / "STOP").write_text("x", encoding="utf-8")
        time.sleep(2.5)
        res["log_issues"] = h.scan_logs(st)[:30]
        snap = ob.snapshot()
        with ob.lock:
            raw = {"all_lo": list(ob.all_lo), "tx": list(ob.tx), "rx": list(ob.rx), "ts": list(ob.ts), "traj": {k: list(v) for k, v in ob.traj.items()},
                   "lo": list(ob.lo), "gcs_rx": list(ob.gcs_rx), "clock": clock, "events": events, "marks": marks}
        ob.close()
    finally:
        st.down()
        p0.stop(extra)
    import gzip
    import pickle
    with gzip.open(out / "raw.pkl.gz", "wb") as f:
        pickle.dump(raw, f)
    res["snapshot"] = snap
    summary = analyse(res, raw, json.loads((ext_dir / "ext.json").read_text(encoding="utf-8")),
                      json.loads((out / "gw1.json").read_text(encoding="utf-8")))
    (out / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, default=str))


def lat_stats(rows: list[float]) -> dict:
    if not rows:
        return {"n": 0}
    v = sorted(rows)
    return {"n": len(v), "min": round(v[0], 1), "p50": round(v[len(v) // 2], 1), "p95": round(v[int(len(v) * 0.95)], 1),
            "max": round(v[-1], 1)}


def link_timing(lo: list[tuple]) -> dict:
    """프레임 0 송신과 이후 프레임의 지연(ms), 지상 발행자 지연을 요약한다"""
    ok = [x for x in lo if x[5] == "DELIVERED"]
    out: dict = {}
    for msg in ("FlightCapability", "NavigationReport", "SystemStatus", "TaskStatus"):
        f0 = [(x[1] - x[0]) / 1000 for x in ok if x[4] == msg and x[0] == 0]
        rest = [(x[1] - x[0]) / 1000 for x in ok if x[4] == msg and x[0] > 0]
        out[msg] = {"frame0": lat_stats(f0), "later": lat_stats(rest)}
    out["frame0_tx_total"] = sum(1 for x in lo if x[0] == 0)
    out["frame0_undelivered"] = sum(1 for x in lo if x[0] == 0 and x[5] != "DELIVERED")
    gr = [x for x in ok if x[2] == GCS and x[4] in ("RoutePlan", "MissionPlan", "ApprovalResponse", "TaskCommand")]
    out["ground_delay_ms"] = lat_stats([(x[1] - x[0]) / 1000 for x in gr])
    out["ground_tx_zero"] = sum(1 for x in gr if x[0] == 0)
    return out


def diff_sets(a: list[tuple], b: list[tuple]) -> dict:
    """두 실행의 기록 차이를 (메시지, 발신, 시각) 단위로 요약한다"""
    ca, cb = Counter(a), Counter(b)
    only_a, only_b = list((ca - cb).elements()), list((cb - ca).elements())
    return {"n_only_a": len(only_a), "n_only_b": len(only_b), "only_a": sorted(only_a)[:6], "only_b": sorted(only_b)[:6]}


def frame0_tx(lo: list[tuple]) -> dict:
    c: Counter = Counter()
    for x in lo:
        if x[0] == 0:
            c[x[4]] += 1
    return dict(sorted(c.items()))


def lockstep_det(base: Path, base_port: int, n_runs: int = 2) -> None:
    """Gateway 없이 lockstep(rate 0) 같은 시드 2회: truth·LinkOutcome·GCS 수신을 비교한다"""
    variants = {"noloss": scenario(),
                "loss": scenario({"p_gb": 0.05, "p_bg": 0.3, "loss_good": 0.0, "loss_bad": 0.5}, 30.0, 8.0)}
    report: dict = {}
    for var, sc in variants.items():
        sp = SCN / f"qa_gw_plan_ls_{var}.json"
        sp.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")
        runs = []
        for run in range(1, n_runs + 1):
            out = base / var / f"run{run}"
            st = h.Stack(out, sp, base_port=base_port, lockstep=True, rate=0.0, record=False,
                         core_extra=["--terrain-flat", "0"])
            try:
                st.start_one("datalink")
                st.start_one("agent")
                time.sleep(st.settle)
                ob = PlanObserver([st.endpoint()])
                time.sleep(1.0)
                st.start_one("core")
                t0 = time.monotonic()
                while ob.sim_s() < LS_END_S + 1.0 and time.monotonic() - t0 < 240 and not st.dead():
                    time.sleep(0.1)
                snap, dead = ob.snapshot(), st.dead()
                issues = h.scan_logs(st)[:10]
                with ob.lock:
                    data = (list(ob.all_lo), list(ob.gcs_hdr), {k: list(v) for k, v in ob.traj.items()}, list(ob.ts))
                ob.close()
            finally:
                st.down()
            lim_us, lim_fr = int(LS_END_S * 1e6), int(LS_END_S * 50)
            lo = sorted(x for x in data[0] if x[0] < lim_us)
            hdr = sorted(x for x in data[1] if x[3] < lim_us)
            traj = {k: [x for x in v if x[0] <= lim_fr] for k, v in data[2].items()}
            first = defaultdict(list)
            for _t, src, task, state, _r in data[3]:
                if task == "task-001":
                    first[src].append(state)
            runs.append({"lo": lo, "hdr": hdr, "traj": traj,
                         "info": {"frames": snap["last_frame"], "gap": snap["gap_frames"], "dead": dead, "issues": issues,
                                  "lo": len(lo), "hdr": len(hdr), "traj_frames": {k: len(v) for k, v in traj.items()},
                                  "timing": link_timing(lo), "frame0_tx": frame0_tx(lo),
                                  "task001": {e: first[e] for e in sorted(first)}}})
        a = runs[0]
        pairs = {}
        for i, b in enumerate(runs[1:], 2):
            c: dict = {"lo_same": a["lo"] == b["lo"], "hdr_same": a["hdr"] == b["hdr"], "traj_same": a["traj"] == b["traj"]}
            if not c["lo_same"]:
                c["lo_diff"] = diff_sets(a["lo"], b["lo"])
            if not c["hdr_same"]:
                c["hdr_diff"] = diff_sets(a["hdr"], b["hdr"])
            if not c["traj_same"]:
                c["traj_first_diff"] = next(((k, x, y) for k in sorted(a["traj"])
                                             for x, y in zip(a["traj"][k], b["traj"][k]) if x != y), None)
            pairs[f"1v{i}"] = c
        report[var] = {"compare": pairs, "runs": [r["info"] for r in runs]}
    base.mkdir(parents=True, exist_ok=True)
    (base / "det.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, default=str))


def dist(a: tuple, b: tuple) -> float:
    return math.hypot((a[0] - b[0]) * M_LAT, (a[1] - b[1]) * M_LAT * math.cos(math.radians(a[0])))


def analyse(res: dict, raw: dict, ext: dict, gw: dict) -> dict:  # noqa: C901, PLR0912, PLR0915
    S: dict = {"run": {k: res.get(k) for k in ("wall_over", "dead_at_end", "log_issues", "ui_hello")},
               "frames": {k: res["snapshot"].get(k) for k in ("last_frame", "sim_s", "gap_frames", "overruns", "findings")}}
    clock = raw["clock"]
    # 외부 수신 요약
    by, ok = Counter(), Counter()
    for r in ext["rx"]:
        by[r[1]] += 1
        ok[r[1]] += bool(r[3])
    S["ext_rx"] = {k: [by[k], ok[k]] for k in sorted(by)}
    S["ext_xsd_fail"] = ext["xsd_fail"][:5]
    S["ext_errors"] = ext["errors"][:5]
    S["tap"] = ext["tap"]
    S["gw_counters"] = {k: v for k, v in gw["counters"].items() if not k.startswith("exported.")}
    S["gw_rejections"] = gw["rejections"]
    S["gw_scope"] = {"subscribe": gw["subscribe"], "put": gw["put"], "rx_prefix": gw["rx_prefix"]}
    # 외부 전송 결과
    S["ext_cmds"] = [{k: c.get(k) for k in ("tag", "name", "xsd_ok", "pub", "xsd_err")} for c in ext["cmds"]]
    # 계획별 경로
    lo_tx = [x for x in raw["lo"] if x[1] == GCS and x[3] in ("RoutePlan", "MissionPlan", "ApprovalResponse", "TaskCommand")]
    S["outcomes"] = [{"t": round(x[0], 2), "dst": x[2], "msg": x[3], "o": x[4], "r": x[5], "seq": x[6]} for x in lo_tx]
    S["tx"] = raw["tx"]
    S["rx"] = raw["rx"]
    ts = defaultdict(list)
    for t, src, task, state, reason in raw["ts"]:
        ts[f"{src}/{task}"].append((t, state + (f"({reason})" if reason else "")))
    S["task_status_gcs"] = dict(sorted(ts.items()))
    ext_ts = defaultdict(list)
    for r in ext["rx"]:
        if r[1] == "MA_TaskStatus":
            k = f"{r[6].get('by')}/{r[6].get('task')}"
            ext_ts[k].append((round(sim_at(clock, r[0]), 2), r[6].get("state")))
    S["task_status_ext"] = dict(sorted(ext_ts.items()))
    # 항로점 도달 거리
    tr = {e: [(fr / 50.0, la, lo, al) for fr, la, lo, al in v] for e, v in raw["traj"].items()}
    plans = []
    for i, ev in enumerate(raw["events"]):
        if ev.get("resend"):
            plans.append({k: ev[k] for k in ("sim_s", "entity", "route", "plan", "label")})
            continue
        later = [x["sim_s"] for x in raw["events"][i + 1:] if x["entity"] == ev["entity"] and x["route"] != ev["route"]]
        t1 = later[0] if later else 1e9
        win = [x for x in tr.get(ev["entity"], []) if ev["sim_s"] <= x[0] < t1]
        rows, tprev = [], ev["sim_s"]
        for pt in ev["pts"]:
            cand = [(dist(x[1:3], pt), x[0]) for x in win if x[0] >= tprev]
            d, t = min(cand) if cand else (None, None)
            rows.append({"min_m": round(d, 1) if d is not None else None, "t": round(t, 2) if t is not None else None})
            tprev = t if t is not None else tprev
        plans.append({k: ev[k] for k in ("sim_s", "entity", "route", "plan", "label")} | {"wp": rows, "until": t1})
    S["plans"] = plans
    # 대조 기체
    ctrl = {}
    for e in CONTROL:
        v = tr.get(e, [])
        if v:
            p0_, p1_ = v[0], v[-1]
            ctrl[e] = {"east_m": round((p1_[2] - p0_[2]) * M_LAT * math.cos(math.radians(p0_[1])), 0),
                       "north_m": round((p1_[1] - p0_[1]) * M_LAT, 0), "t_end": p1_[0],
                       "rx_mp": sum(1 for r in raw["rx"] if r["to"] == e and "/mp/" in r["key"]),
                       "rx_c2_gcs": sum(1 for r in raw["rx"] if r["to"] == e and "/c2/" in r["key"]),
                       "task_ids": sorted({k.split("/")[1] for k in ts if k.startswith(e + "/")})}
    S["control"] = ctrl
    S["marks"] = raw["marks"]
    S["link_timing"] = link_timing(raw["all_lo"])
    trials = []
    idx = {(r["msg"], r.get("id")): i for i, r in reversed(list(enumerate(raw["rx"])))}
    for ev in raw["events"]:
        if not ev["label"].startswith("gap") or ev.get("resend"):
            continue
        r, pl = ev["route"], ev["route"].replace("r-z", "p-z")
        ir, im = idx.get(("RoutePlan", r)), idx.get(("MissionPlan", pl))
        states = [x[1] for x in ts.get(f"{ev['entity']}/{r}", [])]
        trials.append({"route": r, "gap": ev["label"], "order": None if ir is None or im is None else
                       ("route_first" if ir < im else "mission_first"),
                       "dt_ms": None if ir is None or im is None else
                       round((raw["rx"][im]["sim_s"] - raw["rx"][ir]["sim_s"]) * 1000),
                       "states": states, "min_m": next(([w["min_m"] for w in p["wp"]] for p in plans
                                                        if p["route"] == r and "wp" in p), None)})
    if trials:
        S["trials"] = trials
    return S


def mcap_check(d: Path) -> None:
    from mcap.reader import make_reader

    from swarm.v1 import link_pb2
    keys = ("TaskCommand", "ApprovalResponse", "RoutePlan", "MissionPlan")
    tab: Counter = Counter()
    seqs = defaultdict(list)
    with open(d / "stack" / "rec.mcap", "rb") as f:
        for _schema, ch, msg in make_reader(f).iter_messages():
            t = ch.topic
            if not (t.startswith(f"swarm/{GCS}/tx/") or "/rx/" in t) or t.rsplit("/", 1)[-1] not in keys:
                continue
            env = link_pb2.LinkEnvelope.FromString(msg.data)
            side = "tx" if "/tx/" in t else "rx"
            tab[(side, t.rsplit("/", 1)[-1], env.publisher)] += 1
            if t == f"swarm/{GCS}/tx/c2/TaskCommand":
                seqs[env.publisher].append(env.header.seq)
    out = {"counts": sorted([[*k, v] for k, v in tab.items()]), "taskcommand_tx_seq": dict(seqs)}
    (d / "mcap.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    finally:
        h.Stack.down_all()
