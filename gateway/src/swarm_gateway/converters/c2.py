"""C2 변환기 (IMP-GW-006).

- 1단계: TaskStatus, ApprovalRequest를 UCI로 내보낸다.
- 2단계: 외부 MA_TaskCommand를 내부 TaskCommand로 바꾼다 (DEC-068).

MA_TaskCommand는 "TaskID 작업을 CapabilityID 능력으로 수행하라"는 명령이고 작업 내용(목적지·영역)은
임무 계획(MP)에 따로 둔다. 임무 계획 연동 전까지 Gateway는 다음 규칙을 쓴다 (계약 변경 요청 CR-GW-003).
- Command 항목 하나 = 수행 기체 하나. CapabilityID.DescriptiveLabel = "<엔티티 ID>/<작업 종류>"
- 작업 종류: 위치 정보가 필요 없는 hold(현재 위치 선회 대기), return_to_base
- TaskID.DescriptiveLabel = 내부 task_id. CommandState CANCEL = 취소
"""
from __future__ import annotations

import datetime as dt

from swarm.v1 import c2_pb2, common_pb2
from swarm_api.keys import ENTITY_ID_RE

from ..lacal import uci_timestamp
from .base import ConvContext, ConversionError, Converter, label_ok, register

_EXECUTION = {
    common_pb2.COMMAND_STATE_UNSPECIFIED: "EXECUTION_PENDING",
    common_pb2.COMMAND_STATE_ACCEPTED: "EXECUTION_PENDING",
    common_pb2.COMMAND_STATE_EXECUTING: "EXECUTING",
    common_pb2.COMMAND_STATE_COMPLETED: "COMPLETED",
    common_pb2.COMMAND_STATE_REJECTED: "DROPPED",
    common_pb2.COMMAND_STATE_FAILED: "FAILED",
    common_pb2.COMMAND_STATE_CANCELLED: "CANCELED",
}

# 외부 명령으로 받을 수 있는 작업 종류 (oneof 필드 이름)
IMPORTABLE_TASKS = ("hold", "return_to_base")

APPROVAL_WINDOW = dt.timedelta(seconds=60)


@register
class TaskStatusConverter(Converter):
    proto = "swarm.v1.TaskStatus"

    def to_uci(self, msg: c2_pb2.TaskStatus, ctx: ConvContext) -> dict:
        state = _EXECUTION.get(msg.state, "EXECUTION_PENDING")
        out: dict = {
            "ExecutingSystemOrPackage": {"SystemID": ctx.system(msg.header.source)},
            "ExecutionState": state,
            "TaskID": ctx.ids.ref("task", msg.task_id),
        }
        if state in ("DROPPED", "FAILED"):
            reason = {"Reason": "CAPABILITY_PERFORMANCE"}
            if msg.reason:
                reason["Description"] = label_ok(msg.reason)
            out["ExecutionStateReason"] = reason
        return out


@register
class ApprovalRequestConverter(Converter):
    proto = "swarm.v1.ApprovalRequest"

    def to_uci(self, msg: c2_pb2.ApprovalRequest, ctx: ConvContext) -> dict:
        return {
            "RequestID": ctx.ids.ref("request", msg.request_id),
            "RequestState": "NEW",
            "Approver": {"OperatorRoleID": ctx.ids.ref("operator_role", ctx.gcs)},
            "ApprovalReferences": {
                "ApprovalPolicyID": ctx.ids.ref("policy", "engagement"),
                "ApprovalItem": {"RequirementExecutionApproval": {
                    "RequirementID": {"TaskID": ctx.ids.ref("task", msg.task_id)}}},
            },
            "RespondBy": uci_timestamp(ctx.now() + APPROVAL_WINDOW),
        }


@register
class TaskCommandConverter(Converter):
    proto = "swarm.v1.TaskCommand"

    def to_uci(self, msg: c2_pb2.TaskCommand, ctx: ConvContext) -> dict:
        kind = msg.WhichOneof("task") or ""
        if not msg.cancel and kind not in IMPORTABLE_TASKS:
            raise ConversionError(f"task kind {kind!r} has no UCI form (only {IMPORTABLE_TASKS})")
        if not msg.assignees:
            raise ConversionError("assignees is empty")
        return {"Command": [{"Capability": {
            "CommandID": ctx.ids.ref("command", f"{msg.task_id}/{a}"),
            "CommandState": "CANCEL" if msg.cancel else "NEW",
            "CapabilityID": ctx.ids.ref("capability", f"{a}/{kind or 'hold'}"),
            "Ranking": {"Rank": {"Priority": 0, "PrecedenceWithinPriority": 0}},
            "TaskID": ctx.ids.ref("task", msg.task_id),
        }} for a in msg.assignees]}

    def from_uci(self, data: dict, ctx: ConvContext) -> tuple[c2_pb2.TaskCommand, list[str]]:
        commands = data.get("Command") or []
        msg = c2_pb2.TaskCommand()
        kinds: set[str] = set()
        states: set[str] = set()
        task_ids: set[str] = set()
        for cmd in commands:
            cap = cmd.get("Capability")
            if cap is None:
                raise ConversionError("only Capability commands are supported")
            label = ctx.ids.internal(cap.get("CapabilityID"))
            entity, _, kind = label.partition("/")
            if not ENTITY_ID_RE.match(entity):
                raise ConversionError(f"CapabilityID label {label!r} does not name an entity")
            kinds.add(kind)
            states.add(cap.get("CommandState", ""))
            task_ids.add(ctx.ids.internal(cap.get("TaskID")))
            if entity not in msg.assignees:
                msg.assignees.append(entity)
        if not msg.assignees:
            raise ConversionError("no Command")
        if len(task_ids) != 1 or len(states) != 1:
            raise ConversionError("commands must share one TaskID and CommandState")
        msg.task_id = task_ids.pop()
        state = states.pop()
        if state == "CANCEL":
            msg.cancel = True
        else:
            if len(kinds) != 1 or not kinds <= set(IMPORTABLE_TASKS):
                raise ConversionError(f"unsupported task kind(s) {sorted(kinds)}")
            getattr(msg, kinds.pop()).SetInParent()
        msg.header.source = ctx.gcs
        return msg, list(msg.assignees)
