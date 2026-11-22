"""TC-AGT-146: 승인 흐름 시험용 MA approval_demo (IMP-AGT-056, DEC-103, QA O-2)

승인 → 발사 명령 → 유도 객체 도달(IMPACT)로 COMPLETED, 거부·시간 초과 → 발사 명령 없이 REJECTED.
"""

from importlib.metadata import entry_points

from swarm.v1 import c2_pb2, common_pb2, ms_pb2
from swarm_agent.plugins import DEFAULT_MA, PluginRegistry
from swarm_agent.testing import Harness, make_scenario, send_c2
from swarm_api import keys
from swarm_api.bus import protobuf_encoding

S = common_pb2
A = "uav-001"
ACC, REJ, EXE, DONE, FAIL = (S.COMMAND_STATE_ACCEPTED, S.COMMAND_STATE_REJECTED, S.COMMAND_STATE_EXECUTING,
                             S.COMMAND_STATE_COMPLETED, S.COMMAND_STATE_FAILED)


def scenario(require_approval=True, params=None, stores=(("sta1", "aam_short", 1), ("sta2", "agm_short", 2))):
    sc = make_scenario(1, "approval_demo", params or {})
    sc.engagement_criteria.require_approval = require_approval
    for e in sc.entities:
        if e.id == A:
            for sid, typ, n in stores:
                e.payloads.add(id=sid, type=typ, profile="x", count=n)
    return sc


class Spy:
    """onboard/<id>/StrikeCommand(MA → Payload)를 모은다"""

    def __init__(self, h):
        self.cmds = []
        h.bus.subscribe(keys.onboard(A, "StrikeCommand"), lambda s: self.cmds.append(ms_pb2.StrikeCommand.FromString(s.payload)))


def strike(task_id="s1", target="red-1", weapon=""):
    t = c2_pb2.TaskCommand(task_id=task_id, assignees=[A])
    t.strike.target_id = target
    if weapon:
        t.strike.weapon_type = weapon
    return t


def of(h, name):
    return [m for m in h.gcs_rx if m.DESCRIPTOR.name == name and m.header.source == A]


def states(h, task_id="s1"):
    return [(m.state, m.reason) for m in of(h, "TaskStatus") if m.task_id == task_id]


def respond(h, rid, approved):
    send_c2(h.bus, "gcs-01", c2_pb2.ApprovalResponse(request_id=rid, approved=approved), [A])


def activity(h, payload, state, reason=""):
    msg = ms_pb2.StrikeActivity(payload_id=payload, weapon_entity=f"{A}-w1", state=state, reason=reason)
    msg.header.source = A
    msg.header.frame = h.core.frame - 2
    msg.header.sim_time_us = msg.header.frame * h.core.dt_us
    h.bus.put(keys.onboard(A, "StrikeActivity"), msg.SerializeToString(), protobuf_encoding(msg.DESCRIPTOR.full_name))


def start(sc):
    h = Harness(sc)
    spy = Spy(h)
    h.core.step(2)
    return h, spy


def test_tc_agt_146_registered_as_test_demo_not_default():
    names = {e.name: e.value for e in entry_points(group="swarm.ma")}
    assert names["approval_demo"] == "swarm_algorithms.approval_demo:ApprovalDemo"
    assert DEFAULT_MA == "hold"                                     # 기본 MA가 아니다
    from swarm_algorithms.approval_demo import ApprovalDemo
    from swarm_algorithms.hold import Hold
    reg = PluginRegistry()
    assert reg.ma_class("") is Hold and reg.ma_class("approval_demo") is ApprovalDemo


