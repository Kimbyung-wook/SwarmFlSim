"""MA/FA 플러그인 인터페이스 (PRP-BHV-001, PRP-BHV-002).

등록: 플러그인 패키지의 pyproject.toml에 entry point를 둔다.
    [project.entry-points."swarm.ma"]
    flocking = "my_pkg.flocking:Flocking"
시나리오는 AutonomySpec.ma_plugin = "flocking" 으로 고른다.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from .ports import Ports

if TYPE_CHECKING:
    from swarm.v1 import fa_pb2, vi_pb2

MA_ENTRY_POINT_GROUP = "swarm.ma"
FA_ENTRY_POINT_GROUP = "swarm.fa"


@dataclass
class AgentContext:
    entity_id: str
    frame: int
    sim_time_s: float
    dt_s: float
    ports: Ports
    params: Mapping[str, Any]
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

    def on_init(self, ctx: AgentContext) -> None:
        pass

    @abstractmethod
    def on_step(self, ctx: AgentContext) -> None: ...

    def on_shutdown(self, ctx: AgentContext) -> None:
        pass


class BatchMissionAutonomy(ABC):
    """군집 일괄 MA. 같은 플러그인을 쓰는 같은 호스트의 기체를 한 번에 처리한다 (DEC-006).

    기체마다 ctxs[i].ports로만 송수신한다. 다른 기체의 포트로 받은 정보를
    공유 메모리처럼 섞어 쓰면 안 된다 (DEC-008: 기체는 데이터링크로 받은 정보만 본다).
    """

    def on_init(self, ctxs: Sequence[AgentContext]) -> None:
        pass

    @abstractmethod
    def on_step_batch(self, ctxs: Sequence[AgentContext], nav: NavBatch) -> None: ...

    def on_shutdown(self, ctxs: Sequence[AgentContext]) -> None:
        pass


class FlightAutonomy(ABC):
    """FA: VI 명령을 받아 동역학 제어 출력을 만든다. 기본안은 C++(WP3)."""

    def on_init(self, entity_id: str, params: Mapping[str, Any]) -> "vi_pb2.FlightCapability":
        raise NotImplementedError

    @abstractmethod
    def on_command(self, cmd: "vi_pb2.FlightCommand") -> "vi_pb2.FlightCommandStatus": ...

    @abstractmethod
    def step(self, nav: "vi_pb2.NavigationReport", dt_s: float) -> "fa_pb2.ControlOutput": ...

    def pending_status(self) -> "Sequence[vi_pb2.FlightCommandStatus]":
        """진행 상태 변화(EXECUTING, COMPLETED 등). 매 프레임 런타임이 가져간다."""
        return ()
