// IMP-UI-080: 기체별 현재 행동 (REQ-UI-003, DEC-013). Cesium에 의존하지 않는다.
// GCS가 아는 것만 쓴다. truth/**·onboard/**·MA 내부 상태는 쓰지 않는다.
// - 현재 작업: 그 기체가 보낸 TaskStatus 중 끝나지 않은(ACCEPTED·EXECUTING) 가장 최근 작업. 끝 상태(COMPLETED·CANCELLED·FAILED·REJECTED)면 지운다
// - 작업 내용: swarm/<gcs>/tx/**로 나간 TaskCommand·MissionPlan·RoutePlan(UI 자신과 Gateway), 시나리오 mission_plan(sim/ctrl/scenario)
// - 기체 위치: swarm/<gcs>/rx/vi/NavigationReport. 표시할 때는 받은 뒤 흐른 시간만큼 속도로 외삽한다
// - 귀환점: 그 기체가 처음 보고한 NavigationReport 위치 (Agent MA home 규칙, algorithms common.py TaskTracker.update와 같다)
// - 타격 표적: aim_point, 없으면 GCS가 받은 TrackShare(rx/p2p) 중 그 target_id의 최근 위치
// 편대 슬롯·flocking 목표처럼 GCS가 모르는 것은 그리지 않는다.
// IMP-UI-085: 재밍 작업은 영역 윤곽(원·다각형)과 중심을 그린다
import { fromBinary } from "@bufbuild/protobuf";
import type { TaskCommand } from "../gen/swarm/v1/c2_pb";
import { TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import type { Area, Geodetic } from "../gen/swarm/v1/common_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import type { MissionPlan, RoutePlan } from "../gen/swarm/v1/mp_pb";
import { MissionPlanSchema, RoutePlanSchema } from "../gen/swarm/v1/mp_pb";
import { TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import type { Scenario } from "../gen/swarm/v1/sim_pb";
import { NavigationReportSchema } from "../gen/swarm/v1/vi_pb";
import type { GeoPoint } from "./commands";
import { distanceBearing, fromLocal, racetrackGeometry } from "./racetrack";

/** 작업에 반경이 없을 때 내장 MA(waypoint·flocking)의 hold_radius_m 기본값. MA 변수가 보이면 그 값을 쓴다 */
export const MA_DEFAULT_HOLD_RADIUS_M = 300;
/** 내장 MA의 항로점 도달 판정 기본값(acceptance_m) */
export const MA_DEFAULT_ACCEPTANCE_M = 80;
/** 보고 뒤 이보다 오래 외삽하지 않는다(링크 상실 등). 이후에는 마지막 위치에 멈춘다 */
export const MAX_EXTRAPOLATE_S = 3;

export type ActivityKind = "moveTo" | "route" | "hold" | "returnToBase" | "strike" | "track" | "search" | "jam";
export type Glyph = "o" | "x";

export interface ActivityMark {
  pos: GeoPoint;
  glyph: Glyph;
}

/** 기체 하나의 현재 행동 도형 */
export interface ActivityShape {
  entityId: string;
  taskId: string;
  kind: ActivityKind;
  /** 짧은 설명 (선택 기체 라벨) */
  label: string;
  /** 기체 → 이 점 대시선. 없으면 긋지 않는다 */
  lead: GeoPoint | null;
  marks: ActivityMark[];
  /** 옅은 채움 원 (선회·항로점 선회·정찰) */
  circles: { center: GeoPoint; radiusM: number }[];
  /** 실선 (남은 항로·레이스트랙·영역 윤곽) */
  paths: GeoPoint[][];
  /** 다음 항로점을 추정했으면 true */
  estimated: boolean;
}

interface NavFix {
  pos: GeoPoint;
  /** 북·동·아래 m/s */
  vel: { n: number; e: number; d: number };
  /** 보고 시각(모의 us) */
  sentUs: bigint;
  /** 받은 벽시계(ms). 모의 시각을 모를 때만 쓴다 */
  wallMs: number;
}

interface StatusView {
  state: CommandState;
  progress: number;
  /** 받은 순번 (작업 간 최근 비교) */
  seq: number;
  /** 이 작업의 첫 보고를 받을 때의 기체 위치 (중심 없는 선회의 중심) */
  startPos: GeoPoint | null;
}

interface QuietRoute {
  routeId: string;
  waypoints: { pos: GeoPoint; acceptM: number }[];
  seq: number;
  /** 도달했다고 본 항로점 수 (추정) */
  reached: number;
}

const TERMINAL = new Set([CommandState.COMPLETED, CommandState.CANCELLED, CommandState.FAILED, CommandState.REJECTED]);
const ACTIVE = new Set([CommandState.ACCEPTED, CommandState.EXECUTING]);

const geo = (g: Geodetic | undefined): GeoPoint | null => (g ? { latDeg: g.latDeg, lonDeg: g.lonDeg, altM: g.altM } : null);
const msgName = (key: string) => key.slice(key.lastIndexOf("/") + 1);

const KIND_LABEL: Record<ActivityKind, string> = {
  moveTo: "이동",
  route: "항로",
  hold: "선회",
  returnToBase: "귀환",
  strike: "타격",
  track: "추적",
  search: "정찰",
  jam: "재밍",
};

/** 영역 윤곽(닫힘)과 중심. 원은 48각형으로 그린다 */
export function areaOutline(a: Area | undefined, altM = 0): { outline: GeoPoint[]; center: GeoPoint } | null {
  const s = a?.shape;
  if (s?.case === "circle" && s.value.center) {
    const c = s.value.center;
    const out: GeoPoint[] = [];
    for (let i = 0; i <= 48; i++) {
      const t = (2 * Math.PI * i) / 48;
      const p = fromLocal(c, s.value.radiusM * Math.cos(t), s.value.radiusM * Math.sin(t));
      out.push({ ...p, altM });
    }
    return { outline: out, center: { latDeg: c.latDeg, lonDeg: c.lonDeg, altM } };
  }
  if (s?.case === "polygon" && s.value.vertices.length >= 3) {
    const vs = s.value.vertices.map((v) => ({ latDeg: v.latDeg, lonDeg: v.lonDeg, altM }));
    const n = vs.length;
    const center = { latDeg: vs.reduce((x, v) => x + v.latDeg, 0) / n, lonDeg: vs.reduce((x, v) => x + v.lonDeg, 0) / n, altM };
    return { outline: [...vs, vs[0]], center };
  }
  return null;
}

export class ActivityStore {
  /** task_id → 작업 내용 */
  private readonly tasks = new Map<string, TaskCommand>();
  /** 기체 → (task_id → 최근 상태). 끝난 작업은 지운다 */
  private readonly status = new Map<string, Map<string, StatusView>>();
  private readonly nav = new Map<string, NavFix>();
  private readonly home = new Map<string, GeoPoint>();
  private readonly tracks = new Map<string, { pos: GeoPoint; observedUs: bigint }>();
  /** 상태를 보고하지 않는 단독 RoutePlan (같은 ID의 작업이 없을 때). 기체별 */
  private readonly quiet = new Map<string, QuietRoute>();
  private seq = 0;
  private scenarioKey = "";
  private lastSimUs = -1n;
  private clock: { simUs: bigint; wallMs: number; rate: number } | null = null;
  /** 무엇이든 바뀌면 1 증가 */
  version = 0;

  constructor(
    /** 그 기체 MA 변수 hold_radius_m (sim/param). 모르면 undefined */
    private readonly holdRadiusOf: (id: string) => number | undefined = () => undefined,
  ) {}

  // ---- 입력 ----

  /** swarm/<gcs>/tx/** 로 나간 봉투 (UI 자신과 Gateway) */
  onTx(key: string, env: LinkEnvelope): void {
    const name = env.msgType.slice(env.msgType.lastIndexOf(".") + 1) || msgName(key);
    try {
      if (name === "TaskCommand") this.addTask(fromBinary(TaskCommandSchema, env.payload));
      else if (name === "MissionPlan") this.addPlan(fromBinary(MissionPlanSchema, env.payload));
      else if (name === "RoutePlan") this.addRoutePlan(fromBinary(RoutePlanSchema, env.payload));
      else return;
    } catch {
      return;
    }
    this.version++;
  }

  /** sim/ctrl/scenario. 다른 시나리오면 지난 실행의 상태를 지우고 mission_plan 작업을 담는다 */
  onScenario(s: Scenario): void {
    const key = `${s.name}|${s.missionPlan?.planId ?? ""}|${s.run?.seed ?? 0n}`;
    if (key === this.scenarioKey) return;
    if (this.scenarioKey !== "") this.resetRun(true);
    this.scenarioKey = key;
    if (s.missionPlan) this.addPlan(s.missionPlan);
    this.version++;
  }

  /**
   * sim/ctrl/status. 표시 위치 외삽의 모의 시각 기준이다(rate는 실행 중 배속, 멈춤이면 0).
   * 시각이 크게 뒤로 가면(Reset) 기체 보고·귀환점을 지운다. 작업 내용은 둔다
   */
  onSimStatus(simUs: bigint, rate: number, wallMs = Date.now()): void {
    if (this.lastSimUs >= 0n && simUs + 1_000_000n < this.lastSimUs) this.resetRun(false);
    this.lastSimUs = simUs;
    this.clock = { simUs, wallMs, rate };
  }

  /** 지금 모의 시각 추정(us): 마지막 status 시각 + 흐른 벽시계 × 배속. status를 받은 적 없으면 null */
  simNowUs(wallMs = Date.now()): bigint | null {
    const c = this.clock;
    if (!c) return null;
    return c.simUs + BigInt(Math.round(Math.max(0, wallMs - c.wallMs) * 1000 * c.rate));
  }

  /** swarm/<gcs>/rx/** */
  onRx(key: string, env: LinkEnvelope, wallMs = Date.now()): void {
    const name = env.msgType.slice(env.msgType.lastIndexOf(".") + 1);
    try {
      if (name === "NavigationReport") this.onNav(env, wallMs);
      else if (name === "TaskStatus") this.onStatus(env);
      else if (name === "TrackShare") this.onTrack(env);
      else return;
    } catch {
      return;
    }
    this.version++;
    void key;
  }

  private addTask(t: TaskCommand): void {
    if (t.cancel || !t.taskId || t.task.case === undefined) return;
    this.tasks.set(t.taskId, t);
    // 같은 ID의 계획 작업이 생기면 단독 항로가 아니다
    for (const [id, q] of this.quiet) if (q.routeId === t.taskId) this.quiet.delete(id);
  }

  private addPlan(p: MissionPlan): void {
    for (const t of p.tasks) this.addTask(t);
  }

  /** Gateway는 route_id를 task_id로 쓴다. 같은 ID의 작업이 있으면 그 작업이 수행하므로 따로 보지 않는다 (waypoint MA와 같은 규칙) */
  private addRoutePlan(rp: RoutePlan): void {
    if (!rp.entityId || rp.waypoints.length === 0 || this.tasks.has(rp.routeId)) return;
    const wps = rp.waypoints.flatMap((w) => {
      const p = geo(w.position);
      return p ? [{ pos: p, acceptM: w.acceptanceRadiusM > 0 ? w.acceptanceRadiusM : MA_DEFAULT_ACCEPTANCE_M }] : [];
    });
    if (wps.length) this.quiet.set(rp.entityId, { routeId: rp.routeId, waypoints: wps, seq: ++this.seq, reached: 0 });
  }

  private onNav(env: LinkEnvelope, wallMs: number): void {
    const r = fromBinary(NavigationReportSchema, env.payload);
    const id = r.header?.source || env.header?.source || "";
    const p = geo(r.kinematics?.position);
    if (!id || !p) return;
    const v = r.kinematics?.velocityNedMps;
    const sentUs = r.header?.simTimeUs ?? env.header?.simTimeUs ?? 0n;
    this.nav.set(id, { pos: p, vel: { n: v?.x ?? 0, e: v?.y ?? 0, d: v?.z ?? 0 }, sentUs, wallMs });
    if (!this.home.has(id)) this.home.set(id, p);
    this.advanceQuiet(id, p);
  }

  private onStatus(env: LinkEnvelope): void {
    const st = fromBinary(TaskStatusSchema, env.payload);
    const id = st.header?.source || env.header?.source || "";
    if (!id || !st.taskId) return;
    let per = this.status.get(id);
    if (TERMINAL.has(st.state)) {
      per?.delete(st.taskId);
      const q = this.quiet.get(id);
      if (q?.routeId === st.taskId) this.quiet.delete(id);
      return;
    }
    if (!ACTIVE.has(st.state)) return;
    if (!per) this.status.set(id, (per = new Map()));
    const prev = per.get(st.taskId);
    per.set(st.taskId, {
      state: st.state,
      progress: st.progress,
      seq: prev?.seq ?? ++this.seq, // 같은 작업의 진행 보고는 순서를 바꾸지 않는다
      startPos: prev?.startPos ?? this.nav.get(id)?.pos ?? null,
    });
  }

  private onTrack(env: LinkEnvelope): void {
    const t = fromBinary(TrackShareSchema, env.payload);
    const p = geo(t.position);
    if (!t.targetId || !p) return;
    const prev = this.tracks.get(t.targetId);
    if (prev && prev.observedUs > t.observedTimeUs) return;
    this.tracks.set(t.targetId, { pos: p, observedUs: t.observedTimeUs });
  }

  /**
   * 단독 항로의 다음 항로점 추정: GCS는 이 항로의 진행 보고를 받지 못한다.
   * 보고 위치가 다음 점의 도달 반경(1 Hz 보고 간격을 감안해 최소 150 m) 안이면 그 점을 지난 것으로 본다. 마지막 점을 지나면 지운다.
   */
  private advanceQuiet(id: string, p: GeoPoint): void {
    const q = this.quiet.get(id);
    if (!q) return;
    while (q.reached < q.waypoints.length) {
      const w = q.waypoints[q.reached];
      if (distanceBearing(p, w.pos).distM > Math.max(w.acceptM, 150)) break;
      q.reached++;
    }
    if (q.reached >= q.waypoints.length) this.quiet.delete(id);
  }

  private resetRun(dropTasks: boolean): void {
    this.status.clear();
    this.nav.clear();
    this.home.clear();
    this.tracks.clear();
    this.quiet.clear();
    if (dropTasks) this.tasks.clear();
    this.version++;
  }

  // ---- 출력 ----

  /**
   * 표시 위치: 마지막 NavigationReport의 보고 시각부터 지금 모의 시각(simNowUs)까지 속도로 외삽한다.
   * 모의 시각을 모르면 받은 뒤 흐른 벽시계로 대신한다. MAX_EXTRAPOLATE_S를 넘으면 더 나가지 않는다. 보고를 받은 적 없으면 null
   */
  positionAt(id: string, wallMs = Date.now()): GeoPoint | null {
    const f = this.nav.get(id);
    if (!f) return null;
    const now = this.simNowUs(wallMs);
    const raw = now !== null ? Number(now - f.sentUs) / 1e6 : (wallMs - f.wallMs) / 1000;
    const dt = Math.min(MAX_EXTRAPOLATE_S, Math.max(0, raw));
    const p = fromLocal(f.pos, f.vel.n * dt, f.vel.e * dt);
    return { ...p, altM: f.pos.altM - f.vel.d * dt };
  }

  /** 행동을 아는 기체 ID */
  entityIds(): string[] {
    return [...new Set([...this.status.keys(), ...this.quiet.keys()])].sort();
  }

  /** 기체 하나의 현재 행동. 모르면 null */
  shapeOf(id: string): ActivityShape | null {
    const per = this.status.get(id);
    let cur: [string, StatusView] | null = null;
    for (const e of per ?? []) if (!cur || e[1].seq > cur[1].seq) cur = e;
    const q = this.quiet.get(id);
    if (q && (!cur || q.seq > cur[1].seq)) return this.quietShape(id, q);
    if (!cur) return null;
    const t = this.tasks.get(cur[0]);
    return t ? this.taskShape(id, t, cur[1]) : null;
  }

  shapes(filter?: ReadonlySet<string>): ActivityShape[] {
    const out: ActivityShape[] = [];
    for (const id of this.entityIds()) {
      if (filter && !filter.has(id)) continue;
      const s = this.shapeOf(id);
      if (s) out.push(s);
    }
    return out;
  }

  /** 고도 0은 "현재 고도 유지"(DEC-038) */
  private alt(id: string, p: GeoPoint): GeoPoint {
    return p.altM > 0 ? p : { ...p, altM: this.nav.get(id)?.pos.altM ?? 0 };
  }

  private holdRadius(id: string, r: number | undefined): number {
    return r !== undefined && r > 0 ? r : (this.holdRadiusOf(id) ?? MA_DEFAULT_HOLD_RADIUS_M);
  }

  private taskShape(id: string, t: TaskCommand, st: StatusView): ActivityShape | null {
    const base = { entityId: id, taskId: t.taskId, circles: [], paths: [], estimated: false } as const;
    const mk = (kind: ActivityKind, lead: GeoPoint | null, marks: ActivityMark[], extra: Partial<ActivityShape> = {}): ActivityShape => ({
      ...base,
      circles: [],
      paths: [],
      kind,
      label: KIND_LABEL[kind],
      lead,
      marks,
      ...extra,
    });
    const task = t.task;
    switch (task.case) {
      case "moveTo": {
        const d = geo(task.value.destination);
        if (!d) return null;
        const p = this.alt(id, d);
        return mk("moveTo", p, [{ pos: p, glyph: "o" }]);
      }
      case "returnToBase": {
        const h = this.home.get(id);
        return h ? mk("returnToBase", h, [{ pos: h, glyph: "o" }]) : null;
      }
      case "hold": {
        const h = task.value;
        const c0 = geo(h.center) ?? st.startPos;
        if (!c0) return null;
        const c = this.alt(id, c0);
        const r = this.holdRadius(id, h.radiusM);
        const race = h.racetrack && h.racetrack.legLengthM > 0 ? h.racetrack : undefined;
        if (race) {
          const g = racetrackGeometry(c, r, { legLengthM: race.legLengthM, axisHeadingDeg: race.axisHeadingDeg }, h.direction);
          return mk("hold", c, [{ pos: c, glyph: "o" }], { paths: [g.outline.map((p) => ({ ...p, altM: c.altM }))] });
        }
        return mk("hold", c, [{ pos: c, glyph: "o" }], { circles: [{ center: c, radiusM: r }] });
      }
      case "strike":
      case "track": {
        const aim = task.case === "strike" ? geo(task.value.aimPoint) : null;
        const p = aim ?? this.tracks.get(task.value.targetId)?.pos ?? null;
        if (!p) return null;
        return task.case === "strike" ? mk("strike", p, [{ pos: p, glyph: "x" }]) : mk("track", p, [{ pos: p, glyph: "o" }]);
      }
      case "searchArea":
      case "jam": {
        const a = areaOutline(task.value.area, this.nav.get(id)?.pos.altM ?? 0);
        if (!a) return null;
        return mk(task.case === "jam" ? "jam" : "search", a.center, [{ pos: a.center, glyph: "o" }], { paths: [a.outline] });
      }
      case "route": {
        const wps = task.value.waypoints.flatMap((w) => {
          const p = geo(w.position);
          return p ? [{ pos: this.alt(id, p), w }] : [];
        });
        const n = wps.length;
        if (n === 0) return null;
        // 다음 항로점 추정: 내장 MA의 progress = 이번 바퀴에서 마친 항로점 / 전체 (common.py TaskPilot.progress).
        // 다른 MA는 progress 뜻이 다를 수 있어 추정으로 표시한다
        let k = Math.floor(st.progress * n + 1e-6);
        if (k >= n) k = task.value.loop ? 0 : n - 1;
        const order = task.value.loop ? [...wps.slice(k), ...wps.slice(0, k)] : wps.slice(k);
        const circles: { center: GeoPoint; radiusM: number }[] = [];
        for (const { pos, w } of order) {
          if (w.action.case === "loiter") circles.push({ center: pos, radiusM: this.holdRadius(id, w.action.value.radiusM) });
          else if (w.action.case === "recon") circles.push({ center: pos, radiusM: w.action.value.radiusM });
        }
        const line = order.map((o) => o.pos);
        if (task.value.loop && n >= 2) line.push(line[0]);
        return mk("route", order[0].pos, order.map((o) => ({ pos: o.pos, glyph: "o" as const })), {
          label: `항로 ${k + 1}/${n}`,
          circles,
          paths: line.length >= 2 ? [line] : [],
          estimated: true,
        });
      }
      default:
        return null;
    }
  }

  private quietShape(id: string, q: QuietRoute): ActivityShape {
    const rest = q.waypoints.slice(q.reached).map((w) => this.alt(id, w.pos));
    return {
      entityId: id,
      taskId: q.routeId,
      kind: "route",
      label: `항로 ${q.reached + 1}/${q.waypoints.length}`,
      lead: rest[0],
      marks: rest.map((pos) => ({ pos, glyph: "o" })),
      circles: [],
      paths: rest.length >= 2 ? [rest] : [],
      estimated: true,
    };
  }
}
