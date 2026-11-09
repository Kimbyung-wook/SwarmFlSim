"""상호작용(메시지)별 변환기 플러그인 (IMP-GW-004, DEC-013).

변환기는 내부 proto 메시지 하나(전체 이름)를 맡는다. 대응 UCI 메시지명은 변환기가 정하지 않고
매핑 표(descriptor의 uci_name)에서 받는다.

- to_uci: 내부 메시지 → UCI MessageData(OMS JSON 객체). 1단계(발행)
- from_uci: UCI MessageData → (내부 메시지, 수신 엔티티 목록). 2단계(수신). 지원하지 않으면 None

추가 UCI 변환기(DEC-072): proto의 (uci_also)에 적힌 UCI 메시지는 그 UCI 메시지를 맡는 변환기가 채운다.
이 변환기는 `uci`(맡는 UCI 메시지명)와 `protos`(받을 수 있는 내부 메시지, 비우면 전부)를 갖는다.
어느 내부 메시지에 쓸지는 변환기가 아니라 descriptor의 uci_also가 정한다.

외부 패키지는 엔트리 포인트 그룹 `swarm_gateway.converters`로 변환기 클래스를 추가할 수 있다.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import OrderedDict
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Callable, ClassVar

from google.protobuf.message import Message

from ..ids import IdMap
from ..lacal import uci_timestamp

ENTRY_POINT_GROUP = "swarm_gateway.converters"


class ConversionError(ValueError):
    """변환할 수 없는 값(매핑 없음, 필수 값 없음)"""


class BoundedStore:
    """오래된 항목부터 버리는 표. 수신 경로 계획과 승인 요청자를 기억한다 (프로세스 재기동 시 사라진다)"""

    def __init__(self, limit: int = 1024):
        self.limit = limit
        self._items: OrderedDict[str, tuple[int | None, object]] = OrderedDict()

    def put(self, key: str, version: int | None, value: object) -> None:
        self._items[key] = (version, value)
        self._items.move_to_end(key)
        while len(self._items) > self.limit:
            self._items.popitem(last=False)

    def get(self, key: str, version: int | None = None):
        """없거나, version을 지정했는데 저장한 판과 다르면 None"""
        found = self._items.get(key)
        if found is None or (version is not None and found[0] != version):
            return None
        return found[1]


@dataclass
class ConvContext:
    ids: IdMap
    gcs: str
    now: Callable[[], dt.datetime] = field(default=lambda: dt.datetime.now(dt.timezone.utc))
    routes: BoundedStore = field(default_factory=BoundedStore)      # 수신한 RoutePlan (UUID → 메시지, DEC-076)
    approvals: BoundedStore = field(default_factory=BoundedStore)   # 내보낸 ApprovalRequest (request_id → 요청 기체)

    def ts(self) -> str:
        return uci_timestamp(self.now())

    def system(self, entity_id: str) -> dict:
        return self.ids.ref("system", entity_id)


class Converter:
    proto: ClassVar[str] = ""       # 내부 메시지 전체 이름. 예: swarm.v1.NavigationReport

    def to_uci(self, msg: Message, ctx: ConvContext) -> dict:  # pragma: no cover - 기본은 미지원
        raise NotImplementedError

    def from_uci(self, data: dict, ctx: ConvContext) -> tuple[Message, list[str]] | None:
        return None

    @classmethod
    def supports_export(cls) -> bool:
        return cls.to_uci is not Converter.to_uci

    @classmethod
    def supports_import(cls) -> bool:
        return cls.from_uci is not Converter.from_uci


class AlsoConverter(Converter):
    """uci_also 대상 UCI 메시지 하나를 맡는 변환기 (DEC-072). 내보내기만 한다"""
    uci: ClassVar[str] = ""                 # 맡는 UCI 메시지명. 예: MA_PositionReport
    protos: ClassVar[tuple[str, ...]] = ()  # 받을 수 있는 내부 메시지. 비우면 제한 없음

    def accepts(self, full_name: str) -> bool:
        return not self.protos or full_name in self.protos


_BUILTIN: dict[str, type[Converter]] = {}
_BUILTIN_ALSO: dict[str, type[AlsoConverter]] = {}


def register(cls: type[Converter]) -> type[Converter]:
    if not cls.proto:
        raise ValueError(f"{cls.__name__}: proto is empty")
    _BUILTIN[cls.proto] = cls
    return cls


def register_also(cls: type[AlsoConverter]) -> type[AlsoConverter]:
    if not cls.uci:
        raise ValueError(f"{cls.__name__}: uci is empty")
    _BUILTIN_ALSO[cls.uci] = cls
    return cls


def _load_builtin() -> None:
    from . import c2, mp, ms, p2p, position, vi  # noqa: F401  내장 변환기 등록


def _entry_point_classes(include: bool) -> list[type]:
    return [ep.load() for ep in entry_points(group=ENTRY_POINT_GROUP)] if include else []


def load_converters(include_entry_points: bool = True) -> dict[str, Converter]:
    """내부 메시지 → uci_name 변환기 (전체 이름 → 인스턴스)"""
    _load_builtin()
    found: dict[str, type[Converter]] = dict(_BUILTIN)
    for cls in _entry_point_classes(include_entry_points):
        if not issubclass(cls, AlsoConverter):
            found[cls.proto] = cls
    return {name: cls() for name, cls in found.items()}


def load_also_converters(include_entry_points: bool = True) -> dict[str, AlsoConverter]:
    """uci_also 대상 변환기 (UCI 메시지명 → 인스턴스, DEC-072)"""
    _load_builtin()
    found: dict[str, type[AlsoConverter]] = dict(_BUILTIN_ALSO)
    for cls in _entry_point_classes(include_entry_points):
        if issubclass(cls, AlsoConverter):
            found[cls.uci] = cls
    return {uci: cls() for uci, cls in found.items()}


# ---- 단위·값 도우미 (UCI 각도는 라디안, 거리·고도 m, 속력 m/s) ----

def rad(deg: float) -> float:
    return math.radians(deg)


def lon_rad(deg: float) -> float:
    """AngleType 범위 [-π, π]로 감는다"""
    r = math.radians(deg)
    return math.atan2(math.sin(r), math.cos(r))


def finite(*values: float) -> None:
    for v in values:
        if not math.isfinite(v):
            raise ConversionError(f"non-finite value: {v}")


def point(lat_deg: float, lon_deg: float, alt_m: float, ts: str | None = None) -> dict:
    """Point4D_Type/Point3D_Type 계열 (MSL 고도)"""
    finite(lat_deg, lon_deg, alt_m)
    p = {"Latitude": rad(lat_deg), "Longitude": lon_rad(lon_deg), "Altitude": float(alt_m),
         "AltitudeReference": "MSL"}
    if ts is not None:
        p["Timestamp"] = ts
    return p


def label_ok(text: str) -> str:
    return text[:1024]
