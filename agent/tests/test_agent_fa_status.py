"""TC-AGT-070~074: 비행 명령 갱신이 상태를 뒤로 돌리지 않음 (IMP-AGT-033, D-28, DEC-071)"""

from swarm.v1 import common_pb2, link_pb2, vi_pb2
from swarm_agent.fa import DefaultFlightAutonomy
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys

S = common_pb2
RANK = {S.COMMAND_STATE_ACCEPTED: 1, S.COMMAND_STATE_EXECUTING: 2, S.COMMAND_STATE_COMPLETED: 3,
        S.COMMAND_STATE_FAILED: 3, S.COMMAND_STATE_CANCELLED: 3, S.COMMAND_STATE_REJECTED: 3}


def hsa(cmd_id: str, hdg: float = 90.0) -> vi_pb2.FlightCommand:
    c = vi_pb2.FlightCommand(command_id=cmd_id)
    c.hsa.heading_deg = hdg
    return c


def nav() -> vi_pb2.NavigationReport:
    n = vi_pb2.NavigationReport()
    k = n.kinematics
    k.position.lat_deg, k.position.lon_deg, k.position.alt_m = 37.5, 128.0, 1500.0
    k.velocity_ned_mps.x = 22.0
    return n


def make_fa() -> DefaultFlightAutonomy:
    fa = DefaultFlightAutonomy()
    fa.on_init("uav-001", {})
    return fa


def fcs_rx(h: Harness) -> list[tuple[int, str, int]]:
    """GCS가 받은 FlightCommandStatus의 (송신 모의 시각, command_id, 상태)"""
    out: list = []

    def on(s):
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        m = vi_pb2.FlightCommandStatus.FromString(env.payload)
        out.append((env.header.sim_time_us, m.command_id, m.state))
    h.bus.subscribe(keys.rx("gcs-01", keys.Iface.VI, "FlightCommandStatus"), on)
    return out


def test_tc_agt_070_update_while_executing_keeps_executing():
    fa = make_fa()
    assert fa.on_command(hsa("a")).state == S.COMMAND_STATE_ACCEPTED
    fa.step(nav(), 0.02)
    assert [s.state for s in fa.pending_status()] == [S.COMMAND_STATE_EXECUTING]
    for hdg in (100.0, 110.0, 120.0):
        assert fa.on_command(hsa("a", hdg)).state == S.COMMAND_STATE_EXECUTING
        fa.step(nav(), 0.02)
        assert list(fa.pending_status()) == []      # EXECUTING을 다시 내지 않는다


def test_tc_agt_071_update_before_execution_stays_accepted():
    fa = make_fa()
    assert fa.on_command(hsa("a")).state == S.COMMAND_STATE_ACCEPTED
    assert fa.on_command(hsa("a", 100.0)).state == S.COMMAND_STATE_ACCEPTED
    fa.step(nav(), 0.02)
    assert [s.state for s in fa.pending_status()] == [S.COMMAND_STATE_EXECUTING]


def test_tc_agt_072_new_id_cancels_then_accepts():
    fa = make_fa()
    fa.on_command(hsa("a"))
    fa.step(nav(), 0.02)
    fa.pending_status()
    assert fa.on_command(hsa("b")).state == S.COMMAND_STATE_ACCEPTED    # 수행 중이던 a를 이어받지 않는다
    assert [(s.command_id, s.state) for s in fa.pending_status()] == [("a", S.COMMAND_STATE_CANCELLED)]
    # 같은 ID라도 종류가 바뀌면 새 명령이다
    fa.step(nav(), 0.02)
    fa.pending_status()
    orbit = vi_pb2.FlightCommand(command_id="b")
    orbit.curve.orbit.center.lat_deg, orbit.curve.orbit.center.lon_deg = 37.5, 128.0
    orbit.curve.orbit.radius_m = 300.0
    assert fa.on_command(orbit).state == S.COMMAND_STATE_ACCEPTED
    # REJECTED는 수행 상태와 무관하다
    assert fa.on_command(vi_pb2.FlightCommand(command_id="b")).state == S.COMMAND_STATE_REJECTED


def test_tc_agt_073_gcs_status_never_regresses():
    h = Harness(make_scenario(3, "flocking"))     # 매 프레임 같은 ID로 명령을 낸다
    rx = fcs_rx(h)
    h.run_s(5.0)
    by_cmd: dict[str, list[int]] = {}
    for _, cmd, state in rx:
        by_cmd.setdefault(cmd, []).append(state)
    assert any(S.COMMAND_STATE_EXECUTING in v for v in by_cmd.values())
    for cmd, states in by_cmd.items():
        ranks = [RANK[s] for s in states]
        assert ranks == sorted(ranks), (cmd, states)
        assert len(set(states)) == len(states), (cmd, states)   # 같은 상태 반복도 없다


def test_tc_agt_074_lockstep_deterministic():
    def run() -> list[tuple[int, str, int]]:
        h = Harness(make_scenario(3, "flocking"))
        rx = fcs_rx(h)
        h.run_s(3.0)
        return list(rx)
    a, b = run(), run()
    assert a and a == b
