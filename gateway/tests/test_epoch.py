"""TC-GW-042~043: UCI 시각 기준 = 시나리오 기준 시각 (DEC-098, 계약 0.20.0 §1, IMP-GW-033)"""
import datetime as dt

from swarm.v1 import sim_pb2

import samples as S
from swarm_gateway.converters.base import SimClock
from swarm_gateway.gateway import Gateway, GatewayConfig
from swarm_gateway.lacal import uci_timestamp
from test_qa29 import FakeWall, _iter_timestamps

UTC = dt.timezone.utc
E1 = dt.datetime(2026, 1, 1, tzinfo=UTC)
E2 = dt.datetime(2026, 3, 1, 12, tzinfo=UTC)


def _us(t: dt.datetime) -> int:
    return int((t - dt.datetime(1970, 1, 1, tzinfo=UTC)).total_seconds() * 1_000_000)


def _gw(bus, codec, sent, **cfg):
    gw = Gateway(bus, GatewayConfig(S.GCS, **cfg), codec=codec, sink=lambda t, o: sent.append(o))
    gw.clock.wall = FakeWall()
    gw.start()
    return gw


def _nav_at(bus, sim_s: float):
    m = S.nav()
    m.header.sim_time_us = int(sim_s * 1_000_000)
    S.deliver(bus, m)


def _stamps(sent):
    return {ts for o in sent for _, ts in _iter_timestamps(o)}


# ---------------------------------------------------------------- TC-GW-042 우선순위
def test_scenario_epoch_is_used(bus, codec):
    sent = []
    gw = _gw(bus, codec, sent)
    try:
        S.load_scenario(bus, epoch_utc_us=_us(E1))
        _nav_at(bus, 2.5)
        assert _stamps(sent) == {uci_timestamp(E1 + dt.timedelta(seconds=2.5))}
        assert gw.clock.source == SimClock.SCENARIO and gw.counters["epoch_set"] == 1
    finally:
        gw.close()


def test_sim_epoch_overrides_scenario(bus, codec):
    sent = []
    gw = _gw(bus, codec, sent, sim_epoch=E2)
    try:
        S.load_scenario(bus, epoch_utc_us=_us(E1))
        _nav_at(bus, 1)
        assert _stamps(sent) == {uci_timestamp(E2 + dt.timedelta(seconds=1))}
        assert gw.clock.source == SimClock.OVERRIDE and gw.counters["epoch_set"] == 0
    finally:
        gw.close()


def test_zero_epoch_keeps_first_message_base(bus, codec, caplog):
    """시나리오 값이 0이면(옛 Core) 첫 메시지 벽시계 기준을 쓰고 로그에 남긴다"""
    sent = []
    gw = _gw(bus, codec, sent)
    try:
        S.load_scenario(bus)
        with caplog.at_level("WARNING", logger="swarm_gateway"):
            _nav_at(bus, 4)
        assert gw.clock.source == SimClock.FIRST and "no scenario epoch" in caplog.text
        assert _stamps(sent) == {uci_timestamp(FakeWall().t)}
    finally:
        gw.close()


# ---------------------------------------------------------------- TC-GW-043 바뀔 때
def test_first_message_base_switches_to_scenario(bus, codec, caplog):
    """시나리오 전에 첫 메시지로 정했어도 시나리오 값이 오면 그 값으로 바꾸고 차이를 경고한다"""
    sent = []
    gw = _gw(bus, codec, sent)
    try:
        _nav_at(bus, 1)                                         # 시나리오 전: 벽시계 기준
        assert gw.clock.source == SimClock.FIRST
        with caplog.at_level("WARNING", logger="swarm_gateway"):
            S.load_scenario(bus, epoch_utc_us=_us(E1))
        assert "time base changed" in caplog.text and gw.counters["epoch_changed"] == 1
        sent.clear()
        for s in (2, 3, 30):                                    # 그 뒤로는 (Timestamp − 모의 시각) 일정
            _nav_at(bus, s)
        assert _stamps(sent) == {uci_timestamp(E1 + dt.timedelta(seconds=s)) for s in (2, 3, 30)}
    finally:
        gw.close()


def test_new_scenario_rebases_same_does_not(bus, codec):
    sent = []
    gw = _gw(bus, codec, sent)
    try:
        S.load_scenario(bus, epoch_utc_us=_us(E1))
        S.load_scenario(bus, epoch_utc_us=_us(E1))                       # Core 재발행: 그대로
        assert gw.counters["epoch_set"] == 1 and gw.counters["epoch_changed"] == 0
        S.load_scenario(bus, "uav-002", name="next", epoch_utc_us=_us(E2))   # 새 적재: 다시 정함
        assert gw.clock.epoch == E2 and gw.counters["epoch_changed"] == 1
        S.load_scenario(bus, name="no-epoch")                            # 0: 그대로 둔다
        assert gw.clock.epoch == E2
        _nav_at(bus, 1)
        assert _stamps(sent) == {uci_timestamp(E2 + dt.timedelta(seconds=1))}
    finally:
        gw.close()


def test_sim_clock_scenario_unit():
    c = SimClock(wall=FakeWall())
    assert c.on_scenario_epoch(0) is None and c.source is None
    assert c.on_scenario_epoch(_us(E1)) == "set" and c.utc(0) == E1
    assert c.on_scenario_epoch(_us(E1)) is None
    assert c.on_scenario_epoch(_us(E2)) == "changed" and c.changes == 1
    o = SimClock(E2)
    assert o.on_scenario_epoch(_us(E1)) is None and o.epoch == E2
    assert sim_pb2.RunSpec.DESCRIPTOR.fields_by_name["epoch_utc_us"].number == 7
