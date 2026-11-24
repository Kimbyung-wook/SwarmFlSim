"""A-GRA 시험 하네스용 기체 내부 인터페이스(MA-VI, MA-MS) 어댑터 (IMP-AGT-061, DEC-113).

시험 전용이고 기본은 꺼져 있다. 켜면 고른 기체 하나의 VI·MS 포트가 `onboard/**`와 내장 FA 대신
하네스 STOMP 버스(`/topic/<UCI 이름>`, 봉투 없음)로 주고받는다. 하네스가 FA와 MS 역할을 한다.
MA는 여전히 L1 포트(VIPort·MSPort)로만 말한다 (DEC-013, DEC-094는 바뀌지 않는다).

- 내기: FlightCommand → MA_FlightCommand, SensorCommand → PO_Command, JammerCommand → EA_Command,
  StrikeCommand → StrikeCommand. XSD를 통과한 UCI XML만 낸다.
- 받기: MA_FlightCommandStatus → FlightCommandStatus, PO_Activity·EA_Activity·StrikeActivity →
  SensorActivity·JammerActivity·StrikeActivity. 기체 적재에 없는 CapabilityID나 대응이 없는 상태는 세고 버린다.
- 항법(NavigationReport)·SystemStatus·Detection·StoreLoadout은 그대로 모의(Core·Payload)에서 받는다.
- 시작·정지 신호(`/topic/TestHarness_StartSignal`·`StopSignal`)에 응답(`TestHarness_SignalAck`)한다. MA 출력을 기다리는
  시험의 시작 신호에는 그 기체 C2 입력에 시험 작업(TaskCommand)을 넣어 MA가 실제로 명령을 내게 한다 (INJECT).

UCI 직렬화(XSD 코덱, ID 대응, 봉투 모양, STOMP 클라이언트)는 Gateway(DEC-110)의 것을 import해서 쓴다.
swarm_gateway는 켤 때만 읽는다. 꺼져 있으면 이 모듈은 import되지 않는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
import threading
import uuid
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.protobuf.message import Message
from swarm.v1 import c2_pb2, common_pb2, ms_pb2, vi_pb2

if TYPE_CHECKING:
    from .runtime import AgentRuntime
    from .vehicle import Vehicle

log = logging.getLogger("swarm_agent.harness")

SIGNAL_START = "/topic/TestHarness_StartSignal"
SIGNAL_STOP = "/topic/TestHarness_StopSignal"
SIGNAL_ACK = "/topic/TestHarness_SignalAck"
SCHEMA_VERSION_5_0A = "005.0a.ASK"
INBOUND = ("MA_FlightCommandStatus", "PO_Activity", "EA_Activity", "StrikeActivity")
_EPOCH = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)


def topic(uci_name: str) -> str:
    return f"/topic/{uci_name}"


# ---------------------------------------------------------------- 단위 (UCI 각도는 라디안, 거리 m, 속력 m/s)

def _finite(*values: float) -> None:
    for v in values:
        if not math.isfinite(v):
            raise ValueError(f"non-finite value: {v}")


def _lon(deg: float) -> float:
    r = math.radians(deg)
    return math.atan2(math.sin(r), math.cos(r))


def _heading(deg: float) -> float:
    """AngleType [-π, π]"""
    return _lon(deg)


def point2d(g: common_pb2.Geodetic) -> dict:
    _finite(g.lat_deg, g.lon_deg, g.alt_m)
    return {"Latitude": math.radians(g.lat_deg), "Longitude": _lon(g.lon_deg), "Altitude": float(g.alt_m),
            "AltitudeReference": "MSL"}


def offset(g: common_pb2.Geodetic, north_m: float, east_m: float) -> common_pb2.Geodetic:
    """평면 근사 이동 (시험 작업 위치용)"""
    r = 6378137.0
    lat = g.lat_deg + math.degrees(north_m / r)
    lon = g.lon_deg + math.degrees(east_m / (r * max(math.cos(math.radians(g.lat_deg)), 1e-6)))
    return common_pb2.Geodetic(lat_deg=lat, lon_deg=lon, alt_m=g.alt_m)


def _turn(d: int) -> str:
    return "LEFT" if d == vi_pb2.TURN_DIRECTION_CCW else "RIGHT"   # UNSPECIFIED는 FA 기본(시계 방향)과 같게


# ---------------------------------------------------------------- 변환기

class UciConverter:
    """swarm.v1 VI·MS ⇄ UCI(OMS JSON). XSD 검증과 XML 직렬화는 Gateway의 OmsJsonCodec이 한다"""

    def __init__(self, codec: Any, ids: Any, system_uuid: str, schema_version: str = SCHEMA_VERSION_5_0A,
                 classification: str = "U", owner_producer: str = "USA", mode: str = "SIMULATION") -> None:
        self.codec, self.ids = codec, ids
        self.system_uuid, self.schema_version = system_uuid, schema_version
        self.classification, self.owner_producer, self.mode = classification, owner_producer, mode

    # ---- 봉투 (Gateway.envelope와 같은 모양)
    def envelope(self, uci_name: str, data: dict, sim_time_us: int | None = None) -> dict:
        at = _EPOCH + dt.timedelta(microseconds=sim_time_us) if sim_time_us is not None else None
        from swarm_gateway.lacal import uci_timestamp
        return {uci_name: {
            "SecurityInformation": {"Classification": self.classification,
                                    "OwnerProducer": [{"GovernmentIdentifier": self.owner_producer}]},
            "MessageHeader": {"SystemID": {"UUID": self.system_uuid}, "Timestamp": uci_timestamp(at),
                              "SchemaVersion": self.schema_version, "Mode": self.mode},
            "MessageData": data,
        }}

    def to_xml(self, obj: dict) -> bytes:
        return self.codec.to_xml_bytes(obj)

    def _rank(self) -> dict:
        return {"Rank": {"Priority": 1, "PrecedenceWithinPriority": 1}}

    def _capability(self, command_id: str, capability: str) -> dict:
        return {"CommandID": self.ids.ref("command", command_id), "CommandState": "NEW",
                "CapabilityID": self.ids.ref("capability", capability), "Ranking": self._rank()}

    def _activity_cmd(self, command_id: str, activity: str, change: str) -> dict:
        return {"CommandID": self.ids.ref("command", command_id), "CommandState": "NEW",
                "ActivityID": self.ids.ref("activity", activity), "ChangeActivityState": change}

    # ---- 내기
    def flight_command(self, entity_id: str, cmd: vi_pb2.FlightCommand) -> tuple[str, dict]:
        cap = self._capability(cmd.command_id, f"{entity_id}/flight")
        mode = cmd.WhichOneof("mode")
        if mode == "hsa":
            h = cmd.hsa
            hsa: dict = {}
            if h.HasField("altitude_m"):
                _finite(h.altitude_m)
                hsa["Altitude"] = {"AltitudeReference": "MSL", "Altitude": h.altitude_m}
            if h.HasField("speed_mps"):
                _finite(h.speed_mps)
                hsa["Speed"] = {"SpeedChoice": {"SpeedValue": {"Value": max(h.speed_mps, 0.0), "Reference": "GROUNDSPEED"}}}
            if h.HasField("heading_deg"):
                _finite(h.heading_deg)
                hsa["Direction"] = {"Heading": {"Value": _heading(h.heading_deg), "Reference": "TRUE_NORTH"}}
            cap["FlightControlMode"] = {"HSA_CSA": hsa}
        elif mode == "waypoint":
            cap["FlightControlMode"] = {"WaypointFollowing": self._route(cmd.command_id, cmd.waypoint)}
        elif mode == "curve":
            cap["Loiter"] = {"Orbit": self._orbit(cmd.curve)}
        else:
            raise ValueError("FlightCommand without mode")
        return "MA_FlightCommand", {"Command": [{"Capability": cap}]}

    def _route(self, command_id: str, wp: vi_pb2.WaypointCommand) -> dict:
        if not wp.waypoints:
            raise ValueError("WaypointCommand without waypoints")
        path_id = self.ids.ref("path", f"{command_id}/p0")
        segs = []
        for i, w in enumerate(wp.waypoints):
            seg: dict = {"PathSegmentID": self.ids.ref("segment", f"{command_id}/s{i}"), "Source": "OPERATOR_DEFINED",
                         "EndPoint": {"WayPoint": {"PointChoice": {"Point2D": point2d(w.position)},
                                                   "WaypointType": "NAV_ONLY"}}}
            if w.HasField("speed_mps"):
                _finite(w.speed_mps)
                seg["Speed"] = {"SpeedChoice": {"SpeedValue": {"Value": max(w.speed_mps, 0.0), "Reference": "GROUNDSPEED"}}}
            segs.append(seg)
        return {"Route": {"Detailed": True, "FirstInRoutePathID": path_id, "RouteProjection": "GREAT_CIRCLE",
                          "Path": [{"PathID": path_id, "PathType": "PRIMARY",
                                    "FirstInPathSegmentID": segs[0]["PathSegmentID"], "PathSegment": segs}]}}

    def _orbit(self, curve: vi_pb2.CurveCommand) -> dict:
        which = curve.WhichOneof("curve")
        if which == "orbit":
            o = curve.orbit
            _finite(o.radius_m)
            return {"OrbitShape": {"Circle": {
                "OrbitType": "CIRCLE",
                "Circle": [{"PointChoice": {"AbsolutePoint": point2d(o.center)}, "Radius": max(o.radius_m, 0.0)}],
                "TurnDirection": _turn(o.direction)}}}
        if which == "racetrack":
            r = curve.racetrack
            _finite(r.radius_m, r.leg_length_m, r.axis_heading_deg)
            a = math.radians(r.axis_heading_deg)
            half = r.leg_length_m / 2.0
            fix = offset(r.center, half * math.cos(a), half * math.sin(a))   # 축 방향 입항 구간의 끝
            return {"OrbitShape": {"FixPoint": {
                "Point": {"AbsolutePoint": point2d(fix)},
                "InboundDirection": {"Heading": {"Value": _heading(r.axis_heading_deg), "Reference": "TRUE_NORTH"}},
                "LegLength": {"Distance": max(r.leg_length_m, 0.0)},
                "TurnGeometry": {"TurnRadius": max(r.radius_m, 0.0)},
                "TurnDirection": _turn(r.direction)}}}
        raise ValueError("CurveCommand without curve")

    def ms_command(self, msg: Message) -> tuple[str, dict]:
        name = msg.DESCRIPTOR.name
        cmd_id = f"{msg.header.source}/{name}/{msg.header.seq}"
        if name == "SensorCommand":
            if not msg.enable:
                return "PO_Command", {"Command": [{"Activity": self._activity_cmd(cmd_id, msg.payload_id, "DISABLE")}]}
            cap = self._capability(cmd_id, msg.payload_id)
            tgt = self._pointing(msg.pointing)
            if tgt is not None:
                cap["Pointing"] = {"Geospatial": [tgt]}
            return "PO_Command", {"Command": [{"Capability": cap}]}
        if name == "JammerCommand":
            if not msg.enable:
                return "EA_Command", {"Command": [{"Activity": self._activity_cmd(cmd_id, msg.payload_id, "DISABLE")}]}
            return "EA_Command", {"Command": [{"Capability": self._capability(cmd_id, msg.payload_id)}]}
        if name == "StrikeCommand":
            if msg.HasField("aim_point"):
                assign = {"OpPointID": self.ids.ref("oppoint", f"{cmd_id}/aim")}
            else:
                assign = {"EntityID": self.ids.ref("entity", msg.target_id)}
            first = self._capability(cmd_id + "/assign", msg.payload_id) | {"CommandType": {"AssignTarget": assign}}
            second = self._capability(cmd_id + "/release", msg.payload_id) | {"CommandType": {"SelectForRelease": True}}
            return "StrikeCommand", {"Command": [{"Capability": first}, {"Capability": second}]}
        raise ValueError(f"unsupported MS command {name}")

    def _pointing(self, p: ms_pb2.GimbalPointing) -> dict | None:
        which = p.WhichOneof("target")
        if which == "track_entity":
            return {"EntityID": self.ids.ref("entity", p.track_entity)}
        if which == "geo_point":
            return {"PointTarget": {"Point": {"AbsolutePoint": point2d(p.geo_point)}}}
        return None     # 기체 기준 방위·고각은 UCI Geospatial 대상이 아니다. 지향 없이 켠다

    # ---- 받기
    def parse(self, body: bytes) -> tuple[str, dict]:
        from lxml import etree
        root = etree.fromstring(body, parser=etree.XMLParser(resolve_entities=False, no_network=True))
        self.codec.validate_xml(root)
        obj = self.codec.xml_to_json(root)
        return next(iter(obj)), obj

    def from_uci(self, name: str, obj: dict, payloads: dict[str, str]) -> list[Message]:
        """payloads: 이 기체 적재 id → 종류(camera|jammer|...). 적재에 없는 CapabilityID는 버린다"""
        data = obj[name]["MessageData"]
        if name == "MA_FlightCommandStatus":
            state = {"ACCEPTED": common_pb2.COMMAND_STATE_ACCEPTED, "REJECTED": common_pb2.COMMAND_STATE_REJECTED,
                     "CANCELED": common_pb2.COMMAND_STATE_CANCELLED}.get(data.get("CommandProcessingState", ""))
            if state is None:
                return []
            return [vi_pb2.FlightCommandStatus(command_id=self.ids.internal(data.get("CommandID")), state=state)]
        out: list[Message] = []
        for act in data.get("Activity", []):
            caps = [self.ids.internal(c) for c in act.get("CapabilityID", [])]
            pid = next((c for c in caps if c in payloads), "")
            if not pid:
                continue
            st = act.get("ActivityState", "")
            active = st.startswith("ACTIVE")
            if name == "PO_Activity":
                out.append(ms_pb2.SensorActivity(payload_id=pid, active=active))
            elif name == "EA_Activity":
                out.append(ms_pb2.JammerActivity(payload_id=pid, active=active))
            elif name == "StrikeActivity":
                if active and act.get("SelectedForRelease"):
                    s = ms_pb2.STRIKE_STATE_LAUNCHED
                elif st == "COMPLETED":
                    s = ms_pb2.STRIKE_STATE_IMPACT
                elif st == "FAILED":
                    s = ms_pb2.STRIKE_STATE_MISSED
                else:
                    continue
                out.append(ms_pb2.StrikeActivity(payload_id=pid, state=s))
        return out


# ---------------------------------------------------------------- 시작 신호 → 시험 작업

def _nav_pos(v: Vehicle) -> common_pb2.Geodetic | None:
    return v.nav.kinematics.position if v.nav is not None else None


def _move_to(v: Vehicle, n: int) -> c2_pb2.TaskCommand | None:
    p = _nav_pos(v)
    if p is None:
        return None
    t = c2_pb2.TaskCommand(task_id=f"harness-{n}")
    t.move_to.destination.CopyFrom(offset(p, 2000.0 if n % 2 else -2000.0, 0.0))
    return t


def _hold(v: Vehicle, n: int) -> c2_pb2.TaskCommand | None:
    p = _nav_pos(v)
    if p is None:
        return None
    t = c2_pb2.TaskCommand(task_id=f"harness-{n}")
    t.hold.center.CopyFrom(p)
    t.hold.radius_m = 400.0 + 10.0 * (n % 5)
    return t


def _search(v: Vehicle, n: int) -> c2_pb2.TaskCommand | None:
    p = _nav_pos(v)
    if p is None:
        return None
    t = c2_pb2.TaskCommand(task_id=f"harness-{n}")
    t.search_area.area.circle.center.CopyFrom(offset(p, 800.0, 0.0))
    t.search_area.area.circle.radius_m = 500.0
    return t


# 시작 신호 DescriptiveLabel "<인터페이스>/<이름>_Direction1"의 <이름> → 시험 작업. 값은 하네스가 보지 않는다(XSD·순서만)
INJECT: dict[str, Callable[[Vehicle, int], c2_pb2.TaskCommand | None]] = {
    "ControlbyCurveFollowing": _hold,          # HoldTask → CurveCommand(orbit) → Loiter.Orbit
    "ControlbyWaypointFollowing": _move_to,    # MoveTo → WaypointCommand → WaypointFollowing
    "ControlbyHSACSACommand": _move_to,        # 기본 MA는 C2 작업으로 HSA를 내지 않는다. WaypointFollowing으로 답한다
    "ValidateReleaseEnvelope": _move_to,
    "ControlModeAuthorization": _move_to,      # 하네스가 FlightCapability·ControlStatus 등을 보낸 뒤 MA_FlightCommand를 기다린다
    "PublishControlStatus": _move_to,
    "ReceiveControlRequest": _move_to,
    "CommandSensorPOCapability": _search,      # SearchArea → PayloadTasker SensorCommand → PO_Command
}


def signal_label(body: bytes) -> tuple[dict, str]:
    """ServiceConfigurationChangeRequest의 RequestID와 시험 이름(<이름>, _Direction 앞)"""
    from lxml import etree
    rid: dict = {}
    try:
        root = etree.fromstring(body, parser=etree.XMLParser(resolve_entities=False, no_network=True))
        node = root.find("{*}MessageData/{*}RequestID")
        if node is not None:
            u, label = node.findtext("{*}UUID"), node.findtext("{*}DescriptiveLabel")
            if u:
                rid["UUID"] = str(uuid.UUID(u.strip()))
            if label:
                rid["DescriptiveLabel"] = label
    except (etree.XMLSyntaxError, ValueError):
        pass
    if "UUID" not in rid:
        rid["UUID"] = str(uuid.uuid4())
    name = rid.get("DescriptiveLabel", "").rsplit("/", 1)[-1].split("_Direction", 1)[0]
    return rid, name


# ---------------------------------------------------------------- 브리지

@dataclass
class HarnessConfig:
    host: str = "127.0.0.1"
    port: int = 61613
    vehicle: str = ""                       # 비우면 런타임의 첫 기체
    system_uuid: str = "c5a0850c-282d-3211-b852-b92eb618a4ad"   # 하네스 test-config의 platform_system_id 기본값
    schema_version: str = SCHEMA_VERSION_5_0A
    login: str = ""
    passcode: str = ""
    inject: bool = True                     # 시작 신호에 시험 작업을 넣는다
    connect_timeout_s: float = 30.0


class HarnessBridge:
    """런타임 스레드: bind·drain·flight_command·ms_command. STOMP는 별도 스레드의 asyncio 루프에서 돈다"""

    def __init__(self, config: HarnessConfig, codec: Any = None, client_factory: Callable[[], Any] | None = None) -> None:
        from swarm_gateway.ids import IdMap
        from swarm_gateway.lacal import load_codec
        self.config = config
        self.conv = UciConverter(codec or load_codec(), IdMap(), config.system_uuid, config.schema_version)
        if client_factory is None:
            from swarm_gateway.stomp import StompClient

            def client_factory() -> Any:
                return StompClient(config.host, config.port, login=config.login, passcode=config.passcode)
        self._factory = client_factory
        self._client: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop: asyncio.Event | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._inbox: deque = deque(maxlen=4096)      # (종류, 값). 루프 스레드가 넣고 런타임 스레드가 꺼낸다
        self.vehicle: Vehicle | None = None
        self._payloads: dict[str, str] = {}
        self._n = 0
        self.counters: Counter = Counter()
        self.sent: list[tuple[str, bytes]] = []      # 시험용 기록 (최근 것만)

    # ---- 수명
    def start(self, wait: bool = True) -> None:
        self._thread = threading.Thread(target=self._thread_main, name="harness-stomp", daemon=True)
        self._thread.start()
        if wait and (not self._ready.wait(self.config.connect_timeout_s + 5.0) or self._error is not None):
            raise RuntimeError(f"harness STOMP connect failed: {self._error}")

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._main())
        except BaseException as e:  # noqa: BLE001 - 연결 실패를 start()에 넘긴다
            self._error = e
            self._ready.set()

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._client = self._factory()
        await self._client.connect(timeout=self.config.connect_timeout_s)
        for name in INBOUND:
            await self._client.subscribe(topic(name), self._on_message)
        for d in (SIGNAL_START, SIGNAL_STOP):
            await self._client.subscribe(d, self._on_signal)
        log.info("harness: STOMP %s:%d connected, vehicle=%s", self.config.host, self.config.port,
                 self.config.vehicle or "(first)")
        self._ready.set()
        await self._stop.wait()
        await self._client.close()

    def close(self) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(5.0)

    # ---- 런타임 연결
    def bind(self, rt: AgentRuntime) -> None:
        """시나리오를 읽은 뒤 호출된다. 고른 기체의 VI·MS 포트를 이 브리지로 돌린다"""
        if self.vehicle is not None:
            self.vehicle.bridge = None
        vid = self.config.vehicle
        v = rt.vehicles.get(vid) if vid else (rt._order[0] if rt._order else None)
        if v is None:
            rt.warn(f"harness: vehicle {vid or '(first)'} not hosted here; adapter idle")
            self.vehicle = None
            return
        v.bridge = self
        self.vehicle = v
        self._payloads = {p.id: p.type for p in v.spec.payloads}
        log.info("harness: %s VI/MS ports bridged to STOMP", v.entity_id)

    def drain(self) -> None:
        """틱 시작(begin_frame 전)에 받은 것을 기체에 넣는다. 런타임 스레드에서만 호출한다"""
        v = self.vehicle
        while self._inbox:
            kind, value = self._inbox.popleft()
            if v is None:
                continue
            if kind == "inject":
                fn = INJECT.get(value)
                self._n += 1
                task = fn(v, self._n) if fn is not None else None
                if task is None:
                    self.counters["inject_none"] += 1
                    continue
                task.header.source = v.spec.controlling_gcs or "harness"
                task.assignees.append(v.entity_id)
                v.ports.c2.buffer.push(task)
                self.counters["inject"] += 1
                log.info("harness: start %s → test task %s (%s)", value, task.task_id, task.WhichOneof("task"))
            elif isinstance(value, vi_pb2.FlightCommandStatus):
                v.ports.vi.push_status(value)
                self.counters["rx_status"] += 1
            else:
                v.stamp(value)
                v._rt._apply_onboard(v, value.DESCRIPTOR.name, value)
                self.counters["rx_activity"] += 1

    def flight_command(self, v: Vehicle, cmd: vi_pb2.FlightCommand) -> None:
        self._emit(v, *self.conv.flight_command(v.entity_id, cmd))

    def ms_command(self, v: Vehicle, msg: Message) -> bool:
        """MS 명령이면 하네스로 내고 True. 그 밖의 onboard 메시지는 False(원래 경로)"""
        if msg.DESCRIPTOR.name not in ("SensorCommand", "JammerCommand", "StrikeCommand"):
            return False
        self._emit(v, *self.conv.ms_command(msg))
        return True

    def _emit(self, v: Vehicle, uci_name: str, data: dict) -> None:
        try:
            body = self.conv.to_xml(self.conv.envelope(uci_name, data, v.sim_time_us))
        except Exception as e:  # noqa: BLE001 - XSD를 못 통과한 것은 내지 않는다
            self.counters["tx_invalid"] += 1
            v.warn(f"harness: {uci_name} not sent: {e}")
            return
        self.sent.append((uci_name, body))
        del self.sent[:-64]
        self.counters[f"tx {uci_name}"] += 1
        self._send(topic(uci_name), body)

    def _send(self, dest: str, body: bytes) -> None:
        if self._loop is None or self._client is None:
            self.counters["tx_dropped"] += 1
            return
        asyncio.run_coroutine_threadsafe(self._client.send(dest, body), self._loop)

    # ---- 루프 스레드
    async def _on_signal(self, dest: str, body: bytes, hdr: dict) -> None:
        start = dest == SIGNAL_START
        rid, name = signal_label(body)
        ack = self.conv.envelope("ServiceConfigurationChangeRequestStatus",
                                 {"RequestID": rid, "RequestProcessingState": "COMPLETED" if start else "CANCELED"})
        await self._client.send(SIGNAL_ACK, self.conv.to_xml(ack))
        self.counters["signal_start" if start else "signal_stop"] += 1
        log.info("harness: %s signal %s acked", "start" if start else "stop", rid.get("DescriptiveLabel", rid["UUID"]))
        if start and self.config.inject and name in INJECT:
            self._inbox.append(("inject", name))

    def _on_message(self, dest: str, body: bytes, hdr: dict) -> None:
        try:
            name, obj = self.conv.parse(body)
            msgs = self.conv.from_uci(name, obj, self._payloads)
        except Exception as e:  # noqa: BLE001 - 어떤 입력에도 계속 받는다
            self.counters["rx_invalid"] += 1
            log.debug("harness: %s dropped: %s", dest, e)
            return
        if not msgs:
            self.counters[f"rx_unmapped {name}"] += 1
        for m in msgs:
            self._inbox.append(("msg", m))
