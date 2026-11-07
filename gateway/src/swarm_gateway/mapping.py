"""내부 proto ⇄ UCI 메시지 매핑 표 (IMP-GW-002, DEC-013, DEC-014, docs/10_contracts.md §4).

proto 메시지 옵션 (uci_name), (mapping), (l1)을 descriptor에서 읽어 만든다. 메시지명을 하드코딩하지 않는다.
등록부 §5 표와 어긋나면 proto가 기준이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from google.protobuf import descriptor as _d
from google.protobuf import message_factory
from google.protobuf.message import Message

from swarm.v1 import (c2_pb2, common_pb2, entity_pb2, fa_pb2, link_pb2, mp_pb2, ms_pb2, options_pb2,
                      p2p_pb2, sim_pb2, truth_pb2, vi_pb2)

PROTO_MODULES: tuple[ModuleType, ...] = (c2_pb2, common_pb2, entity_pb2, fa_pb2, link_pb2, mp_pb2, ms_pb2,
                                          p2p_pb2, sim_pb2, truth_pb2, vi_pb2)

# L1Interface 값 → Zenoh 키의 <iface> 마디 (docs/10_contracts.md §3.3)
L1_IFACE = {
    options_pb2.L1_INTERFACE_C2: "c2",
    options_pb2.L1_INTERFACE_VI: "vi",
    options_pb2.L1_INTERFACE_MS: "ms",
    options_pb2.L1_INTERFACE_MP: "mp",
    options_pb2.L1_INTERFACE_MD: "md",
    options_pb2.L1_INTERFACE_P2P: "p2p",
}

STD = options_pb2.MAPPING_CLASS_STD
EXT = options_pb2.MAPPING_CLASS_EXT
SIM = options_pb2.MAPPING_CLASS_SIM


@dataclass(frozen=True)
class MappingEntry:
    full_name: str           # swarm.v1.NavigationReport
    short_name: str          # NavigationReport
    uci_name: str            # MA_NavigationReport (STD가 아니면 "")
    mapping: int             # MappingClass
    l1: int                  # L1Interface
    descriptor: _d.Descriptor

    @property
    def mapping_name(self) -> str:
        return options_pb2.MappingClass.Name(self.mapping).removeprefix("MAPPING_CLASS_")

    @property
    def iface(self) -> str:
        return L1_IFACE.get(self.l1, "")

    @property
    def exportable(self) -> bool:
        """외부로 내보낼 수 있는가: STD이고 uci_name이 있다 (DEC-014)"""
        return self.mapping == STD and bool(self.uci_name)

    def new_message(self) -> Message:
        return message_factory.GetMessageClass(self.descriptor)()


class MappingTable:
    def __init__(self, entries: list[MappingEntry]):
        self.entries = entries
        self._by_full = {e.full_name: e for e in entries}
        self._by_uci: dict[str, list[MappingEntry]] = {}
        for e in entries:
            if e.exportable:
                self._by_uci.setdefault(e.uci_name, []).append(e)

    @classmethod
    def from_descriptors(cls, modules: tuple[ModuleType, ...] = PROTO_MODULES) -> "MappingTable":
        entries: list[MappingEntry] = []
        for mod in modules:
            for desc in mod.DESCRIPTOR.message_types_by_name.values():
                opts = desc.GetOptions()
                entries.append(MappingEntry(
                    full_name=desc.full_name, short_name=desc.name,
                    uci_name=opts.Extensions[options_pb2.uci_name],
                    mapping=opts.Extensions[options_pb2.mapping],
                    l1=opts.Extensions[options_pb2.l1],
                    descriptor=desc))
        return cls(entries)

    def by_full_name(self, full_name: str) -> MappingEntry | None:
        return self._by_full.get(full_name)

    def by_uci(self, uci_name: str) -> list[MappingEntry]:
        """한 UCI 메시지에 내부 메시지 여러 개가 대응할 수 있다"""
        return list(self._by_uci.get(uci_name, ()))

    def exportable(self) -> list[MappingEntry]:
        return [e for e in self.entries if e.exportable]

    def by_class(self, mapping: int) -> list[MappingEntry]:
        return [e for e in self.entries if e.mapping == mapping]

    def markdown(self) -> str:
        """TRACE.md·README용 표"""
        rows = ["| 내부 메시지 | UCI 메시지 | 구분 | L1 |", "|---|---|---|---|"]
        for e in sorted(self.entries, key=lambda e: (e.mapping or 9, e.iface, e.short_name)):
            if e.mapping == 0:
                continue
            rows.append(f"| `{e.short_name}` | {('`' + e.uci_name + '`') if e.uci_name else '—'} "
                        f"| {e.mapping_name} | {e.iface or '—'} |")
        return "\n".join(rows)
