"""TC-GW-010, TC-GW-011: agra_lacal CAL Server(로컬 기동)와 왕복 시험

InMemoryBus ─rx─► Gateway ─OWP PUB─► CAL Server ─MSG─► 외부 C2 클라이언트(external_c2)
외부 C2 클라이언트 ─PUB MA_TaskCommand─► CAL Server ─MSG─► Gateway ─► swarm/gcs-01/tx/c2/TaskCommand
"""
import asyncio

import pytest
from swarm.v1 import c2_pb2, link_pb2

import samples as S
from conftest import CONFIG_DIR
from swarm_gateway.gateway import GatewayConfig
from swarm_gateway.lacal import CalError, LaCalClient
from swarm_gateway.mapping import MappingTable
from swarm_gateway.runner import start_gateway

from server.app import CalServer  # agra_lacal (lacal.py가 sys.path에 넣는다)
from server.config import load


@pytest.fixture
async def cal_server(codec):
    cfg = load(CONFIG_DIR / "lacal_server.yaml")
    cfg.port = 0
    cfg.admin_port = 0
    server = CalServer(cfg, codec)
    await server.start()
    yield server
    await server.stop()


async def _wait(cond, timeout=5.0):
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("timeout")
        await asyncio.sleep(0.02)


async def test_roundtrip_with_cal_server(cal_server, bus, codec):
    url = f"ws://127.0.0.1:{cal_server.port}"
    running = await start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec)
    gw = running.gateway
    ext = LaCalClient(url, "external_c2")
    await ext.connect()
    received: list[tuple[str, dict]] = []
    table = MappingTable.from_descriptors()
    for uci in S.EXPORT_SAMPLES:
        (entry,) = table.by_uci(uci)
        await ext.subscribe(uci, f"swarm.{entry.iface}", lambda n, obj: received.append((n, obj)))
    # uci_also (DEC-072): NavigationReport는 swarm.vi, PeerStatus는 swarm.p2p로 MA_PositionReport가 나간다
    for topic in sorted({f"swarm.{e.iface}" for e in table.by_uci("MA_PositionReport")}):
        await ext.subscribe("MA_PositionReport", topic, lambda n, obj: received.append((n, obj)))
    expected = sorted([*S.EXPORT_SAMPLES, *(u for also in S.ALSO.values() for u in also)])
    tx = []
    bus.subscribe("swarm/gcs-01/tx/c2/**", lambda s: tx.append(s))
    try:
        # 1단계: VI·C2·P2P·MS 상태 13종
        for make in S.EXPORT_SAMPLES.values():
            S.deliver(bus, make())
        await _wait(lambda: len(received) == len(expected))
        assert sorted(n for n, _ in received) == expected
        for n, obj in received:  # 서버가 다시 XML로 바꿔 검증한 메시지가 그대로 왔다
            codec.to_xml_bytes(obj)
            assert obj[n]["MessageHeader"]["SystemID"]["UUID"] == running.client.system_uuid
        assert gw.counters["sent"] == len(expected) and gw.counters["send_failed"] == 0
        positions = [o["MA_PositionReport"]["MessageData"] for n, o in received if n == "MA_PositionReport"]
        assert all(p["InertialState"]["Position"]["Altitude"] in (1500, 520) for p in positions)

        # EXT는 서버로 가지 않는다
        from test_export import _ext_messages
        for m in _ext_messages():
            S.deliver(bus, m)
        await asyncio.sleep(0.2)
        assert len(received) == len(expected)

        # 2단계: 외부 C2 → 내부 tx
        tc = c2_pb2.TaskCommand(task_id="task-ext-1", assignees=[S.UAV])
        tc.return_to_base.SetInParent()
        cmd = gw.envelope("MA_TaskCommand", gw.converters["swarm.v1.TaskCommand"].to_uci(tc, gw.ctx))
        await ext.publish("swarm.c2", cmd)
        await _wait(lambda: len(tx) == 1)
        env = link_pb2.LinkEnvelope.FromString(tx[0].payload)
        got = c2_pb2.TaskCommand.FromString(env.payload)
        assert tx[0].key == "swarm/gcs-01/tx/c2/TaskCommand"
        assert list(env.dst) == [S.UAV] and got.task_id == "task-ext-1" and got.HasField("return_to_base")

        # 잘못된 외부 메시지는 서버에서 거부되고 내부로 들어오지 않는다
        bad = gw.envelope("MA_TaskCommand", {"Command": []})
        with pytest.raises(CalError):
            await ext.publish("swarm.c2", bad)
        await asyncio.sleep(0.2)
        assert len(tx) == 1
    finally:
        await ext.close()
        await running.stop()


async def test_send_failure_is_counted_and_gateway_continues(cal_server, bus, codec):
    """TC-GW-011: LA-CAL이 거부한 PUB(허용되지 않은 토픽)는 세고, Gateway는 계속 동작한다"""
    url = f"ws://127.0.0.1:{cal_server.port}"
    running = await start_gateway(bus, GatewayConfig(S.GCS, topic_prefix="other"), url, codec=codec,
                                  inbound_topic="swarm.c2")
    gw = running.gateway
    try:
        S.deliver(bus, S.nav())
        S.deliver(bus, S.task_status())
        await _wait(lambda: gw.counters["send_failed"] == 3)   # nav는 MA_PositionReport까지 2건
        assert gw.counters["exported"] == 3 and gw.counters["sent"] == 0
        assert all(r.status == "send_failed" for r in gw.rejections)
        gw.config.topic_prefix = "swarm"
        S.deliver(bus, S.nav())
        await _wait(lambda: gw.counters["sent"] == 2)
    finally:
        await running.stop()


async def test_ready_is_logged_after_subscription(cal_server, bus, codec, caplog):
    """TC-GW-015 (O-13): 접속·XSD 적재·SUB 완료·ready 시점을 로그로 남긴다. ready는 SUB 뒤다"""
    import logging

    caplog.set_level(logging.INFO, logger="swarm_gateway")
    running = await start_gateway(bus, GatewayConfig(S.GCS), f"ws://127.0.0.1:{cal_server.port}", codec=codec)
    try:
        msgs = [r.getMessage() for r in caplog.records if r.name == "swarm_gateway"]
        order = [next(i for i, m in enumerate(msgs) if key in m)
                 for key in ("LA-CAL connected", "not ready yet", "XSD loaded", "SUB MA_TaskCommand@swarm.c2",
                             "ready at +")]
        assert order[0] == order[1] and order[1] < order[2] < order[3] < order[4]
        assert running.ready_after_s >= 0.0  # codec을 미리 적재한 시험이라 짧다
    finally:
        await running.stop()
