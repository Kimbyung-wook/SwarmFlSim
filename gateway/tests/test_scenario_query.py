"""TC-GW-047~051: 시작 때 시나리오 조회 (DEC-109, 계약 0.24.0, QA O-53, IMP-GW-035).

메모리 버스에서 Core 응답자(`bus.serve(sim/ctrl/scenario)`)를 흉내 낸다.
"""
import logging

from swarm.v1 import entity_pb2
from swarm_api import keys
from swarm_api.bus import Sample, protobuf_encoding

import samples as S
from conftest import RecordingBus
from swarm_gateway.gateway import Gateway, GatewayConfig
from test_epoch import E1, E2, _nav_at, _us
from test_import import _task_command
from test_qa29 import FakeWall

ENC = protobuf_encoding("swarm.v1.Scenario")


def _core(bus, payload: bytes):
    """Core 응답자: 적재된 시나리오를 조회에 답한다"""
    calls = []

    def handler(key):
        calls.append(key)
        return [Sample(keys.SIM_CTRL_SCENARIO, payload, ENC)]
    return bus.serve(keys.SIM_CTRL_SCENARIO, handler), calls


def _gw(bus, codec, sent=None, **cfg):
    cfg.setdefault("scenario_query_interval_s", 0.02)
    gw = Gateway(bus, GatewayConfig(S.GCS, **cfg), codec=codec,
                 sink=lambda t, o: sent.append(o) if sent is not None else None)
    gw.clock.wall = FakeWall()
    return gw


def _cmd(gw, *assignees):
    return gw.handle_external("MA_TaskCommand", _task_command(gw, assignees=assignees)).status


# ---------------------------------------------------------------- TC-GW-047
def test_missed_publication_is_fetched_by_query(bus, codec):
    """Core가 첫 틱 전 재발행을 끝낸 뒤 Gateway가 시작해도 조회로 시나리오를 받는다"""
    S.load_scenario(bus, "uav-002", epoch_utc_us=_us(E1))          # 구독자 없이 지나간 발행
    srv, calls = _core(bus, S.scenario_bytes("uav-002", epoch_utc_us=_us(E1)))
    gw = _gw(bus, codec)
    gw.start()
    try:
        gw.wait_scenario_query(2)
        assert bus.subscribed.index(keys.SIM_CTRL_SCENARIO) >= 0 and len(calls) == 1   # 구독 뒤 한 번 조회
        assert gw.counters["scenario_by_query"] == 1 and gw.counters["scenario_query"] == 1
        assert gw.entities.snapshot()["scenario"] == ["uav-002"]
        assert gw.clock.source == "scenario" and gw.clock.epoch == E1 and gw.counters["epoch_set"] == 1
    finally:
        gw.close()
        srv.close()


def test_subscription_is_opened_before_query(codec):
    order = []

    class Bus(RecordingBus):
        def subscribe(self, keyexpr, callback):
            order.append(("sub", keyexpr))
            return super().subscribe(keyexpr, callback)

        def get(self, keyexpr, timeout_s=1.0):
            order.append(("get", keyexpr))
            return super().get(keyexpr, timeout_s)

    bus = Bus()
    srv, _ = _core(bus, S.scenario_bytes())
    gw = _gw(bus, codec)
    gw.start()
    gw.wait_scenario_query(2)
    gw.close()
    srv.close()
    assert order.index(("sub", keys.SIM_CTRL_SCENARIO)) < order.index(("get", keys.SIM_CTRL_SCENARIO))


# ---------------------------------------------------------------- TC-GW-048
def test_query_and_subscription_duplicate_is_idempotent(bus, codec):
    """같은 시나리오를 조회·구독(1 s 재발행)으로 여러 번 받아도 한 번만 반영한다. 다른 시나리오는 기존 규칙"""
    payload = S.scenario_bytes(S.UAV, epoch_utc_us=_us(E1))
    srv, _ = _core(bus, payload)
    gw = _gw(bus, codec)
    gw.start()
    try:
        gw.wait_scenario_query(2)
        S.deliver(bus, S.nav())                                     # uav-001 보고
        before = gw.entities.snapshot()
        for _ in range(3):                                          # Core 재발행
            bus.put(keys.SIM_CTRL_SCENARIO, payload, ENC)
        assert gw.query_scenario() is True                          # 조회를 다시 해도
        assert gw.entities.snapshot() == before                     # 보고 목록을 비우지 않는다
        assert gw.counters["scenario_duplicate"] == 3 and gw.counters["scenario_by_query"] == 1
        assert gw.counters["scenario_by_subscription"] == 0
        assert gw.counters["epoch_set"] == 1 and gw.counters["epoch_changed"] == 0 and gw.clock.changes == 0
        S.load_scenario(bus, "uav-002", epoch_utc_us=_us(E2))      # 재적재: 다른 시나리오
        assert gw.counters["scenario_by_subscription"] == 1 and gw.counters["epoch_changed"] == 1
        assert gw.entities.snapshot() == {"scenario": ["uav-002"], "reported": []}
        assert gw.clock.epoch == E2
    finally:
        gw.close()
        srv.close()


