// IMP-UI-093: 목 소스의 운용 시나리오 흉내 (docs/51 §4 UI 보완을 Core·Agent 없이 화면에서 확인하려는 것)
// - 고장 주입(InjectFault): KILL은 엔티티를 파괴(자리에 멈춤), LINK_CUT·GCS_LINK_CUT은 그 기체와 GCS 사이 송수신을 끊는다.
//   ENGINE·SENSOR·NAV는 기록만 한다 (목 동역학·센서가 없다)
// - 승인: 작업 종류가 MA 변수 approval_tasks에 있거나, 교전 기준(tx/mp/EngagementCriteria) require_approval이고 타격이면
//   ApprovalRequest를 rx/c2로 내고 ApprovalResponse를 기다린다. approval_timeout_s가 지나면 REJECTED(approval timeout).
//   기본 MA처럼 대기 중인 요청에 처음 온 응답 하나만 처리한다 (common.py TaskTracker)
// - StoreLoadout(rx/ms): 적재·Reset 때 UAV마다
// - LeaderUpdate(rx/p2p): FormationCommand를 받으면 리더(지정, 없으면 사전순 첫 기체)가 term을 올려 알린다
// - TrackShare(rx/p2p): 추적·타격(target_id) 중인 기체가 1 Hz로 표적 위치를 공유한다
import type { DescMessage, MessageShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { TaskCommand } from "../gen/swarm/v1/c2_pb";
import { ApprovalRequestSchema } from "../gen/swarm/v1/c2_pb";
import { Vec3Schema } from "../gen/swarm/v1/common_pb";
import type { EntityState } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import type { EngagementCriteria } from "../gen/swarm/v1/mp_pb";
import { StoreLoadoutSchema } from "../gen/swarm/v1/ms_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { LeaderUpdateSchema, TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import type { InjectFault } from "../gen/swarm/v1/sim_pb";
import { FaultKind } from "../gen/swarm/v1/sim_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";

/** 기본 MA의 작업 이름 (TaskCommand oneof → approval_tasks 이름) */
const TASK_NAME: Record<string, string> = {
  moveTo: "move_to",
  hold: "hold",
  returnToBase: "return_to_base",
  searchArea: "search_area",
  route: "route",
  strike: "strike",
  track: "track",
  jam: "jam",
};

export interface Outbound {
  key: string;
  env: LinkEnvelope;
}

interface Awaiting {
  requestId: string;
  entity: string;
  cmd: TaskCommand;
  sinceUs: bigint;
}

export class MockOps {
  /** 파괴한 엔티티 → 고정한 상태 (null이면 다음 프레임에 고정) */
  private readonly killed = new Map<string, EntityState | null>();
  /** 기체 → 단절 끝 모의 us (해제까지면 최대값) */
  private readonly cut = new Map<string, bigint>();
  private readonly faultsOther = new Map<string, bigint>();
  private criteria: EngagementCriteria | null = null;
  private readonly awaiting = new Map<string, Awaiting>();
  private approvalN = 0;
  private readonly terms = new Map<string, bigint>();
  /** 기체 → 추적 중 표적 */
  private readonly targetOf = new Map<string, string>();

  constructor(private readonly gcs: string) {}

  reset(): void {
    this.killed.clear();
    this.cut.clear();
    this.faultsOther.clear();
    this.criteria = null;
    this.awaiting.clear();
    this.terms.clear();
    this.targetOf.clear();
  }

  // ---- 고장 ----

  fault(f: InjectFault, nowUs: bigint): void {
    const until = f.durationS > 0 ? nowUs + BigInt(Math.round(f.durationS * 1e6)) : BigInt(Number.MAX_SAFE_INTEGER);
    switch (f.fault) {
      case FaultKind.KILL:
        if (!f.clear && !this.killed.has(f.entityId)) this.killed.set(f.entityId, null); // 다음 프레임에서 위치를 고정한다
        return;
      case FaultKind.LINK_CUT:
      case FaultKind.GCS_LINK_CUT:
        if (f.clear) this.cut.delete(f.entityId);
        else this.cut.set(f.entityId, until);
        return;
      case FaultKind.ENGINE:
      case FaultKind.SENSOR:
      case FaultKind.NAV: {
        const k = `${f.entityId}|${f.fault}`;
        if (f.clear) this.faultsOther.delete(k);
        else this.faultsOther.set(k, until);
        return;
      }
      default:
        return;
    }
  }

  /** 그 기체와 GCS 사이 링크가 살아 있는지 (파괴된 기체는 보내지 않는다) */
  linked(id: string, nowUs: bigint): boolean {
    if (this.killed.has(id)) return false;
    const u = this.cut.get(id);
    if (u === undefined) return true;
    if (nowUs >= u) {
      this.cut.delete(id);
      return true;
    }
    return false;
  }

  isKilled(id: string): boolean {
    return this.killed.has(id);
  }

  /** 파괴된 엔티티는 alive=false로, 파괴 시점 자리에 고정한다 */
  applyFrame(f: TruthFrame): void {
    if (this.killed.size === 0) return;
    f.entities = f.entities.map((e) => {
      if (!this.killed.has(e.id)) return e;
      let snap = this.killed.get(e.id);
      if (!snap) {
        snap = { ...e, alive: false, kinematics: e.kinematics && { ...e.kinematics, velocityNedMps: create(Vec3Schema, {}) } };
        this.killed.set(e.id, snap);
      }
      return snap;
    });
  }

  // ---- 승인 ----

  onCriteria(c: EngagementCriteria): void {
    this.criteria = c;
  }

  /** 이 기체가 이 작업 전에 승인을 받아야 하는지. approvalTasks는 그 기체 MA 변수 approval_tasks */
  needsApproval(cmd: TaskCommand, approvalTasks: string): boolean {
    const kind = cmd.task.case;
    if (!kind || cmd.cancel) return false;
    const listed = new Set(approvalTasks.split(",").map((s) => s.trim()).filter(Boolean));
    if (listed.has(TASK_NAME[kind] ?? kind)) return true;
    return kind === "strike" && this.criteria?.requireApproval === true;
  }

  /** 승인 요청을 낸다. 같은 기체가 기다리던 요청은 밀려난다(취소 작업 ID를 돌려준다) */
  request(entity: string, cmd: TaskCommand, nowUs: bigint, frame: bigint): { out: Outbound; preempted: string | null } {
    let preempted: string | null = null;
    for (const [rid, a] of this.awaiting) if (a.entity === entity) {
      this.awaiting.delete(rid);
      if (a.cmd.taskId !== cmd.taskId) preempted = a.cmd.taskId;
    }
    const requestId = `${entity}-approval-${++this.approvalN}`;
    this.awaiting.set(requestId, { requestId, entity, cmd, sinceUs: nowUs });
    const kind = cmd.task.case ?? "";
    const msg = create(ApprovalRequestSchema, {
      header: { simTimeUs: nowUs, frame, source: entity, correlationId: cmd.taskId },
      requestId,
      taskId: cmd.taskId,
      targetId: cmd.task.case === "strike" || cmd.task.case === "track" ? cmd.task.value.targetId : "",
      description: `${TASK_NAME[kind] ?? kind} ${cmd.taskId}`,
    });
    return { out: this.wrap(entity, "c2", ApprovalRequestSchema, msg, nowUs, frame, L1Interface.C2), preempted };
  }

  /** 응답. 기다리는 요청이면 그것을 돌려주고 지운다(처음 응답만). 모르는·끝난 요청이면 null */
  answer(requestId: string): Awaiting | null {
    const a = this.awaiting.get(requestId);
    if (!a) return null;
    this.awaiting.delete(requestId);
    return a;
  }

  /** 그 기체가 이 작업의 승인을 기다리면 버린다(취소 명령) */
  cancelAwaiting(entity: string, taskId: string): boolean {
    for (const [rid, a] of this.awaiting) if (a.entity === entity && a.cmd.taskId === taskId) {
      this.awaiting.delete(rid);
      return true;
    }
    return false;
  }

  /** 다른 명령이 오면 그 기체의 승인 대기를 버린다. 취소된 작업 ID */
  dropAwaiting(entity: string, keepTaskId: string): string | null {
    for (const [rid, a] of this.awaiting) if (a.entity === entity) {
      this.awaiting.delete(rid);
      return a.cmd.taskId === keepTaskId ? null : a.cmd.taskId;
    }
    return null;
  }

  /** 시간 초과한 요청 (지운다). timeoutOf: 기체 MA 변수 approval_timeout_s (0 = 무한) */
  expired(nowUs: bigint, timeoutOf: (id: string) => number): Awaiting[] {
    const out: Awaiting[] = [];
    for (const [rid, a] of this.awaiting) {
      const t = timeoutOf(a.entity);
      if (t > 0 && nowUs - a.sinceUs > BigInt(Math.round(t * 1e6))) {
        this.awaiting.delete(rid);
        out.push(a);
      }
    }
    return out;
  }

  // ---- 수신 정보 ----

  loadout(entity: string, nowUs: bigint, frame: bigint): Outbound {
    const msg = create(StoreLoadoutSchema, {
      header: { simTimeUs: nowUs, frame, source: entity },
      stores: [
        { id: "cam0", type: "camera", count: 0 },
        { id: "jam0", type: "jammer", count: 0 },
        { id: "sta1", type: "agm_short", count: 2 },
      ],
    });
    return this.wrap(entity, "ms", StoreLoadoutSchema, msg, nowUs, frame, L1Interface.MS);
  }

  leader(groupId: string, members: readonly string[], leader: string, nowUs: bigint, frame: bigint): Outbound | null {
    const who = leader || [...members].sort()[0];
    if (!who) return null;
    const term = (this.terms.get(groupId) ?? 0n) + 1n;
    this.terms.set(groupId, term);
    const msg = create(LeaderUpdateSchema, { header: { simTimeUs: nowUs, frame, source: who }, groupId, leader: who, term });
    return this.wrap(who, "p2p", LeaderUpdateSchema, msg, nowUs, frame, L1Interface.P2P);
  }

  /** 작업을 받은 기체의 추적 표적을 고친다 */
  onTask(entity: string, cmd: TaskCommand): void {
    if (cmd.cancel) {
      this.targetOf.delete(entity);
      return;
    }
    const t = cmd.task;
    if ((t.case === "track" || t.case === "strike") && t.value.targetId) this.targetOf.set(entity, t.value.targetId);
    else this.targetOf.delete(entity);
  }

  /** 추적 중인 기체마다 TrackShare (표적 위치는 목 프레임) */
  tracks(f: TruthFrame, nowUs: bigint, frame: bigint): Outbound[] {
    const out: Outbound[] = [];
    for (const [uav, tgt] of this.targetOf) {
      if (!this.linked(uav, nowUs)) continue;
      const e = f.entities.find((x) => x.id === tgt);
      if (!e?.alive || !e.kinematics?.position) continue;
      const msg = create(TrackShareSchema, {
        header: { simTimeUs: nowUs, frame, source: uav },
        trackId: `${uav}-${tgt}`,
        targetId: tgt,
        position: e.kinematics.position,
        velocityNedMps: e.kinematics.velocityNedMps,
        kind: e.kind,
        observedTimeUs: nowUs,
      });
      out.push(this.wrap(uav, "p2p", TrackShareSchema, msg, nowUs, frame, L1Interface.P2P));
    }
    return out;
  }

  private wrap<D extends DescMessage>(src: string, iface: string, schema: D, msg: MessageShape<D>, nowUs: bigint, frame: bigint, l1: L1Interface): Outbound {
    const env = create(LinkEnvelopeSchema, {
      header: { simTimeUs: nowUs, frame, source: src },
      dst: [this.gcs],
      iface: l1,
      msgType: schema.typeName,
      payload: toBinary(schema, msg),
      rxTimeUs: nowUs,
    });
    return { key: `swarm/${this.gcs}/rx/${iface}/${schema.typeName.slice(schema.typeName.lastIndexOf(".") + 1)}`, env };
  }
}
