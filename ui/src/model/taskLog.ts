// IMP-UI-027: 명령 기록과 swarm/<gcs>/rx/** 상태 보고 (REQ-UI-003, REQ-UI-004)
// 보낸 명령을 task_id로 기억하고, 데이터링크를 거쳐 돌아온 TaskStatus를 기체별로 붙인다.
import { fromBinary } from "@bufbuild/protobuf";
import { TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import type { OutgoingC2 } from "./commands";

export interface ReportView {
  state: CommandState;
  progress: number;
  reason: string;
  simTimeUs: bigint;
}

export interface TaskEntry {
  id: string;
  summary: string;
  assignees: string[];
  /** 보낸 시각 (Date.now) */
  sentAt: number;
  /** 전송 실패 사유. 성공이면 비어 있다 */
  error: string;
  reports: Map<string, ReportView>;
}

export interface RxView {
  key: string;
  source: string;
  msgType: string;
  simTimeUs: bigint;
  size: number;
}

const STATE_LABEL: Record<CommandState, string> = {
  [CommandState.UNSPECIFIED]: "?",
  [CommandState.ACCEPTED]: "수락",
  [CommandState.REJECTED]: "거부",
  [CommandState.EXECUTING]: "수행",
  [CommandState.COMPLETED]: "완료",
  [CommandState.FAILED]: "실패",
  [CommandState.CANCELLED]: "취소",
};

export function commandStateLabel(s: CommandState): string {
  return STATE_LABEL[s] ?? "?";
}

export class TaskLog {
  private readonly tasks = new Map<string, TaskEntry>();
  /** 최근 수신(종류 무관) */
  readonly recentRx: RxView[] = [];
  version = 0;

  constructor(
    private readonly maxTasks = 30,
    private readonly maxRx = 20,
  ) {}

  sent(out: OutgoingC2, error = ""): TaskEntry {
    // TaskCommand는 task_id, 그 밖(편대·그룹)은 메시지 이름#seq로 구분한다
    const id = out.taskId ?? `${out.key.slice(out.key.lastIndexOf("/") + 1)}#${out.envelope.header?.seq ?? 0}`;
    const e: TaskEntry = { id, summary: out.summary, assignees: out.assignees, sentAt: Date.now(), error, reports: new Map() };
    this.tasks.delete(id);
    this.tasks.set(id, e);
    while (this.tasks.size > this.maxTasks) this.tasks.delete(this.tasks.keys().next().value!);
    this.version++;
    return e;
  }

  /** swarm/<gcs>/rx/** 로 받은 봉투. TaskStatus면 해당 명령에 붙인다 */
  received(key: string, env: LinkEnvelope): void {
    const source = env.header?.source ?? "";
    this.recentRx.unshift({ key, source, msgType: env.msgType, simTimeUs: env.header?.simTimeUs ?? 0n, size: env.payload.length });
    if (this.recentRx.length > this.maxRx) this.recentRx.length = this.maxRx;
    this.version++;
    if (env.msgType !== TaskStatusSchema.typeName) return;
    let st;
    try {
      st = fromBinary(TaskStatusSchema, env.payload);
    } catch {
      return;
    }
    const entry = this.tasks.get(st.taskId);
    if (!entry) return;
    entry.reports.set(st.header?.source || source, {
      state: st.state,
      progress: st.progress,
      reason: st.reason,
      simTimeUs: st.header?.simTimeUs ?? env.header?.simTimeUs ?? 0n,
    });
  }

  /** 최근 것이 먼저 */
  list(): TaskEntry[] {
    return [...this.tasks.values()].reverse();
  }

  get(id: string): TaskEntry | undefined {
    return this.tasks.get(id);
  }
}
