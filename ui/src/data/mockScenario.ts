// IMP-UI-009: 목 시나리오. 시각 t에서 TruthFrame을 해석적으로 만든다 (결정론적, REQ-UI-001)
// IMP-UI-041: TaskCommand를 받은 기체는 그때부터 유도 비행(mockGuidance)으로 바뀐다. 시각을 되돌리면 해석 궤도로 돌아간다.
// 청군 UAV 4개 편대×6대가 선회하고, 적 지상표적·공중표적·재밍기지와 GCS가 있다. 좌표는 충청 내륙.
import { create } from "@bufbuild/protobuf";
import type { EntityState } from "../gen/swarm/v1/entity_pb";
import { EntityKind, EntityStateSchema, Side } from "../gen/swarm/v1/entity_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import type { TaskCommand } from "../gen/swarm/v1/c2_pb";
import { HoldTaskSchema } from "../gen/swarm/v1/c2_pb";
import { DEG, eulerToQuat, flightPathAngle } from "../model/attitude";
import type { GuideEvent, Ned2, PlanContext } from "./mockGuidance";
import { Guided, planFor } from "./mockGuidance";

const R_EARTH = 6378137;
const G = 9.80665;

export const MOCK_ORIGIN = { lat: 36.6, lon: 127.5 };
export const MOCK_SOURCE_ID = "mock-0";

interface Ned {
  n: number;
  e: number;
  d: number;
}

interface Sample {
  pos: Ned;      // 원점 기준 m (d는 −고도)
  vel: Ned;      // m/s
  roll: number;  // rad
}

interface Actor {
  id: string;
  kind: EntityKind;
  side: Side;
  at(t: number): Sample;
}

export function geodeticToNed(g: { latDeg: number; lonDeg: number }): Ned2 {
  const lat0 = MOCK_ORIGIN.lat * DEG;
  return {
    n: (g.latDeg - MOCK_ORIGIN.lat) * DEG * R_EARTH,
    e: (g.lonDeg - MOCK_ORIGIN.lon) * DEG * R_EARTH * Math.cos(lat0),
  };
}

const GUIDE_STEP_S = 0.1;

function nedToGeodetic(p: Ned) {
  const lat0 = MOCK_ORIGIN.lat * DEG;
  return {
    latDeg: MOCK_ORIGIN.lat + p.n / R_EARTH / DEG,
    lonDeg: MOCK_ORIGIN.lon + p.e / (R_EARTH * Math.cos(lat0)) / DEG,
    altM: -p.d,
  };
}

const stationary = (n: number, e: number, alt: number) => (): Sample => ({
  pos: { n, e, d: -alt },
  vel: { n: 0, e: 0, d: 0 },
  roll: 0,
});

/**
 * 원 궤도. bearing은 중심에서 본 방위(북쪽 기준 시계방향). dir +1 시계방향, −1 반시계방향.
 * 고도는 altAmp 진폭, altPeriod 주기로 오르내린다.
 */
function orbit(
  cn: number, ce: number, r: number, speed: number, phase: number, dir: 1 | -1,
  alt: number, altAmp = 0, altPeriod = 120,
) {
  const w = (dir * speed) / r;
  return (t: number): Sample => {
    const b = phase + w * t;
    const wa = (2 * Math.PI) / altPeriod;
    return {
      pos: { n: cn + r * Math.cos(b), e: ce + r * Math.sin(b), d: -(alt + altAmp * Math.sin(wa * t)) },
      vel: { n: -r * w * Math.sin(b), e: r * w * Math.cos(b), d: -altAmp * wa * Math.cos(wa * t) },
      // 협조선회 뱅크각 tanφ = v·ω/g, 오른쪽 선회 +
      roll: Math.atan((speed * w) / G),
    };
  };
}

