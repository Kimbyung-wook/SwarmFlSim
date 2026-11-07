"""상호작용(메시지)별 변환기 플러그인 (IMP-GW-004, DEC-013).

변환기는 내부 proto 메시지 하나(전체 이름)를 맡는다. 대응 UCI 메시지명은 변환기가 정하지 않고
매핑 표(descriptor의 uci_name)에서 받는다.

- to_uci: 내부 메시지 → UCI MessageData(OMS JSON 객체). 1단계(발행)
- from_uci: UCI MessageData → (내부 메시지, 수신 엔티티 목록). 2단계(수신). 지원하지 않으면 None

외부 패키지는 엔트리 포인트 그룹 `swarm_gateway.converters`로 변환기 클래스를 추가할 수 있다.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Callable, ClassVar

from google.protobuf.message import Message

from ..ids import IdMap
from ..lacal import uci_timestamp

ENTRY_POINT_GROUP = "swarm_gateway.converters"


class ConversionError(ValueError):
    """변환할 수 없는 값(매핑 없음, 필수 값 없음)"""


@dataclass
class ConvContext:
    ids: IdMap
    gcs: str
    now: Callable[[], dt.datetime] = field(default=lambda: dt.datetime.now(dt.timezone.utc))

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


_BUILTIN: dict[str, type[Converter]] = {}


def register(cls: type[Converter]) -> type[Converter]:
    if not cls.proto:
        raise ValueError(f"{cls.__name__}: proto is empty")
    _BUILTIN[cls.proto] = cls
    return cls


def load_converters(include_entry_points: bool = True) -> dict[str, Converter]:
    from . import c2, ms, p2p, vi  # noqa: F401  내장 변환기 등록

    found: dict[str, type[Converter]] = dict(_BUILTIN)
    if include_entry_points:
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            cls = ep.load()
            found[cls.proto] = cls
    return {name: cls() for name, cls in found.items()}


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
