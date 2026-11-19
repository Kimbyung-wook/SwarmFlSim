"""TC-GW-028~030: 변화 보고 마지막 값 보관과 늦게 붙은 외부 구독자 전달 (DEC-089, QA O-19)"""
import asyncio

import pytest
from swarm.v1 import c2_pb2, common_pb2, ms_pb2, vi_pb2

import samples as S
from swarm_gateway.gateway import GatewayConfig
from swarm_gateway.lacal import LaCalClient
from swarm_gateway.retain import LateJoinReplayer, RetainedReports, admin_url_for
from swarm_gateway.runner import start_gateway
from test_roundtrip import _wait, cal_server  # noqa: F401  (fixture)


def _retained_names(gw):
    return sorted(next(iter(o)) for u, t in gw.retained.targets() for o in gw.retained.latest(u, t))


# ---------------------------------------------------------------- TC-GW-028
def test_change_reports_are_retained_by_key(gateway, sent):
    """변화 보고만 키별 마지막 값으로 남는다. 주기 보고·사건성 메시지는 남지 않는다"""
    for make in S.EXPORT_SAMPLES.values():
        S.deliver(gateway.bus, make())
    # FlightCommandStatus는 보관하지 않는다: 끝 상태 뒤 다시 내지 않는다 (DEC-097)
    assert _retained_names(gateway) == sorted([
        "SystemStatus", "MA_FlightCapability", "MA_TaskStatus",
        "PO_Activity", "EA_Activity", "StrikeActivity", "StoreLoadoutConfiguration"])
    # NavigationReport·PeerStatus(주기)와 ApprovalRequest·LeaderUpdate·MA_Entity(사건)는 없다
    assert not gateway.retained.latest("MA_NavigationReport", "swarm.vi")
    assert not gateway.retained.latest("MA_PositionReport", "swarm.vi")
    assert not gateway.retained.latest("MA_Entity", "swarm.p2p")


def test_latest_value_replaces_and_keys_are_per_vehicle_and_item(gateway):
    ok = S.system_status()
    ok.health = vi_pb2.HEALTH_NOMINAL
    S.deliver(gateway.bus, S.system_status())
    S.deliver(gateway.bus, ok)                                   # 같은 기체: 덮어쓴다
    other = S.system_status()
    other.header.source = "uav-002"
    S.deliver(gateway.bus, other)                                # 다른 기체: 따로 둔다
    got = gateway.retained.latest("SystemStatus", "swarm.vi")
    assert [o["SystemStatus"]["MessageData"]["SystemState"] for o in got] == ["OPERATIONAL", "DEGRADED"]
    # 임무장비는 payload_id별, StrikeActivity는 무장별 (DEC-063)
    for pid in ("cam0", "cam1"):
        m = S.sensor_activity()
        m.payload_id = pid
        S.deliver(gateway.bus, m)
    for wpn in ("wpn-a", "wpn-b"):
        m = S.strike_activity()
        m.weapon_entity = wpn
        S.deliver(gateway.bus, m)
    assert len(gateway.retained.latest("PO_Activity", "swarm.ms")) == 2
    assert len(gateway.retained.latest("StrikeActivity", "swarm.ms")) == 2


def test_terminal_states_remove_the_key(gateway):
    """종료 상태를 받은 키는 지운다 (Agent 변화 보고와 같은 규칙, DEC-063·071)"""
    m = S.strike_activity()
    S.deliver(gateway.bus, m)
    m.state = ms_pb2.STRIKE_STATE_IMPACT
    S.deliver(gateway.bus, m)
    assert gateway.retained.latest("StrikeActivity", "swarm.ms") == []
    fcs = S.flight_command_status()
    fcs.state = common_pb2.COMMAND_STATE_EXECUTING
    S.deliver(gateway.bus, fcs)
    assert gateway.retained.latest("MA_FlightCommandStatus", "swarm.vi") == []   # 보관 안 함 (DEC-097)
    ts = S.task_status()
    S.deliver(gateway.bus, ts)
    ts.state = common_pb2.COMMAND_STATE_CANCELLED
    S.deliver(gateway.bus, ts)
    assert gateway.retained.latest("MA_TaskStatus", "swarm.c2") == []


