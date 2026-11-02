"""TC-AGT-044~046: lockstep 수신 결정성 (IMP-AGT-026, DEC-040)"""

from swarm.v1 import link_pb2, mp_pb2, sim_pb2
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding


def put_route(h: Harness, route_id: str, rx_time_us: int) -> None:
    rp = mp_pb2.RoutePlan(route_id=route_id, entity_id="uav-001")
    env = link_pb2.LinkEnvelope(msg_type="swarm.v1.RoutePlan", payload=rp.SerializeToString(), rx_time_us=rx_time_us)
    env.header.source = "gcs-01"
    h.bus.put(keys.rx("uav-001", keys.Iface.MP, "RoutePlan"), env.SerializeToString(), "")


def routes(h: Harness) -> list[str]:
    return [r.route_id for r in h.rt.vehicles["uav-001"].ports.mp.route_plans()]


def tick(h: Harness, frame: int, mode=sim_pb2.RUN_MODE_LOCKSTEP) -> None:
    t = sim_pb2.ClockTick(frame=frame, sim_time_us=frame * 20000, dt_us=20000, mode=mode)
    h.bus.put(keys.CLOCK_TICK, t.SerializeToString(), protobuf_encoding(t.DESCRIPTOR.full_name))


def done(h: Harness, who: str, frame: int) -> None:
    d = sim_pb2.FrameDone(participant=who, frame=frame)
    h.bus.put(keys.clock_done(who), d.SerializeToString(), protobuf_encoding(d.DESCRIPTOR.full_name))


def agent_done(h: Harness) -> list[int]:
    out: list[int] = []
    h.bus.subscribe(keys.clock_done("agent-0"), lambda s: out.append(sim_pb2.FrameDone.FromString(s.payload).frame))
    return out


def test_tc_agt_044_lockstep_consumes_only_due_rx():
    h = Harness(make_scenario(1, "hold"), load=True)
    put_route(h, "now", 40000)     # 틱 2의 시각
    put_route(h, "later", 60000)   # 틱 3의 시각
    tick(h, 1)
    assert routes(h) == []         # 틱 1(20 ms): 아직 닿지 않았다
    tick(h, 2)
    assert routes(h) == ["now"]
    tick(h, 3)
    assert sorted(routes(h)) == ["later", "now"]


def test_tc_agt_045_waits_for_datalink_frame_done():
    sc = make_scenario(1, "hold")
    sc.run.participants.append("datalink-0")
    h = Harness(sc, load=True)
    out = agent_done(h)
    tick(h, 0)
    assert out == [0]              # 틱 0은 기다리지 않는다
    tick(h, 1)
    assert out == [0]              # Datalink FrameDone{0} 전: 보류
    put_route(h, "late", 20000)    # Datalink가 틱 0의 rx를 FrameDone 전에 낸다
    done(h, "datalink-0", 0)
    assert out == [0, 1]           # 보류된 틱 1을 처리했고 rx도 소비했다
    assert routes(h) == ["late"]
    done(h, "datalink-0", 0)       # 같은 프레임 중복은 다음 틱을 풀지 못한다
    tick(h, 2)
    assert out == [0, 1]
    done(h, "datalink-0", 1)
    assert out == [0, 1, 2]


def test_tc_agt_046_realtime_is_not_gated():
    sc = make_scenario(1, "hold")
    sc.run.mode = sim_pb2.RUN_MODE_REALTIME
    sc.run.participants.append("datalink-0")
    h = Harness(sc, load=True)
    put_route(h, "far", 10**12)    # rx_time_us가 미래여도 바로 소비
    assert routes(h) == ["far"]
    tick(h, 5, mode=sim_pb2.RUN_MODE_REALTIME)  # FrameDone 없이 처리
    assert h.rt.stats.ticks == 1