/** 두 점 사이 왕복 직선 비행. 끝점에서 바로 돌아선다 */
function pingPong(a: Ned, b: Ned, speed: number) {
  const dn = b.n - a.n, de = b.e - a.e, dd = b.d - a.d;
  const len = Math.hypot(dn, de, dd);
  const legT = len / speed;
  return (t: number): Sample => {
    const k = t % (2 * legT);
    const fwd = k < legT;
    const s = (fwd ? k : 2 * legT - k) / legT;
    const sgn = fwd ? 1 : -1;
    return {
      pos: { n: a.n + dn * s, e: a.e + de * s, d: a.d + dd * s },
      vel: { n: (sgn * dn) / legT, e: (sgn * de) / legT, d: (sgn * dd) / legT },
      roll: 0,
    };
  };
}

const pad = (n: number, w: number) => String(n).padStart(w, "0");

export interface MockScenarioOptions {
  flights: number;      // 편대 수
  perFlight: number;    // 편대당 기체 수
}

export interface GuideReport extends GuideEvent {
  entityId: string;
}

export class MockScenario {
  readonly actors: Actor[] = [];
  /** 명령을 받아 유도 비행 중인 기체 */
  private readonly guided = new Map<string, Guided>();
  private guidedT = 0;
  private readonly pending: GuideReport[] = [];

  constructor(opts: MockScenarioOptions = { flights: 4, perFlight: 6 }) {
    this.actors.push({ id: "gcs-01", kind: EntityKind.GCS, side: Side.BLUE, at: stationary(-6000, -8000, 80) });

    // 편대: 리더가 원 궤도를 돌고, 윙맨은 궤도 뒤쪽으로 각도를, 좌우로 반경을 엇갈려 V자를 만든다
    const centers: [number, number][] = [[6000, -6000], [6000, 6000], [-6000, 6000], [-2000, -2000]];
    let seq = 1;
    for (let f = 0; f < opts.flights; f++) {
      const [cn, ce] = centers[f % centers.length];
      const r = 3500 + 500 * f;
      const speed = 28 + 2 * f;
      const dir: 1 | -1 = f % 2 === 0 ? 1 : -1;
      const alt = 1200 + 300 * f;
      for (let j = 0; j < opts.perFlight; j++) {
        const rank = Math.ceil(j / 2);
        const side = j % 2 === 1 ? 1 : -1;
        const rj = r + side * rank * 250;
        const phase = f * 1.3 - dir * rank * (300 / r);
        this.actors.push({
          id: `uav-${pad(seq++, 3)}`,
          kind: EntityKind.UAV,
          side: Side.BLUE,
          at: orbit(cn, ce, rj, speed * (rj / r), phase, dir, alt, f === 1 ? 150 : 0),
        });
      }
    }

    const targets: [number, number][] = [[14000, 2000], [15500, 4500], [13000, 7000], [16500, -1500]];
    targets.forEach(([n, e], i) =>
      this.actors.push({ id: `tgt-${pad(i + 1, 3)}`, kind: EntityKind.GROUND_TARGET, side: Side.RED, at: stationary(n, e, 120) }),
    );
    this.actors.push({ id: "site-01", kind: EntityKind.JAMMER_SITE, side: Side.RED, at: stationary(17000, 3000, 150) });
    this.actors.push({
      id: "tgt-101", kind: EntityKind.AIR_TARGET, side: Side.RED,
      at: pingPong({ n: 20000, e: -10000, d: -2500 }, { n: 20000, e: 12000, d: -2500 }, 60),
    });
    this.actors.push({
      id: "tgt-102", kind: EntityKind.AIR_TARGET, side: Side.RED,
      at: pingPong({ n: 24000, e: 10000, d: -3000 }, { n: 10000, e: 14000, d: -2000 }, 70),
    });
  }

  /** 시각 t의 위치 (유도 중이면 유도 상태) */
  private sample(a: Actor, t: number): Sample {
    const g = this.guided.get(a.id);
    if (!g) return a.at(t);
    const s = g.state;
    return {
      pos: { n: s.n, e: s.e, d: -s.alt },
      vel: { n: s.speed * Math.cos(s.heading), e: s.speed * Math.sin(s.heading), d: s.vd },
      roll: s.roll,
    };
  }

  private context(t: number): PlanContext {
    const gcs = this.actors.find((a) => a.kind === EntityKind.GCS);
    const home = gcs ? gcs.at(t).pos : { n: 0, e: 0 };
    return {
      toNed: geodeticToNed,
      entityNed: (id) => {
        const a = this.actors.find((x) => x.id === id);
        if (!a) return null;
        const p = this.sample(a, this.guidedT).pos;
        return { n: p.n, e: p.e };
      },
      home: { n: home.n, e: home.e },
    };
  }

