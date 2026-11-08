"""TC-GW-012~014: uci_also와 MA_PositionReport (DEC-072)"""
import math

import pytest
from lxml import etree
from swarm.v1 import p2p_pb2, vi_pb2
from swarm_gateway.converters import AlsoConverter, load_also_converters
from swarm_gateway.converters.position import euler_zyx
from swarm_gateway.lacal import schema_path
from swarm_gateway.mapping import MappingTable

import samples as S


@pytest.fixture(scope="module")
def xsd():
    return etree.XMLSchema(etree.parse(str(schema_path())))


def test_uci_also_read_from_descriptor():
    """TC-GW-012: uci_also를 descriptor에서 읽는다. 대상과 대응 내부 메시지가 표에 나온다"""
    t = MappingTable.from_descriptors()
    nav = t.by_full_name("swarm.v1.NavigationReport")
    peer = t.by_full_name("swarm.v1.PeerStatus")
    assert nav.uci_also == ("MA_PositionReport",) and peer.uci_also == ("MA_PositionReport",)
    assert nav.uci_targets == ("MA_NavigationReport", "MA_PositionReport")
    assert {e.short_name for e in t.by_uci("MA_PositionReport")} == {"NavigationReport", "PeerStatus"}
    # descriptor 옵션 값과 시험 표본의 기대값이 같다
    for e in t.exportable():
        if e.uci_also:
            assert S.ALSO[e.uci_name] == e.uci_also
    assert "| `NavigationReport` | `MA_NavigationReport` | `MA_PositionReport` | STD | vi |" in t.markdown()


def test_also_converters_are_bound_by_descriptor(gateway):
    convs = load_also_converters(include_entry_points=False)
    assert set(convs) == {"MA_PositionReport"}
    assert all(isinstance(c, AlsoConverter) for c in convs.values())
    targets = {(e.short_name, u) for e, u in gateway.export_targets()}
    assert ("NavigationReport", "MA_PositionReport") in targets
    assert ("PeerStatus", "MA_PositionReport") in targets
    # uci_also가 없는 내부 메시지에는 붙지 않는다
    assert ("TrackShare", "MA_PositionReport") not in targets


@pytest.mark.parametrize("make,iface", [(S.nav, "vi"), (S.peer_status, "p2p")])
def test_position_report_valid_and_content(gateway, bus, sent, xsd, make, iface):
    """TC-GW-013: 한 내부 메시지 → uci_name과 MA_PositionReport 각각 발행, 공개 XSD 통과, 값 변환"""
    msg = make()
    S.deliver(bus, msg)
    names = [list(o)[0] for _, o in sent]
    assert names[1] == "MA_PositionReport" and len(names) == 2
    topic, obj = sent[1]
    assert topic == f"swarm.{iface}"
    assert xsd.validate(etree.fromstring(gateway.to_xml(obj))), xsd.error_log
    d = obj["MA_PositionReport"]["MessageData"]
    assert d["SystemID"]["DescriptiveLabel"] == S.UAV and d["DisplayName"] == S.UAV
    st = d["InertialState"]
    p = msg.kinematics.position
    assert st["Position"]["Latitude"] == pytest.approx(math.radians(p.lat_deg))
    assert st["Position"]["Longitude"] == pytest.approx(math.radians(p.lon_deg))
    assert st["Position"]["Altitude"] == p.alt_m and st["Position"]["AltitudeReference"] == "MSL"
    v = msg.kinematics.velocity_ned_mps
    assert (st["DomainVelocity"]["NorthSpeed"], st["DomainVelocity"]["EastSpeed"],
            st["DomainVelocity"]["DownSpeed"]) == (v.x, v.y, v.z)
    if make is S.nav:
        assert st["Orientation"]["Yaw"] == pytest.approx(math.pi / 2)
        assert st["Orientation"]["Pitch"] == pytest.approx(0) and st["Orientation"]["Roll"] == pytest.approx(0)
        assert st["PositionUncertainty"]["UncertaintyEllipse"]["SemiMajorAxisLength"] == 3.0
    else:
        assert "Orientation" not in st and "PositionUncertainty" not in st


def test_position_failure_does_not_block_primary(gateway, bus, sent):
    """TC-GW-014: 추가 UCI 변환이 실패해도 uci_name 메시지는 나가고, 실패는 기록된다 (그 반대도)"""
    no_pos = vi_pb2.NavigationReport()            # kinematics 없음
    no_pos.header.source = S.UAV
    S.deliver(bus, no_pos)
    assert [list(o)[0] for _, o in sent] == ["MA_NavigationReport"]
    assert gateway.rejections[-1].uci_name == "MA_PositionReport"
    assert "position is missing" in gateway.rejections[-1].reason

    sent.clear()
    far = S.peer_status()
    far.kinematics.position.lat_deg = 95.0         # XSD 위반 → MA_PositionReport만 거부
    S.deliver(bus, far)
    assert [list(o)[0] for _, o in sent] == ["MA_PackagePartnerStatusReport"]
    assert "maxInclusive" in gateway.rejections[-1].reason
    assert gateway.counters["exported.MA_PositionReport"] == 0


def test_euler_zyx():
    assert euler_zyx(0, 0, 0, 0) is None
    yaw, pitch, roll = euler_zyx(1, 0, 0, 0)
    assert (yaw, pitch, roll) == (0, 0, 0)
    # 롤 30°
    h = math.radians(15)
    assert euler_zyx(math.cos(h), math.sin(h), 0, 0)[2] == pytest.approx(math.radians(30))


def test_peer_status_sample_has_kinematics():
    assert isinstance(S.peer_status(), p2p_pb2.PeerStatus) and S.peer_status().kinematics.position.alt_m == 520
