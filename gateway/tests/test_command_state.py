"""TC-GW-039~041: 외부 명령 상태의 UCI Command-2 상태 기계 (DEC-097, IMP-GW-032)"""
import pytest
from swarm.v1 import common_pb2

import samples as S
from swarm_gateway.command_state import CommandStateGate, command_key
from swarm_gateway.gateway import Gateway, GatewayConfig

CS = common_pb2
TERMINAL = {"ACCEPTED", "REJECTED", "CANCELED"}
FIRST_OK = {"RECEIVED", "ACCEPTED", "REJECTED", "CANCELED"}


def _fcs(cid, state, src=S.UAV):
    m = S.flight_command_status()
    m.header.source = src
    m.command_id = cid
    m.state = state
    m.reason = ""
    return m


def _states(sent, cid=None):
    out = []
    for _, o in sent:
        if "MA_FlightCommandStatus" in o:
            d = o["MA_FlightCommandStatus"]["MessageData"]
            if cid is None or d["CommandID"]["DescriptiveLabel"] == cid:
                out.append(d["CommandProcessingState"])
    return out


def check_command2(states):
    """docs/44 C5 '명령 상태' 판정과 같은 규칙"""
    if not states:
        return True
    if states[0] not in FIRST_OK:
        return False
    for prev, cur in zip(states, states[1:]):
        if prev in TERMINAL or cur == "RECEIVED":
            return False
    return True


# ---------------------------------------------------------------- TC-GW-039
@pytest.mark.parametrize("internal,want", [
    # 내부 상태 순서 → 외부 CommandProcessingState
    ((CS.COMMAND_STATE_ACCEPTED, CS.COMMAND_STATE_EXECUTING, CS.COMMAND_STATE_COMPLETED), ["ACCEPTED"]),
    ((CS.COMMAND_STATE_ACCEPTED, CS.COMMAND_STATE_EXECUTING, CS.COMMAND_STATE_CANCELLED), ["ACCEPTED"]),
    ((CS.COMMAND_STATE_ACCEPTED, CS.COMMAND_STATE_EXECUTING, CS.COMMAND_STATE_FAILED), ["ACCEPTED"]),
    ((CS.COMMAND_STATE_REJECTED, CS.COMMAND_STATE_EXECUTING), ["REJECTED"]),             # QA D-37 모양
    ((CS.COMMAND_STATE_CANCELLED,), ["CANCELED"]),                                       # 접수 전 대체 (O-47)
    ((CS.COMMAND_STATE_CANCELLED, CS.COMMAND_STATE_ACCEPTED), ["CANCELED"]),
    ((CS.COMMAND_STATE_UNSPECIFIED, CS.COMMAND_STATE_UNSPECIFIED, CS.COMMAND_STATE_ACCEPTED,
      CS.COMMAND_STATE_COMPLETED), ["RECEIVED", "ACCEPTED"]),
    ((CS.COMMAND_STATE_EXECUTING, CS.COMMAND_STATE_COMPLETED), ["ACCEPTED"]),            # 첫 보고가 수행 중
    ((CS.COMMAND_STATE_ACCEPTED, CS.COMMAND_STATE_ACCEPTED, CS.COMMAND_STATE_ACCEPTED), ["ACCEPTED"]),  # 반복
])
def test_terminal_state_is_sent_once(gateway, sent, internal, want):
    for st in internal:
        S.deliver(gateway.bus, _fcs("uav-001-fc-1", st))
    got = _states(sent)
    assert got == want and check_command2(got)
    assert gateway.counters["skipped_command_state"] == len(internal) - len(want)
    assert gateway.counters["rejected"] == 0


