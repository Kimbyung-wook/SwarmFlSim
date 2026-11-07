"""TC-GW-009: Gateway는 swarm/<gcs>/rx/**만 구독하고 swarm/<gcs>/tx/c2/**에만 발행한다 (DEC-068)"""
import asyncio

import pytest
from swarm.v1 import truth_pb2
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

import samples as S


def test_subscribes_only_gcs_rx(gateway, bus):
    assert bus.subscribed == ["swarm/gcs-01/rx/**"]
    for prefix in ("truth/", "onboard/", "link/", "sim/"):
        assert not any(k.startswith(prefix) for k in bus.subscribed)


def test_ignores_truth_onboard_link_and_other_entities(gateway, bus, sent):
    frame = truth_pb2.TruthFrame()
    enc = protobuf_encoding(frame.DESCRIPTOR.full_name)
    bus.put(keys.TRUTH_STATE, frame.SerializeToString(), enc)
    bus.put(keys.onboard(S.UAV, "NavigationReport"), S.nav().SerializeToString(), enc)
    bus.put(keys.link_state("gcs-01", S.UAV), b"", enc)
    S.deliver(bus, S.nav(), dst="uav-002")            # 다른 엔티티의 rx
    bus.put(keys.tx(S.UAV, keys.Iface.VI, "NavigationReport"), S.envelope(S.nav()).SerializeToString(), enc)
    assert gateway.counters["rx"] == 0 and sent == []


def test_publishes_only_gcs_tx_c2(gateway, bus):
    from test_import import _task_command

    for m in S.EXPORT_SAMPLES.values():
        S.deliver(bus, m())
    gateway.handle_external("MA_TaskCommand", _task_command(gateway))
    own = [k for k in bus.published if not k.startswith("swarm/gcs-01/rx/")]   # 시험이 주입한 rx 제외
    assert own == ["swarm/gcs-01/tx/c2/TaskCommand"]


def test_cli_opens_bus_with_open_bus(monkeypatch):
    """진입점은 open_bus(BusConfig)로 버스를 연다 (DEC-026)"""
    import swarm_gateway.__main__ as cli

    seen = {}

    def fake_open_bus(cfg):
        seen["cfg"] = cfg
        from swarm_api import InMemoryBus
        return InMemoryBus()

    async def fake_start(bus, config, url, **kw):
        seen.update(gcs=config.gcs, url=url, **kw)
        raise asyncio.CancelledError

    monkeypatch.setattr(cli, "open_bus", fake_open_bus)
    monkeypatch.setattr(cli, "start_gateway", fake_start)
    args = cli.build_parser().parse_args(["--gcs", "gcs-01", "--lacal", "ws://127.0.0.1:9", "--bus", "memory"])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cli._run(args))
    assert seen["cfg"].backend == "memory"
    assert (seen["gcs"], seen["url"], seen["service_id"]) == ("gcs-01", "ws://127.0.0.1:9", "swarm_gateway")


def test_rejects_invalid_gcs_id():
    from swarm_gateway.gateway import GatewayConfig

    with pytest.raises(ValueError):
        GatewayConfig("GCS 1")
