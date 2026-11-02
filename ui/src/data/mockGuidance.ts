// IMP-UI-041: 목 소스 임무 비행. TaskCommand를 구간(직진·선회)으로 바꾸고 선회율 제한 유도로 따라간다 (REQ-UI-003, REQ-UI-004, DEC-033)
// 지도 임무를 화면에서 확인하려는 흉내다. 실제 동역학·임무 판단은 Sim Core와 Agent가 맡는다.
import type { TaskCommand } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";

const G = 9.80665;
const MAX_BANK = (30 * Math.PI) / 180;
const CLIMB_MPS = 6;
const ACCEL_MPS2 = 2;
const MIN_SPEED = 15;
export const GUIDE_DEFAULT_RADIUS_M = 600;
const ARRIVE_M = 200;
const STRIKE_ORBIT_M = 400;

export interface Ned2 {
  n: number;
  e: number;
}

export interface GuideState extends Ned2 {
  alt: number;
  /** 진행 방향 rad, 북쪽 기준 시계방향 */
  heading: number;
  speed: number;
  vd: number;
  roll: number;
}

export type Leg =
  | { kind: "goto"; to: Ned2 | (() => Ned2); alt: number; speed?: number; acceptM: number }
  /** durationS가 null이면 다음 명령까지 */
  | { kind: "orbit"; center: Ned2 | (() => Ned2); radiusM: number; dir: 1 | -1; alt: number; durationS: number | null; speed?: number };

export interface Plan {
  taskId: string;
  legs: Leg[];
  loop: boolean;
  /** 이 구간을 마치면 COMPLETED를 보고한다 (이후 구간은 끝난 뒤의 대기 선회) */
  completeAfter: number;
}

export interface GuideEvent {
  taskId: string;
  state: CommandState;
  progress: number;
  reason: string;
}

const wrapPi = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));
const dirOf = (d: TurnDirection): 1 | -1 => (d === TurnDirection.CCW ? -1 : 1);
const pos = (to: Ned2 | (() => Ned2)) => (typeof to === "function" ? to() : to);

/** 기체 하나를 구간 목록대로 움직인다 */
export class Guided {
  private idx = 0;
  /** 선회 구간에서 원에 붙은 뒤 지난 시간 */
  private onCircleS = 0;
  private reported = false;

  constructor(
    public state: GuideState,
    public plan: Plan,
    readonly cruise: number,
  ) {}

  get legIndex(): number {
    return this.idx;
  }

  private progress(): number {
    return Math.min(1, this.idx / (this.plan.completeAfter + 1));
  }

  /** dt초 진행. 구간이 바뀌거나 끝나면 보고할 사건을 돌려준다 */
  step(dt: number): GuideEvent[] {
    const ev: GuideEvent[] = [];
    const leg = this.plan.legs[this.idx];
    if (!leg) return ev;
    const s = this.state;
    let course: number;
    let speed = leg.speed ?? this.cruise;
    let done = false;
    if (leg.kind === "goto") {
      const to = pos(leg.to);
      const dn = to.n - s.n, de = to.e - s.e;
      course = Math.atan2(de, dn);
      done = Math.hypot(dn, de) < leg.acceptM;
    } else {
      const c = pos(leg.center);
      const dn = s.n - c.n, de = s.e - c.e;
      const d = Math.hypot(dn, de);
      const b = Math.atan2(de, dn);
      const k = 1 / Math.max(150, 0.3 * leg.radiusM);
      course = b + leg.dir * (Math.PI / 2 + Math.atan(k * (d - leg.radiusM)));
      if (Math.abs(d - leg.radiusM) < Math.max(150, 0.25 * leg.radiusM)) this.onCircleS += dt;
      done = leg.durationS !== null && this.onCircleS >= leg.durationS;
    }
    // 속력·선회율·상승률 제한
    speed = Math.max(MIN_SPEED, speed);
    s.speed += Math.max(-ACCEL_MPS2 * dt, Math.min(ACCEL_MPS2 * dt, speed - s.speed));
    const maxRate = (G * Math.tan(MAX_BANK)) / Math.max(MIN_SPEED, s.speed);
    const turn = Math.max(-maxRate * dt, Math.min(maxRate * dt, wrapPi(course - s.heading)));
    s.heading = wrapPi(s.heading + turn);
    s.roll = Math.atan((s.speed * (turn / dt)) / G);
    const climb = Math.max(-CLIMB_MPS, Math.min(CLIMB_MPS, (leg.alt - s.alt) / Math.max(dt, 1)));
    s.alt += climb * dt;
    s.vd = -climb;
    s.n += s.speed * Math.cos(s.heading) * dt;
    s.e += s.speed * Math.sin(s.heading) * dt;

    if (done) {
      this.idx++;
      this.onCircleS = 0;
      if (this.idx >= this.plan.legs.length && this.plan.loop) this.idx = 0;
      if (!this.reported && !this.plan.loop && this.idx > this.plan.completeAfter) {
        this.reported = true;
        ev.push({ taskId: this.plan.taskId, state: CommandState.COMPLETED, progress: 1, reason: "목 소스: 임무 완료" });
      } else if (this.idx < this.plan.legs.length && !this.reported) {
        ev.push({ taskId: this.plan.taskId, state: CommandState.EXECUTING, progress: this.plan.loop ? 0 : this.progress(), reason: `구간 ${this.idx + 1}/${this.plan.legs.length}` });
      }
    }
    return ev;
  }
}

