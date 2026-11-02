// IMP-UI-025: GCS C2 명령 생성 (REQ-UI-002, REQ-UI-003, REQ-UI-004, DEC-013, DEC-014)
// TaskCommand(MoveTo·Hold·RTB), FormationCommand, GroupAssignment를 LinkEnvelope로 싸서 swarm/<gcs>/tx/c2/<msg>로 보낸다.
// dst는 명령을 받을 기체(assignees·members). 데이터링크(WP4)가 그 기체의 swarm/<id>/rx/c2/<msg>로 전달한다.
// IMP-UI-035: 지도 임무(이동·선회 대기·타격·정찰·항로)를 MissionSpec으로 받아 TaskCommand를 만든다 (DEC-033)
import type { DescMessage, MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { FormationShape } from "../gen/swarm/v1/c2_pb";
import { FormationCommandSchema, GroupAssignmentSchema, RouteWaypointSchema, TaskCommandSchema } from "../gen/swarm/v1/c2_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";

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
  /** 지도 임무 명령이면 그 내용 (지도 표시·항로 다시 편집용) */
  mission?: MissionSpec;
}

export type TaskKind = "moveTo" | "hold" | "returnToBase";

export interface MoveToTarget {
  latDeg: number;
  lonDeg: number;
  altM: number;
  speedMps?: number;
}

export interface GeoPoint {
  latDeg: number;
  lonDeg: number;
  altM: number;
}

export const WEAPON_TYPES = ["aam_short", "agm_short", "fpv"] as const;
export type WeaponType = (typeof WEAPON_TYPES)[number];

/** 항로점 행위 (DEC-033) */
export type WaypointAction =
  | { kind: "none" }
  | { kind: "loiter"; durationS: number; radiusM?: number; direction: TurnDirection }
  | { kind: "recon"; radiusM: number; durationS?: number };

export interface WaypointSpec {
  position: GeoPoint;
  speedMps?: number;
  action: WaypointAction;
}

/** 지도에서 내리는 임무 하나 */
export type MissionSpec =
  | { kind: "moveTo"; destination: GeoPoint; speedMps?: number }
  | { kind: "hold"; center?: GeoPoint; radiusM?: number; durationS?: number; direction: TurnDirection }
  | { kind: "strike"; weapon: WeaponType; targetId?: string; aimPoint?: GeoPoint }
  | { kind: "search"; center: GeoPoint; radiusM: number }
  | { kind: "route"; waypoints: WaypointSpec[]; loop: boolean }
  | { kind: "returnToBase" };

type TaskInit = MessageInitShape<typeof TaskCommandSchema>["task"];
type WaypointInit = MessageInitShape<typeof RouteWaypointSchema>;

const geo = (g: GeoPoint) => ({ latDeg: g.latDeg, lonDeg: g.lonDeg, altM: g.altM });
const fmtGeo = (g: GeoPoint) => `${g.latDeg.toFixed(4)}, ${g.lonDeg.toFixed(4)} @${g.altM.toFixed(0)} m`;
/** 0·음수·NaN은 "지정 안 함"(필드 없음)으로 본다 */
const opt = (v: number | undefined) => (v !== undefined && Number.isFinite(v) && v > 0 ? v : undefined);

function waypointInit(w: WaypointSpec): WaypointInit {
  const a = w.action;
  let action: WaypointInit["action"] = { case: undefined };
  if (a.kind === "loiter") {
    action = { case: "loiter", value: { durationS: a.durationS, radiusM: opt(a.radiusM), direction: a.direction } };
  } else if (a.kind === "recon") {
    action = { case: "recon", value: { radiusM: a.radiusM, durationS: opt(a.durationS) } };
  }
  return { position: geo(w.position), speedMps: opt(w.speedMps), action };
}

/** MissionSpec → TaskCommand.task와 요약 */
export function missionTask(m: MissionSpec): { task: TaskInit; summary: string } {
  switch (m.kind) {
    case "moveTo":
      return {
        task: { case: "moveTo", value: { destination: geo(m.destination), speedMps: opt(m.speedMps) } },
        summary: `이동 ${fmtGeo(m.destination)}`,
      };
    case "hold": {
      const r = opt(m.radiusM);
      const dur = opt(m.durationS);
      return {
        task: { case: "hold", value: { center: m.center && geo(m.center), radiusM: r, durationS: dur, direction: m.direction } },
        summary: `선회 대기${m.center ? ` ${fmtGeo(m.center)}` : ""}${r ? ` r${r.toFixed(0)}` : ""}${dur ? ` ${dur.toFixed(0)} s` : ""}`,
      };
    }
    case "strike":
      if (!m.targetId && !m.aimPoint) throw new Error("타격에는 표적이나 조준점이 필요하다");
      return {
        task: {
          case: "strike",
          value: { targetId: m.targetId ?? "", aimPoint: m.targetId ? undefined : geo(m.aimPoint!), weaponType: m.weapon },
        },
        summary: `타격 ${m.targetId ?? fmtGeo(m.aimPoint!)} (${m.weapon})`,
      };
    case "search":
      if (!(m.radiusM > 0)) throw new Error("정찰 반경은 0보다 커야 한다");
      return {
        task: { case: "searchArea", value: { area: { shape: { case: "circle", value: { center: geo(m.center), radiusM: m.radiusM } } } } },
        summary: `정찰 ${fmtGeo(m.center)} r${m.radiusM.toFixed(0)}`,
      };
    case "route":
      if (m.waypoints.length === 0) throw new Error("항로점이 없다");
      return {
        task: { case: "route", value: { waypoints: m.waypoints.map(waypointInit), loop: m.loop } },
        summary: `항로 ${m.waypoints.length}점${m.loop ? " (반복)" : ""}`,
      };
    case "returnToBase":
      return { task: { case: "returnToBase", value: {} }, summary: "귀환" };
  }
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
    if (kind === "moveTo") {
      if (!target) throw new Error("MoveTo에는 목적지가 필요하다");
      const { speedMps, ...destination } = target;
      return this.mission({ kind: "moveTo", destination, speedMps }, assignees);
    }
    if (kind === "hold") {
      return { ...this.mission({ kind: "hold", direction: TurnDirection.UNSPECIFIED }, assignees), summary: "대기" };
    }
    return this.mission({ kind: "returnToBase" }, assignees);
  }

  /** 지도 임무. taskId를 주면 그 작업을 같은 ID로 대체한다(항로 재전송, DEC-033) */
  mission(spec: MissionSpec, assignees: readonly string[], taskId?: string): OutgoingC2 {
    if (assignees.length === 0) throw new Error("대상 기체가 없다");
    const { task, summary } = missionTask(spec);
    const id = taskId ?? `${this.uiId}-t${++this.taskCounter}`;
    const msg = create(TaskCommandSchema, { header: this.header(id), taskId: id, assignees: [...assignees], task });
    return { ...this.wrap(TaskCommandSchema, msg, assignees, id), summary, taskId: id, mission: spec };
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