  /**
   * 시각 t에 받은 TaskCommand. 대상 UAV를 유도 비행으로 바꾼다.
   * 취소면 그 임무를 하던 기체를 그 자리 선회로 바꾼다. 다룰 수 없는 임무를 받은 기체 ID를 돌려준다.
   */
  command(cmd: TaskCommand, t: number): string[] {
    this.advanceTo(t);
    const rejected: string[] = [];
    const ctx = this.context(t);
    cmd.assignees.forEach((id, k) => {
      const a = this.actors.find((x) => x.id === id && x.kind === EntityKind.UAV);
      if (!a) return void rejected.push(id);
      const prev = this.guided.get(id);
      const s = this.sample(a, t);
      const state = prev?.state ?? {
        n: s.pos.n, e: s.pos.e, alt: -s.pos.d,
        heading: Math.atan2(s.vel.e, s.vel.n), speed: Math.hypot(s.vel.n, s.vel.e), vd: s.vel.d, roll: s.roll,
      };
      const cruise = prev?.cruise ?? Math.max(20, state.speed);
      if (cmd.cancel) {
        if (prev && prev.plan.taskId === cmd.taskId) {
          const hold = planFor({ ...cmd, task: { case: "hold", value: create(HoldTaskSchema, {}) } }, 0, state, ctx);
          if (hold) this.guided.set(id, new Guided(state, hold, cruise));
        }
        return;
      }
      const plan = planFor(cmd, k, state, ctx);
      if (!plan) return void rejected.push(id);
      this.guided.set(id, new Guided(state, plan, cruise));
    });
    return rejected;
  }

  /** 유도 기체를 t까지 진행한다. t가 과거면 유도를 모두 풀어 해석 궤도로 돌아간다 */
  private advanceTo(t: number): void {
    if (t < this.guidedT) {
      this.guided.clear();
      this.pending.length = 0;
    }
    if (this.guided.size === 0) {
      this.guidedT = t;
      return;
    }
    while (this.guidedT < t - 1e-9) {
      const dt = Math.min(GUIDE_STEP_S, t - this.guidedT);
      this.guidedT += dt;
      for (const [id, g] of this.guided) for (const ev of g.step(dt)) this.pending.push({ ...ev, entityId: id });
    }
  }

  /** 지난 호출 뒤 생긴 진행 보고 */
  takeReports(): GuideReport[] {
    return this.pending.splice(0);
  }

  isGuided(id: string): boolean {
    return this.guided.has(id);
  }

  entityAt(a: Actor, t: number): EntityState {
    const s = this.sample(a, t);
    const yaw = Math.atan2(s.vel.e, s.vel.n);
    const moving = Math.hypot(s.vel.n, s.vel.e) > 0.01;
    return create(EntityStateSchema, {
      id: a.id,
      kind: a.kind,
      side: a.side,
      alive: true,
      energyFrac: a.kind === EntityKind.UAV ? Math.max(0, 1 - t / 7200) : 1,
      kinematics: {
        position: nedToGeodetic(s.pos),
        velocityNedMps: { x: s.vel.n, y: s.vel.e, z: s.vel.d },
        attitude: eulerToQuat({
          yaw: moving ? yaw : 0,
          pitch: flightPathAngle(s.vel.n, s.vel.e, s.vel.d),
          roll: s.roll,
        }),
        angularRateFrdRps: { x: 0, y: 0, z: 0 },
      },
    });
  }

  frameAt(frame: bigint, frameHz: number): TruthFrame {
    const simTimeUs = (frame * 1_000_000n) / BigInt(frameHz);
    const t = Number(simTimeUs) / 1e6;
    this.advanceTo(t);
    return create(TruthFrameSchema, {
      header: { simTimeUs, frame, source: MOCK_SOURCE_ID, seq: Number(frame & 0xffffffffn) },
      entities: this.actors.map((a) => this.entityAt(a, t)),
    });
  }
}
