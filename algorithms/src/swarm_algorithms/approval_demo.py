"""MA "approval_demo" (IMP-AGT-056, DEC-103, QA O-2): 승인 흐름 시험·데모 전용 최소 MA. 기본 MA로 지정하지 않는다.

`strike` 작업만 수행한다. 다른 작업은 REJECTED(unsupported). 비행 명령은 내지 않는다(FA 기본 비행 그대로).

- 작업이 승인을 요구하면(교전 기준 `require_approval` 또는 MA 변수 `approval_tasks`에 `strike`) `ApprovalRequest`를 통제
  GCS로 보내고, 승인 `ApprovalResponse`를 받은 뒤에만 발사 명령(`StrikeCommand`)을 낸다. 승인 처리는 common.TaskTracker와 같다.
- 거부면 REJECTED("approval denied"), `approval_timeout_s`(0 = 무한)를 넘기면 REJECTED("approval timeout")로 끝내고
  발사 명령을 내지 않는다.
- 승인이 필요 없으면 받는 즉시 발사 명령을 낸다.
- 발사 명령을 내면 TaskStatus EXECUTING. 스테이션은 작업 `weapon_type`과 같은 종류 중 잔량이 있는 첫 스테이션(ID 순),
  종류가 없으면 잔량이 있는 첫 스테이션이다. 없으면 FAILED("no store").
- 그 스테이션의 StrikeActivity로 끝낸다: IMPACT(유도 객체 도달) → COMPLETED, MISSED → FAILED("missed"),
  REJECTED → FAILED("strike rejected: <reason>"). 파괴 여부는 판단하지 않는다(DEC-067).

링크 상실 행동·탐지 공유·편대는 없다. params: approval_tasks(""), approval_timeout_s(0)
"""

from swarm.v1 import common_pb2, ms_pb2
from swarm_api import AgentContext, MissionAutonomy

from .common import APPROVAL_PARAMS, TaskTracker

S = common_pb2


class ApprovalDemo(MissionAutonomy):
    PARAMS = (*APPROVAL_PARAMS,)

    def on_init(self, ctx: AgentContext) -> None:
        self.tracker = TaskTracker(ctx, supported=("strike",))
        self.launched: tuple[str, str] | None = None   # (task_id, payload_id): 발사 명령을 낸 작업

    def _station(self, ctx: AgentContext, weapon_type: str) -> str:
        stores = sorted((s for s in ctx.ports.ms.loadout().stores if s.count > 0), key=lambda s: s.id)
        for s in stores:
            if not weapon_type or s.type == weapon_type:
                return s.id
        return ""

    def _launch(self, ctx: AgentContext) -> None:
        task = self.tracker.current
        payload = self._station(ctx, task.strike.weapon_type)
        if not payload:
            self.tracker.finish(S.COMMAND_STATE_FAILED, "no store")
            return
        cmd = ms_pb2.StrikeCommand(payload_id=payload, target_id=task.strike.target_id)
        if task.strike.HasField("aim_point"):
            cmd.aim_point.CopyFrom(task.strike.aim_point)
        cmd.header.correlation_id = task.task_id
        ctx.ports.ms.command(cmd)
        self.launched = (task.task_id, payload)
        ctx.ports.md.record("strike_command", task.task_id)
        self.tracker.status(task, S.COMMAND_STATE_EXECUTING)

    def on_step(self, ctx: AgentContext) -> None:
        for m in ctx.ports.c2.inbox():
            self.tracker.handle(m)
        ctx.ports.vi.command_status()
        self.tracker.update(ctx.ports.vi.nav())
        if self.tracker.changed:
            self.tracker.changed = False
            cur = self.tracker.current
            if self.launched is not None and (cur is None or cur.task_id != self.launched[0]):
                self.launched = None                    # 취소·대체된 작업의 활동은 더 보지 않는다
            if cur is not None and self.launched is None:
                self._launch(ctx)
        for a in ctx.ports.ms.activities():
            if self.launched is None or not isinstance(a, ms_pb2.StrikeActivity) or a.payload_id != self.launched[1]:
                continue
            if a.state == ms_pb2.STRIKE_STATE_IMPACT:
                self._end(S.COMMAND_STATE_COMPLETED)
            elif a.state == ms_pb2.STRIKE_STATE_MISSED:
                self._end(S.COMMAND_STATE_FAILED, "missed")
            elif a.state == ms_pb2.STRIKE_STATE_REJECTED:
                self._end(S.COMMAND_STATE_FAILED, f"strike rejected: {a.reason}" if a.reason else "strike rejected")

    def _end(self, state: int, reason: str = "") -> None:
        self.launched = None
        self.tracker.finish(state, reason)
        self.tracker.changed = False
