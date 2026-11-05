"""TC-AGT-051~054: 임무장비 상태 자동 보고 (IMP-AGT-029, DEC-051, DEC-044)"""

from swarm.v1 import ms_pb2, sim_pb2
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding


def put_sensor(h: Harness, active: bool, eid: str = "uav-001") -> None:
    m = ms_pb2.SensorActivity(payload_id="eo-1", active=active, hfov_deg=30.0)
    m.header.source = eid
    m.header.frame = h.core.frame  # 헤더만 다른 값은 변화가 아니다
    h.bus.put(keys.onboard(eid, "SensorActivity"), m.SerializeToString(), protobuf_encoding(m.DESCRIPTOR.full_name))


def reports(h: Harness) -> list:
    return [m for m in h.gcs_rx if isinstance(m, ms_pb2.SensorActivity)]


def test_tc_agt_051_reports_change_immediately():
    h = Harness(make_scenario(1, "hold"))
    h.core.step(5)                     # 첫 주기 경계를 지난다
    assert reports(h) == []            # 받은 상태가 없으면 보내지 않는다
    put_sensor(h, True)
    h.core.step(1)
    assert [m.active for m in reports(h)] == [True]
    put_sensor(h, True)                # 같은 값(헤더만 다름): 다시 보내지 않는다
    h.core.step(1)
    assert len(reports(h)) == 1
    put_sensor(h, False)
    h.core.step(1)
    assert [m.active for m in reports(h)] == [True, False]


def test_tc_agt_052_reports_every_sim_second():
    h = Harness(make_scenario(1, "hold"))
    h.core.step(5)
    put_sensor(h, True)
    h.core.step(1)                     # 변화 보고 (모의 시간 0.1 s)
    h.run_s(3.0)                       # 1 s, 2 s, 3 s 경계마다 1회
    assert len(reports(h)) == 4


def test_tc_agt_053_reports_counted_in_sent_count():
    h = Harness(make_scenario(1, "hold"))
    got: list[dict] = []
    h.bus.subscribe(keys.clock_done("agent-0"),
                    lambda s: got.append(dict(sim_pb2.FrameDone.FromString(s.payload).sent_count)))
    h.core.step(5)
    before = got[-1].get("uav-001", 0)
    put_sensor(h, True)
    h.core.step(1)
    assert got[-1].get("uav-001", 0) == before + 1


def test_tc_agt_054_lost_when_gcs_link_down():
    h = Harness(make_scenario(1, "hold"), drop=lambda iface, src, dst: dst == "gcs-01")
    h.core.step(5)
    put_sensor(h, True)
    h.run_s(2.0)
    assert reports(h) == []            # Datalink에서 손실되어 GCS에 닿지 않는다
    assert h.datalink.dropped >= 3
