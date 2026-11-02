"""TC-AGT-036~037: sim/ctrl/scenario 구독 적재와 lockstep 준비 신호 (IMP-AGT-023, DEC-037)"""

from swarm.v1 import sim_pb2
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding


def publish(h: Harness, sc: sim_pb2.Scenario) -> None:
    h.bus.put(keys.SIM_CTRL_SCENARIO, sc.SerializeToString(), protobuf_encoding(sc.DESCRIPTOR.full_name))


def readiness(h: Harness) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    h.bus.subscribe("sim/clock/done/*", lambda s: out.append(
        (lambda d: (d.participant, d.frame))(sim_pb2.FrameDone.FromString(s.payload))))
    return out


def test_tc_agt_036_loads_from_scenario_key_and_dedups_by_name():
    sc = make_scenario(2, "hold")
    h = Harness(sc, load=False)
    assert h.rt.scenario is None
    publish(h, sc)  # LoadScenario 없이 적재
    assert h.rt.scenario is not None and set(h.rt.vehicles) == {"uav-001", "uav-002"}
    first = h.rt.vehicles["uav-001"]
    publish(h, sc)  # 같은 name: 무시 (기체 객체 유지)
    assert h.rt.vehicles["uav-001"] is first
    sc2 = make_scenario(3, "hold")
    sc2.name = "other"
    publish(h, sc2)  # 다른 name: 다시 적재
    assert set(h.rt.vehicles) == {"uav-001", "uav-002", "uav-003"} and h.rt.vehicles["uav-001"] is not first
    h.core.step(5)  # 적재 뒤 틱을 정상 처리한다


def test_tc_agt_037_lockstep_ready_signal_on_load():
    sc = make_scenario(1, "hold")
    h = Harness(sc, load=False)
    done = readiness(h)
    publish(h, sc)
    assert done == [("agent-0", 0)]
    publish(h, sc)  # 같은 name은 준비 신호를 다시 보내지 않는다
    assert done == [("agent-0", 0)]
    sc2 = make_scenario(1, "hold")
    sc2.name = "other"
    publish(h, sc2)  # 다시 적재하면 다시 보낸다
    assert done == [("agent-0", 0)] * 2
    # free-run이면 보내지 않는다
    sc3 = make_scenario(1, "hold")
    sc3.name, sc3.run.mode = "free", sim_pb2.RUN_MODE_FREERUN
    publish(h, sc3)
    assert done == [("agent-0", 0)] * 2
