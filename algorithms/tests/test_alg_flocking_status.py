"""TC-AGT-147: flocking 작업 상태의 EXECUTING 시점 (IMP-AGT-057, QA O-28)

다른 기본 MA(TaskPilot)와 같이 ACCEPTED → (그 작업의 비행 명령을 FA가 EXECUTING으로 보고한 다음 틱) EXECUTING → COMPLETED.
"""

from swarm.v1 import c2_pb2, common_pb2
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_api.geo import offset_geo

S = common_pb2
A = "uav-001"
ACC, EXE, DONE, CAN = (S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_EXECUTING, S.COMMAND_STATE_COMPLETED,
                       S.COMMAND_STATE_CANCELLED)


def move(task_id, n, e=0.0):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A])
    lat, lon = offset_geo(37.5, 128.0, n, e)
    t.move_to.destination.lat_deg, t.move_to.destination.lon_deg = float(lat), float(lon)
    return t


def hold(task_id, duration_s):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A])
    t.hold.radius_m = 400.0
    t.hold.duration_s = duration_s
    return t


def statuses(h, task_id):
    return [(m.state, m.header.frame) for m in h.gcs_rx if m.DESCRIPTOR.name == "TaskStatus" and m.task_id == task_id]


def beat(h):
    h.datalink.heartbeat("gcs-01", [A], rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def run(ma, *tasks, seconds=60.0, params=None):
    h = Harness(make_scenario(1, ma, params or {}, course_deg=0.0))
    h.core.step(2)
    for t in tasks:
        send_c2(h.bus, "gcs-01", t, [A])
    h.run_s(seconds)
    return h


def test_tc_agt_147_flocking_executing_same_point_as_waypoint():
    f, w = run("flocking", move("m1", 600.0)), run("waypoint", move("m1", 600.0))
    sf, sw = statuses(f, "m1"), statuses(w, "m1")
    assert [s for s, _ in sf] == [ACC, EXE, DONE] and [s for s, _ in sw] == [ACC, EXE, DONE]
    assert sf[1][1] - sf[0][1] == sw[1][1] - sw[0][1] == 1        # ACCEPTED 다음 틱
    # Hold(duration)도 같은 흐름. 선점된 작업은 EXECUTING 뒤 CANCELLED, 새 작업은 다시 EXECUTING
    h = run("flocking", hold("h1", 20.0), seconds=120.0)
    assert [s for s, _ in statuses(h, "h1")] == [ACC, EXE, DONE]
    h = Harness(make_scenario(1, "flocking", course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("a", 20000.0), [A])
    h.run_s(2.0)
    send_c2(h.bus, "gcs-01", move("b", -20000.0), [A])
    h.run_s(2.0)
    assert [s for s, _ in statuses(h, "a")] == [ACC, EXE, CAN] and [s for s, _ in statuses(h, "b")] == [ACC, EXE]


def test_tc_agt_147b_lost_link_hold_and_recovery():
    """링크 상실 선회 중 받은 작업은 선회가 끝나 그 작업으로 비행할 때 EXECUTING. 재개해도 EXECUTING은 작업마다 한 번"""
    h = Harness(make_scenario(1, "flocking", {"lost_link_timeout_s": 1.0, "lost_link_recover_hold_s": 0.0,
                                              "lost_link_policy": "resume_on_recovery"}, course_deg=0.0))
    h.core.step(2)
    send_c2(h.bus, "gcs-01", move("a", 20000.0), [A])
    for _ in range(3):
        beat(h)
        h.core.step(50)
    h.core.step(150)                                      # 상실 → 선회
    for _ in range(3):                                    # 복구 → 재개
        beat(h)
        h.core.step(50)
    # 세 번째는 런타임의 링크 복구 재보고(DEC-101)다. MA는 재개 뒤 EXECUTING을 다시 내지 않는다
    assert [s for s, _ in statuses(h, "a")] == [ACC, EXE, EXE]
    assert h.rt.vehicles[A].task_reports["a"].state == EXE
    assert [r[2] for r in h.rt.vehicles[A].ports.md.records if r[1] == "lost_link_action"] == ["hold", "resume"]
