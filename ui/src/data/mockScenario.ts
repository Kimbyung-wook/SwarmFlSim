// IMP-UI-009: 목 시나리오. 시각 t에서 TruthFrame을 해석적으로 만든다 (결정론적, REQ-UI-001)
// 청군 UAV 4개 편대×6대가 선회하고, 적 지상표적·공중표적·재밍기지와 GCS가 있다. 좌표는 충청 내륙.
import { create } from "@bufbuild/protobuf";
import type { EntityState } from "../gen/swarm/v1/entity_pb";
import { EntityKind, EntityStateSchema, Side } from "../gen/swarm/v1/entity_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { DEG, eulerToQuat, flightPathAngle } from "../model/attitude";

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

export class MockScenario {
  readonly actors: Actor[] = [];

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

  entityAt(a: Actor, t: number): EntityState {
    const s = a.at(t);
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
    return create(TruthFrameSchema, {
      header: { simTimeUs, frame, source: MOCK_SOURCE_ID, seq: Number(frame & 0xffffffffn) },
      entities: this.actors.map((a) => this.entityAt(a, t)),
    });
  }
}
