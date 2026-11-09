"""TC-AGT-088~093: lockstep onboard 입력의 처리 틱은 도착 순서와 무관 (IMP-AGT-036, D-30, DEC-039)"""

import pytest

from swarm.v1 import link_pb2, ms_pb2, sim_pb2, vi_pb2
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

UAV = "uav-001"
ORDERS = ["before_nav", "after_tick"]


def put(h, name, msg):
    h.bus.put(keys.onboard(UAV, name), msg.SerializeToString(), protobuf_encoding(msg.DESCRIPTOR.full_name))


def status(frame, energy, seq=0):
    m = vi_pb2.SystemStatus(health=vi_pb2.HEALTH_NOMINAL, energy_frac=energy)
    m.header.source, m.header.frame, m.header.seq = UAV, frame, seq
    return m


def sensor(frame, active, seq=0):
    m = ms_pb2.SensorActivity(payload_id="eo-1", active=active, hfov_deg=30.0)
    m.header.source, m.header.frame, m.header.seq = UAV, frame, seq
    return m


def gcs_tx(h):
    """GCS가 받은 보고의 (메시지 키, 송신 모의 시각, seq, payload). 프레임 0의 FlightCapability·Nav도 포함"""
    out = []

    def on(s):
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        out.append((s.key, env.header.sim_time_us, env.header.seq, env.payload))
    h.bus.subscribe(keys.rx_all("gcs-01"), on)
    return out


def step_with(h, order, name, msg):
    """입력이 이번 틱의 항법 보고보다 앞서거나, 이번 틱 처리가 끝난 뒤 도착한다"""
    if order == "before_nav":
        put(h, name, msg)
        h.core.step(1)
    else:
        h.core.step(1)
        put(h, name, msg)


def times(rx, name):
    return [t for k, t, _, _ in rx if k.endswith("/" + name)]


@pytest.mark.parametrize("order", ORDERS)
def test_tc_agt_088_system_status_report_tick_from_frame(order):
    h = Harness(make_scenario(1, "hold"))
    rx = gcs_tx(h)
    step_with(h, order, "SystemStatus", status(0, 1.0))      # 첫 프레임: QA에서 0 또는 1로 갈리던 경우
    assert times(rx, "SystemStatus") == []
    h.core.step(1)
    assert times(rx, "SystemStatus") == [20_000]             # 프레임 0의 상태는 틱 1에 보고


@pytest.mark.parametrize("order", ORDERS)
def test_tc_agt_089_activity_report_tick_from_frame(order):
    h = Harness(make_scenario(1, "hold"))
    h.core.step(5)
    rx = gcs_tx(h)
    # Core는 적분 프레임 4의 출력을 틱 5 앞에 낸다
    step_with(h, order, "SensorActivity", sensor(4, True))
    assert times(rx, "SensorActivity") == []
    h.core.step(1)
    assert times(rx, "SensorActivity") == [120_000]


@pytest.mark.parametrize("order", ORDERS)
def test_tc_agt_090_detection_visible_to_ma_from_frame(order):
    h = Harness(make_scenario(1, "hold"))
    h.core.step(5)
    det = ms_pb2.Detection(payload_id="cam0", target_id="tgt-001")
    det.header.frame = 4
    step_with(h, order, "Detection", det)
    ms = h.rt.vehicles[UAV].ports.ms
    assert list(ms.detections()) == []
    h.core.step(1)
    assert [d.target_id for d in ms.detections()] == ["tgt-001"]


def run_mixed(order):
    """프레임마다 SystemStatus·SensorActivity가 바뀌는 실행. 도착 순서만 다르다"""
    h = Harness(make_scenario(2, "hold"))
    rx = gcs_tx(h)
    for f in range(100):
        msgs = []
        if f % 7 == 0:
            msgs.append(("SystemStatus", status(f, 1.0 - f * 0.001, f)))
        if f >= 1 and f % 11 == 0:
            msgs.append(("SensorActivity", sensor(f - 1, f % 2 == 0, f)))
        if order == "before_nav":
            for name, m in msgs:
                put(h, name, m)
            h.core.step(1)
        else:
            h.core.step(1)
            for name, m in reversed(msgs):
                put(h, name, m)
    h.core.step(3)
    return list(rx)


def test_tc_agt_091_outputs_equal_for_both_arrival_orders():
    a, b = run_mixed("before_nav"), run_mixed("after_tick")
    assert any(k.endswith("/SystemStatus") for k, *_ in a) and any(k.endswith("/SensorActivity") for k, *_ in a)
    assert a == b


def test_tc_agt_092_realtime_unchanged():
    sc = make_scenario(1, "hold")
    sc.run.mode = sim_pb2.RUN_MODE_REALTIME
    h = Harness(sc)
    h.core.step(5)
    rx = gcs_tx(h)
    put(h, "SystemStatus", status(5, 0.9))     # realtime은 받은 다음 틱에 보고한다
    h.core.step(1)
    assert times(rx, "SystemStatus") == [100_000]


def test_tc_agt_093_late_input_is_counted_and_not_lost():
    h = Harness(make_scenario(1, "hold"))
    h.core.step(10)
    rx = gcs_tx(h)
    put(h, "SystemStatus", status(2, 0.5))     # 처리할 틱(3)이 지난 뒤 도착
    assert h.rt.stats.late_onboard == 1
    h.core.step(1)
    assert times(rx, "SystemStatus") == [200_000]
