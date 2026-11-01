// IMP-UI-025: GCS C2 명령 생성 (REQ-UI-002, REQ-UI-003, REQ-UI-004, DEC-013, DEC-014)
// TaskCommand(MoveTo·Hold·RTB), FormationCommand, GroupAssignment를 LinkEnvelope로 싸서 swarm/<gcs>/tx/c2/<msg>로 보낸다.
// dst는 명령을 받을 기체(assignees·members). 데이터링크(WP4)가 그 기체의 swarm/<id>/rx/c2/<msg>로 전달한다.
import type { DescMessage, MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { FormationShape } from "../gen/swarm/v1/c2_pb";
import { FormationCommandSchema, GroupAssignmentSchema, TaskCommandSchema } from "../gen/swarm/v1/c2_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";

export const ENVELOPE_ENCODING = `application/protobuf;${LinkEnvelopeSchema.typeName}`;

export function c2TxKey(gcs: string, msgName: string): string {
  return `swarm/${gcs}/tx/c2/${msgName}`;
}

/** 보낼 C2 메시지 하나 */
export interface OutgoingC2 {
  key: string;
  envelope: LinkEnvelope;
  /** 사람이 읽는 요약 (명령 기록용) */
  summary: string;
  taskId?: string;
  assignees: string[];
}

export type TaskKind = "moveTo" | "hold" | "returnToBase";

export interface MoveToTarget {
  latDeg: number;
  lonDeg: number;
  altM: number;
  speedMps?: number;
}

/** 현재 시뮬레이션 시각 (헤더용). 최신 truth/state에서 읽는다 */
export interface SimClock {
  simTimeUs: bigint;
  frame: bigint;
}

const SHORT_NAME = (s: DescMessage) => s.typeName.slice(s.typeName.lastIndexOf(".") + 1);

export class C2Commander {
  private readonly seq = new Map<string, number>();
  private taskCounter = 0;

  /** uiId는 task_id를 UI 인스턴스끼리 겹치지 않게 하는 접두어 (DEC-020) */
  constructor(
    readonly gcs: string,
    private readonly uiId: string,
    private readonly clock: () => SimClock = () => ({ simTimeUs: 0n, frame: 0n }),
  ) {}

  task(kind: TaskKind, assignees: readonly string[], target?: MoveToTarget): OutgoingC2 {
    if (assignees.length === 0) throw new Error("대상 기체가 없다");
    const taskId = `${this.uiId}-t${++this.taskCounter}`;
    let task: MessageInitShape<typeof TaskCommandSchema>["task"];
    let summary: string;
    if (kind === "moveTo") {
      if (!target) throw new Error("MoveTo에는 목적지가 필요하다");
      task = {
        case: "moveTo",
        value: { destination: { latDeg: target.latDeg, lonDeg: target.lonDeg, altM: target.altM }, speedMps: target.speedMps },
      };
      summary = `이동 ${target.latDeg.toFixed(4)}, ${target.lonDeg.toFixed(4)} @${target.altM.toFixed(0)} m`;
    } else if (kind === "hold") {
      task = { case: "hold", value: {} };
      summary = "대기";
    } else {
      task = { case: "returnToBase", value: {} };
      summary = "귀환";
    }
    const header = this.header(taskId);
    const msg = create(TaskCommandSchema, { header, taskId, assignees: [...assignees], task });
    return { ...this.wrap(TaskCommandSchema, msg, assignees, taskId), summary, taskId };
  }

  cancel(taskId: string, assignees: readonly string[]): OutgoingC2 {
    const msg = create(TaskCommandSchema, { header: this.header(taskId), taskId, assignees: [...assignees], cancel: true });
    return { ...this.wrap(TaskCommandSchema, msg, assignees, taskId), summary: "취소", taskId };
  }

  /** 편대 지정. members[0]이 리더(leader를 비우면 알고리즘이 정한다) */
  formation(groupId: string, members: readonly string[], shape: FormationShape, spacingM: number, leader = members[0] ?? ""): OutgoingC2 {
    if (members.length === 0) throw new Error("편대 구성원이 없다");
    const msg = create(FormationCommandSchema, {
      header: this.header(groupId),
      groupId,
      members: [...members],
      leader,
      shape,
      spacingM,
    });
    return { ...this.wrap(FormationCommandSchema, msg, members, groupId), summary: `편대 ${groupId}` };
  }

  /** 부대 그룹 지정 (Ctrl+숫자). 빈 members는 그룹 해제 */
  group(groupId: string, members: readonly string[], previous: readonly string[] = []): OutgoingC2 {
    const msg = create(GroupAssignmentSchema, { header: this.header(groupId), groupId, members: [...members] });
    // 그룹에서 빠진 기체도 알아야 하므로 이전 구성원에게도 보낸다
    const dst = [...new Set([...members, ...previous])];
    return { ...this.wrap(GroupAssignmentSchema, msg, dst, groupId), summary: `그룹 ${groupId} (${members.length})` };
  }

  private header(correlationId: string) {
    const c = this.clock();
    return { simTimeUs: c.simTimeUs, frame: c.frame, source: this.gcs, correlationId };
  }

  private wrap<D extends DescMessage>(schema: D, msg: MessageShape<D>, dst: readonly string[], correlationId: string) {
    const name = SHORT_NAME(schema);
    const key = c2TxKey(this.gcs, name);
    const seq = (this.seq.get(key) ?? 0) + 1;
    this.seq.set(key, seq);
    // 내부 메시지 헤더의 seq도 같은 값으로 맞춘다
    (msg as { header?: { seq: number } }).header!.seq = seq;
    const envelope = create(LinkEnvelopeSchema, {
      header: { ...this.header(correlationId), seq },
      dst: [...dst],
      iface: L1Interface.C2,
      msgType: schema.typeName,
      payload: toBinary(schema, msg),
      priority: 0,
    });
    return { key, envelope, assignees: [...dst] };
  }
}
