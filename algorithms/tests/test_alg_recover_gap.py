"""TC-AGT-149: 복구 확정의 Heartbeat 간격 조건 (IMP-AGT-059, DEC-105, QA O-51)

기본값(lost_link_timeout_s 5, lost_link_recover_hold_s 5, lost_link_recover_gap_s 2). 틱 20 ms.
"""

from swarm.v1 import c2_pb2
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_algorithms.common import LOST_LINK_PARAMS
from swarm_api.geo import offset_geo

A = "uav-001"
RESUME = c2_pb2.LOST_LINK_POLICY_RESUME_ON_RECOVERY
OFF = 86400.0          # 간격 조건을 사실상 끈 값(DEC-105 전 동작과 비교용)


def move():
    t = c2_pb2.TaskCommand(task_id="far", assignees=[A], lost_link_policy=RESUME)
    lat, lon = offset_geo(37.5, 128.0, 20000.0, 0.0)
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg = float(lat), float(lon)
    return t


def beat(h):
    h.datalink.heartbeat("gcs-01", [A], rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def beats(h, n, every_frames=50):
    for _ in range(n):
        beat(h)
        h.core.step(every_frames)


def lost_harness(params=None):
    """1 Hz로 2 s 들은 뒤 6 s 끊어 상실 선회에 들어간 상태"""
    h = Harness(make_scenario(1, "waypoint", params or {}, course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move(), [A])
    beats(h, 2)
    h.core.step(300)
    assert md(h, "link_state") == ["lost"] and md(h, "lost_link_action") == ["hold"]
    return h


def md(h, name):
    return [r[2] for r in h.rt.vehicles[A].ports.md.records if r[1] == name]


def md_frames(h, name):
    return [(r[0], r[2]) for r in h.rt.vehicles[A].ports.md.records if r[1] == name]


def test_tc_agt_149_param_default():
    spec = {p.name: p for p in LOST_LINK_PARAMS}["lost_link_recover_gap_s"]
    assert spec.default == 2.0 and spec.unit == "s"


def test_tc_agt_149a_single_heartbeat_does_not_confirm():
    """O-51: 잠깐 들린 Heartbeat 1건 뒤 다시 끊기면 복구가 확정되지 않는다"""
    h = lost_harness()
    beats(h, 1, every_frames=600)                      # 1건 뒤 12 s 끊김
    assert md(h, "link_state") == ["lost", "recovering", "recover_aborted"]
    assert md(h, "lost_link_action") == ["hold"] and h.rt.vehicles[A].ma.pilot.link.lost
    (f0, _), (f1, _) = md_frames(h, "link_state")[1:]
    assert f1 - f0 == 101                              # 간격 2 s를 넘은 첫 틱(2.02 s), 유지 시간 5 s보다 먼저
    # 간격 조건이 없으면(DEC-105 전) 유지 시간이 상실 판정보다 한 틱 먼저 차서 복구했다가 바로 다시 상실한다
    h0 = lost_harness({"lost_link_recover_gap_s": OFF})
    beats(h0, 1, every_frames=600)
    assert md(h0, "link_state") == ["lost", "recovering", "recovered", "lost"]
    assert md(h0, "lost_link_action") == ["hold", "resume", "hold"]


def test_tc_agt_149b_one_hz_for_hold_confirms():
    h = lost_harness()
    beats(h, 5)                                        # 1 Hz로 5 s 전(4.98 s)까지는 확정 안 함
    assert md(h, "link_state") == ["lost", "recovering"] and md(h, "lost_link_action") == ["hold"]
    beats(h, 1)
    assert md(h, "link_state") == ["lost", "recovering", "recovered"] and md(h, "lost_link_action") == ["hold", "resume"]
    (f0, _), (f1, _) = md_frames(h, "link_state")[1:]
    assert f1 - f0 == 250                              # 재수신 뒤 정확히 5 s
    # 간격이 정확히 2 s면 이어진 것으로 본다(이하)
    h2 = lost_harness()
    beats(h2, 4, every_frames=100)
    assert md(h2, "link_state") == ["lost", "recovering", "recovered"]


def test_tc_agt_149c_gap_over_limit_discards_hold():
    """간격이 2 s를 넘으면 대기를 버린다. 상실 판정(5 s) 전이어도 그렇고 "lost"를 다시 내지 않는다"""
    h = lost_harness()
    beats(h, 2)
    h.core.step(150)                                   # 마지막 수신 뒤 3 s: 간격 초과, 상실 판정 전
    assert md(h, "link_state") == ["lost", "recovering", "recover_aborted"] and md(h, "lost_link_action") == ["hold"]
    beats(h, 6)                                        # 다시 이어지면 새로 대기해 확정
    assert md(h, "link_state") == ["lost", "recovering", "recover_aborted", "recovering", "recovered"]
    assert md(h, "lost_link_action") == ["hold", "resume"]
    # 2.5 s 간격은 기본값에선 확정되지 않고, 변수를 3 s로 올리면 확정된다
    h2 = lost_harness()
    beats(h2, 6, every_frames=125)
    assert "recovered" not in md(h2, "link_state") and md(h2, "link_state").count("lost") == 1
    assert md(h2, "lost_link_action") == ["hold"]
    h3 = lost_harness({"lost_link_recover_gap_s": 3.0})
    beats(h3, 4, every_frames=125)
    assert md(h3, "link_state") == ["lost", "recovering", "recovered"]


def _boundary(params=None):
    """O-36 모사: 상실 뒤 Heartbeat가 1 Hz로 3 s 들렸다 3 s 끊기기를 10회 되풀이"""
    h = lost_harness(params)
    for _ in range(10):
        beats(h, 3)
        h.core.step(150)
    return h


def test_tc_agt_149d_jam_boundary_no_repeat():
    h = _boundary()
    assert md(h, "lost_link_action") == ["hold"]       # 재개·재상실 반복 0회
    assert md(h, "link_state").count("lost") == 1 and "recovered" not in md(h, "link_state")
    assert md(h, "link_state").count("recover_aborted") == 10
    h0 = _boundary({"lost_link_recover_gap_s": OFF})   # 간격 조건 없이 기본 5 s/5 s면 끊긴 동안 확정해 버린다
    assert "resume" in md(h0, "lost_link_action")


def test_tc_agt_149e_deterministic():
    def once():
        h = _boundary()
        return h.rt.vehicles[A].ports.md.records

    assert once() == once()
