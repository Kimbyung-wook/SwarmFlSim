// IMP-UI-004: TruthFrame → 전시용 엔티티 뷰 (REQ-UI-001, PRP-SIM-003)
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import type { EntityState } from "../gen/swarm/v1/entity_pb";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import type { Euler, Quat } from "./attitude";
import { headingFromVelocity, quatToEuler, wrap2Pi } from "./attitude";

export interface EntityView {
  id: string;
  kind: EntityKind;
  side: Side;
  alive: boolean;
  lat: number;     // deg
  lon: number;     // deg
  alt: number;     // m MSL
  vn: number;      // m/s
  ve: number;
  vd: number;
  speed: number;   // 지면 속도 m/s
  heading: number; // rad, 북쪽 기준 시계방향. 정지체는 자세 yaw
  attitude: Quat;  // NED → FRD
  euler: Euler;
  energy: number;
}

export interface FrameView {
  frame: bigint;
  simTimeUs: bigint;
  entities: EntityView[];
}

const IDENTITY: Quat = { w: 1, x: 0, y: 0, z: 0 };

export function toEntityView(s: EntityState): EntityView {
  const k = s.kinematics;
  const p = k?.position;
  const v = k?.velocityNedMps;
  const q = k?.attitude;
  const attitude: Quat = q && (q.w || q.x || q.y || q.z) ? { w: q.w, x: q.x, y: q.y, z: q.z } : IDENTITY;
  const euler = quatToEuler(attitude);
  const vn = v?.x ?? 0, ve = v?.y ?? 0, vd = v?.z ?? 0;
  return {
    id: s.id,
    kind: s.kind,
    side: s.side,
    alive: s.alive,
    lat: p?.latDeg ?? 0,
    lon: p?.lonDeg ?? 0,
    alt: p?.altM ?? 0,
    vn,
    ve,
    vd,
    speed: Math.hypot(vn, ve),
    heading: headingFromVelocity(vn, ve) ?? wrap2Pi(euler.yaw),
    attitude,
    euler,
    energy: s.energyFrac,
  };
}

export function toFrameView(f: TruthFrame): FrameView {
  return {
    frame: f.header?.frame ?? 0n,
    simTimeUs: f.header?.simTimeUs ?? 0n,
    entities: f.entities.map(toEntityView),
  };
}

/** 사람이 읽는 종류 이름 */
export function kindLabel(k: EntityKind): string {
  switch (k) {
    case EntityKind.UAV: return "UAV";
    case EntityKind.GCS: return "GCS";
    case EntityKind.GROUND_TARGET: return "지상표적";
    case EntityKind.AIR_TARGET: return "공중표적";
    case EntityKind.MISSILE: return "미사일";
    case EntityKind.FPV: return "FPV";
    case EntityKind.JAMMER_SITE: return "재밍기지";
    default: return "미상";
  }
}

export function sideLabel(s: Side): string {
  switch (s) {
    case Side.BLUE: return "청군";
    case Side.RED: return "적군";
    case Side.NEUTRAL: return "중립";
    default: return "미상";
  }
}

/** 공중을 나는 종류 (진행 방향 표시·1인칭 시점 대상) */
export function isAirborneKind(k: EntityKind): boolean {
  return k === EntityKind.UAV || k === EntityKind.AIR_TARGET || k === EntityKind.MISSILE || k === EntityKind.FPV;
}
