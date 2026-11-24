"""TC-GW-057~061: A-GRA 시험 하네스 STOMP 경로 (DEC-110, IMP-GW-037).

가짜 STOMP 1.2 브로커(asyncio)를 띄워 Gateway를 붙인다. 브로커는 CONNECT·SUBSCRIBE·SEND만 알고 SEND를 같은 목적지
구독자에게 MESSAGE로 돌린다(ActiveMQ 토픽과 같은 비지속 전달).
"""
import asyncio
import re
import time
import uuid

import pytest
from lxml import etree
from swarm.v1 import c2_pb2, link_pb2

import samples as S
import swarm_gateway.__main__ as cli
from swarm_gateway.envelope import RX, TX, Envelopes
from swarm_gateway.gateway import GatewayConfig
from swarm_gateway.runner import SIGNAL_ACK, SIGNAL_START, SIGNAL_STOP, start_stomp_gateway
from swarm_gateway.stomp import StompClient, encode_frame, read_frame
from test_import import _task_command
from test_roundtrip import _wait

PLATFORM = "5b0d7c1e-2222-4333-8444-555566667777"   # 우리 플랫폼 UUID (시험 값)
C2 = "a2f74db0-1111-4222-8333-444455556666"
NS = "{https://www.vdl.afrl.af.mil/programs/oam}"


