"""TC-AGT-051~062: 임무장비 상태 자동 보고, 최대 빈도, 무장별 키 (IMP-AGT-029~031, DEC-051, DEC-056, DEC-063, DEC-044)"""

from swarm.v1 import link_pb2, ms_pb2, sim_pb2
from swarm_agent.testing import Harness, make_scenario
from swarm_api import keys
from swarm_api.bus import protobuf_encoding


def put_sensor(h: Harness, active: bool, eid: str = "uav-001", hfov: float = 30.0) -> None:
    m = ms_pb2.SensorActivity(payload_id="eo-1", active=active, hfov_deg=hfov)
    m.header.source = eid
    m.header.frame = h.core.frame - 2  # 이번 틱에 처리될 프레임 (D-30). 헤더만 다른 값은 변화가 아니다
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
    h.core.step(5)                     # 최대 빈도(기본 10 Hz) 간격이 지난 뒤 보낸다 (DEC-056)
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


def report_times(h: Harness) -> list[tuple[int, float]]:
    """GCS가 받은 SensorActivity의 (송신 모의 시각, hfov)"""
    out: list[tuple[int, float]] = []

    def on(s):
        env = link_pb2.LinkEnvelope.FromString(s.payload)
        if env.msg_type == "swarm.v1.SensorActivity":
            out.append((env.header.sim_time_us, ms_pb2.SensorActivity.FromString(env.payload).hfov_deg))
    h.bus.subscribe(keys.rx("gcs-01", keys.Iface.MS, "SensorActivity"), on)
    return out


def change_every_tick(h: Harness, frames: int) -> None:
    for i in range(frames):
        put_sensor(h, True, hfov=10.0 + h.core.frame)   # 매 틱 연속값 변화
        h.core.step(1)


def change_gaps_us(times: list[tuple[int, float]]) -> list[int]:
    """1 s 경계(전체 보고) 틱을 뺀 변화 보고 간격"""
    ts = [t for t, _ in times if t % 1_000_000 >= 20_000]
    return [b - a for a, b in zip(ts, ts[1:])]


def test_tc_agt_055_default_10hz_min_gap():
    h = Harness(make_scenario(1, "hold"))
    times = report_times(h)
    h.core.step(55)                    # 1.1 s: 첫 1 s 경계를 지난다
    change_every_tick(h, 40)           # 0.8 s 동안 매 틱 변화
    gaps = change_gaps_us(times)
    assert gaps and min(gaps) >= 100_000
    assert len(times) <= 9             # 50 Hz가 아니라 10 Hz 수준


def test_tc_agt_056_deferred_change_sent_with_latest_value():
    h = Harness(make_scenario(1, "hold"))
    times = report_times(h)
    h.core.step(55)
    put_sensor(h, True, hfov=1.0)
    h.core.step(1)                     # 즉시 보고
    put_sensor(h, True, hfov=2.0)
    h.core.step(1)                     # 미룸
    put_sensor(h, True, hfov=3.0)
    h.core.step(1)                     # 미룸, 최신 값 갱신
    assert [v for _, v in times] == [1.0]
    h.core.step(5)
    assert [v for _, v in times] == [1.0, 3.0]   # 2.0은 건너뛰고 최신 값만 보낸다
    assert times[1][0] - times[0][0] == 100_000


def test_tc_agt_057_max_hz_setting():
    h = Harness(make_scenario(1, "hold"))
    h.rt.config.activity_max_hz = 0    # 0 이하: 제한 없음
    times = report_times(h)
    h.core.step(55)
    change_every_tick(h, 10)
    assert len(times) == 10
    h2 = Harness(make_scenario(1, "hold"))
    h2.rt.config.activity_max_hz = 2.0
    times2 = report_times(h2)
    h2.core.step(55)
    change_every_tick(h2, 40)
    assert min(change_gaps_us(times2)) >= 500_000
    from swarm_agent.cli import parse_args
    assert parse_args([]).activity_max_hz == 10.0
    assert parse_args(["--activity-max-hz", "5"]).activity_max_hz == 5.0


