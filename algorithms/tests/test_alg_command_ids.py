"""TC-AGT-139~141: 끝 상태에 이른 FlightCommand ID를 다시 쓰지 않는다 (D-37, IMP-AGT-051, 기준 44 §C5)"""

from swarm.v1 import c2_pb2, common_pb2, sim_pb2
from swarm_agent.testing import Harness, make_scenario, put_sim_command, send_c2
from swarm_algorithms.common import CommandIds

S = common_pb2
A, B, C = "uav-001", "uav-002", "uav-003"
END = {S.COMMAND_STATE_COMPLETED, S.COMMAND_STATE_CANCELLED, S.COMMAND_STATE_FAILED, S.COMMAND_STATE_REJECTED}
FAST = {"lost_link_timeout_s": 1.0, "lost_link_policy": "resume_on_recovery"}


def record(h):
    """FA가 낸 FlightCommandStatus를 기체별로 모은다 (변화 보고로 합쳐지기 전 내부 흐름)"""
    log = {}
    for eid, v in h.rt.vehicles.items():
        vi, push = v.ports.vi, v.ports.vi.push_status
        out = log.setdefault(eid, [])

        def wrapped(st, push=push, out=out):
            out.append((st.command_id, st.state, st.reason))
            push(st)
        vi.push_status = wrapped
    return log


def violations(seq):
    """command_id마다 끝 상태 뒤에 다른 상태가 오면 위반"""
    ended, bad = {}, []
    for cid, state, _ in seq:
        if cid in ended and state != ended[cid]:
            bad.append((cid, ended[cid], state))
        if state in END:
            ended.setdefault(cid, state)
    return bad


def ids(seq):
    return list(dict.fromkeys(cid for cid, _, _ in seq))


def beat(h, *eids):
    h.datalink.heartbeat("gcs-01", list(eids), rx_time_us=max(0, h.core.frame - 1) * h.core.dt_us)


def beating(h, seconds, *eids):
    for _ in range(round(seconds)):
        beat(h, *eids)
        h.core.step(50)


def test_tc_agt_139_command_ids_part():
    c = CommandIds()
    assert c.current("x") == "x" and c.current("x") == "x"     # 흐름이 이어지면 같은 ID
    c.end()
    assert c.current("x") == "x-2"
    assert c.current("y") == "y" and c.current("x") == "x-3"    # base가 바뀌어도 이전 ID는 다시 쓰지 않는다
    assert c.new("x") == "x-4" and c.new("x") == "x-5"


def test_tc_agt_140_formation_follower_no_reject_no_reuse():
    h = Harness(make_scenario(3, "formation"))
    log = record(h)
    h.core.step(2)
    fc = c2_pb2.FormationCommand(group_id="beta", members=[A, B, C], shape=c2_pb2.FORMATION_SHAPE_LINE, spacing_m=100)
    send_c2(h.bus, "gcs-01", fc, [A, B, C])
    h.run_s(5.0)
    for eid in (B, C):
        seq = log[eid]
        # 리더 정보가 오기 전에는 명령을 내지 않는다: mode 없는 명령 REJECTED가 없다
        assert not [s for s in seq if s[1] == S.COMMAND_STATE_REJECTED], seq
        # 편대 명령 전에는 혼자 리더(fmn-lead)였고, 편대에 든 뒤로는 추종 명령 하나만 쓴다
        assert ids(seq) == [f"{eid}-fmn-lead", f"{eid}-fmn-beta"], ids(seq)
        fol = [st for cid, st, _ in seq if cid == f"{eid}-fmn-beta"]
        assert fol[0] == S.COMMAND_STATE_ACCEPTED and S.COMMAND_STATE_EXECUTING in fol
        assert violations(seq) == [], seq
    # 리더를 B로 바꿨다가 A로 되돌린다: 리더 명령과 추종 명령 모두 새 ID
    fc.leader = B
    send_c2(h.bus, "gcs-01", fc, [A, B, C])
    h.run_s(3.0)
    fc.leader = A
    send_c2(h.bus, "gcs-01", fc, [A, B, C])
    h.run_s(3.0)
    for eid in (A, B, C):
        assert violations(log[eid]) == [], (eid, log[eid])
    assert f"{A}-fmn-lead" in ids(log[A]) and f"{A}-fmn-beta" in ids(log[A]) and f"{B}-fmn-lead" in ids(log[B])
    assert f"{B}-fmn-beta-2" in ids(log[B])
    # GCS 변화 보고(외부)도 끝 상태 뒤 전이가 없다
    gcs = [(m.command_id, m.state, m.reason) for m in h.gcs_rx if m.DESCRIPTOR.name == "FlightCommandStatus"]
    assert gcs and violations(gcs) == []


def test_tc_agt_141_resume_uses_new_id():
    # formation 추종기: 링크 상실 선회 뒤 재개하면 새 추종 ID
    h = Harness(make_scenario(2, "formation", FAST))
    log = record(h)
    h.core.step(2)
    send_c2(h.bus, "gcs-01", c2_pb2.FormationCommand(group_id="g", members=[A, B], spacing_m=100), [A, B])
    beating(h, 3, A, B)
    h.core.step(60)                                  # 상실: 선회가 추종 명령을 대신한다
    beating(h, 3, A, B)                              # 복구: 추종 재개
    seq = log[B]
    assert violations(seq) == [], seq
    got = ids(seq)
    assert got == [f"{B}-fmn-lead", f"{B}-fmn-g", f"{B}-lost-link-1", f"{B}-fmn-g-2"], got
    # hold: 재개와 매개변수 변경 모두 새 ID
    h = Harness(make_scenario(1, "hold", FAST))
    log = record(h)
    h.core.step(2)
    beating(h, 3, A)
    h.core.step(60)
    beating(h, 2, A)
    cmd = sim_pb2.SimCommand(issuer="test")
    cmd.set_params.entity_id, cmd.set_params.owner = A, sim_pb2.PARAM_OWNER_MA
    cmd.set_params.values.update({"orbit_radius_m": 400.0})
    put_sim_command(h.bus, cmd)
    beating(h, 2, A)
    seq = log[A]
    assert violations(seq) == [], seq
    got = ids(seq)
    assert got == [f"{A}-hold", f"{A}-lost-link-1", f"{A}-hold-2", f"{A}-hold-3"], got
