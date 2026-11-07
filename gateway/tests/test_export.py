"""TC-GW-003~006: 1단계 발행 (rx 상태 → UCI XML → XSD 검증 → LA-CAL)"""
import pytest
from lxml import etree
from swarm.v1 import c2_pb2, link_pb2, ms_pb2, p2p_pb2
from swarm_api.bus import protobuf_encoding
from swarm_gateway.lacal import schema_path

import samples as S


@pytest.fixture(scope="module")
def xsd():
    """Gateway 코덱과 별도로 공개 XSD를 직접 적재해 다시 검증한다"""
    return etree.XMLSchema(etree.parse(str(schema_path())))


@pytest.mark.parametrize("uci_name", sorted(S.EXPORT_SAMPLES))
def test_status_to_valid_uci_xml(gateway, bus, sent, xsd, uci_name):
    """TC-GW-003: GCS rx로 받은 VI·C2·P2P·MS 상태가 XSD를 통과한 UCI XML로 나간다"""
    msg = S.EXPORT_SAMPLES[uci_name]()
    S.deliver(bus, msg)
    assert len(sent) == 1, gateway.rejections
    topic, obj = sent[0]
    assert list(obj) == [uci_name]
    assert topic == f"swarm.{S.iface_of(msg)}"
    xml = gateway.to_xml(obj)
    assert xsd.validate(etree.fromstring(xml)), xsd.error_log
    root = etree.fromstring(xml)
    assert etree.QName(root).localname == uci_name
    assert gateway.counters["exported"] == 1


def test_content_mapping(gateway, bus, sent):
    S.deliver(bus, S.track_share())
    S.deliver(bus, S.task_status())
    S.deliver(bus, S.sensor_activity())
    entity = sent[0][1]["MA_Entity"]["MessageData"]
    pt = entity["Kinematics"]["Position"]["FixedPositionType"]["FixedPoint"]
    assert pt["Latitude"] == pytest.approx(0.6562437)  # 37.6° → rad
    assert entity["EntityID"]["DescriptiveLabel"] == "trk-1"
    task = sent[1][1]["MA_TaskStatus"]["MessageData"]
    assert task["ExecutionState"] == "EXECUTING" and task["TaskID"]["DescriptiveLabel"] == "task-3"
    assert task["ExecutingSystemOrPackage"]["SystemID"]["DescriptiveLabel"] == S.UAV
    fov = sent[2][1]["PO_Activity"]["MessageData"]["Activity"][0]["FOV"]
    assert fov["LOS"]["Elevation"] == pytest.approx(-0.6435, abs=1e-3)  # 아래로 36.9°


def _ext_messages():
    det = ms_pb2.Detection(payload_id="cam0", target_id="tgt-001")
    det.header.source = S.UAV
    algo = p2p_pb2.PeerAlgorithmMessage(topic="auction", payload=b"\x01")
    algo.header.source = S.UAV
    form = c2_pb2.FormationCommand(group_id="grp-a", members=[S.UAV])
    form.header.source = "gcs-02"
    resp = c2_pb2.ApprovalResponse(request_id="req-1", approved=True)
    resp.header.source = "gcs-02"
    return [det, algo, form, resp]


def test_ext_is_never_exported(gateway, bus, sent):
    """TC-GW-004: EXT 메시지는 내보내지 않는다 (DEC-014)"""
    for m in _ext_messages():
        S.deliver(bus, m)
    assert sent == []
    assert gateway.counters["skipped_ext"] == 4
    assert gateway.counters["exported"] == 0


def test_invalid_is_rejected_and_gateway_continues(gateway, bus, sent):
    """TC-GW-005: XSD 검증 실패·변환 실패·깨진 봉투는 보내지 않고 기록하며, 다음 메시지는 처리한다"""
    bad = S.track_share()
    bad.position.lat_deg = 120.0                     # 라디안으로 π/2 초과 → XSD maxInclusive 위반
    S.deliver(bus, bad)
    nan = S.sensor_activity()
    nan.hfov_deg = float("nan")                      # 비유한 값 → 변환 거부
    S.deliver(bus, nan)
    bus.put("swarm/gcs-01/rx/vi/NavigationReport", b"\xff\xff\xff", protobuf_encoding("swarm.v1.LinkEnvelope"))
    env = S.envelope(S.nav())
    env.payload = b"\x0a\xff"
    bus.put(S.rx_key(S.nav()), env.SerializeToString(), protobuf_encoding("swarm.v1.LinkEnvelope"))
    assert sent == []
    assert gateway.counters["invalid"] == 2
    assert gateway.counters["rejected"] == 4
    reasons = [r.reason for r in gateway.rejections]
    assert "maxInclusive" in reasons[0] and "non-finite" in reasons[1]
    S.deliver(bus, S.nav())
    assert [list(o)[0] for _, o in sent] == ["MA_NavigationReport"]


def test_sim_and_unknown_types_are_not_exported(gateway, bus, sent):
    """TC-GW-006: SIM 메시지와 알 수 없는 msg_type은 내보내지 않는다"""
    inner = link_pb2.LinkState(a="gcs-01", b=S.UAV)
    env = link_pb2.LinkEnvelope(msg_type=inner.DESCRIPTOR.full_name, payload=inner.SerializeToString())
    bus.put("swarm/gcs-01/rx/vi/LinkState", env.SerializeToString(), protobuf_encoding(env.DESCRIPTOR.full_name))
    env = link_pb2.LinkEnvelope(msg_type="other.v1.Unknown")
    bus.put("swarm/gcs-01/rx/c2/Unknown", env.SerializeToString(), protobuf_encoding(env.DESCRIPTOR.full_name))
    assert sent == []
    assert gateway.counters["skipped_sim"] == 1 and gateway.counters["unmapped"] == 1


def test_inbound_command_kind_is_not_echoed(gateway, bus, sent):
    """외부에서 받는 명령 종류(MA_TaskCommand)가 rx에 보이더라도 되돌려 보내지 않는다"""
    tc = c2_pb2.TaskCommand(task_id="t", assignees=[S.UAV])
    tc.hold.SetInParent()
    tc.header.source = "gcs-02"
    S.deliver(bus, tc)
    assert sent == [] and gateway.counters["skipped_inbound_kind"] == 1
