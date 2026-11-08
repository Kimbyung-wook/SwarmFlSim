"""TC-GW-001, TC-GW-002: descriptor 기반 매핑 표"""
import inspect

from swarm.v1 import options_pb2
from swarm_gateway.converters import base as conv_base
from swarm_gateway.converters import load_converters
from swarm_gateway.mapping import EXT, SIM, STD, MappingTable


def test_table_from_descriptor_options(codec):
    """TC-GW-001: proto 옵션에서 표를 만들고, STD의 uci_name은 모두 공개 XSD의 전역 요소다"""
    t = MappingTable.from_descriptors()
    nav = t.by_full_name("swarm.v1.NavigationReport")
    assert (nav.uci_name, nav.mapping, nav.iface) == ("MA_NavigationReport", STD, "vi")
    assert t.by_full_name("swarm.v1.TaskCommand").iface == "c2"
    assert t.by_full_name("swarm.v1.FormationCommand").mapping == EXT
    assert t.by_full_name("swarm.v1.LinkEnvelope").mapping == SIM
    std = t.exportable()
    assert len(std) >= 20
    for e in std:
        assert codec.global_element(e.uci_name) is not None, e.uci_name
    # EXT·SIM에는 uci_name이 없다 (options.proto 규칙)
    for e in t.by_class(EXT) + t.by_class(SIM):
        assert not e.uci_name and not e.exportable
    # 내부 메시지 여러 개가 같은 UCI에 대응할 수 있다 (DEC-013)
    assert [e.short_name for e in t.by_uci("MA_TaskCommand")] == ["TaskCommand"]


def test_converters_take_uci_name_from_table_only():
    """TC-GW-002: 변환기는 UCI 메시지명을 갖지 않는다. 매핑은 descriptor가 정한다"""
    t = MappingTable.from_descriptors()
    convs = load_converters(include_entry_points=False)
    for name, conv in convs.items():
        entry = t.by_full_name(name)
        assert entry is not None and entry.exportable, name
        assert not hasattr(conv, "uci_name")
        assert issubclass(type(conv), conv_base.Converter)
    # 변환기 소스에 UCI 메시지명 문자열을 하드코딩하지 않는다 (MessageData 내부 필드명만 쓴다)
    for name, conv in convs.items():
        uci = t.by_full_name(name).uci_name
        assert f'"{uci}"' not in inspect.getsource(type(conv)), (uci, type(conv).__name__)


def test_markdown_table_lists_std_and_ext():
    md = MappingTable.from_descriptors().markdown()
    assert "| `StrikeActivity` | `StrikeActivity` | — | STD | ms |" in md
    assert "| `FormationCommand` | — | — | EXT | c2 |" in md


def test_mapping_class_enum_is_contract():
    assert options_pb2.MAPPING_CLASS_STD == STD
