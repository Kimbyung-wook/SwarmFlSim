"""TC-GW-044~046: 준비 전 외부 명령을 잃지 않는다 (QA O-13, IMP-GW-034)"""
import asyncio
import logging
import time

from swarm.v1 import c2_pb2, link_pb2

import samples as S
from swarm_gateway import runner
from swarm_gateway.gateway import Gateway, GatewayConfig
from swarm_gateway.lacal import LaCalClient
from swarm_gateway.runner import PreReadyInbox, start_gateway
from test_import import _task_command
from test_roundtrip import _wait, cal_server  # noqa: F401  (fixture)


def _cmd(gw, n, assignees=(S.UAV,)):
    tc = c2_pb2.TaskCommand(task_id=f"pre-{n}", assignees=list(assignees))
    tc.hold.SetInParent()
    return gw.envelope("MA_TaskCommand", gw.converters["swarm.v1.TaskCommand"].to_uci(tc, gw.ctx))


def _tx_ids(bus):
    got = []
    bus.subscribe("swarm/gcs-01/tx/c2/TaskCommand",
                  lambda s: got.append(c2_pb2.TaskCommand.FromString(link_pb2.LinkEnvelope.FromString(s.payload).payload)
                                       .task_id))
    return got


# ---------------------------------------------------------------- TC-GW-044
def test_inbox_keeps_order_and_limit(gateway, bus):
    tx = _tx_ids(bus)
    box = PreReadyInbox(limit=3)
    for n in range(5):
        box.on_message("MA_TaskCommand", _cmd(gateway, n))
    assert [o[2]["MA_TaskCommand"]["MessageData"]["Command"][0]["Capability"]["TaskID"]["DescriptiveLabel"]
            for o in box.queued] == ["pre-2", "pre-3", "pre-4"] and box.dropped == 2
    assert tx == []                                              # 준비 전에는 버스에 내지 않는다
    box.gateway = gateway
    outs = box.flush()
    assert [o.status for o in outs] == ["published"] * 3 and tx == ["pre-2", "pre-3", "pre-4"]
    assert gateway.counters["pre_ready_dropped"] == 2 and gateway.counters["pre_ready_flushed"] == 3
    box.on_message("MA_TaskCommand", _cmd(gateway, 9))           # 처리 뒤에는 바로 처리한다
    assert tx[-1] == "pre-9" and not box.queued


def test_settle_lets_reports_make_entities_known(bus, codec):
    """재기동 뒤 시나리오가 다시 오지 않아도(Core는 첫 틱 전만 재발행) 수신 보고로 알려진 기체가 된다"""
    gw = Gateway(bus, GatewayConfig(S.GCS), codec=codec, sink=lambda t, o: None)
    gw.start()
    try:
        tx = _tx_ids(bus)
        box = PreReadyInbox(gateway=gw)
        box.on_message("MA_TaskCommand", _cmd(gw, 1))
        S.deliver(bus, S.nav())                                   # 기다리는 동안 uav-001 보고
        assert [o.status for o in box.flush()] == ["published"] and tx == ["pre-1"]
        box2 = PreReadyInbox(gateway=gw)
        box2.on_message("MA_TaskCommand", _cmd(gw, 2, assignees=("uav-002",)))
        assert [o.status for o in box2.flush()] == ["rejected"]   # 보고도 시나리오도 없으면 D-35대로 거부
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-045
class _Ready(logging.Handler):
    def __init__(self, loop, key):
        super().__init__()
        self.loop, self.key, self.event = loop, key, asyncio.Event()

    def emit(self, record):
        if self.key in record.getMessage():
            self.loop.call_soon_threadsafe(self.event.set)


async def test_commands_during_xsd_load_are_not_lost(cal_server, bus, codec, monkeypatch):  # noqa: F811
    """실제 CAL Server: SUB 뒤 XSD 적재(느리게 흉내 낸 1 s) 동안 외부가 PUB한 명령이 순서대로 tx로 나간다"""
    class SlowGateway(Gateway):
        def __init__(self, *a, **kw):
            time.sleep(1.0)                                       # XSD 적재 흉내 (스레드에서 돈다)
            super().__init__(*a, **kw)

    monkeypatch.setattr(runner, "Gateway", SlowGateway)
    loop = asyncio.get_running_loop()
    sub = _Ready(loop, "receiving external commands")
    log = logging.getLogger("swarm_gateway")
    level = log.level
    log.setLevel(logging.INFO)
    log.addHandler(sub)
    url = f"ws://127.0.0.1:{cal_server.port}"
    ext = LaCalClient(url, "external_c2")
    await ext.connect()
    tx = _tx_ids(bus)
    maker = Gateway(bus, GatewayConfig(S.GCS), codec=codec, sink=lambda t, o: None)
    try:
        start = asyncio.create_task(start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec, admin_url=None,
                                                  settle_s=0.3))
        await asyncio.wait_for(sub.event.wait(), 5)
        for n in range(4):                                        # Gateway가 XSD를 적재하는 중
            await ext.publish("swarm.c2", _cmd(maker, n))
            await asyncio.sleep(0.1)
        assert not start.done() and tx == []
        running = await start
        S.load_scenario(bus)                                      # settle 안에 시나리오가 온다
        await _wait(lambda: len(tx) == 4)
        assert tx == [f"pre-{n}" for n in range(4)]
        assert running.inbox.held == 4 and running.gateway.counters["pre_ready_flushed"] == 4
        assert running.subscribed_after_s < 1.0 <= running.ready_after_s
        await ext.publish("swarm.c2", _cmd(maker, 9))             # 준비 뒤는 바로
        await _wait(lambda: len(tx) == 5)
    finally:
        log.removeHandler(sub)
        log.setLevel(level)
        maker.close()
        await ext.close()
        if start.done():
            await start.result().stop()


# ---------------------------------------------------------------- TC-GW-046
def test_subscription_set_does_not_need_xsd():
    """준비 전 SUB 목록(descriptor·변환기)이 XSD를 적재한 Gateway의 수신 목록과 같다"""
    from swarm_gateway.converters import load_converters
    from swarm_gateway.gateway import inbound_entries
    from swarm_gateway.mapping import MappingTable

    early = {e.uci_name for e in inbound_entries(MappingTable.from_descriptors(), load_converters())}
    assert early == {"MA_TaskCommand", "MA_ApprovalRequestStatus", "MA_RoutePlan", "MA_MissionPlan"}


def test_full_gateway_import_names_match(gateway):
    assert set(gateway.import_names()) == {"MA_TaskCommand", "MA_ApprovalRequestStatus", "MA_RoutePlan",
                                           "MA_MissionPlan"}