def test_ids_and_vehicles_are_separate(gateway, sent):
    """끝 상태는 (보고 기체, CommandID)별이다. 다른 ID·다른 기체의 같은 ID는 따로 낸다"""
    S.deliver(gateway.bus, _fcs("fc-a", CS.COMMAND_STATE_ACCEPTED))
    S.deliver(gateway.bus, _fcs("fc-b", CS.COMMAND_STATE_REJECTED))
    S.deliver(gateway.bus, _fcs("fc-a", CS.COMMAND_STATE_ACCEPTED, src="uav-002"))
    S.deliver(gateway.bus, _fcs("fc-a", CS.COMMAND_STATE_COMPLETED))
    S.deliver(gateway.bus, _fcs("fc-b", CS.COMMAND_STATE_ACCEPTED))
    assert _states(sent) == ["ACCEPTED", "REJECTED", "ACCEPTED"]


def test_other_messages_are_not_gated(gateway, sent):
    """CommandProcessingState가 없는 메시지(MA_TaskStatus 등)는 상태 기계 밖이다"""
    for st in (CS.COMMAND_STATE_ACCEPTED, CS.COMMAND_STATE_EXECUTING, CS.COMMAND_STATE_COMPLETED):
        m = S.task_status()
        m.state = st
        S.deliver(gateway.bus, m)
    assert [o["MA_TaskStatus"]["MessageData"]["ExecutionState"] for _, o in sent] == [
        "EXECUTION_PENDING", "EXECUTING", "COMPLETED"]
    assert gateway.counters["skipped_command_state"] == 0


# ---------------------------------------------------------------- TC-GW-040
def test_gate_unit_rules():
    g = CommandStateGate(limit=2)
    obj = lambda st, cid="c1": {"M": {"MessageData": {"CommandID": {"UUID": cid}, "CommandProcessingState": st}}}  # noqa: E731
    assert g.admit("M", obj("RECEIVED"), "u") == (True, "")
    assert g.admit("M", obj("RECEIVED"), "u")[0] is False
    assert g.admit("M", obj("CANCELED"), "u") == (True, "")
    assert g.admit("M", obj("ACCEPTED"), "u") == (False, "after terminal CANCELED")
    assert command_key("M", {"M": {"MessageData": {"CommandID": {"UUID": "x"}}}}) is None
    for c in ("c2", "c3"):
        g.admit("M", obj("ACCEPTED", c), "u")
    assert len(g) == 2 and g.last("M", obj("X"), "u") is None              # 상한: 오래된 ID부터 잊는다


def test_restart_forgets_finished_ids(bus, codec, sent):
    """재기동한 Gateway는 끝난 ID를 모른다: 처음 보는 보고 하나를 첫 보고로 내고 그 뒤는 다시 막는다"""
    gw = Gateway(bus, GatewayConfig(S.GCS), codec=codec, sink=lambda t, o: sent.append((t, o)))
    gw.start()
    S.deliver(bus, _fcs("fc-r", CS.COMMAND_STATE_ACCEPTED))
    gw.close()
    gw2 = Gateway(bus, GatewayConfig(S.GCS), codec=codec, sink=lambda t, o: sent.append((t, o)))
    gw2.start()
    try:
        S.deliver(bus, _fcs("fc-r", CS.COMMAND_STATE_EXECUTING))
        S.deliver(bus, _fcs("fc-r", CS.COMMAND_STATE_COMPLETED))
    finally:
        gw2.close()
    assert _states(sent) == ["ACCEPTED", "ACCEPTED"]                       # 재기동 앞뒤 한 번씩


# ---------------------------------------------------------------- TC-GW-041
def test_flight_command_status_is_not_replayed(gateway, sent):
    """늦게 붙은 구독자 전달(DEC-089)은 MA_FlightCommandStatus를 다시 내지 않는다 (기존 구독자에게 반복이 된다)"""
    S.deliver(gateway.bus, _fcs("fc-x", CS.COMMAND_STATE_UNSPECIFIED))
    S.deliver(gateway.bus, _fcs("fc-y", CS.COMMAND_STATE_ACCEPTED))
    assert gateway.retained.latest("MA_FlightCommandStatus", "swarm.vi") == []
    assert ("MA_FlightCommandStatus", "swarm.vi") not in gateway.retained.targets()