/** 시나리오가 넘기는 좌표 변환과 표적 위치 */
export interface PlanContext {
  toNed(g: { latDeg: number; lonDeg: number }): Ned2;
  /** 엔티티 현재 위치. 없으면 null */
  entityNed(id: string): Ned2 | null;
  home: Ned2;
}

/**
 * TaskCommand → 구간 목록. k는 같은 명령을 받은 기체 중 순번으로, 고도·반경·도착점을 조금씩 엇갈린다.
 * 다룰 수 없는 임무면 null.
 */
export function planFor(cmd: TaskCommand, k: number, cur: GuideState, ctx: PlanContext): Plan | null {
  const t = cmd.task;
  const dAlt = 30 * k;
  const dR = 120 * k;
  const spread = (p: Ned2): Ned2 => (k === 0 ? p : { n: p.n + 150 * k * Math.cos(2.4 * k), e: p.e + 150 * k * Math.sin(2.4 * k) });
  const here: Ned2 = { n: cur.n, e: cur.e };
  const hold = (c: Ned2 | (() => Ned2), alt: number, r = GUIDE_DEFAULT_RADIUS_M, dir: 1 | -1 = 1, durationS: number | null = null): Leg => ({
    kind: "orbit", center: c, radiusM: r + dR, dir, alt: alt + dAlt, durationS,
  });
  const goto = (to: Ned2 | (() => Ned2), alt: number, speed?: number, acceptM = ARRIVE_M): Leg => ({
    kind: "goto", to, alt: alt + dAlt, speed, acceptM,
  });
  const lap = (r: number, speed?: number) => (2 * Math.PI * (r + dR)) / (speed ?? Math.max(cur.speed, MIN_SPEED));
  const plan = (legs: Leg[], completeAfter = legs.length - 1, loop = false): Plan => ({ taskId: cmd.taskId, legs, loop, completeAfter });

  switch (t.case) {
    case "moveTo": {
      const g = t.value.destination;
      if (!g) return null;
      const to = spread(ctx.toNed(g));
      return plan([goto(to, g.altM, t.value.speedMps), hold(to, g.altM)], 0);
    }
    case "hold": {
      const v = t.value;
      const c = v.center ? ctx.toNed(v.center) : here;
      const alt = v.center ? v.center.altM : cur.alt - dAlt;
      const r = v.radiusM ?? GUIDE_DEFAULT_RADIUS_M;
      if (v.durationS) return plan([hold(c, alt, r, dirOf(v.direction), v.durationS), hold(c, alt, r, dirOf(v.direction))], 0);
      return plan([hold(c, alt, r, dirOf(v.direction))], 0);
    }
    case "strike": {
      const v = t.value;
      const alt = cur.alt - dAlt;
      let aim: Ned2 | (() => Ned2);
      if (v.targetId) {
        const id = v.targetId;
        const last = ctx.entityNed(id);
        if (!last) return null;
        let memo = last;
        aim = () => (memo = ctx.entityNed(id) ?? memo);
      } else if (v.aimPoint) {
        aim = ctx.toNed(v.aimPoint);
      } else return null;
      return plan([goto(aim, alt, undefined, 250), hold(aim, alt, STRIKE_ORBIT_M)], 0);
    }
    case "searchArea": {
      const sh = t.value.area?.shape;
      if (sh?.case !== "circle" || !sh.value.center) return null;
      const c = ctx.toNed(sh.value.center);
      const r = sh.value.radiusM;
      const alt = sh.value.center.altM;
      return plan([hold(c, alt, r, 1, lap(r)), hold(c, alt, r)], 0);
    }
    case "route": {
      const legs: Leg[] = [];
      for (const w of t.value.waypoints) {
        if (!w.position) continue;
        const p = ctx.toNed(w.position);
        const alt = w.position.altM;
        legs.push(goto(p, alt, w.speedMps, w.acceptanceRadiusM ?? ARRIVE_M));
        const a = w.action;
        if (a.case === "loiter") legs.push(hold(p, alt, a.value.radiusM ?? GUIDE_DEFAULT_RADIUS_M, dirOf(a.value.direction), a.value.durationS));
        if (a.case === "recon") legs.push(hold(p, alt, a.value.radiusM, 1, a.value.durationS ?? lap(a.value.radiusM, w.speedMps)));
      }
      if (!legs.length) return null;
      if (t.value.loop) return plan(legs, legs.length - 1, true);
      const last = legs[legs.length - 1];
      const endAt = last.kind === "orbit" ? last.center : last.to;
      return plan([...legs, hold(endAt, last.alt - dAlt)], legs.length - 1);
    }
    case "returnToBase":
      return plan([goto(ctx.home, cur.alt - dAlt), hold(ctx.home, cur.alt - dAlt)], 0);
    default:
      return null;
  }
}
