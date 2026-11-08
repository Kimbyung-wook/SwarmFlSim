"""TC-AGT-063~069: 기체 VI 상태 GCS 자동 보고 (IMP-AGT-032, DEC-071, DEC-056, DEC-044)"""

import pytest

from swarm.v1 import common_pb2, link_pb2, vi_pb2
from swarm_agent.cli import parse_args
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

S = common_pb2


def vi_rx(h: Harness) -> list[tuple[str, int, int, object]]:
    """GCS가 받은 swarm/gcs-01/rx/vi/* 의 (메시지, 송신 모의 시각, seq, 메시지)"""
    out: list = []

    def on(s):
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        name = env.msg_type.rsplit(".", 1)[1]
        out.append((name, env.header.sim_time_us, env.header.seq,
                    getattr(vi_pb2, name).FromString(env.payload)))
    h.bus.subscribe(keys.rx("gcs-01", keys.Iface.VI, "*"), on)
    return out


def names(rx, name: str) -> list:
    return [r for r in rx if r[0] == name]


def put_status(h: Harness, energy: float, eid: str = "uav-001") -> None:
    m = vi_pb2.SystemStatus(health=vi_pb2.HEALTH_NOMINAL, energy_frac=energy)
    m.header.source = eid
    m.header.frame = h.core.frame          # 헤더만 다른 값은 변화가 아니다
    h.bus.put(keys.onboard(eid, "SystemStatus"), m.SerializeToString(), protobuf_encoding(m.DESCRIPTOR.full_name))


def test_tc_agt_063_nav_report_1hz():
    h = Harness(make_scenario(2, "hold"))
    rx = vi_rx(h)
    h.run_s(5.0)                           # 0~4.98 s: 경계 0,1,2,3,4 s
    for eid in ("uav-001", "uav-002"):
        nav = [r for r in names(rx, "NavigationReport") if r[3].header.source == eid]
        assert [t for _, t, _, _ in nav] == [0, 1_000_000, 2_000_000, 3_000_000, 4_000_000]
        assert [seq for _, _, seq, _ in nav] == [0, 1, 2, 3, 4]     # tx 키별 seq (DEC-051과 같은 경로)


def test_tc_agt_064_nav_report_off_and_rate():
    h = Harness(make_scenario(1, "hold"))
    h.rt.config.vi_report_hz = 0
    rx = vi_rx(h)
    h.run_s(3.0)
    assert names(rx, "NavigationReport") == []
    assert len(names(rx, "FlightCapability")) == 1                # 끄는 것은 NavigationReport뿐
    h2 = Harness(make_scenario(1, "hold"))
    h2.rt.config.vi_report_hz = 5.0
    rx2 = vi_rx(h2)
    h2.run_s(2.0)
    assert len(names(rx2, "NavigationReport")) == 10
    assert parse_args([]).vi_report_hz == 1.0
    assert parse_args(["--vi-report-hz", "0"]).vi_report_hz == 0.0


def test_tc_agt_065_system_status_on_change_with_rate_limit():
    h = Harness(make_scenario(1, "hold"))
    rx = vi_rx(h)
    h.core.step(5)
    assert names(rx, "SystemStatus") == []                        # 받은 상태가 없으면 보내지 않는다
    put_status(h, 0.9)
    h.core.step(1)
    put_status(h, 0.9)                     # 같은 값: 다시 보내지 않는다
    h.core.step(1)
    put_status(h, 0.8)                     # 0.1 s 상한으로 미룸
    h.core.step(1)
    put_status(h, 0.7)                     # 미룬 동안 최신 값 갱신
    h.core.step(1)
    assert [r[3].energy_frac for r in names(rx, "SystemStatus")] == [0.9]
    h.core.step(5)
    st = names(rx, "SystemStatus")
    assert [r[3].energy_frac for r in st] == [0.9, 0.7]
    assert st[1][1] - st[0][1] == 100_000
    h.run_s(3.0)                           # 주기 전체 보고는 없다
    assert len(names(rx, "SystemStatus")) == 2


def hsa(cmd_id: str, hdg: float) -> vi_pb2.FlightCommand:
    c = vi_pb2.FlightCommand(command_id=cmd_id)
    c.hsa.heading_deg = hdg
    return c