def test_tc_agt_058_full_report_every_second_kept():
    h = Harness(make_scenario(1, "hold"))
    h.rt.config.activity_max_hz = 0.5  # 변화 보고 간격 2 s
    times = report_times(h)
    h.core.step(5)
    put_sensor(h, True)
    h.core.step(1)
    h.run_s(3.0)
    assert len(times) == 4             # 첫 보고 + 1 s·2 s·3 s 전체 보고


S = ms_pb2


def put_strikes(h: Harness, items: list[tuple[str, int]], eid: str = "uav-001") -> None:
    """같은 프레임에 같은 스테이션(wpn-1)의 무장 여러 개 상태를 낸다"""
    for weapon, state in items:
        m = S.StrikeActivity(payload_id="wpn-1", weapon_entity=weapon, state=state)
        m.header.source = eid
        m.header.frame = h.core.frame - 2
        h.bus.put(keys.onboard(eid, "StrikeActivity"), m.SerializeToString(), protobuf_encoding(m.DESCRIPTOR.full_name))


def strikes(h: Harness) -> list[tuple[str, int]]:
    return [(m.weapon_entity, m.state) for m in h.gcs_rx if isinstance(m, S.StrikeActivity)]


def test_tc_agt_059_same_frame_weapons_all_reported():
    for hz in (0, 10.0):
        h = Harness(make_scenario(1, "hold"))
        h.rt.config.activity_max_hz = hz
        h.core.step(5)
        put_strikes(h, [("w01", S.STRIKE_STATE_IMPACT), ("w04", S.STRIKE_STATE_LAUNCHED)])
        h.core.step(1)
        assert sorted(strikes(h)) == [("w01", S.STRIKE_STATE_IMPACT), ("w04", S.STRIKE_STATE_LAUNCHED)], hz


def test_tc_agt_060_terminal_weapon_dropped_from_full_report():
    h = Harness(make_scenario(1, "hold"))
    h.core.step(5)
    put_strikes(h, [("w01", S.STRIKE_STATE_LAUNCHED), ("w02", S.STRIKE_STATE_LAUNCHED)])
    h.core.step(10)
    put_strikes(h, [("w01", S.STRIKE_STATE_IMPACT), ("w02", S.STRIKE_STATE_MISSED), ("", S.STRIKE_STATE_REJECTED)])
    h.core.step(1)
    n = len(strikes(h))
    assert n == 5
    h.run_s(2.0)                       # 1 s·2 s 전체 보고: 종료 키는 빠지고 남은 키가 없다
    assert len(strikes(h)) == n
    keys_left = h.rt.vehicles["uav-001"].activity_reports.state
    assert not any(k[0] == "StrikeActivity" for k in keys_left)
    assert not h.rt.vehicles["uav-001"].activity_reports.sent     # 송신 시각도 정리된다


def test_tc_agt_061_full_report_keeps_live_weapon_only():
    h = Harness(make_scenario(1, "hold"))
    h.core.step(5)
    put_strikes(h, [("w01", S.STRIKE_STATE_LAUNCHED), ("w02", S.STRIKE_STATE_LAUNCHED)])
    h.core.step(10)
    put_strikes(h, [("w01", S.STRIKE_STATE_IMPACT)])
    h.core.step(1)
    before = len(strikes(h))
    h.run_s(1.0)                       # 1 s 경계: 아직 비행 중인 w02만 다시 보낸다
    assert strikes(h)[before:] == [("w02", S.STRIKE_STATE_LAUNCHED)]


def test_tc_agt_062_rate_limit_per_weapon_key():
    h = Harness(make_scenario(1, "hold"))
    h.core.step(55)
    put_strikes(h, [("w01", S.STRIKE_STATE_LAUNCHED)])
    h.core.step(1)                     # w01 보고
    put_strikes(h, [("w01", S.STRIKE_STATE_IMPACT), ("w02", S.STRIKE_STATE_LAUNCHED)])
    h.core.step(1)                     # w02는 새 키라 바로, w01은 0.1 s 상한으로 미룸
    assert strikes(h) == [("w01", S.STRIKE_STATE_LAUNCHED), ("w02", S.STRIKE_STATE_LAUNCHED)]
    h.core.step(4)
    assert strikes(h)[-1] == ("w01", S.STRIKE_STATE_IMPACT)