class FakeBroker:
    def __init__(self):
        self.subs: list[tuple[str, str, asyncio.StreamWriter]] = []   # (destination, id, writer)
        self.frames: list[tuple[str, dict, bytes]] = []
        self.server = None
        self.port = 0

    async def start(self):
        self.server = await asyncio.start_server(self._conn, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def _conn(self, reader, writer):
        try:
            while (f := await read_frame(reader)) is not None:
                cmd, hdr, body = f
                self.frames.append(f)
                if cmd in ("CONNECT", "STOMP"):
                    writer.write(encode_frame("CONNECTED", {"version": "1.2", "server": "fake/1"}))
                elif cmd == "SUBSCRIBE":
                    self.subs.append((hdr["destination"], hdr["id"], writer))
                elif cmd == "SEND":
                    await self.publish(hdr["destination"], body)
                elif cmd == "DISCONNECT":
                    break
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def publish(self, dest: str, body: bytes):
        for d, sid, w in list(self.subs):
            if d == dest and not w.is_closing():
                w.write(encode_frame("MESSAGE", {"destination": d, "subscription": sid,
                                                 "message-id": str(uuid.uuid4())}, body))
                await w.drain()

    def sent(self, dest: str) -> list[bytes]:
        return [b for c, h, b in self.frames if c == "SEND" and h["destination"] == dest]

    def subscribed(self) -> list[str]:
        return [h["destination"] for c, h, b in self.frames if c == "SUBSCRIBE"]

    async def close(self):
        self.server.close()
        await self.server.wait_closed()


@pytest.fixture
async def broker():
    b = await FakeBroker().start()
    yield b
    await b.close()


async def _start(bus, codec, broker, **cfg):
    cfg.setdefault("envelope", True)
    running = await start_stomp_gateway(bus, GatewayConfig(S.GCS, scenario_query_attempts=0, **cfg), "127.0.0.1",
                                        broker.port, system_uuid=PLATFORM, codec=codec, settle_s=0)
    S.load_scenario(bus)
    await _wait(lambda: running.inbox._direct and len(broker.subs) == len(running.client._subs))
    return running


def _signal(state: str, rid: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ServiceConfigurationChangeRequest xmlns="https://www.vdl.afrl.af.mil/programs/oam">
<MessageData><RequestID><UUID>{rid}</UUID><DescriptiveLabel>harness</DescriptiveLabel></RequestID>
<RequestState>{state}</RequestState></MessageData></ServiceConfigurationChangeRequest>""".encode()


# ---------------------------------------------------------------- TC-GW-057 프레임·클라이언트
async def test_frame_encoding_roundtrip():
    r = asyncio.StreamReader()
    r.feed_data(b"\n\n" + encode_frame("MESSAGE", {"destination": "/topic/a:b", "x": "l1\nl2"}, b"<a>\x00</a>")
                + encode_frame("RECEIPT", {"receipt-id": "7"}))
    r.feed_eof()
    assert await read_frame(r) == ("MESSAGE", {"destination": "/topic/a:b", "x": "l1\nl2", "content-length": "8"},
                                   b"<a>\x00</a>")   # 머리 이스케이프, content-length로 NUL 포함 본문
    assert await read_frame(r) == ("RECEIPT", {"receipt-id": "7"}, b"")
    assert await read_frame(r) is None
    assert b"accept-version:1.2" in encode_frame("CONNECT", {"accept-version": "1.2", "host": "a:b"})
    assert b"host:a:b" in encode_frame("CONNECT", {"host": "a:b"})   # CONNECT 머리는 이스케이프하지 않는다


async def test_client_subscribe_send(broker):
    c = StompClient("127.0.0.1", broker.port)
    assert (await c.connect())["server"] == "fake/1"
    got = []
    await c.subscribe("/topic/X", lambda d, b, h: got.append((d, b)))
    await c.send("/topic/X", b"<x/>")
    await _wait(lambda: got == [("/topic/X", b"<x/>")])
    connect = broker.frames[0]
    assert connect[0] == "CONNECT" and connect[1]["accept-version"] == "1.2" and connect[1]["heart-beat"] == "0,0"
    await c.close()


# ---------------------------------------------------------------- TC-GW-058 구독·수신 (봉투)
async def test_subscriptions_and_inbound_envelope(broker, bus, codec):
    tx = []
    bus.subscribe("swarm/gcs-01/tx/c2/TaskCommand",
                  lambda s: tx.append(c2_pb2.TaskCommand.FromString(link_pb2.LinkEnvelope.FromString(s.payload).payload)
                                      .task_id))
    running = await _start(bus, codec, broker)
    gw = running.gateway
    try:
        assert broker.subscribed() == [f"/topic/{RX}", SIGNAL_START, SIGNAL_STOP]
        env = Envelopes(codec)
        rx = env.rx(_task_command(gw), originator=C2, receiver=PLATFORM, destinations=[PLATFORM])
        await broker.publish(f"/topic/{RX}", codec.to_xml_bytes(rx))
        await _wait(lambda: tx == ["task-5"])
        other = env.rx(_task_command(gw), originator=C2, receiver=PLATFORM, destinations=[C2])
        await broker.publish(f"/topic/{RX}", codec.to_xml_bytes(other))
        await _wait(lambda: gw.counters["envelope_not_addressed"] == 1)
        await broker.publish(f"/topic/{RX}", b"<not-xml")
        await _wait(lambda: gw.counters["ext_invalid"] == 1)
        assert tx == ["task-5"]
    finally:
        await running.stop()


async def test_messages_before_ready_are_held(broker, bus, codec, monkeypatch):
    """구독은 XSD 적재 전에 건다. 그동안 온 봉투는 쌓았다가 처리한다 (O-13과 같은 규칙)"""
    import swarm_gateway.runner as R
    env = Envelopes(codec)
    proto = R.Gateway(bus, GatewayConfig(S.GCS, envelope=True, scenario_query_attempts=0), codec=codec)
    body = codec.to_xml_bytes(env.rx(_task_command(proto), originator=C2, receiver=PLATFORM))
    real = R.Gateway

    def slow(*a, **k):
        while len(broker.subs) < 3:                                  # 브로커가 SUBSCRIBE를 다 처리할 때까지
            time.sleep(0.01)
        asyncio.run_coroutine_threadsafe(broker.publish(f"/topic/{RX}", body), loop).result(2)
        asyncio.run_coroutine_threadsafe(broker.publish(SIGNAL_START, _signal("NEW", C2)), loop).result(2)
        return real(*a, **k)

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(R, "Gateway", slow)
    running = await _start(bus, codec, broker)
    try:
        await _wait(lambda: running.gateway.counters["pre_ready_flushed"] == 1)
        assert running.inbox.held == 1
        await _wait(lambda: len(broker.sent(SIGNAL_ACK)) == 1)   # 준비 전 신호도 응답한다
    finally:
        await running.stop()


# ---------------------------------------------------------------- TC-GW-059 송신 XML
async def test_outbound_tx_envelope_xml_on_topic(broker, bus, codec):
    running = await _start(bus, codec, broker, envelope_destinations=(C2,))
    try:
        S.deliver(bus, S.task_status())
        await _wait(lambda: broker.sent(f"/topic/{TX}"))
        body = broker.sent(f"/topic/{TX}")[0]
        root = etree.fromstring(body)
        codec.validate_xml(root)
        assert root.tag == f"{NS}{TX}"
        uuids = [e.text for e in root.iter(f"{NS}UUID")]
        assert uuids and all(re.fullmatch(r"[0-9A-F]{32}", u) for u in uuids)   # 32자 hex
        assert uuid.UUID(root.findtext(f"{NS}MessageHeader/{NS}SystemID/{NS}UUID")) == uuid.UUID(PLATFORM)
        name, inner = Envelopes(codec).open_tx(codec.xml_to_json(root))
        assert name == "MA_TaskStatus"
        assert inner[name]["MessageHeader"]["SchemaVersion"] == "006.0.ASK"
    finally:
        await running.stop()


async def test_raw_mode_topics_by_uci_name(broker, bus, codec):
    running = await _start(bus, codec, broker, envelope=False)
    try:
        assert f"/topic/{RX}" not in broker.subscribed() and "/topic/MA_TaskCommand" in broker.subscribed()
        S.deliver(bus, S.task_status())
        await _wait(lambda: broker.sent("/topic/MA_TaskStatus"))
    finally:
        await running.stop()


# ---------------------------------------------------------------- TC-GW-060 신호 Ack
async def test_start_stop_signals_are_acked(broker, bus, codec):
    running = await _start(bus, codec, broker)
    rid = "0123456789abcdef0123456789abcdef"
    try:
        await broker.publish(SIGNAL_START, _signal("NEW", rid))
        await broker.publish(SIGNAL_STOP, _signal("CANCEL", rid))
        await _wait(lambda: len(broker.sent(SIGNAL_ACK)) == 2)
        states = []
        for body in broker.sent(SIGNAL_ACK):
            root = etree.fromstring(body)
            codec.validate_xml(root)
            assert root.tag == f"{NS}ServiceConfigurationChangeRequestStatus"
            assert root.findtext(f"{NS}MessageData/{NS}RequestID/{NS}UUID") == rid.upper()   # RequestID 그대로
            states.append(root.findtext(f"{NS}MessageData/{NS}RequestProcessingState"))
        assert states == ["COMPLETED", "CANCELED"]
        assert running.gateway.counters["signal_start"] == 1 and running.gateway.counters["signal_stop"] == 1
        await broker.publish(SIGNAL_START, b"garbage")           # 읽을 수 없어도 응답은 한다
        await _wait(lambda: len(broker.sent(SIGNAL_ACK)) == 3)
    finally:
        await running.stop()


# ---------------------------------------------------------------- TC-GW-061 5.0a 설정
async def test_schema_5_0a_excludes_and_version(broker, bus, codec):
    args = cli.build_parser().parse_args(["--gcs", S.GCS, "--transport", "stomp", "--schema-version", "005.0a.ASK"])
    assert cli.exclude_list(args) == ("MA_NavigationReport", "MA_Entity")
    running = await _start(bus, codec, broker, envelope=False, schema_version="005.0a.ASK",
                           exclude_messages=cli.exclude_list(args))
    try:
        S.deliver(bus, S.nav())
        S.deliver(bus, S.task_status())
        await _wait(lambda: broker.sent("/topic/MA_TaskStatus"))
        assert not broker.sent("/topic/MA_NavigationReport") and not broker.sent("/topic/MA_Entity")
        assert running.gateway.counters["excluded.MA_NavigationReport"] == 1
        root = etree.fromstring(broker.sent("/topic/MA_TaskStatus")[0])
        assert root.findtext(f"{NS}MessageHeader/{NS}SchemaVersion") == "005.0a.ASK"
    finally:
        await running.stop()


def test_cli_options():
    p = cli.build_parser()
    a = p.parse_args(["--gcs", S.GCS])
    assert a.transport == "lacal" and a.schema_version == "006.0.ASK" and cli.exclude_list(a) == ()
    a = p.parse_args(["--gcs", S.GCS, "--schema-version", "005.0a.ASK", "--exclude", "none"])
    assert cli.exclude_list(a) == ()
    a = p.parse_args(["--gcs", S.GCS, "--exclude", "MA_Entity", "--system-uuid", "0123456789ABCDEF0123456789ABCDEF"])
    assert cli.exclude_list(a) == ("MA_Entity",) and a.system_uuid == "01234567-89ab-cdef-0123-456789abcdef"
    assert cli.platform_uuid(S.GCS) == cli.platform_uuid(S.GCS) != cli.platform_uuid("gcs-02")
    assert cli.gateway_config(a).schema_version == "006.0.ASK"