def test_tc_agt_066_flight_command_status_on_change():
    """FA 상태는 MA 포트(VIPort.command → FA.on_command)와 FA.pending_status 두 곳에서 나온다"""
    h = Harness(make_scenario(1, "hold"))
    raw = vi_rx(h)

    def mine(rx=raw):                          # hold MA 자신의 명령(uav-001-hold)은 빼고 본다
        return [r for r in rx if r[0] == "FlightCommandStatus" and r[3].command_id in ("c1", "c2", "c3")]
    v = h.rt.vehicles["uav-001"]
    h.core.step(55)
    v.ports.vi.command(hsa("c1", 90.0))      # c1 ACCEPTED
    h.core.step(1)                            # 보고 t0
    t0 = mine()[0][1]
    v.ports.vi.command(hsa("c2", 180.0))     # c2 ACCEPTED, 다음 FA 단계에 c1 CANCELLED
    h.core.step(1)                            # c2는 새 키라 바로
    h.core.step(1)                            # c1 CANCELLED: c1 키 상한(0.1 s)으로 미룸
    got = [(m.command_id, m.state) for _, _, _, m in mine()]
    assert got == [("c1", S.COMMAND_STATE_ACCEPTED), ("c2", S.COMMAND_STATE_ACCEPTED)]
    h.core.step(5)
    fcs = mine()
    assert (fcs[2][3].command_id, fcs[2][3].state, fcs[2][1] - t0) == ("c1", S.COMMAND_STATE_CANCELLED, 100_000)
    v.ports.vi.command(vi_pb2.FlightCommand(command_id="c3"))   # 모드 없음: REJECTED
    assert [st.command_id for st in v.ports.vi.command_status()] == ["c3"]   # MA가 읽는 상태는 보고가 가로채지 않는다
    h.core.step(1)
    assert (fcs := mine())[-1][3].state == S.COMMAND_STATE_REJECTED
    h.run_s(2.0)                              # 주기 전체 보고는 없다
    assert [(m.command_id, m.state) for _, _, _, m in mine()] == [
        ("c1", S.COMMAND_STATE_ACCEPTED), ("c2", S.COMMAND_STATE_ACCEPTED), ("c1", S.COMMAND_STATE_CANCELLED),
        ("c2", S.COMMAND_STATE_EXECUTING), ("c3", S.COMMAND_STATE_REJECTED)]   # 바뀔 때만, 주기 재전송 없음
    done = {("FlightCommandStatus", c, "") for c in ("c1", "c3")}
    assert not done & set(v.vi_reports.state)      # 종료 상태를 보낸 키는 지운다
    assert not done & set(v.vi_reports.sent)


def test_tc_agt_067_flight_capability_once():
    h = Harness(make_scenario(2, "hold"))
    rx = vi_rx(h)
    h.run_s(3.0)
    cap = names(rx, "FlightCapability")
    assert sorted(r[3].header.source for r in cap) == ["uav-001", "uav-002"]
    assert all(r[1] == 0 for r in cap)
    v = h.rt.vehicles["uav-001"]
    assert cap[0][3].max_speed_mps == v.capability.max_speed_mps > 0


@pytest.mark.parametrize("ma", ["hold", "waypoint", "flocking", "formation", "legacy"])
def test_tc_agt_068_independent_of_ma_plugin(ma):
    h = Harness(make_scenario(2, ma))
    rx = vi_rx(h)
    h.run_s(2.0)
    for eid in ("uav-001", "uav-002"):
        assert len([r for r in names(rx, "NavigationReport") if r[3].header.source == eid]) == 2, ma
        assert len([r for r in names(rx, "FlightCapability") if r[3].header.source == eid]) == 1, ma


def test_tc_agt_069_lockstep_deterministic():
    def run() -> list[tuple[str, int, int, bytes]]:
        h = Harness(make_scenario(3, "waypoint"))
        rx = vi_rx(h)
        h.core.step(30)
        put_status(h, 0.5, "uav-002")
        h.run_s(3.0)
        return [(n, t, seq, m.SerializeToString(deterministic=True)) for n, t, seq, m in rx]
    a, b = run(), run()
    assert a and a == b
