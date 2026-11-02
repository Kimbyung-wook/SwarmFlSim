"""MA/FA 플러그인 인터페이스 (PRP-BHV-001, PRP-BHV-002).

등록: 플러그인 패키지의 pyproject.toml에 entry point를 둔다.
    [project.entry-points."swarm.ma"]
    flocking = "my_pkg.flocking:Flocking"
시나리오는 AutonomySpec.ma_plugin = "flocking" 으로 고른다.

매개변수 (DEC-035): 플러그인은 PARAMS에 기본값과 함께 선언한다. 런타임이
기본값 ← 시나리오(ma_params/fa_params) ← 실행 중 SetParams 순으로 덮어쓴
값을 ctx.params(FA는 on_init params)로 넘기고, 실행 중 변경은 on_params로 알린다.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from .ports import Ports

if TYPE_CHECKING:
    from swarm.v1 import fa_pb2, vi_pb2

MA_ENTRY_POINT_GROUP = "swarm.ma"
FA_ENTRY_POINT_GROUP = "swarm.fa"


class ParamLayer(IntEnum):
    """proto ParamLayer와 같은 값"""

    AIRFRAME = 1
    CONTROL = 2
    GUIDANCE = 3
    BEHAVIOR = 4
    DECISION = 5


@dataclass(frozen=True)
class ParamDef:
    """매개변수 선언 (DEC-035). default의 타입(float | str | bool)이 값의 타입이다."""

    name: str
    default: float | str | bool
    layer: ParamLayer
    unit: str = ""
    min: float | None = None
    max: float | None = None
    description: str = ""
    runtime: bool = True  # 실행 중 변경 가능
    choices: tuple[str, ...] = ()  # 문자열 값의 허용 목록. 비면 제한 없음 (DEC-036)


def resolve_params(
    defs: Sequence[ParamDef],
    base: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    running: bool = False,
) -> tuple[dict[str, Any], dict[str, str]]:
    """base(현재 값, 비어 있으면 기본값)에 changes를 덮어쓴다.

    반환: (적용 값 전체, 거부 {이름: unknown | type | range | choice | not_runtime}).
    거부한 항목은 적용하지 않는다. 정수는 float로 받는다.
    """
    by_name = {d.name: d for d in defs}
    values = {d.name: base.get(d.name, d.default) for d in defs}
    rejected: dict[str, str] = {}
    for name, v in changes.items():
        d = by_name.get(name)
        if d is None:
            rejected[name] = "unknown"
            continue
        if running and not d.runtime:
            rejected[name] = "not_runtime"
            continue
        if isinstance(d.default, bool):
            ok = isinstance(v, bool)
        elif isinstance(d.default, str):
            ok = isinstance(v, str)
        else:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            v = float(v) if ok else v
        if not ok:
            rejected[name] = "type"
            continue
        if isinstance(v, str) and d.choices and v not in d.choices:
            rejected[name] = "choice"
            continue
        if isinstance(v, float) and ((d.min is not None and v < d.min) or (d.max is not None and v > d.max)):
            rejected[name] = "range"
            continue
        values[name] = v
    return values, rejected


@dataclass
class AgentContext:
    entity_id: str
    frame: int
    sim_time_s: float
    dt_s: float
    ports: Ports
    params: Mapping[str, Any]   # 기본값을 채운 적용 값 (DEC-035)
    rng: np.random.Generator  # 시드 고정. lockstep 결정론을 위해 이것만 쓴다


@dataclass
class NavBatch:
    """군집 일괄 호출 입력. 행 i는 ids[i] 기체. 각 기체의 항법 상태(잡음 포함)다."""

    ids: Sequence[str]
    lat_lon_alt: np.ndarray       # (N, 3) deg, deg, m
    velocity_ned: np.ndarray      # (N, 3) m/s
    valid: np.ndarray             # (N,) bool, 항법 상태 수신 여부


class MissionAutonomy(ABC):
    """기체별 MA. 기체 하나당 인스턴스 하나, 매 프레임 on_step을 호출한다."""

    PARAMS: ClassVar[Sequence[ParamDef]] = ()

    def on_init(self, ctx: AgentContext) -> None:
        pass

    def on_params(self, ctx: AgentContext, changed: Mapping[str, Any]) -> None:
        """실행 중 변경. ctx.params는 이미 새 값이다. 프레임 시작 전에 호출한다."""

    @abstractmethod
    def on_step(self, ctx: AgentContext) -> None: ...

    def on_shutdown(self, ctx: AgentContext) -> None:
        pass


class BatchMissionAutonomy(ABC):
    """군집 일괄 MA. 같은 플러그인을 쓰는 같은 호스트의 기체를 한 번에 처리한다 (DEC-006).

    기체마다 ctxs[i].ports로만 송수신한다. 다른 기체의 포트로 받은 정보를
    공유 메모리처럼 섞어 쓰면 안 된다 (DEC-008: 기체는 데이터링크로 받은 정보만 본다).
    """

    PARAMS: ClassVar[Sequence[ParamDef]] = ()

    def on_init(self, ctxs: Sequence[AgentContext]) -> None:
        pass

    def on_params(self, ctx: AgentContext, changed: Mapping[str, Any]) -> None:
        """기체 하나의 실행 중 변경. ctx.params는 이미 새 값이다."""

    @abstractmethod
    def on_step_batch(self, ctxs: Sequence[AgentContext], nav: NavBatch) -> None: ...

    def on_shutdown(self, ctxs: Sequence[AgentContext]) -> None:
        pass


class FlightAutonomy(ABC):
    """FA: VI 명령을 받아 동역학 제어 출력을 만든다. 기본안은 C++(WP3)."""

    PARAMS: ClassVar[Sequence[ParamDef]] = ()

    def on_init(self, entity_id: str, params: Mapping[str, Any]) -> "vi_pb2.FlightCapability":
        raise NotImplementedError

    def on_params(self, values: Mapping[str, Any], changed: Mapping[str, Any]) -> None:
        """실행 중 변경. values는 적용 값 전체다."""

    @abstractmethod
    def on_command(self, cmd: "vi_pb2.FlightCommand") -> "vi_pb2.FlightCommandStatus": ...

    @abstractmethod
    def step(self, nav: "vi_pb2.NavigationReport", dt_s: float) -> "fa_pb2.ControlOutput": ...

    def pending_status(self) -> "Sequence[vi_pb2.FlightCommandStatus]":
        """진행 상태 변화(EXECUTING, COMPLETED 등). 매 프레임 런타임이 가져간다."""
        return ()