# ---------------------------------------------------------------- TC-GW-049
def test_no_responder_retries_then_publication_stops_query(codec):
    """응답자가 없으면 간격을 두고 다시 조회하고, 그 사이 구독으로 받으면 조회를 멈춘다"""
    gets = []

    class Bus(RecordingBus):
        def get(self, keyexpr, timeout_s=1.0):
            gets.append(timeout_s)
            if len(gets) == 2:
                S.load_scenario(self, "uav-002")                    # 두 번째 조회 중 Core 발행이 온다
            return super().get(keyexpr, timeout_s)

    bus = Bus()
    gw = _gw(bus, codec, scenario_query_attempts=5, scenario_query_timeout_s=0.3)
    gw.start()
    try:
        gw.wait_scenario_query(2)
        assert gets == [0.3, 0.3]                                   # 세 번째는 하지 않는다
        assert gw.counters["scenario_query"] == 2 and gw.counters["scenario_by_subscription"] == 1
        assert gw.counters["scenario_query_none"] == 0 and gw.entities.known("uav-002")
    finally:
        gw.close()


def test_no_responder_gives_up_after_attempts(bus, codec, caplog):
    gw = _gw(bus, codec, scenario_query_attempts=3)
    with caplog.at_level(logging.WARNING, logger="swarm_gateway"):
        gw.start()
        gw.wait_scenario_query(2)
    try:
        assert gw.counters["scenario_query"] == 3 and gw.counters["scenario_query_none"] == 1
        assert any("no scenario after 3 queries" in r.getMessage() for r in caplog.records)
        S.load_scenario(bus, "uav-002")                             # 그 뒤 발행으로도 받는다
        assert gw.entities.known("uav-002") and gw.counters["scenario_by_subscription"] == 1
    finally:
        gw.close()


def test_query_disabled_and_close_stops_waiting(bus, codec):
    gw = _gw(bus, codec, scenario_query_attempts=0)
    gw.start()
    assert gw._query_thread is None and gw.counters["scenario_query"] == 0
    gw.close()
    gw2 = _gw(bus, codec, scenario_query_attempts=100, scenario_query_interval_s=10.0)
    gw2.start()
    gw2.close()                                                     # 간격 대기 중에도 바로 끝난다
    gw2.wait_scenario_query(2)
    assert not gw2._query_thread.is_alive() and gw2.counters["scenario_query"] <= 2


def test_query_error_keeps_subscription(codec):
    class Bus(RecordingBus):
        def get(self, keyexpr, timeout_s=1.0):
            raise RuntimeError("no route")

    bus = Bus()
    gw = _gw(bus, codec, scenario_query_attempts=2)
    gw.start()
    try:
        gw.wait_scenario_query(2)
        assert gw.counters["scenario_query_error"] == 2
        S.load_scenario(bus)
        assert gw.entities.known(S.UAV)
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-050
def test_known_entities_use_queried_list(bus, codec):
    """알려진 기체 확인(IMP-GW-029)이 조회로 받은 시나리오 목록을 쓴다"""
    srv, _ = _core(bus, S.scenario_bytes("uav-002", "uav-003",
                                         others=(("tgt-001", entity_pb2.ENTITY_KIND_GROUND_TARGET),)))
    gw = _gw(bus, codec)
    gw.start()
    try:
        gw.wait_scenario_query(2)
        assert gw.counters["scenario_by_query"] == 1 and gw.counters["rx"] == 0   # 보고 없이
        assert _cmd(gw, "uav-002", "uav-003") == "published"
        assert _cmd(gw, S.UAV) == "rejected"                        # 조회한 목록에 없다
        assert _cmd(gw, "tgt-001") == "rejected"
    finally:
        gw.close()
        srv.close()


# ---------------------------------------------------------------- TC-GW-051
def test_first_message_base_switch_is_logged(bus, codec, caplog):
    """첫 메시지 기준으로 낸 뒤 조회로 시나리오가 오면 기준을 바꾸고, 바뀐 시점(앞 기준 경과·모의 시각)을 남긴다"""
    sent = []
    gw = _gw(bus, codec, sent, scenario_query_attempts=0)
    t = [100.0]
    gw.clock.mono = lambda: t[0]
    gw.start()
    try:
        _nav_at(bus, 0.2)                                           # 시나리오 전 첫 메시지: 첫 메시지 기준
        assert gw.clock.source == "first_message"
        t[0] += 0.515
        _nav_at(bus, 0.7)
        srv, _ = _core(bus, S.scenario_bytes(epoch_utc_us=_us(E1)))
        gw.config.scenario_query_attempts = 1
        with caplog.at_level(logging.WARNING, logger="swarm_gateway"):
            assert gw.query_scenario() is True
        ch = gw.clock.last_change
        assert ch["old_source"] == "first_message" and ch["via"] == "query"
        assert abs(ch["after_s"] - 0.515) < 1e-9 and ch["sim_s"] == 0.7 and ch["new"] == E1
        msg = [r.getMessage() for r in caplog.records if "time base changed" in r.getMessage()]
        assert len(msg) == 1 and "by query" in msg[0] and "0.515 s on first_message base" in msg[0]
        assert "last sim 0.700 s" in msg[0]
        assert gw.counters["epoch_changed"] == 1
        srv.close()
    finally:
        gw.close()


def test_override_still_wins_over_queried_scenario(bus, codec):
    """우선순위 그대로: --sim-epoch > 시나리오(조회·구독) > 첫 메시지"""
    srv, _ = _core(bus, S.scenario_bytes(epoch_utc_us=_us(E2)))
    gw = _gw(bus, codec, sim_epoch=E1)
    gw.start()
    try:
        gw.wait_scenario_query(2)
        assert gw.counters["scenario_by_query"] == 1
        assert gw.clock.source == "override" and gw.clock.epoch == E1 and gw.clock.changes == 0
    finally:
        gw.close()
        srv.close()