def test_tc_agt_146a_approve_then_launch_and_reach():
    h, spy = start(scenario())
    send_c2(h.bus, "gcs-01", strike(weapon="agm_short"), [A])
    h.run_s(1.0)
    req = of(h, "ApprovalRequest")
    assert [(r.task_id, r.target_id) for r in req] == [("s1", "red-1")]
    assert spy.cmds == [] and states(h) == []                 # 응답 전: 발사 명령·상태 없음
    respond(h, req[0].request_id, True)
    h.run_s(0.5)
    assert [(c.payload_id, c.target_id) for c in spy.cmds] == [("sta2", "red-1")]   # 종류가 같은 스테이션
    assert spy.cmds[0].header.correlation_id == "s1"
    assert states(h) == [(ACC, ""), (EXE, "")]
    activity(h, "sta2", ms_pb2.STRIKE_STATE_LAUNCHED)
    h.run_s(0.5)
    assert states(h)[-1] == (EXE, "")
    activity(h, "sta1", ms_pb2.STRIKE_STATE_IMPACT)            # 다른 스테이션의 활동은 보지 않는다
    h.run_s(0.5)
    assert states(h)[-1] == (EXE, "")
    activity(h, "sta2", ms_pb2.STRIKE_STATE_IMPACT)            # 유도 객체 도달
    h.run_s(0.5)
    assert states(h) == [(ACC, ""), (EXE, ""), (DONE, "")] and len(spy.cmds) == 1


def test_tc_agt_146b_deny_no_launch():
    h, spy = start(scenario())
    send_c2(h.bus, "gcs-01", strike(), [A])
    h.run_s(1.0)
    respond(h, of(h, "ApprovalRequest")[0].request_id, False)
    h.run_s(3.0)
    assert spy.cmds == [] and states(h) == [(REJ, "approval denied")]


def test_tc_agt_146c_timeout_no_launch():
    h, spy = start(scenario(params={"approval_timeout_s": 2.0}))
    send_c2(h.bus, "gcs-01", strike(), [A])
    h.run_s(2.0)
    assert states(h) == [] and len(of(h, "ApprovalRequest")) == 1
    h.run_s(1.0)
    assert spy.cmds == [] and states(h) == [(REJ, "approval timeout")]
    respond(h, of(h, "ApprovalRequest")[0].request_id, True)   # 늦은 승인은 무시
    h.run_s(1.0)
    assert spy.cmds == [] and states(h) == [(REJ, "approval timeout")]


def test_tc_agt_146d_no_approval_needed_and_end_states():
    h, spy = start(scenario(require_approval=False))
    send_c2(h.bus, "gcs-01", strike(), [A])
    h.run_s(0.5)
    assert of(h, "ApprovalRequest") == [] and [c.payload_id for c in spy.cmds] == ["sta1"]   # 종류 없음: 첫 스테이션
    activity(h, "sta1", ms_pb2.STRIKE_STATE_MISSED)
    h.run_s(0.5)
    assert states(h) == [(ACC, ""), (EXE, ""), (FAIL, "missed")]
    send_c2(h.bus, "gcs-01", strike("s2"), [A])
    h.run_s(0.5)
    activity(h, spy.cmds[-1].payload_id, ms_pb2.STRIKE_STATE_REJECTED, "out of range")
    h.run_s(0.5)
    assert states(h, "s2")[-1] == (FAIL, "strike rejected: out of range")
    # 잔량 없음 → 발사 명령 없이 FAILED, 미지원 작업 → REJECTED
    h2, spy2 = start(scenario(require_approval=False, stores=()))
    send_c2(h2.bus, "gcs-01", strike(), [A])
    mv = c2_pb2.TaskCommand(task_id="m1", assignees=[A])
    mv.move_to.destination.lat_deg, mv.move_to.destination.lon_deg = 37.6, 128.0
    send_c2(h2.bus, "gcs-01", mv, [A])
    h2.run_s(0.5)
    assert spy2.cmds == [] and states(h2)[-1] == (FAIL, "no store")
    assert states(h2, "m1") == [(REJ, "unsupported task move_to")]


def test_tc_agt_146e_deterministic():
    def once():
        h, spy = start(scenario())
        send_c2(h.bus, "gcs-01", strike(), [A])
        h.run_s(1.0)
        respond(h, of(h, "ApprovalRequest")[0].request_id, True)
        h.run_s(1.0)
        activity(h, "sta1", ms_pb2.STRIKE_STATE_IMPACT)
        h.run_s(1.0)
        return [m.SerializeToString(deterministic=True) for m in h.gcs_rx] + [c.SerializeToString() for c in spy.cmds]

    a, b = once(), once()
    assert a == b and len(a) > 3
