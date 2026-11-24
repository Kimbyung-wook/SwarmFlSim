"""TC-AGT-158~164: 시험 하네스 MA-VI·MA-MS 어댑터 (IMP-AGT-061, DEC-113).

swarm_gateway(DEC-110 변환기·STOMP 클라이언트)가 있어야 돈다. 루트 작업 공간에는 gateway가 없으므로
`uv run --project gateway --extra zenoh --with-editable ./agent --with-editable ./algorithms pytest agent/tests/...`로 돌린다.
꺼진 경로 시험(TC-AGT-164)은 swarm_gateway 없이도 돈다.

가짜 STOMP 1.2 브로커를 별도 스레드의 asyncio 루프로 띄운다. SEND를 같은 목적지 구독자에게 MESSAGE로 돌린다
(ActiveMQ 비지속 토픽과 같은 전달).
"""
import asyncio
import subprocess
import sys
import threading
import time
import uuid

import pytest
from swarm.v1 import common_pb2, entity_pb2, ms_pb2, vi_pb2
from swarm_agent.testing import Harness, make_scenario

UAV, OTHER = "uav-001", "uav-002"
PLATFORM = "c5a0850c-282d-3211-b852-b92eb618a4ad"
NS = "{https://www.vdl.afrl.af.mil/programs/oam}"


def _gw():
    return pytest.importorskip("swarm_gateway.stomp", reason="swarm_gateway not installed (run with --project gateway)")


@pytest.fixture(scope="module")
def codec():
    pytest.importorskip("swarm_gateway.lacal", reason="swarm_gateway not installed")
    from swarm_gateway.lacal import load_codec
    try:
        return load_codec()
    except RuntimeError as e:
        pytest.skip(str(e))


@pytest.fixture
def conv(codec):
    from swarm_agent.harness_bridge import UciConverter
    from swarm_gateway.ids import IdMap
    return UciConverter(codec, IdMap(), PLATFORM)


class FakeBroker:
    def __init__(self):
        stomp = _gw()
        self._enc, self._read = stomp.encode_frame, stomp.read_frame
        self.frames: list[tuple[str, dict, bytes]] = []
        self.subs: list[tuple[str, str, asyncio.StreamWriter]] = []
        self.loop = asyncio.new_event_loop()
        self.port = 0
        started = threading.Event()

        def run():
            asyncio.set_event_loop(self.loop)
            self.server = self.loop.run_until_complete(asyncio.start_server(self._conn, "127.0.0.1", 0))
            self.port = self.server.sockets[0].getsockname()[1]
            started.set()
            self.loop.run_forever()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        started.wait(5)

    async def _conn(self, reader, writer):
        try:
            while (f := await self._read(reader)) is not None:
                cmd, hdr, body = f
                self.frames.append(f)
                if cmd in ("CONNECT", "STOMP"):
                    writer.write(self._enc("CONNECTED", {"version": "1.2", "server": "fake/1"}))
                elif cmd == "SUBSCRIBE":
                    self.subs.append((hdr["destination"], hdr["id"], writer))
                elif cmd == "SEND":
                    await self._publish(hdr["destination"], body)
                elif cmd == "DISCONNECT":
                    break
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _publish(self, dest, body):
        for d, sid, w in list(self.subs):
            if d == dest and not w.is_closing():
                w.write(self._enc("MESSAGE", {"destination": d, "subscription": sid, "message-id": str(uuid.uuid4())}, body))
                await w.drain()

    def publish(self, dest: str, body: bytes) -> None:
        asyncio.run_coroutine_threadsafe(self._publish(dest, body), self.loop).result(5)

    def sent(self, dest: str) -> list[bytes]:
        return [b for c, h, b in list(self.frames) if c == "SEND" and h["destination"] == dest]

    def close(self):
        async def stop():
            self.server.close()
            for t in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                t.cancel()
        asyncio.run_coroutine_threadsafe(stop(), self.loop).result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


@pytest.fixture
def broker():
    b = FakeBroker()
    yield b
    b.close()


def wait(cond, timeout=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.01)
    return False


def scenario(ma="waypoint"):
    sc = make_scenario(2, ma)
    for e in sc.entities:
        if e.kind == entity_pb2.ENTITY_KIND_UAV:
            e.payloads.add(id="cam0", type="camera")
            e.payloads.add(id="jam0", type="jammer")
    return sc


def bridged(broker, codec, ma="waypoint", **cfg):
    from swarm_agent.harness_bridge import HarnessBridge, HarnessConfig
    h = Harness(scenario(ma), load=False)
    b = HarnessBridge(HarnessConfig(host="127.0.0.1", port=broker.port, vehicle=UAV, **cfg), codec=codec)
    b.start()
    assert wait(lambda: len(broker.subs) == 6)
    h.rt.harness = b
    from swarm_agent.testing import load_command, put_sim_command
    put_sim_command(h.bus, load_command(h.scenario))
    return h, b


