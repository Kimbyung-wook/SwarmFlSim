"""TC-GW-007, TC-GW-008: 2단계 수신 (외부 C2 STD → swarm/<gcs>/tx/c2/<msg>)"""
import copy

import pytest
from swarm.v1 import c2_pb2, link_pb2, options_pb2

import samples as S


def _task_command(gateway, kind="hold", cancel=False, assignees=(S.UAV, "uav-002")) -> dict:
    tc = c2_pb2.TaskCommand(task_id="task-5", assignees=list(assignees), cancel=cancel)
    if kind:
        getattr(tc, kind).SetInParent()
    data = gateway.converters["swarm.v1.TaskCommand"].to_uci(tc, gateway.ctx)
    return gateway.envelope("MA_TaskCommand", data)


def _captured(bus):
    got = []
    bus.subscribe("swarm/gcs-01/tx/c2/**", lambda s: got.append(s))
    return got


@pytest.mark.parametrize("kind,cancel", [("hold", False), ("return_to_base", False), ("", True)])
def test_external_task_command_to_tx(gateway, bus, kind, cancel):
    """TC-GW-007: 외부 MA_TaskCommand → 내부 TaskCommand를 GCS tx/c2에 싣는다 (Datalink 경유)"""
    got = _captured(bus)
    out = gateway.handle_external("MA_TaskCommand", _task_command(gateway, kind, cancel))
    assert out.status == "published", out.reason
    assert [s.key for s in got] == ["swarm/gcs-01/tx/c2/TaskCommand"]
    assert got[0].encoding == "application/protobuf;swarm.v1.LinkEnvelope"
    env = link_pb2.LinkEnvelope.FromString(got[0].payload)
    assert env.header.source == S.GCS and list(env.dst) == [S.UAV, "uav-002"]
    assert env.iface == options_pb2.L1_INTERFACE_C2 and env.msg_type == "swarm.v1.TaskCommand"
    tc = c2_pb2.TaskCommand.FromString(env.payload)
    assert tc.task_id == "task-5" and list(tc.assignees) == [S.UAV, "uav-002"]
    assert tc.cancel is cancel
    assert (tc.WhichOneof("task") or "") == kind
    assert tc.header.source == S.GCS
    assert gateway.counters["ext_published"] == 1


def test_seq_increments(gateway, bus):
    got = _captured(bus)
    for _ in range(3):
        gateway.handle_external("MA_TaskCommand", _task_command(gateway))
    assert [link_pb2.LinkEnvelope.FromString(s.payload).header.seq for s in got] == [0, 1, 2]


def test_invalid_or_unmapped_external_is_rejected(gateway, bus):
    """TC-GW-008: XSD 위반, 매핑 없는 메시지, 변환할 수 없는 명령은 거부하고 기록한다"""
    got = _captured(bus)
    bad = _task_command(gateway)
    del bad["MA_TaskCommand"]["MessageData"]["Command"][0]["Capability"]["TaskID"]   # 필수 요소 누락
    assert gateway.handle_external("MA_TaskCommand", bad).status == "rejected"

    wrong_enum = _task_command(gateway)
    wrong_enum["MA_TaskCommand"]["MessageData"]["Command"][0]["Capability"]["CommandState"] = "GO"
    assert gateway.handle_external("MA_TaskCommand", wrong_enum).status == "rejected"

    # 매핑이 없는(또는 C2가 아닌) UCI 메시지
    nav = gateway.envelope("MA_NavigationReport",
                           gateway.converters["swarm.v1.NavigationReport"].to_uci(S.nav(), gateway.ctx))
    assert "no inbound mapping" in gateway.handle_external("MA_NavigationReport", nav).reason
    assert gateway.handle_external("MA_FlightCommand", {"MA_FlightCommand": {}}).status == "rejected"

    # XSD는 통과하지만 Gateway 규칙으로 변환할 수 없는 작업 (CapabilityID 라벨이 엔티티가 아님)
    odd = copy.deepcopy(_task_command(gateway))
    odd["MA_TaskCommand"]["MessageData"]["Command"][0]["Capability"]["CapabilityID"] = {
        "UUID": "11111111-2222-4333-8444-555555555555", "DescriptiveLabel": "SENSOR CAP"}
    out = gateway.handle_external("MA_TaskCommand", odd)
    assert out.status == "rejected" and "does not name an entity" in out.reason

    unknown_kind = _task_command(gateway)
    unknown_kind["MA_TaskCommand"]["MessageData"]["Command"][0]["Capability"]["CapabilityID"][
        "DescriptiveLabel"] = f"{S.UAV}/strike"
    unknown_kind["MA_TaskCommand"]["MessageData"]["Command"][1]["Capability"]["CapabilityID"][
        "DescriptiveLabel"] = f"{S.UAV}/strike"
    assert gateway.handle_external("MA_TaskCommand", unknown_kind).status == "rejected"

    assert got == []
    assert gateway.counters["ext_invalid"] == 2 and gateway.counters["ext_published"] == 0
    assert len(gateway.rejections) == 6


def test_task_kinds_without_uci_form_are_not_exportable(gateway):
    """위치가 필요한 작업(move_to 등)은 MA_TaskCommand만으로 표현할 수 없어 변환하지 않는다"""
    from swarm_gateway.converters import ConversionError

    tc = c2_pb2.TaskCommand(task_id="t", assignees=[S.UAV])
    tc.move_to.destination.lat_deg = 37.0
    with pytest.raises(ConversionError):
        gateway.converters["swarm.v1.TaskCommand"].to_uci(tc, gateway.ctx)
