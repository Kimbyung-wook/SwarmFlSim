"""TC-AGT-144~145: 링크 복구 재보고와 복구 유지 시간 (IMP-AGT-054~055, DEC-101, QA O-34·O-36)"""

from swarm.v1 import c2_pb2, common_pb2
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_api.geo import offset_geo

S = common_pb2
A = "uav-001"
ORIGIN = (37.5, 128.0)
ACC, EXE, CAN = S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_CANCELLED
RESUME = c2_pb2.LOST_LINK_POLICY_RESUME_ON_RECOVERY


def move(task_id, n=20000.0, e=0.0, policy=c2_pb2.LOST_LINK_POLICY_UNSPECIFIED):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A], lost_link_policy=policy)
    lat, lon = offset_geo(ORIGIN[0], ORIGIN[1], n, e)
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg = float(lat), float(lon)
    return t


def beat(h):
    h.datalink.heartbeat("gcs-01", [A], rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def md(h, name):
    return [r[2] for r in h.rt.vehicles[A].ports.md.records if r[1] == name]


def gcs(h, name):
    return [m for m in h.gcs_rx if m.DESCRIPTOR.name == name and m.header.source == A]


def cut_harness(ma="waypoint", params=None):
    """GCS_LINK_CUT 모사: cut[0]이 참인 동안 Heartbeat를 넣지 않고 기체 → GCS도 버린다"""
    cut = [False]
    sc = make_scenario(1, ma, params or {}, course_deg=0.0)
    h = Harness(sc, drop=lambda iface, src, dst: cut[0] and src == A)
    return h, cut


def run(h, seconds, beats=True):
    for _ in range(round(seconds)):
        if beats:
            beat(h)
        h.core.step(50)


# ---- TC-AGT-144: 복구 재보고 (DEC-101(1), O-34) ----

def test_tc_agt_144_link_cut_recovery_resends_once():
    h, cut = cut_harness()
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("far"), [A])
    run(h, 3)
    assert [m.state for m in gcs(h, "TaskStatus")] == [ACC, EXE]
    fcs0 = len(gcs(h, "FlightCommandStatus"))
    cut[0] = True
    run(h, 10, beats=False)                         # 5 s 뒤 상실 → 제자리 선회. 선회 명령 상태는 GCS에 가지 않는다
    assert md(h, "lost_link_action") == ["hold"]
    assert len(gcs(h, "FlightCommandStatus")) == fcs0
    lost_cmd = h.rt.vehicles[A].last_command_status
    assert "lost-link" in lost_cmd.command_id and lost_cmd.state == EXE
    cut[0] = False
    run(h, 1)                                       # 복구 판정 틱에 한 번
    fcs = gcs(h, "FlightCommandStatus")
    assert len(fcs) == fcs0 + 1 and fcs[-1].command_id == lost_cmd.command_id and fcs[-1].state == EXE
    ts = gcs(h, "TaskStatus")
    assert [(m.task_id, m.state) for m in ts] == [("far", ACC), ("far", EXE), ("far", EXE)]
    run(h, 10)                                      # 그 뒤로는 늘지 않는다 (hold_until_command: 선회 유지)
    assert len(gcs(h, "FlightCommandStatus")) == fcs0 + 1 and len(gcs(h, "TaskStatus")) == 3
    assert md(h, "lost_link_action") == ["hold", "keep_hold"]


def test_tc_agt_144b_terminal_command_and_finished_task():
    """현재 명령이 단절 중 종료 상태가 되어 지워졌어도 한 번 다시 보낸다. 끝난 작업의 TaskStatus는 다시 보내지 않는다"""
    h, cut = cut_harness("waypoint", {"lost_link_policy": "continue"})
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("near", 300.0, 0.0), [A])
    run(h, 2)
    cut[0] = True
    run(h, 40, beats=False)                         # 단절 중 도착: TaskStatus COMPLETED·명령 COMPLETED가 GCS에 가지 않는다
    v = h.rt.vehicles[A]
    assert v.last_command_status.state == S.COMMAND_STATE_COMPLETED and v.task_reports == {}
    assert S.COMMAND_STATE_COMPLETED not in [m.state for m in gcs(h, "TaskStatus")]
    n_ts = len(gcs(h, "TaskStatus"))
    cut[0] = False
    run(h, 3)
    fcs = gcs(h, "FlightCommandStatus")
    assert fcs[-1].command_id == v.last_command_status.command_id and fcs[-1].state == S.COMMAND_STATE_COMPLETED
    assert len([m for m in fcs if m.command_id == v.last_command_status.command_id
                and m.state == S.COMMAND_STATE_COMPLETED]) == 1
    assert len(gcs(h, "TaskStatus")) == n_ts        # 진행 중 작업이 없으면 TaskStatus 재보고 없음


