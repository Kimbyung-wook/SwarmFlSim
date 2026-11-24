"""MA "approval_demo" (IMP-AGT-056, DEC-103, QA O-2): 승인 흐름 시험·데모 전용 최소 MA. 기본 MA로 지정하지 않는다.

`strike` 작업만 수행한다. 다른 작업은 REJECTED(unsupported). 비행 명령은 내지 않는다(FA 기본 비행 그대로).

- 작업이 승인을 요구하면(교전 기준 `require_approval` 또는 MA 변수 `approval_tasks`에 `strike`) `ApprovalRequest`를 통제
  GCS로 보내고, 승인 `ApprovalResponse`를 받은 뒤에만 발사 명령(`StrikeCommand`)을 낸다. 승인 처리는 common.TaskTracker와 같다.
- 거부면 REJECTED("approval denied"), `approval_timeout_s`(0 = 무한)를 넘기면 REJECTED("approval timeout")로 끝내고
  발사 명령을 내지 않는다.
- 승인이 필요 없으면 받는 즉시 발사 명령을 낸다.
- 발사 명령을 내면 TaskStatus EXECUTING. 스테이션은 작업 `weapon_type`과 같은 종류 중 잔량이 있는 첫 스테이션(ID 순),
  종류가 없으면 잔량이 있는 첫 스테이션이다. 없으면 FAILED("no store").
- 발사·결과 처리는 common.StrikeLauncher(기본 MA의 PayloadTasker와 공유, DEC-106)다. 그 스테이션의 StrikeActivity로 끝낸다: IMPACT(유도 객체 도달) → COMPLETED, MISSED → FAILED("missed"),
  REJECTED → FAILED("strike rejected: <reason>"). 파괴 여부는 판단하지 않는다(DEC-067).

링크 상실 행동·탐지 공유·편대는 없다. params: approval_tasks(""), approval_timeout_s(0)
"""

from swarm.v1 import common_pb2
from swarm_api import AgentContext, MissionAutonomy

from .common import APPROVAL_PARAMS, StrikeLauncher, TaskTracker

S = common_pb2


class ApprovalDemo(MissionAutonomy):
    PARAMS = (*APPROVAL_PARAMS,)

    def on_init(self, ctx: AgentContext) -> None:
        self.tracker = TaskTracker(ctx, supported=("strike",))
        self.launcher = StrikeLauncher(ctx, self.tracker)   # 스테이션 선택·결과 처리는 PayloadTasker와 같다 (DEC-106)

    def on_step(self, ctx: AgentContext) -> None:
        for m in ctx.ports.c2.inbox():
            self.tracker.handle(m)
        ctx.ports.vi.command_status()
        self.tracker.update(ctx.ports.vi.nav())
        launched = self.launcher.launched
        if self.tracker.changed:
            self.tracker.changed = False
            cur = self.tracker.current
            if launched is not None and (cur is None or cur.task_id != launched[0]):
                self.launcher.launched = None           # 취소·대체된 작업의 활동은 더 보지 않는다
            if cur is not None and self.launcher.launched is None and not self.launcher.launch(cur):
                self.tracker.finish(S.COMMAND_STATE_FAILED, "no store")
        r = self.launcher.result(ctx.ports.ms.activities())
        if r is not None:
            self.launcher.launched = None
            self.tracker.finish(*r)
            self.tracker.changed = False