def test_rejected_reports_are_not_retained(gateway, sent):
    """XSD 검증·변환에 실패해 내보내지 않은 보고는 남기지 않는다"""
    bad = S.sensor_activity()
    bad.boresight_ned.x = float("nan")                           # 비유한 값은 거부된다
    S.deliver(gateway.bus, bad)
    assert sent == [] and gateway.counters["rejected"] == 1
    assert gateway.retained.latest("PO_Activity", "swarm.ms") == []


def test_store_is_bounded():
    store = RetainedReports(limit=3)
    for i in range(5):
        m = S.system_status()
        m.header.source = f"uav-00{i}"
        store.note("swarm.v1.SystemStatus", "SystemStatus", "swarm.vi", m, {"SystemStatus": {"i": i}})
    assert [o["SystemStatus"]["i"] for o in store.latest("SystemStatus", "swarm.vi")] == [2, 3, 4]


# ---------------------------------------------------------------- TC-GW-029
async def test_replayer_replays_once_per_new_subscription():
    store = RetainedReports()
    m = S.system_status()
    store.note("swarm.v1.SystemStatus", "SystemStatus", "swarm.vi", m, {"SystemStatus": {}})
    out = []
    r = LateJoinReplayer("ws://127.0.0.1:1", store, lambda t, o: out.append((t, o)), debounce_s=0.01)

    def sub(eid, topic="swarm.vi", name="SystemStatus"):
        return {"kind": "sub", "id": eid, "source": f"topic:{topic}/{name}", "target": "svc:x:1"}

    r.on_event({"type": "snapshot", "graph": {"edges": []}})
    await asyncio.sleep(0.05)
    assert out == []                                             # 구독이 없으면 보내지 않는다
    r.on_event({"type": "edge_added", "edge": sub("sub:svc:x:1:s1")})
    r.on_event({"type": "edge_added", "edge": sub("sub:svc:x:2:s1")})   # 몰린 구독은 한 번으로 합친다
    r.on_event({"type": "edge_added", "edge": sub("sub:svc:x:3:s1", name="MA_TaskStatus", topic="swarm.c2")})
    await asyncio.sleep(0.05)
    assert out == [("swarm.vi", {"SystemStatus": {}})]           # 보관한 값이 없는 대상은 보내지 않는다
    r.on_event({"type": "snapshot", "graph": {"edges": [sub("sub:svc:x:1:s1"), sub("sub:svc:x:2:s1")]}})
    r.on_event({"type": "edge_added", "edge": {"kind": "pub", "id": "pub:svc:y", "source": "svc:y",
                                               "target": "topic:swarm.vi/SystemStatus"}})
    await asyncio.sleep(0.05)
    assert len(out) == 1                                         # 알던 구독·pub 간선은 다시 보내지 않는다
    r.on_event({"type": "edge_removed", "id": "sub:svc:x:1:s1"})
    r.on_event({"type": "edge_added", "edge": sub("sub:svc:x:1:s1")})   # 다시 구독하면 다시 보낸다
    await asyncio.sleep(0.05)
    assert len(out) == 2 and r.replayed == 2
    await r.stop()


async def test_replayer_resyncs_remote_graph(monkeypatch):
    """다른 CAL Server의 구독(remote_updated)은 GET /graph로 다시 읽는다"""
    store = RetainedReports()
    store.note("swarm.v1.SystemStatus", "SystemStatus", "swarm.vi", S.system_status(), {"SystemStatus": {}})
    out = []
    r = LateJoinReplayer("ws://127.0.0.1:1", store, lambda t, o: out.append(t), debounce_s=0.01)
    graph = {"edges": [{"kind": "sub", "id": "sub:svc:calsrv-b:1:s1", "source": "topic:swarm.vi/SystemStatus"}]}
    import urllib.request

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json
            return json.dumps(graph).encode()

    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: (seen.append(url), Resp())[1])
    r.on_event({"type": "remote_updated", "remote_server_id": "calsrv-b"})
    await _wait(lambda: out == ["swarm.vi"], timeout=2)
    assert seen == ["http://127.0.0.1:1/graph"]
    await r.stop()


