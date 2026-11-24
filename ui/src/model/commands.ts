// IMP-UI-025: GCS C2 명령 생성 (REQ-UI-002, REQ-UI-003, REQ-UI-004, DEC-013, DEC-014)
// TaskCommand(MoveTo·Hold·RTB), FormationCommand, GroupAssignment를 LinkEnvelope로 싸서 swarm/<gcs>/tx/c2/<msg>로 보낸다.
// dst는 명령을 받을 기체(assignees·members). 데이터링크(WP4)가 그 기체의 swarm/<id>/rx/c2/<msg>로 전달한다.
// IMP-UI-043: 선회 대기·항로점 선회에 레이스트랙(RacetrackShape) 지정 (DEC-034)
// IMP-UI-035: 지도 임무(이동·선회 대기·타격·정찰·항로)를 MissionSpec으로 받아 TaskCommand를 만든다 (DEC-033)
// IMP-UI-085: 재밍(JamTask: 영역, duration_s)·추적(TrackTask: target_id) 작업 (DEC-106)
// IMP-UI-086: 승인 응답 ApprovalResponse(tx/c2, DEC-075)
// IMP-UI-088: 작업별 링크 상실 정책 TaskCommand.lost_link_policy
// IMP-UI-089: 정찰·재밍 다각형 영역(Polygon, 3~100점)
// IMP-UI-091: 교전 기준 EngagementCriteria 배포 (swarm/<gcs>/tx/mp, L1 MP)
import type { DescMessage, MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { FormationShape } from "../gen/swarm/v1/c2_pb";
import {
  ApprovalResponseSchema,
  FormationCommandSchema,
  GroupAssignmentSchema,
  LostLinkPolicy,
  RouteWaypointSchema,
  TaskCommandSchema,
} from "../gen/swarm/v1/c2_pb";
import type { Side } from "../gen/swarm/v1/entity_pb";
import { EngagementCriteriaSchema } from "../gen/swarm/v1/mp_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";
import type { RacetrackSpec } from "./racetrack";
import { normalizeHeadingDeg } from "./racetrack";

export const ENVELOPE_ENCODING = `application/protobuf;${LinkEnvelopeSchema.typeName}`;

export function c2TxKey(gcs: string, msgName: string): string {
  return `swarm/${gcs}/tx/c2/${msgName}`;
}

/** swarm/<gcs>/tx/mp/<msg> (임무 계획 인터페이스, EngagementCriteria) */
export function mpTxKey(gcs: string, msgName: string): string {
  return `swarm/${gcs}/tx/mp/${msgName}`;
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
  | { kind: "loiter"; durationS: number; radiusM?: number; direction: TurnDirection; racetrack?: RacetrackSpec }
  | { kind: "recon"; radiusM: number; durationS?: number };

export interface WaypointSpec {
  position: GeoPoint;
  speedMps?: number;
  action: WaypointAction;
}

/** 정찰·재밍 영역. polygon(3점 이상)이 있으면 다각형, 없으면 center·radiusM 원 */
export interface AreaSpec {
  center: GeoPoint;
  radiusM: number;
  polygon?: GeoPoint[];
}

/** MA 상한 (algorithms common.py AREA_MAX_VERTICES) */
export const AREA_MAX_VERTICES = 100;

/** 지도에서 내리는 임무 하나 */
export type MissionSpec =
  | { kind: "moveTo"; destination: GeoPoint; speedMps?: number }
  | { kind: "hold"; center?: GeoPoint; radiusM?: number; durationS?: number; direction: TurnDirection; racetrack?: RacetrackSpec }
  | { kind: "strike"; weapon: WeaponType; targetId?: string; aimPoint?: GeoPoint }
  | ({ kind: "search" } & AreaSpec)
  | ({ kind: "jam"; durationS?: number } & AreaSpec)
  | { kind: "track"; targetId: string }
  | { kind: "route"; waypoints: WaypointSpec[]; loop: boolean }
  | { kind: "returnToBase" };

export const LOST_LINK_LABEL: Record<LostLinkPolicy, string> = {
  [LostLinkPolicy.UNSPECIFIED]: "MA 기본",
  [LostLinkPolicy.HOLD_UNTIL_COMMAND]: "선회 후 명령 대기",
  [LostLinkPolicy.RESUME_ON_RECOVERY]: "복구 시 재개",
  [LostLinkPolicy.CONTINUE]: "계속 수행",
};

/** 교전 기준 (EngagementCriteria). 영역은 원(중심·반경)만 지도 입력 없이 숫자로 받는다 */
export interface CriteriaSpec {
  hostileSides: Side[];
  requireApproval: boolean;
  weaponsFree: AreaSpec[];
  noStrike: AreaSpec[];
}

type TaskInit = MessageInitShape<typeof TaskCommandSchema>["task"];
type WaypointInit = MessageInitShape<typeof RouteWaypointSchema>;

const geo = (g: GeoPoint) => ({ latDeg: g.latDeg, lonDeg: g.lonDeg, altM: g.altM });
const fmtGeo = (g: GeoPoint) => `${g.latDeg.toFixed(4)}, ${g.lonDeg.toFixed(4)} @${g.altM.toFixed(0)} m`;
/** 0·음수·NaN은 "지정 안 함"(필드 없음)으로 본다 */
const opt = (v: number | undefined) => (v !== undefined && Number.isFinite(v) && v > 0 ? v : undefined);

/** 레이스트랙 → RacetrackShape. 직선 길이가 0 이하면 원과 같으므로 보내지 않는다 */
function raceInit(r: RacetrackSpec | undefined) {
  if (!r || !(r.legLengthM > 0)) return undefined;
  return { legLengthM: r.legLengthM, axisHeadingDeg: normalizeHeadingDeg(r.axisHeadingDeg) };
}

function waypointInit(w: WaypointSpec): WaypointInit {
  const a = w.action;
  let action: WaypointInit["action"] = { case: undefined };
  if (a.kind === "loiter") {
    action = { case: "loiter", value: { durationS: a.durationS, radiusM: opt(a.radiusM), direction: a.direction, racetrack: raceInit(a.racetrack) } };
  } else if (a.kind === "recon") {
    action = { case: "recon", value: { radiusM: a.radiusM, durationS: opt(a.durationS) } };
  }
  return { position: geo(w.position), speedMps: opt(w.speedMps), action };
}

function areaInit(a: AreaSpec) {
  if (a.polygon && a.polygon.length > 0) {
    if (a.polygon.length < 3) throw new Error("다각형 영역은 꼭짓점이 3개 이상이어야 한다");
    if (a.polygon.length > AREA_MAX_VERTICES) throw new Error(`다각형 영역 꼭짓점은 ${AREA_MAX_VERTICES}개까지`);
    return { shape: { case: "polygon" as const, value: { vertices: a.polygon.map(geo) } } };
  }
  if (!(a.radiusM > 0)) throw new Error("영역 반경은 0보다 커야 한다");
  return { shape: { case: "circle" as const, value: { center: geo(a.center), radiusM: a.radiusM } } };
}

const fmtArea = (a: AreaSpec) => (a.polygon && a.polygon.length ? `다각형 ${a.polygon.length}점` : `${fmtGeo(a.center)} r${a.radiusM.toFixed(0)}`);

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
        task: { case: "hold", value: { center: m.center && geo(m.center), radiusM: r, durationS: dur, direction: m.direction, racetrack: raceInit(m.racetrack) } },
        summary: `${raceInit(m.racetrack) ? "레이스트랙 " : ""}선회 대기${m.center ? ` ${fmtGeo(m.center)}` : ""}${r ? ` r${r.toFixed(0)}` : ""}${dur ? ` ${dur.toFixed(0)} s` : ""}`,
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
      return { task: { case: "searchArea", value: { area: areaInit(m) } }, summary: `정찰 ${fmtArea(m)}` };
    case "jam": {
      const dur = opt(m.durationS);
      return {
        task: { case: "jam", value: { area: areaInit(m), durationS: dur ?? 0 } },
        summary: `재밍 ${fmtArea(m)}${dur ? ` ${dur.toFixed(0)} s` : " (해제까지)"}`,
      };
    }
    case "track":
      if (!m.targetId) throw new Error("추적에는 표적이 필요하다");
      return { task: { case: "track", value: { targetId: m.targetId } }, summary: `추적 ${m.targetId}` };
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

  /** uiId는 브리지 hello의 client ID. task_id 접두어(DEC-020)이자 LinkEnvelope.publisher(IMP-UI-076, DEC-077) */
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

  /**
   * 지도 임무. taskId를 주면 그 작업을 같은 ID로 대체한다(항로 재전송, DEC-033).
   * lostLinkPolicy는 이 작업의 링크 상실 행동. UNSPECIFIED(기본)면 MA 변수 lost_link_policy를 따른다
   */
  mission(spec: MissionSpec, assignees: readonly string[], taskId?: string, lostLinkPolicy = LostLinkPolicy.UNSPECIFIED): OutgoingC2 {
    if (assignees.length === 0) throw new Error("대상 기체가 없다");
    const { task, summary } = missionTask(spec);
    const id = taskId ?? `${this.uiId}-t${++this.taskCounter}`;
    const msg = create(TaskCommandSchema, { header: this.header(id), taskId: id, assignees: [...assignees], task, lostLinkPolicy });
    const pol = lostLinkPolicy !== LostLinkPolicy.UNSPECIFIED ? ` · 상실 시 ${LOST_LINK_LABEL[lostLinkPolicy]}` : "";
    return { ...this.wrap(TaskCommandSchema, msg, assignees, id), summary: summary + pol, taskId: id, mission: spec };
  }

  /** 승인 요청에 대한 응답 (DEC-075). 요청한 기체에게만 보낸다 */
  approval(requestId: string, approved: boolean, requester: string): OutgoingC2 {
    if (!requestId || !requester) throw new Error("승인 요청 ID와 요청 기체가 필요하다");
    const msg = create(ApprovalResponseSchema, { header: this.header(requestId), requestId, approved });
    return { ...this.wrap(ApprovalResponseSchema, msg, [requester], requestId), summary: `${approved ? "승인" : "거부"} ${requestId}` };
  }

  /** 교전 기준 배포 (L1 MP, swarm/<gcs>/tx/mp/EngagementCriteria). 기본 MA는 받는 즉시 이후 승인·타격 판단에 쓴다 */
  engagementCriteria(c: CriteriaSpec, dst: readonly string[]): OutgoingC2 {
    if (dst.length === 0) throw new Error("대상 기체가 없다");
    const msg = create(EngagementCriteriaSchema, {
      header: this.header(""),
      hostileSides: [...c.hostileSides],
      requireApproval: c.requireApproval,
      weaponsFree: c.weaponsFree.map(areaInit),
      noStrike: c.noStrike.map(areaInit),
    });
    const parts = [c.requireApproval ? "승인 필요" : "승인 없음", `무기 사용 ${c.weaponsFree.length}`, `타격 금지 ${c.noStrike.length}`];
    return { ...this.wrap(EngagementCriteriaSchema, msg, dst, "", L1Interface.MP), summary: `교전 기준 (${parts.join(", ")})` };
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

  private wrap<D extends DescMessage>(schema: D, msg: MessageShape<D>, dst: readonly string[], correlationId: string, iface = L1Interface.C2) {
    const name = SHORT_NAME(schema);
    const key = iface === L1Interface.MP ? mpTxKey(this.gcs, name) : c2TxKey(this.gcs, name);
    const seq = (this.seq.get(key) ?? 0) + 1;
    this.seq.set(key, seq);
    // 내부 메시지 헤더의 seq도 같은 값으로 맞춘다
    (msg as { header?: { seq: number } }).header!.seq = seq;
    const envelope = create(LinkEnvelopeSchema, {
      header: { ...this.header(correlationId), seq },
      publisher: this.uiId, // DEC-077: GCS tx 키는 UI와 Gateway가 함께 쓴다. seq는 발행자·키별
      dst: [...dst],
      iface,
      msgType: schema.typeName,
      payload: toBinary(schema, msg),
      priority: 0,
    });
    return { key, envelope, assignees: [...dst] };
  }
}