def signal(label: str, state: str = "UCI_NEW") -> bytes:
    rid = str(uuid.uuid3(uuid.NAMESPACE_DNS, label))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ServiceConfigurationChangeRequest xmlns="https://www.vdl.afrl.af.mil/programs/oam">
<MessageData><RequestID><UUID>{rid}</UUID><DescriptiveLabel>{label}</DescriptiveLabel></RequestID>
<RequestState>{state}</RequestState></MessageData></ServiceConfigurationChangeRequest>""".encode()


def onboard_seen(h, name):
    out = []
    h.bus.subscribe(f"onboard/*/{name}", lambda s: out.append(s.key))
    return out


# ---------------------------------------------------------------- 변환

def test_tc_agt_158_outbound_converters_are_xsd_valid(conv):
    """VI·MS 명령 모든 모양이 XSD를 통과하고 ID 라벨이 원래 ID를 싣는다"""
    g = common_pb2.Geodetic(lat_deg=37.4, lon_deg=128.4, alt_m=500)
    cmds = []
    f = vi_pb2.FlightCommand(command_id="c-hsa")
    f.hsa.heading_deg, f.hsa.speed_mps, f.hsa.altitude_m = 270, 30, 500
    cmds.append(f)
    f = vi_pb2.FlightCommand(command_id="c-wp")
    f.waypoint.waypoints.add(speed_mps=25).position.CopyFrom(g)
    f.waypoint.waypoints.add().position.CopyFrom(g)
    cmds.append(f)
    f = vi_pb2.FlightCommand(command_id="c-orbit")
    f.curve.orbit.center.CopyFrom(g)
    f.curve.orbit.radius_m, f.curve.orbit.direction = 300, vi_pb2.TURN_DIRECTION_CCW
    cmds.append(f)
    f = vi_pb2.FlightCommand(command_id="c-rt")
    f.curve.racetrack.center.CopyFrom(g)
    f.curve.racetrack.radius_m, f.curve.racetrack.leg_length_m, f.curve.racetrack.axis_heading_deg = 300, 2000, 45
    cmds.append(f)
    out = [conv.flight_command(UAV, c) for c in cmds]
    s = ms_pb2.SensorCommand(payload_id="cam0", enable=True)
    s.pointing.track_entity = "tgt-1"
    out.append(conv.ms_command(s))
    s = ms_pb2.SensorCommand(payload_id="cam0", enable=True)
    s.pointing.geo_point.CopyFrom(g)
    out.append(conv.ms_command(s))
    out.append(conv.ms_command(ms_pb2.SensorCommand(payload_id="cam0", enable=False)))
    out.append(conv.ms_command(ms_pb2.JammerCommand(payload_id="jam0", enable=True, radius_m=900)))
    out.append(conv.ms_command(ms_pb2.JammerCommand(payload_id="jam0", enable=False)))
    out.append(conv.ms_command(ms_pb2.StrikeCommand(payload_id="sta1", target_id="tgt-1")))
    k = ms_pb2.StrikeCommand(payload_id="sta1", target_id="tgt-1")
    k.aim_point.CopyFrom(g)
    out.append(conv.ms_command(k))
    names = []
    for name, data in out:
        xml = conv.to_xml(conv.envelope(name, data, 1_000_000))   # 실패하면 InvalidMessage
        assert b"005.0a.ASK" in xml
        names.append(name)
    assert names == ["MA_FlightCommand"] * 4 + ["PO_Command"] * 3 + ["EA_Command"] * 2 + ["StrikeCommand"] * 2
    fc = out[0][1]["Command"][0]["Capability"]
    assert fc["CommandID"]["DescriptiveLabel"] == "c-hsa"
    assert fc["FlightControlMode"]["HSA_CSA"]["Direction"]["Heading"]["Value"] == pytest.approx(-1.5707963, abs=1e-6)
    assert "WaypointFollowing" in out[1][1]["Command"][0]["Capability"]["FlightControlMode"]
    assert out[2][1]["Command"][0]["Capability"]["Loiter"]["Orbit"]["OrbitShape"]["Circle"]["TurnDirection"] == "LEFT"
    assert "FixPoint" in out[3][1]["Command"][0]["Capability"]["Loiter"]["Orbit"]["OrbitShape"]
    po = out[4][1]["Command"][0]["Capability"]
    assert po["CapabilityID"]["DescriptiveLabel"] == "cam0"
    assert po["Pointing"]["Geospatial"][0]["EntityID"]["DescriptiveLabel"] == "tgt-1"
    assert out[6][1]["Command"][0]["Activity"]["ChangeActivityState"] == "DISABLE"
    strike = [c["Capability"]["CommandType"] for c in out[9][1]["Command"]]
    assert list(strike[0]) == ["AssignTarget"] and list(strike[1]) == ["SelectForRelease"]
    assert "OpPointID" in out[10][1]["Command"][0]["Capability"]["CommandType"]["AssignTarget"]


def _activity(conv, name, cap, state, **extra):
    act = {"ActivityID": conv.ids.ref("activity", "a1"), "CapabilityID": [conv.ids.ref("capability", cap)],
           "Interactive": False, "ActivityState": state}
    if name == "StrikeActivity":
        act |= {"SelectedForKeyLoad": False, "WeaponArmed": True, "ReadyForRelease": True,
                "SelectedForRelease": extra.get("release", False), "SelectedForJettison": False}
    if name == "EA_Activity":
        act |= {"EA_Details": {"Unassigned": {"Emission": [], "Activation": "PREEMPTIVE"}}}
    return conv.envelope(name, {"SubsystemID": conv.ids.ref("subsystem", UAV), "Activity": [act]})


def test_tc_agt_159_inbound_mapping(conv):
    """하네스 상태·활동 → swarm.v1. 적재에 없는 CapabilityID와 대응 없는 상태는 버린다"""
    payloads = {"cam0": "camera", "jam0": "jammer", "sta1": "agm_short"}

    def roundtrip(obj):
        name, parsed = conv.parse(conv.to_xml(obj))
        return conv.from_uci(name, parsed, payloads)

    st = conv.envelope("MA_FlightCommandStatus", {"CommandID": conv.ids.ref("command", "uav-001-task-3"),
                                                  "CommandProcessingState": "ACCEPTED"})
    [m] = roundtrip(st)
    assert m.command_id == "uav-001-task-3" and m.state == common_pb2.COMMAND_STATE_ACCEPTED
    st["MA_FlightCommandStatus"]["MessageData"]["CommandProcessingState"] = "RECEIVED"
    assert roundtrip(st) == []
    [a] = roundtrip(_activity(conv, "PO_Activity", "cam0", "ACTIVE_UNCONSTRAINED"))
    assert isinstance(a, ms_pb2.SensorActivity) and a.payload_id == "cam0" and a.active
    [a] = roundtrip(_activity(conv, "PO_Activity", "cam0", "DISABLED"))
    assert not a.active
    assert roundtrip(_activity(conv, "PO_Activity", "random-cap", "ACTIVE_UNCONSTRAINED")) == []
    [a] = roundtrip(_activity(conv, "StrikeActivity", "sta1", "ACTIVE_UNCONSTRAINED", release=True))
    assert a.state == ms_pb2.STRIKE_STATE_LAUNCHED
    [a] = roundtrip(_activity(conv, "StrikeActivity", "sta1", "COMPLETED"))
    assert a.state == ms_pb2.STRIKE_STATE_IMPACT
    assert roundtrip(_activity(conv, "StrikeActivity", "sta1", "ENABLED")) == []


# ---------------------------------------------------------------- 브리지 (가짜 브로커)

def test_tc_agt_160_signals_acked(broker, codec):
    from lxml import etree
    from swarm_agent.harness_bridge import SIGNAL_ACK, SIGNAL_START, SIGNAL_STOP
    h, b = bridged(broker, codec)
    try:
        broker.publish(SIGNAL_START, signal("MA-VI/ReceiveVehicleStateData_Direction1"))
        broker.publish(SIGNAL_STOP, signal("MA-VI/ReceiveVehicleStateData_Direction1", "UCI_CANCEL"))
        assert wait(lambda: len(broker.sent(SIGNAL_ACK)) == 2)
        acks = [etree.fromstring(x) for x in broker.sent(SIGNAL_ACK)]
        codec.validate_xml(acks[0])
        assert [a.findtext(f"{NS}MessageData/{NS}RequestProcessingState") for a in acks] == ["COMPLETED", "CANCELED"]
        assert acks[0].findtext(f"{NS}MessageData/{NS}RequestID/{NS}DescriptiveLabel") == \
            "MA-VI/ReceiveVehicleStateData_Direction1"
        h.core.step(2)
        assert b.counters["inject"] == 0         # MA 출력을 기다리지 않는 시험에는 작업을 넣지 않는다
    finally:
        b.close()


@pytest.mark.parametrize("label,uci,mode", [
    ("MA-VI/ControlbyWaypointFollowing_Direction1", "MA_FlightCommand", "WaypointFollowing"),
    ("MA-VI/ControlbyCurveFollowing_Direction1", "MA_FlightCommand", "Loiter"),
    ("MA-MS/CommandSensorPOCapability_Direction1", "PO_Command", "Capability"),
])
def test_tc_agt_161_start_signal_drives_ma_output_to_harness(broker, codec, label, uci, mode):
    """시작 신호 → 시험 작업 → MA가 L1 포트로 낸 명령이 하네스 토픽으로 나간다. 고른 기체의 명령은 onboard·FA로 가지 않는다"""
    from swarm_agent.harness_bridge import SIGNAL_START, topic
    h, b = bridged(broker, codec)
    sensors = onboard_seen(h, "SensorCommand")
    try:
        h.core.step(2)
        base = len(broker.sent(topic(uci)))
        fa_before = h.rt.vehicles[UAV].fa.on_command
        calls = []
        h.rt.vehicles[UAV].fa.on_command = lambda c: calls.append(c) or fa_before(c)
        broker.publish(SIGNAL_START, signal(label))
        assert wait(lambda: b._inbox or b.counters["inject"])
        h.run_s(2.0)
        assert b.counters["inject"] == 1
        assert wait(lambda: len(broker.sent(topic(uci))) > base)
        body = broker.sent(topic(uci))[-1]
        from lxml import etree
        root = etree.fromstring(body)
        codec.validate_xml(root)
        assert etree.tostring(root).count(mode.encode()) >= 1
        assert calls == []                                # 내장 FA는 이 기체 명령을 받지 않는다
        assert not [k for k in sensors if f"/{UAV}/" in k]
    finally:
        b.close()


def test_tc_agt_162_harness_status_and_activity_reach_ma_and_gcs(broker, codec, conv):
    """하네스가 낸 MA_FlightCommandStatus·PO_Activity가 다음 틱에 포트로 들어가고 GCS 보고로도 나간다"""
    from swarm_agent.harness_bridge import topic
    h, b = bridged(broker, codec)
    try:
        h.core.step(2)
        st = conv.envelope("MA_FlightCommandStatus", {"CommandID": conv.ids.ref("command", "fc-x"),
                                                      "CommandProcessingState": "REJECTED"})
        broker.publish(topic("MA_FlightCommandStatus"), conv.to_xml(st))
        broker.publish(topic("PO_Activity"), conv.to_xml(_activity(conv, "PO_Activity", "cam0", "ACTIVE_UNCONSTRAINED")))
        broker.publish(topic("PO_Activity"), b"<not-xml")
        assert wait(lambda: len(b._inbox) >= 2 and b.counters["rx_invalid"] == 1)
        h.core.step(3)
        assert b.counters["rx_status"] == 1 and b.counters["rx_activity"] == 1
        names = [(m.DESCRIPTOR.name, m.header.source) for m in h.gcs_rx]
        assert ("SensorActivity", UAV) in names
        fcs = [m for m in h.gcs_rx if m.DESCRIPTOR.name == "FlightCommandStatus" and m.command_id == "fc-x"]
        assert fcs and fcs[-1].state == common_pb2.COMMAND_STATE_REJECTED
    finally:
        b.close()


def test_tc_agt_163_other_vehicles_keep_onboard_path(broker, codec):
    """고르지 않은 기체는 그대로 내장 FA·onboard 경로를 쓴다"""
    from swarm.v1 import c2_pb2
    from swarm_agent.testing import send_c2
    h, b = bridged(broker, codec)
    sensors = onboard_seen(h, "SensorCommand")
    try:
        h.core.step(2)
        t = c2_pb2.TaskCommand(task_id="t-other", assignees=[OTHER])
        t.search_area.area.circle.center.CopyFrom(h.rt.vehicles[OTHER].nav.kinematics.position)
        t.search_area.area.circle.radius_m = 400
        send_c2(h.bus, "gcs-01", t, [OTHER])
        h.run_s(3.0)
        assert any(f"/{OTHER}/" in k for k in sensors)
        assert h.rt.vehicles[OTHER].bridge is None and h.rt.vehicles[UAV].bridge is b
    finally:
        b.close()


# ---------------------------------------------------------------- 꺼진 경로

def test_tc_agt_164_off_by_default_no_gateway_import():
    """--harness-stomp가 없으면 어댑터와 swarm_gateway를 읽지 않고 기체의 bridge는 None이다"""
    code = ("import sys, swarm_agent.cli as c, swarm_agent.runtime as r;"
            "a = c.parse_args([]);"
            "assert a.harness_stomp == '';"
            "assert c.start_harness(a, None) is None;"
            "assert 'swarm_agent.harness_bridge' not in sys.modules, 'bridge imported';"
            "assert 'swarm_gateway' not in sys.modules, 'gateway imported';"
            "print('ok')")
    out = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr
    h = Harness(make_scenario(2, "waypoint"))
    h.core.step(3)
    assert h.rt.harness is None
    assert all(v.bridge is None for v in h.rt.vehicles.values())
