"""운용자 번호표: 무장·플랫폼 종류 → MIL-STD-6016 번호 (IMP-GW-040, DEC-051·DEC-068).

6.0a XSD는 무장 종류(`StoreType.StoreType`)와 플랫폼 종류(`PlatformIdentityType.PlatformType`)를
MIL-STD-6016의 숫자 번호로 싣게 하고, 그 열거는 정의하지 않는다("this schema will not redefine the enumerations").
번호는 저장소에 두지 않는다. 운용자가 설정 파일(`--codes`)로 주고, 기본은 비어 있다.
번호가 있는 종류만 구조화된 필드를 내고, 없으면 그 전처럼 Mnemonic·Environment만 낸다.

파일 형식(YAML, `config/codes.example.yaml`):

    stores:        # PayloadSpec.type → 무장 종류
      <type>: {store_type: <번호>, category: <StoreCategoryEnum>}
    platforms:     # EntityKind 이름(ENTITY_KIND_ 뒤, 예 UAV·FPV·MISSILE) → 플랫폼 종류
      <kind>: {platform_type: <번호>, category: <EnvironmentEnum, 생략하면 엔티티 환경>, threat: <ThreatEnum, 생략 가능>}

열거 값은 XSD에서 읽어 검사한다(`CodeTable.check`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

U32 = 2 ** 32


@dataclass(frozen=True)
class StoreCode:
    store_type: int
    category: str


@dataclass(frozen=True)
class PlatformCode:
    platform_type: int
    category: str = ""      # 비우면 엔티티 환경(Environment)과 같게
    threat: str = ""        # ThreatEnum, 비우면 싣지 않는다


def _number(v, where: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < U32:
        raise ValueError(f"{where}: number must be an integer in 0..{U32 - 1}, got {v!r}")
    return v


def _table(d, where: str) -> dict:
    if d is None:
        return {}
    if not isinstance(d, dict):
        raise ValueError(f"{where}: expected a mapping")
    return d


@dataclass(frozen=True)
class CodeTable:
    stores: dict[str, StoreCode] = field(default_factory=dict)
    platforms: dict[str, PlatformCode] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.stores or self.platforms)

    @classmethod
    def from_dict(cls, d: dict | None) -> "CodeTable":
        d = _table(d, "codes")
        unknown = set(d) - {"stores", "platforms"}
        if unknown:
            raise ValueError(f"codes: unknown keys {sorted(unknown)}")
        stores = {}
        for name, v in _table(d.get("stores"), "stores").items():
            v = _table(v, f"stores.{name}")
            if set(v) - {"store_type", "category"} or "category" not in v:
                raise ValueError(f"stores.{name}: needs store_type and category only")
            stores[str(name)] = StoreCode(_number(v.get("store_type"), f"stores.{name}.store_type"), str(v["category"]))
        platforms = {}
        for name, v in _table(d.get("platforms"), "platforms").items():
            v = _table(v, f"platforms.{name}")
            if set(v) - {"platform_type", "category", "threat"}:
                raise ValueError(f"platforms.{name}: allowed keys platform_type, category, threat")
            platforms[str(name).upper()] = PlatformCode(_number(v.get("platform_type"), f"platforms.{name}.platform_type"),
                                                        str(v.get("category") or ""), str(v.get("threat") or ""))
        return cls(stores, platforms)

    @classmethod
    def load(cls, path: str | Path | None) -> "CodeTable":
        if not path:
            return cls()
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    def check(self, codec) -> "CodeTable":
        """열거 값이 XSD 열거에 드는지 (StoreCategoryEnum, EnvironmentEnum, ThreatEnum)"""
        def allowed(t: str) -> set[str]:
            return {str(x) for x in codec.xs.types[t].enumeration}
        cats, envs, threats = allowed("StoreCategoryEnum"), allowed("EnvironmentEnum"), allowed("ThreatEnum")
        for n, s in self.stores.items():
            if s.category not in cats:
                raise ValueError(f"stores.{n}.category {s.category!r} not in StoreCategoryEnum")
        for n, p in self.platforms.items():
            if p.category and p.category not in envs:
                raise ValueError(f"platforms.{n}.category {p.category!r} not in EnvironmentEnum")
            if p.threat and p.threat not in threats:
                raise ValueError(f"platforms.{n}.threat {p.threat!r} not in ThreatEnum")
        return self
