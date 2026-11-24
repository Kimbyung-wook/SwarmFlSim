// IMP-UI-086: 승인 요청 대기 목록 (REQ-UI-003, DEC-075, DEC-088, DEC-013)
// GCS가 아는 것만 쓴다.
// - 요청: swarm/<gcs>/rx/c2/ApprovalRequest (기체 MA가 보낸다)
// - 응답: swarm/<gcs>/tx/c2/ApprovalResponse. 이 UI·다른 UI·Gateway(외부 승인, DEC-075)가 같은 키로 보낸다.
//   MA는 대기 중인 요청에 처음 도착한 응답 하나만 처리하고 나머지는 버린다(common.py TaskTracker._on_approval).
//   그래서 tx에서 처음 본 응답을 "처리된 응답"으로, 그 뒤 것은 "늦음(무시)"으로 표시한다.
//   (데이터링크 지연이 발행자마다 같다고 본 추정이다. 확정은 그 작업의 TaskStatus로 보인다)
// - 응답 없이 끝남: 같은 기체가 그 작업의 TaskStatus를 보내면(시간 초과 REJECTED, 다른 명령에 밀려 CANCELLED 등) 닫는다
import { fromBinary } from "@bufbuild/protobuf";
import { ApprovalRequestSchema, ApprovalResponseSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";

export interface ApprovalAnswer {
  approved: boolean;
  /** LinkEnvelope.publisher (DEC-077). 비면 헤더 source */
  by: string;
  /** 이 UI가 보낸 응답 */
  mine: boolean;
}

export interface ApprovalView {
  requestId: string;
  /** 요청한 기체 */
  requester: string;
  taskId: string;
  targetId: string;
  description: string;
  /** 요청 시각(모의 us) */
  requestedUs: bigint;
  /** 처음 본 응답. MA가 처리하는 것 */
  decision: ApprovalAnswer | null;
  /** 처음 응답 뒤에 본 응답 (MA는 무시한다) */
  late: ApprovalAnswer[];
  /** 응답 없이 끝났거나 결과를 본 작업 상태. 열려 있으면 "" */
  outcome: string;
  /** 결과를 본 작업 상태 (없으면 UNSPECIFIED) */
  outcomeState: CommandState;
}

const STATE_TEXT: Partial<Record<CommandState, string>> = {
  [CommandState.ACCEPTED]: "수락",
  [CommandState.EXECUTING]: "수행",
  [CommandState.COMPLETED]: "완료",
  [CommandState.REJECTED]: "거부",
  [CommandState.CANCELLED]: "취소",
  [CommandState.FAILED]: "실패",
};

export class ApprovalStore {
  private readonly reqs = new Map<string, ApprovalView>();
  /** 같은 응답 봉투를 두 번 세지 않는다 (직접 넣은 것과 tx 되돌림) */
  private readonly seen = new Set<string>();
  version = 0;

  constructor(
    private readonly uiId: string,
    private readonly max = 50,
  ) {}

  /** swarm/<gcs>/rx/** */
  onRx(_key: string, env: LinkEnvelope): void {
    try {
      if (env.msgType === ApprovalRequestSchema.typeName) this.onRequest(env);
      else if (env.msgType === TaskStatusSchema.typeName) this.onStatus(env);
    } catch {
      // 깨진 봉투는 버린다
    }
  }

  /** swarm/<gcs>/tx/** (이 UI가 보낸 것도 직접 넣는다) */
  onTx(_key: string, env: LinkEnvelope): void {
    if (env.msgType !== ApprovalResponseSchema.typeName) return;
    let r;
    try {
      r = fromBinary(ApprovalResponseSchema, env.payload);
    } catch {
      return;
    }
    const by = env.publisher || env.header?.source || "?";
    const tag = `${by}|${env.header?.seq ?? 0}|${r.requestId}`;
    if (this.seen.has(tag)) return;
    this.seen.add(tag);
    if (this.seen.size > this.max * 8) this.seen.delete(this.seen.values().next().value!);
    const v = this.reqs.get(r.requestId);
    if (!v) return;
    const ans = { approved: r.approved, by, mine: by === this.uiId };
    if (v.decision === null && v.outcome === "") v.decision = ans;
    else v.late.push(ans);
    this.version++;
  }

  private onRequest(env: LinkEnvelope): void {
    const q = fromBinary(ApprovalRequestSchema, env.payload);
    if (!q.requestId || this.reqs.has(q.requestId)) return;
    this.reqs.set(q.requestId, {
      requestId: q.requestId,
      requester: q.header?.source || env.header?.source || "",
      taskId: q.taskId,
      targetId: q.targetId,
      description: q.description,
      requestedUs: q.header?.simTimeUs ?? env.header?.simTimeUs ?? 0n,
      decision: null,
      late: [],
      outcome: "",
      outcomeState: CommandState.UNSPECIFIED,
    });
    while (this.reqs.size > this.max) this.reqs.delete(this.reqs.keys().next().value!);
    this.version++;
  }

  private onStatus(env: LinkEnvelope): void {
    const st = fromBinary(TaskStatusSchema, env.payload);
    const src = st.header?.source || env.header?.source || "";
    for (const v of this.reqs.values()) {
      if (v.outcome !== "" || v.taskId !== st.taskId || v.requester !== src) continue;
      v.outcome = `${STATE_TEXT[st.state] ?? "?"}${st.reason ? ` (${st.reason})` : ""}`;
      v.outcomeState = st.state;
      this.version++;
    }
  }

  /** 응답도 결과도 없는 요청 */
  pending(): ApprovalView[] {
    return this.list().filter((v) => v.decision === null && v.outcome === "");
  }

  /** 최근 것이 먼저 */
  list(): ApprovalView[] {
    return [...this.reqs.values()].reverse();
  }

  get(requestId: string): ApprovalView | undefined {
    return this.reqs.get(requestId);
  }

  /** 시나리오가 바뀌거나 Reset되면 지운다 */
  clear(): void {
    this.reqs.clear();
    this.seen.clear();
    this.version++;
  }
}

/**
 * 남은 시간(s). timeoutS는 요청 기체의 MA 변수 approval_timeout_s(0 = 무한, 모르면 undefined).
 * 무한·모름이면 null, 지났으면 0
 */
export function approvalRemainingS(v: ApprovalView, timeoutS: number | undefined, nowUs: bigint | null): number | null {
  if (timeoutS === undefined || !(timeoutS > 0) || nowUs === null) return null;
  return Math.max(0, timeoutS - Number(nowUs - v.requestedUs) / 1e6);
}
