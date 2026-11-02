// IMP-UI-042: 레이스트랙 선회 도형 계산 (REQ-BHV-002, DEC-034)
// 클릭한 점이 두 원 중심의 중점이다. 원 중심 = 중점 ± (leg_length_m/2)·축 방향, 축은 진북 기준 시계 방향 [0,360).
// 평면 근사(국지 위경도 ↔ 북·동 m)로 계산한다. 선회 반경·직선 길이는 수십 km 안이다.
import { TurnDirection } from "../gen/swarm/v1/vi_pb";

const M_PER_DEG = 111_320;
const rad = (d: number) => (d * Math.PI) / 180;

export interface RacetrackSpec {
  legLengthM: number;
  /** 진북 기준 시계 방향 deg */
  axisHeadingDeg: number;
}

export interface LatLon {
  latDeg: number;
  lonDeg: number;
}

/** [0,360)으로 정규화 */
export function normalizeHeadingDeg(d: number): number {
  return ((d % 360) + 360) % 360;
}

/** 위경도 → 중심 기준 북·동 m */
export function toLocal(center: LatLon, p: LatLon): { n: number; e: number } {
  return {
    n: (p.latDeg - center.latDeg) * M_PER_DEG,
    e: (p.lonDeg - center.lonDeg) * M_PER_DEG * Math.cos(rad(center.latDeg)),
  };
}

export function fromLocal(center: LatLon, n: number, e: number): LatLon {
  return {
    latDeg: center.latDeg + n / M_PER_DEG,
    lonDeg: center.lonDeg + e / (M_PER_DEG * Math.cos(rad(center.latDeg))),
  };
}

/** 두 점 사이 거리 m과 진북 기준 방위 deg [0,360) */
export function distanceBearing(a: LatLon, b: LatLon): { distM: number; bearingDeg: number } {
  const l = toLocal(a, b);
  return { distM: Math.hypot(l.n, l.e), bearingDeg: normalizeHeadingDeg((Math.atan2(l.e, l.n) * 180) / Math.PI) };
}

export interface RacetrackGeometry {
  /** 축 방향 끝쪽 원 중심 (+축) */
  c2: LatLon;
  /** 반대쪽 원 중심 (−축) */
  c1: LatLon;
  /** 직선 구간 접점 4개: 원 c1 → 직선 A → 원 c2 → 직선 B 순서로 [A시작, A끝, B시작, B끝] */
  tangents: [LatLon, LatLon, LatLon, LatLon];
  /** 폐곡선 (닫힘: 처음과 끝이 같다). 진행 방향 순 */
  outline: LatLon[];
}

const ARC_STEPS = 16;

/**
 * 레이스트랙 도형. dir은 선회 방향(UNSPECIFIED는 시계로 그린다).
 */
export function racetrackGeometry(center: LatLon, radiusM: number, spec: RacetrackSpec, dir: TurnDirection): RacetrackGeometry {
  const a = rad(normalizeHeadingDeg(spec.axisHeadingDeg));
  const un = Math.cos(a), ue = Math.sin(a); // 축 단위 벡터 (북, 동)
  const rn = -ue, re = un; // 축의 오른쪽 법선 (방위 a+90°)
  const sign = dir === TurnDirection.CCW ? -1 : 1; // +1 시계
  const half = Math.max(0, spec.legLengthM) / 2;
  const c2n = un * half, c2e = ue * half;
  const c1n = -c2n, c1e = -c2e;
  // 시계: 직선 A는 축의 왼쪽에서 +축으로, B는 오른쪽에서 −축으로 달린다. 반시계는 반대
  const ln = -rn * radiusM * sign, le = -re * radiusM * sign;
  const pt = (n: number, e: number) => fromLocal(center, n, e);
  const aStart = pt(c1n + ln, c1e + le);
  const aEnd = pt(c2n + ln, c2e + le);
  const bStart = pt(c2n - ln, c2e - le);
  const bEnd = pt(c1n - ln, c1e - le);
  const outline: LatLon[] = [aStart, aEnd];
  // 원 c2 반원: A끝(왼쪽) → B시작(오른쪽), 축 방향 바깥(+u)을 지난다
  const arc = (cn: number, ce: number, from: number, to: number) => {
    for (let i = 1; i < ARC_STEPS; i++) {
      const t = from + ((to - from) * i) / ARC_STEPS;
      outline.push(pt(cn + radiusM * Math.cos(t), ce + radiusM * Math.sin(t)));
    }
  };
  // 반원은 방위각 t로 매개화한다: 중심 + R(cos t 북, sin t 동)
  const bearing = (vn: number, ve: number) => Math.atan2(ve, vn);
  const aBear = bearing(ln, le); // c2에서 본 A끝 방위
  // 시계: 방위각이 증가하는 쪽으로 반원을 돈다. 반시계: 감소
  const span = Math.PI * sign;
  arc(c2n, c2e, aBear, aBear + span);
  outline.push(bStart, bEnd);
  const bBear = bearing(-ln, -le);
  arc(c1n, c1e, bBear, bBear + span);
  outline.push(aStart);
  return { c2: pt(c2n, c2e), c1: pt(c1n, c1e), tangents: [aStart, aEnd, bStart, bEnd], outline };
}
