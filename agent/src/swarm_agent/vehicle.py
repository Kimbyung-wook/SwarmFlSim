"""런타임이 호스팅하는 기체 한 대 (IMP-AGT-004)."""

from collections import defaultdict
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import numpy as np
from google.protobuf.message import Message

from swarm.v1 import entity_pb2, mp_pb2, vi_pb2
from swarm_api import AgentContext, FlightAutonomy, MissionAutonomy

from .messages import fill_header, full_name
from .params import ParamSet
from .ports import PortsImpl
from .reporting import ChangeReporter, activity_terminal, vi_terminal

if TYPE_CHECKING:
    from .runtime import AgentRuntime


class Vehicle:
    def __init__(self, runtime: "AgentRuntime", spec: entity_pb2.EntitySpec, fa: FlightAutonomy,
                 fa_set: ParamSet, fa_context: Mapping[str, Any], ma_name: str, ma_set: ParamSet,
                 rng: np.random.Generator, plan: mp_pb2.MissionPlan | None,
                 criteria: mp_pb2.EngagementCriteria | None) -> None:
        self._rt = runtime
        self.spec = spec
        self.entity_id = spec.id
        self.fa = fa
        self.fa_set = fa_set  # DEC-035: FA·MA 매개변수 선언·적용 값·거부 목록
        self.ma_set = ma_set
        # fa_context(dynamics, airframe)는 런타임이 주는 정보이고 매개변수가 아니다
        self.capability: vi_pb2.FlightCapability = fa.on_init(spec.id, {**fa_context, **fa_set.values})
        self.ma_name = ma_name
        self.ma: MissionAutonomy | None = None  # 기체별 MA. 일괄 MA면 None
        self.nav: vi_pb2.NavigationReport | None = None
        self.nav_fresh = False  # 지난 프레임 이후 항법 보고를 받았는가
        self.system_status: vi_pb2.SystemStatus | None = None
        self.frame = 0
        self.sim_time_us = 0
        self._seq: dict[str, int] = defaultdict(int)
        # GCS 자동 보고 (DEC-051, DEC-063, DEC-071). 런타임이 틱 시작에 비운다
        self.activity_reports = ChangeReporter(activity_terminal)
        self.vi_reports = ChangeReporter(vi_terminal)
        self.nav_report_period: int | None = None
        self.capability_reported = False
        self.ports = PortsImpl(self, plan, criteria)
        self.ctx = AgentContext(entity_id=spec.id, frame=0, sim_time_s=0.0, dt_s=0.0,
                                ports=self.ports, params=ma_set.values, rng=rng)

    def begin_frame(self, frame: int, sim_time_us: int, dt_s: float) -> None:
        self.frame = frame
        self.sim_time_us = sim_time_us
        self.ctx.frame = frame
        self.ctx.sim_time_s = sim_time_us * 1e-6
        self.ctx.dt_s = dt_s
        self.ports.flip()

    def next_seq(self, key: str) -> int:
        n = self._seq[key]
        self._seq[key] = n + 1
        return n

    def stamp(self, msg: Message) -> None:
        fill_header(msg, self.entity_id, self.frame, self.sim_time_us, self.next_seq(full_name(msg)))

    def send_link(self, iface: str, msg: Message, dst: list[str]) -> None:
        self.stamp(msg)
        self._rt.send_link(self, iface, msg, dst)

    def send_onboard(self, msg: Message) -> None:
        self.stamp(msg)
        self._rt.publish_onboard(self, msg)

    def warn(self, text: str) -> None:
        self._rt.warn(f"{self.entity_id}: {text}")
