"""기체별 매개변수 (IMP-AGT-021, DEC-035).

소유자(FA·MA)별 값 결정과 EntityParams 만들기. 값 순서: 기본값 → 시나리오 → 실행 중 SetParams.
PARAMS를 선언하지 않은 플러그인(빈 목록)은 시나리오 값을 그대로 받고 실행 중 변경은 모두 unknown으로 거부한다.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from google.protobuf import json_format, struct_pb2

from swarm.v1 import sim_pb2
from swarm_api import ParamDef, resolve_params

OWNER_KEY = {sim_pb2.PARAM_OWNER_FA: "fa", sim_pb2.PARAM_OWNER_MA: "ma"}
OWNER_ENUM = {v: k for k, v in OWNER_KEY.items()}


@dataclass
class ParamSet:
    """소유자 하나(FA 또는 MA)의 선언, 적용 값, 직전 거부 목록"""

    owner: str                                  # "fa" | "ma"
    plugin: str
    defs: Sequence[ParamDef] = ()
    values: dict[str, Any] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, owner: str, plugin: str, defs: Sequence[ParamDef], scenario: Mapping[str, Any]) -> "ParamSet":
        scenario, bad = _split_non_finite(defs, scenario)
        if not defs:  # 선언 없음: 시나리오 값을 그대로 넘긴다
            return cls(owner, plugin, (), dict(scenario), bad)
        values, rejected = resolve_params(defs, {}, scenario)
        return cls(owner, plugin, tuple(defs), values, {**rejected, **bad})

    def change(self, changes: Mapping[str, Any]) -> dict[str, Any]:
        """실행 중 변경. 적용한 항목(이름 → 새 값)을 돌려주고 거부 목록을 새로 채운다"""
        if not self.defs:
            self.rejected = {k: "unknown" for k in changes}
            return {}
        changes, bad = _split_non_finite(self.defs, changes)
        values, self.rejected = resolve_params(self.defs, self.values, changes, running=True)
        self.rejected.update(bad)
        changed = {k: v for k, v in values.items() if self.values.get(k) != v}
        self.values = values
        return changed

    def to_message(self, entity_id: str, sim_time_us: int) -> sim_pb2.EntityParams:
        msg = sim_pb2.EntityParams(entity_id=entity_id, owner=OWNER_ENUM[self.owner], plugin=self.plugin,
                                   sim_time_us=sim_time_us)
        for d in self.defs:
            spec = msg.specs.add(name=d.name, layer=int(d.layer), unit=d.unit, description=d.description,
                                 runtime=d.runtime)
            json_format.ParseDict(d.default, spec.default_value)
            spec.choices.extend(d.choices)
            if d.min is not None:
                spec.min = d.min
            if d.max is not None:
                spec.max = d.max
        msg.values.CopyFrom(_to_struct(self.values))
        for name, reason in self.rejected.items():
            msg.rejected.add(name=name, reason=reason)
        return msg


def _non_finite(v: Any) -> bool:
    if isinstance(v, float):
        return not math.isfinite(v)
    if isinstance(v, (list, tuple)):
        return any(_non_finite(x) for x in v)
    return False


def _split_non_finite(defs: Sequence[ParamDef], values: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """NaN·inf는 범위 선언 유무와 관계없이 range로 거부한다 (DEC-038). 선언에 없는 이름은 resolve_params가 unknown 처리"""
    names = {d.name for d in defs}
    ok, bad = {}, {}
    for k, v in values.items():
        if _non_finite(v) and (not names or k in names):
            bad[k] = "range"
        else:
            ok[k] = v
    return ok, bad


def _to_struct(values: Mapping[str, Any]) -> struct_pb2.Struct:
    s = struct_pb2.Struct()
    s.update(dict(values))
    return s


def param_defs(cls: type | None) -> Sequence[ParamDef]:
    return tuple(getattr(cls, "PARAMS", ()) or ()) if cls is not None else ()


__all__ = ["ParamSet", "OWNER_KEY", "OWNER_ENUM", "param_defs"]