def test_admin_url_default():
    assert admin_url_for("ws://10.0.0.5:8765") == "ws://10.0.0.5:8766"
    assert admin_url_for("wss://cal.example:443") == "wss://cal.example:8766"


# ---------------------------------------------------------------- TC-GW-030
async def test_late_external_subscriber_gets_latest_reports(cal_server, bus, codec):  # noqa: F811
    """실제 CAL Server: 외부 시스템이 보고 뒤에 구독해도 현재 상태를 받는다. 평소 보고량은 늘지 않는다"""
    url = f"ws://127.0.0.1:{cal_server.port}"
    running = await start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec,
                                  admin_url=f"ws://127.0.0.1:{cal_server.admin_port}")
    gw = running.gateway
    await asyncio.wait_for(running.replayer.connected.wait(), 5)
    early = LaCalClient(url, "external_c2")
    late = LaCalClient(url, "external_c2")
    await early.connect()
    got_early, got_late = [], []
    try:
        await early.subscribe("SystemStatus", "swarm.vi", lambda n, o: got_early.append(o))
        degraded = S.system_status()
        S.deliver(bus, degraded)
        nominal = S.system_status()
        nominal.health = vi_pb2.HEALTH_NOMINAL
        S.deliver(bus, nominal)                                  # 마지막 값만 남는다
        S.deliver(bus, S.flight_capability())                    # 시작 시 1회 (O-19)
        await _wait(lambda: len(got_early) == 2 and gw.counters["sent"] == 3)
        assert gw.counters["replayed"] == 0                      # 새 구독이 없으면 다시 보내지 않는다

        await late.connect()
        await late.subscribe("SystemStatus", "swarm.vi", lambda n, o: got_late.append(o))
        await late.subscribe("MA_FlightCapability", "swarm.vi", lambda n, o: got_late.append(o))
        await _wait(lambda: len(got_late) == 2)
        names = sorted(next(iter(o)) for o in got_late)
        assert names == ["MA_FlightCapability", "SystemStatus"]
        status = next(o for o in got_late if "SystemStatus" in o)["SystemStatus"]["MessageData"]
        assert status["SystemState"] == "OPERATIONAL"                # 마지막 값 (NOMINAL)
        assert gw.counters["replayed"] == 2
        # 다시 PUB한 값은 같은 토픽의 기존 구독자에게도 한 번 간다
        await _wait(lambda: len(got_early) == 3)
        await asyncio.sleep(0.3)
        assert len(got_late) == 2 and gw.counters["replayed"] == 2   # 주기적으로 다시 보내지 않는다
    finally:
        await late.close()
        await early.close()
        await running.stop()


async def test_replay_can_be_disabled_and_missing_admin_is_tolerated(cal_server, bus, codec, caplog):  # noqa: F811
    import logging

    caplog.set_level(logging.WARNING, logger="swarm_gateway")
    url = f"ws://127.0.0.1:{cal_server.port}"
    off = await start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec, admin_url=None)
    assert off.replayer is None
    await off.stop()
    bad = await start_gateway(bus, GatewayConfig(S.GCS), url, codec=codec, admin_url="ws://127.0.0.1:9")
    try:
        await _wait(lambda: any("admin" in r.getMessage() and "unavailable" in r.getMessage()
                                for r in caplog.records))
        S.deliver(bus, S.system_status())                        # 관리 포트가 없어도 1단계는 그대로 돈다
        await _wait(lambda: bad.gateway.counters["sent"] == 1)
    finally:
        await bad.stop()


def test_cli_lacal_admin_option(monkeypatch):
    import swarm_gateway.__main__ as cli

    seen = {}

    async def fake_start(bus, config, url, **kw):
        seen.update(kw)
        raise asyncio.CancelledError

    monkeypatch.setattr(cli, "start_gateway", fake_start)
    for argv, want in ((["--gcs", "gcs-01", "--bus", "memory"], ""),
                       (["--gcs", "gcs-01", "--bus", "memory", "--lacal-admin", "none"], None),
                       (["--gcs", "gcs-01", "--bus", "memory", "--lacal-admin", "ws://h:1"], "ws://h:1")):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(cli._run(cli.build_parser().parse_args(argv)))
        assert seen["admin_url"] == want
