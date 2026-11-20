"""원자료(harness_run.py 결과 폴더와 정적 수집) → judges.py 입력. 판정 논리는 judges.py에 있고 여기는 짝짓기·추출만 한다."""
from __future__ import annotations

import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import judges as J
import mcap_lite
import static
from confcommon import LACAL_CFG, ROOT, read_json

NEED_APPROVAL = {("uav-001", "ap-yes"), ("uav-002", "ap-no"), ("uav-003", "ap-to"), ("uav-004", "task-001")}
EXT_TO_BUS = {"MA_TaskCommand": "TaskCommand", "MA_ApprovalRequestStatus": "ApprovalResponse",
              "MA_RoutePlan": "RoutePlan", "MA_MissionPlan": "MissionPlan"}
GW_SERVICE = "swarm_gateway"


def label(o) -> str:  # noqa: ANN001
    return o.get("DescriptiveLabel", "") if isinstance(o, dict) else ""


def parse_ts(s: str) -> float | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except (ValueError, TypeError):
        try:
            return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
        except (ValueError, TypeError):
            return None


def load_full(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass        # 끝이 잘린 줄
    return rows


# ------------------------------------------------------------------------------------------------- 실행 자료 읽기

class Run:
    def __init__(self, d: Path) -> None:
        self.d = d
        self.ext = read_json(d / "ext" / "ext.json", default={}) or {}
        self.full = load_full(d / "ext" / "full.jsonl")
        self.obs = read_json(d / "obs.json", default={}) or {}
        self.marks = read_json(d / "marks.json", default={}) or {}
        self.gw = read_json(d / "gw1.json", default={}) or {}
        self.agent = read_json(d / "agent_probe.json", default={}) or {}
        self.graph = read_json(d / "graph.json", default={}) or {}
        self.cfg_text = (d / "lacal_server.yaml").read_text(encoding="utf-8") if (d / "lacal_server.yaml").exists() \
            else LACAL_CFG.read_text(encoding="utf-8")
        self.scenario = read_json(d / "scenario.json", default={}) or {}
        self.rx = [r for r in self.full if r["k"] == "rx"]
        self.tx = [r for r in self.full if r["k"] == "tx"]
        self.events = self.marks.get("events", [])
        # 벽시계 → 모의 시각: 관측기 이벤트(epoch, sim_s)로 구간 보간 대신 가장 가까운 앞 이벤트 기준
        self.bus_in = self.obs.get("bus_in", [])

    def vehicles(self) -> list[str]:
        return [e["id"] for e in self.scenario.get("entities", []) if e.get("autonomy")]


# ------------------------------------------------------------------------------------------------- C2

def c2_inputs(r: Run) -> tuple[list, list, list]:
    rx = [{"client": "ext", "name": x[1], "ok": x[3]} for x in r.ext.get("rx", [])]
    sent = []
    for c in r.ext.get("cmds", []):
        name = c.get("name") or "MA_TaskCommand"
        tag = c.get("tag") or f"{c.get('task_id', '')} {c.get('kind', '')}{' cancel' if c.get('cancel') else ''}".strip()
        neg = str(tag).startswith("neg-") or str(c.get("task_id", "")).startswith("neg-")
        sent.append({"tag": tag, "name": name, "xsd_ok": c.get("xsd_ok"), "pub": c.get("pub"), "negative": neg})
    negs = []
    for e in r.events:
        if not e["tag"].startswith("neg "):
            continue
        pub = str(e.get("pub"))
        how = ""
        if not pub.startswith("+OK"):
            how = f"CAL Server 거부: {pub[:120]}"
        elif e.get("gw_rej_new"):
            how = "Gateway 거부: " + " / ".join(e["gw_rej_new"])[:200]
        negs.append({"tag": e["tag"][4:], "why": e.get("why", ""), "on_bus": bool(e.get("bus")),
                     "bus_key": "; ".join(f"{b['key']} id={b.get('id')} dst={b.get('dst')}" for b in e.get("bus", [])),
                     "how": how, "client_xsd_ok": e.get("xsd_ok"), "pub": pub[:160]})
    return rx, sent, negs


# ------------------------------------------------------------------------------------------------- C3

def _uci_pos(body: dict) -> dict:
    md = body.get("MessageData", {})
    ins = md.get("InertialState", {})
    p = ins.get("Position", {})
    v = ins.get("DomainVelocity")
    o = ins.get("Orientation")
    return {"lat": p.get("Latitude", math.nan), "lon": p.get("Longitude", math.nan), "alt": p.get("Altitude", math.nan),
            "ref": p.get("AltitudeReference"), "ts": p.get("Timestamp", ""),
            "vel": (v["NorthSpeed"], v["EastSpeed"], v["DownSpeed"]) if v else None,
            "ypr": (o["Yaw"], o["Pitch"], o["Roll"]) if o else None, "who": md.get("DisplayName", "")}


def _best_offset(bus: list[dict], uci: list[dict], span: int = 5) -> int:
    """앞쪽 표본에서 위도 차 중앙값이 가장 작은 어긋남 k (uci[i] ↔ bus[i + k])"""
    best, best_k = math.inf, 0
    for k in sorted(range(-span, span + 1), key=abs):    # 같으면 어긋남 0을 고른다 (정지·직선 비행은 여러 k가 같다)
        diffs = [abs(math.radians(bus[i + k]["lat"]) - uci[i]["lat"])
                 + abs(J.wrap_pi(math.radians(bus[i + k]["lon"]) - uci[i]["lon"]))
                 for i in range(min(len(uci), 40)) if 0 <= i + k < len(bus)]
        if diffs:
            m = sorted(diffs)[len(diffs) // 2]
            if m < best:
                best, best_k = m, k
    return best_k


def c3_inputs(r: Run) -> tuple[list, list, dict, list, list, dict]:
    bus = defaultdict(list)          # (entity, topic) → [det + hdr_us]
    for sim_s, short, src, hdr_us, det in r.bus_in:
        if short in ("NavigationReport", "PeerStatus") and det and det.get("has_pos"):
            bus[(src, "swarm.vi" if short == "NavigationReport" else "swarm.p2p")].append({**det, "hdr_us": hdr_us})
    uci = defaultdict(list)
    for x in r.rx:
        if x["name"] == "MA_PositionReport":
            u = _uci_pos(x["body"])
            uci[(u["who"], x["topic"])].append(u)
    pairs, ts_off, unpaired = [], [], {}
    for key in sorted(set(bus) | set(uci)):
        b, u = bus.get(key, []), uci.get(key, [])
        if not b or not u:
            unpaired[f"{key[0]}@{key[1]}"] = {"bus": len(b), "uci": len(u), "offset": None}
            continue
        k = _best_offset(b, u)
        n = 0
        for i, uu in enumerate(u):
            j = i + k
            if not 0 <= j < len(b):
                continue
            bb = b[j]
            cmp = J.compare_position({"lat_deg": bb["lat"], "lon_deg": bb["lon"], "alt_m": bb["alt"],
                                      "vel": bb["vel"], "q": bb["q"]}, uu)
            pairs.append({**cmp, "who": key[0], "topic": key[1]})
            t = parse_ts(uu["ts"])
            if t is not None:
                ts_off.append(t - bb["hdr_us"] * 1e-6)
            n += 1
        if len(b) != len(u) or k:
            unpaired[f"{key[0]}@{key[1]}"] = {"bus": len(b), "uci": len(u), "offset": k, "paired": n}
    # 식별자: Gateway 출력 전체의 {UUID, DescriptiveLabel} (머리의 SystemID는 Gateway 자신이라 따로 본다)
    ids: dict[str, list] = defaultdict(list)
    hdr_sys = Counter()

    def walk(o, key: str) -> None:  # noqa: ANN001
        if isinstance(o, dict):
            if "UUID" in o and isinstance(o["UUID"], str) and key:
                ids[key].append((o.get("DescriptiveLabel", ""), o["UUID"]))
            for k2, v in o.items():
                walk(v, k2)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
    for x in r.rx:
        hdr_sys[(x["body"].get("MessageHeader") or {}).get("SystemID", {}).get("UUID", "")] += 1
        walk(x["body"].get("MessageData", {}), "")
    ids = dict(ids)
    # 상태값: 내부(GCS 수신) ↔ 외부 순서 짝
    states = []
    i_ts, i_fcs = defaultdict(list), defaultdict(list)
    for sim_s, short, src, hdr_us, det in r.bus_in:
        if short == "TaskStatus":
            i_ts[(src, det["task"])].append(det["state"])
        elif short == "FlightCommandStatus":
            i_fcs[("", det["cmd"])].append(det["state"])      # UCI 쪽에 SystemID가 없어 명령 ID로만 짝짓는다
    e_ts, e_fcs = defaultdict(list), defaultdict(list)
    for x in r.rx:
        md = x["body"].get("MessageData", {})
        if x["name"] == "MA_TaskStatus":
            e_ts[(label((md.get("ExecutingSystemOrPackage") or {}).get("SystemID")), label(md.get("TaskID")))].append(
                md.get("ExecutionState"))
        elif x["name"] == "MA_FlightCommandStatus":
            e_fcs[(label(md.get("SystemID")), label(md.get("CommandID")))].append(md.get("CommandProcessingState"))
    st_unpaired = {}
    for msg, I, E in (("TaskStatus", i_ts, e_ts), ("FlightCommandStatus", i_fcs, e_fcs)):
        for key in sorted(set(I) | set(E)):
            a, b = I.get(key, []), E.get(key, [])
            for s_int, s_ext in zip(a, b):
                states.append({"msg": msg, "internal": s_int, "external": s_ext})
            if len(a) != len(b):
                st_unpaired[f"{msg} {key[0]}/{key[1]}"] = {"internal": len(a), "external": len(b)}
    unpaired["states"] = st_unpaired
    unpaired["header_system_uuid"] = dict(hdr_sys)
    # 수신 경로: 보낸 rad 좌표 → 버스 RoutePlan(도)
    routes = []
    for x in r.tx:
        if x["name"] != "MA_RoutePlan" or not x.get("ok"):
            continue
        md = x["body"].get("MessageData", {})
        rid = label(md.get("RoutePlanID"))
        if rid.startswith("neg-"):
            continue
        sent = _route_points(md)
        seen = set()
        for row, where in [(t, f"GCS 송신 {t['key'].split('/tx/')[-1]}") for t in r.obs.get("tx", [])] + \
                          [(t, f"{t['to']} 수신") for t in r.obs.get("rx", [])]:
            if row.get("msg") == "RoutePlan" and row.get("id") == rid and where not in seen:
                seen.add(where)
                routes.append({"route": rid, "where": where, "sent": sent, "bus": [tuple(p) for p in row.get("wps", [])]})
    return pairs, ts_off, ids, states, routes, unpaired


GW_EPOCH_LOG = ("no scenario epoch yet", "UCI time base changed")


def c3_epoch(r: Run) -> dict | None:
    """DEC-098 시각 기준: 관측한 sim/ctrl/scenario epoch, Gateway epoch 카운터, Gateway 로그의 기준 관련 줄.
    33차 이전 원자료(obs.json에 scenario_epochs 없음)는 None"""
    if "scenario_epochs" not in r.obs:
        return None
    log = r.d / "stack" / "gateway.1.log"
    lines = []
    if log.exists():
        lines = [ln.strip()[:200] for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()
                 if any(k in ln for k in GW_EPOCH_LOG)]
    c = (r.gw or {}).get("counters")
    return {"scenario": r.obs["scenario_epochs"],
            "gw": None if c is None else {k: c.get(k, 0) for k in ("epoch_set", "epoch_changed")},
            "log": lines}


def _route_points(md: dict) -> list[tuple[float, float, float]]:
    """MA_RoutePlan의 구간을 FirstInPathSegmentID → NextPathSegment 순으로 따라가 (도, 도, m)"""
    path = (md.get("Plan", {}).get("Route", {}).get("Path") or [{}])[0]
    segs = {s["PathSegmentID"]["UUID"]: s for s in path.get("PathSegment", [])}
    cur = (path.get("FirstInPathSegmentID") or {}).get("UUID")
    out, seen = [], set()
    while cur in segs and cur not in seen:
        seen.add(cur)
        s = segs[cur]
        p = s["EndPoint"]["WayPoint"]["PointChoice"]["Point2D"]
        out.append((math.degrees(p["Latitude"]), math.degrees(p["Longitude"]), p.get("Altitude", 0.0)))
        cur = (s.get("NextPathSegment") or {}).get("PathSegmentID", {}).get("UUID")
    return out


# ------------------------------------------------------------------------------------------------- C4

def c4_inputs(r: Run, proto: list[dict]) -> dict:
    contract = (ROOT / "docs" / "10_contracts.md").read_text(encoding="utf-8")
    allowed = J.agent_allowed(J.parse_contract_keys(contract))
    mcap = r.d / "stack" / "rec.mcap"
    topics = mcap_lite.read(mcap).topics if mcap.exists() else None
    port_msgs = [{"port": p, "dir": d, "msg": m, "n": n} for p, d, m, n in r.agent.get("port", [])]
    return {"subs": r.agent.get("subscribe", []), "puts": list(r.agent.get("put", {})), "rx_keys": r.agent.get("rx", {}),
            "allowed": allowed,
            "hosted": r.vehicles(), "imports": static.ma_imports(), "port_msgs": port_msgs,
            "proto": {p["full_name"]: p for p in proto}, "mcap_topics": topics}


# ------------------------------------------------------------------------------------------------- C5

def c5_inputs(r: Run) -> tuple[dict, list, list]:
    seqs: dict[str, dict[str, list[str]]] = {k: defaultdict(list) for k in J.TABLES}
    first_exec: dict[tuple[str, str], float] = {}
    req_of: dict[str, tuple[str, str]] = {}
    for sim_s, short, src, hdr_us, det in r.bus_in:
        if short == "TaskStatus":
            seqs["TaskStatus(내부)"][f"{src}/{det['task']}"].append(det["state"])
            if det["state"] == "EXECUTING":
                first_exec.setdefault((src, det["task"]), sim_s)
        elif short == "FlightCommandStatus":
            seqs["FlightCommandStatus(내부)"][det["cmd"]].append(det["state"])
        elif short == "ApprovalRequest":
            req_of[det["req"]] = (src, det["task"])
    for x in r.rx:
        md = x["body"].get("MessageData", {})
        if x["name"] == "MA_TaskStatus":
            who = label((md.get("ExecutingSystemOrPackage") or {}).get("SystemID"))
            seqs["MA_TaskStatus(외부)"][f"{who}/{label(md.get('TaskID'))}"].append(md.get("ExecutionState"))
        elif x["name"] == "MA_FlightCommandStatus":
            seqs["MA_FlightCommandStatus(외부)"][label(md.get("CommandID"))].append(
                md.get("CommandProcessingState"))
    seqs = {k: dict(v) for k, v in seqs.items()}
    resp: dict[tuple[str, str], tuple[str, float]] = {}
    for t in r.obs.get("tx", []):
        if t.get("msg") == "ApprovalResponse" and t.get("id") in req_of:
            resp.setdefault(req_of[t["id"]], ("approved" if t.get("approved") else "rejected", t["sim_s"]))
    approvals = []
    for (e, task) in sorted(NEED_APPROVAL | {k for k in first_exec if k[1].startswith(("ap-", "x-"))}):
        rs = resp.get((e, task))
        approvals.append({"entity": e, "task": task, "need": (e, task) in NEED_APPROVAL,
                          "requested": (e, task) in set(req_of.values()),
                          "response": rs[0] if rs else None, "t_resp": rs[1] if rs else None,
                          "t_exec": first_exec.get((e, task))})
    commands = []
    states_by = defaultdict(set)
    for sim_s, short, src, hdr_us, det in r.bus_in:
        if short == "TaskStatus":
            states_by[(src, det["task"])].add(det["state"])
    for c in r.ext.get("cmds", []):
        if "task_id" not in c or str(c["task_id"]).startswith("neg-"):
            continue
        for e in c.get("entities", []):
            seen = states_by.get((e, c["task_id"]), set())
            ok = ("CANCELLED" in seen) if c.get("cancel") else bool(seen)
            commands.append({"entity": e, "task": c["task_id"], "src": "외부 cancel" if c.get("cancel") else
                             f"외부 {c.get('kind', '')}", "status_seen": ok, "states": sorted(seen)})
    return seqs, approvals, commands


# ------------------------------------------------------------------------------------------------- C6

def c6_inputs(r: Run) -> tuple[dict, dict, Counter, Counter, dict]:
    declared = J.parse_declared(r.cfg_text)
    flows = J.graph_flows(r.graph) if r.graph else {}
    # /tap origin은 서비스 노드 ID(svc:<server_id>:<n>)다. /graph 노드 라벨로 Gateway 서비스를 찾는다
    gw_nodes = {n["id"] for n in r.graph.get("nodes", []) if n.get("kind") == "service" and n.get("label") == GW_SERVICE}
    tap = Counter()
    for name, origin, topic, n in r.ext.get("tap3", []):
        if origin in gw_nodes or origin == GW_SERVICE:
            tap[f"{name}@{topic}"] += n
    ext_rx = Counter(f"{x[1]}@{x[2]}" for x in r.ext.get("rx", []))
    inbound = {}
    sent_names = {c.get("name") or "MA_TaskCommand" for c in r.ext.get("cmds", [])
                  if str(c.get("pub", "")).startswith("+OK")}
    for uci in sorted(sent_names):
        busmsg = EXT_TO_BUS.get(uci)
        inbound[uci] = sum(1 for t in r.obs.get("tx", []) if t.get("msg") == busmsg
                           and not str(t.get("id", "")).startswith("neg-"))
    return declared, flows, tap, ext_rx, inbound


# ------------------------------------------------------------------------------------------------- C1·C7 (정적)

def static_inputs(work: Path) -> dict:
    gwd = static.gateway_dump(work / "gateway_dump.json")
    reg = static.registry_rows((ROOT / "docs" / "02_registry.md").read_text(encoding="utf-8"))
    names = sorted({p["short"] for p in gwd["proto"]} | {p["uci_name"] for p in gwd["proto"] if p["uci_name"]})
    trace = static.trace_ids((ROOT / "gateway" / "TRACE.md").read_text(encoding="utf-8"), names)
    return {"gwd": gwd, "xsd": static.xsd_top_elements(), "registry": reg, "trace": trace}


def ms_services(proto: list[dict]) -> dict[str, list[str]]:
    """MS 메시지를 장비 서비스별로 묶는다 (이름 앞부분: Sensor·Jammer·Strike·Store)"""
    out: dict[str, list[str]] = defaultdict(list)
    for p in proto:
        if p["l1"] != "MS":
            continue
        for svc in ("Sensor", "Jammer", "Strike", "Store", "Payload"):
            if p["short"].startswith(svc):
                out[svc].append(f"{p['short']}({p['mapping']}{', ' + p['uci_name'] if p['uci_name'] else ''})")
                break
        else:
            out["기타"].append(f"{p['short']}({p['mapping']})")
    return dict(out)