def test_tc_agt_144c_deterministic():
    def once():
        h, cut = cut_harness("waypoint", {"lost_link_policy": "resume_on_recovery"})
        h.core.step(2)
        send_c2(h.bus, "gcs-01", move("far"), [A])
        run(h, 3)
        cut[0] = True
        run(h, 8, beats=False)
        cut[0] = False
        run(h, 10)
        return [m.SerializeToString(deterministic=True) for m in h.gcs_rx]

    a, b = once(), once()
    assert a == b and len(a) > 5


# ---- TC-AGT-145: 기본 MA 복구 유지 시간 (DEC-101(2), O-36) ----

def test_tc_agt_145_recovery_confirmed_after_hold():
    h, _ = cut_harness("waypoint", {"lost_link_timeout_s": 1.0, "lost_link_recover_hold_s": 3.0})
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("far", policy=RESUME), [A])
    run(h, 2)
    run(h, 3, beats=False)
    assert md(h, "link_state") == ["lost"] and md(h, "lost_link_action") == ["hold"]
    run(h, 3)                                       # Heartbeat 재수신 뒤 3 s 전에는 상실 행동 유지
    assert md(h, "link_state") == ["lost", "recovering"] and md(h, "lost_link_action") == ["hold"]
    assert h.rt.vehicles[A].ma.pilot.link.lost
    run(h, 1)
    assert md(h, "link_state") == ["lost", "recovering", "recovered"] and md(h, "lost_link_action") == ["hold", "resume"]
    # 기본값 5 s
    h2, _ = cut_harness("waypoint", {"lost_link_timeout_s": 1.0})
    h2.core.step(2)
    send_c2(h2.bus, "gcs-01", move("far", policy=RESUME), [A])
    run(h2, 2)
    run(h2, 3, beats=False)
    run(h2, 5)
    assert md(h2, "lost_link_action") == ["hold"]
    run(h2, 1)
    assert md(h2, "lost_link_action") == ["hold", "resume"]


def test_tc_agt_145b_relost_during_hold_keeps_lost_behavior():
    h, _ = cut_harness("waypoint", {"lost_link_timeout_s": 1.0, "lost_link_recover_hold_s": 4.0})
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("far", policy=RESUME), [A])
    run(h, 2)
    run(h, 3, beats=False)
    run(h, 2)                                       # 복구 대기
    run(h, 3, beats=False)                          # 대기 중 다시 상실: 대기를 버린다. "lost"를 다시 내지 않는다
    assert md(h, "link_state") == ["lost", "recovering", "recover_aborted"]
    assert md(h, "lost_link_action") == ["hold"] and md(h, "lost_link_policy") == ["resume_on_recovery"]
    run(h, 5)
    assert md(h, "link_state")[-2:] == ["recovering", "recovered"] and md(h, "lost_link_action") == ["hold", "resume"]


def _boundary(hold_s):
    """재밍 구역 경계 모사(QA §25~28의 RESUME 기체): 상실 뒤 Heartbeat가 3 s 들렸다 3 s 끊기기를 되풀이한다"""
    h, _ = cut_harness("waypoint", {"lost_link_timeout_s": 2.0, "lost_link_recover_hold_s": hold_s})
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("far", policy=RESUME), [A])
    run(h, 2)
    run(h, 4, beats=False)
    for _ in range(10):
        run(h, 3)
        run(h, 3, beats=False)
    return h


def test_tc_agt_145c_jam_boundary_orbit_resume_repeats_reduced():
    before, after = _boundary(0.0), _boundary(5.0)
    resumes0 = md(before, "lost_link_action").count("resume")
    resumes1 = md(after, "lost_link_action").count("resume")
    assert resumes0 >= 5                            # 유지 시간이 없으면 들릴 때마다 재개 → 다시 상실
    assert resumes1 == 0 and md(after, "lost_link_action") == ["hold"]   # 3 s만 들리면 확정하지 않고 선회 유지
    assert md(after, "link_state").count("lost") == 1
