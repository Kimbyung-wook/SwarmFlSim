// IMP-UI-038: 임무 지도 표시 도형 (REQ-UI-003, REQ-UI-004, DEC-033)
// 편집 중 항로, 임무 메뉴 지점, 보낸 임무(항로·선회·정찰·타격)를 점·선·원으로 바꾼다. Cesium에 의존하지 않는다.
import type { GeoPoint, MissionSpec } from "./commands";
import type { RouteDraft } from "./routeDraft";

export type OverlayStyle = "draft" | "pending" | "sent";

export interface OverlayPoint {
  pos: GeoPoint;
  label: string;
  style: OverlayStyle;
  /** 편집 중 항로점이면 그 번호(0부터). 끌어서 옮길 수 있다 */
  handle?: number;
}

export interface OverlayLine {
  positions: GeoPoint[];
  style: OverlayStyle;
}

export interface OverlayCircle {
  center: GeoPoint;
  radiusM: number;
  style: OverlayStyle;
}

export interface Overlay {
  points: OverlayPoint[];
  lines: OverlayLine[];
  circles: OverlayCircle[];
}

export const DEFAULT_LOITER_RADIUS_M = 600;

export function emptyOverlay(): Overlay {
  return { points: [], lines: [], circles: [] };
}

function merge(into: Overlay, o: Overlay): Overlay {
  into.points.push(...o.points);
  into.lines.push(...o.lines);
  into.circles.push(...o.circles);
  return into;
}

/** 편집 중 항로: 번호 붙은 손잡이, 항로선(loop면 닫음), 행위 원 */
export function draftOverlay(d: RouteDraft): Overlay {
  const o = emptyOverlay();
  const ps = d.waypoints.map((w) => w.position);
  d.waypoints.forEach((w, i) => {
    o.points.push({ pos: w.position, label: String(i + 1), style: "draft", handle: i });
    if (w.action.kind === "loiter") o.circles.push({ center: w.position, radiusM: w.action.radiusM ?? DEFAULT_LOITER_RADIUS_M, style: "draft" });
    if (w.action.kind === "recon") o.circles.push({ center: w.position, radiusM: w.action.radiusM, style: "draft" });
  });
  if (ps.length >= 2) o.lines.push({ positions: d.loop ? [...ps, ps[0]] : ps, style: "draft" });
  return o;
}

/**
 * 임무 하나의 도형. label은 기체별 진행 상태 등 붙일 글.
 * from이 있으면 그 위치(대상 기체 평균)에서 첫 지점까지 선을 긋는다.
 */
export function missionOverlay(m: MissionSpec, style: OverlayStyle, label = "", from?: GeoPoint): Overlay {
  const o = emptyOverlay();
  const lead = (p: GeoPoint) => {
    if (from) o.lines.push({ positions: [from, p], style });
  };
  switch (m.kind) {
    case "moveTo":
      lead(m.destination);
      o.points.push({ pos: m.destination, label: label || "이동", style });
      break;
    case "hold":
      if (m.center) {
        lead(m.center);
        o.circles.push({ center: m.center, radiusM: m.radiusM ?? DEFAULT_LOITER_RADIUS_M, style });
        o.points.push({ pos: m.center, label: label || "선회", style });
      }
      break;
    case "search":
      lead(m.center);
      o.circles.push({ center: m.center, radiusM: m.radiusM, style });
      o.points.push({ pos: m.center, label: label || "정찰", style });
      break;
    case "strike":
      if (m.aimPoint) {
        lead(m.aimPoint);
        o.points.push({ pos: m.aimPoint, label: label || `타격 ${m.weapon}`, style });
      }
      break;
    case "route": {
      const ps = m.waypoints.map((w) => w.position);
      if (ps.length) lead(ps[0]);
      if (ps.length >= 2) o.lines.push({ positions: m.loop ? [...ps, ps[0]] : ps, style });
      m.waypoints.forEach((w, i) => {
        o.points.push({ pos: w.position, label: i === 0 && label ? `1 ${label}` : String(i + 1), style });
        if (w.action.kind === "loiter") o.circles.push({ center: w.position, radiusM: w.action.radiusM ?? DEFAULT_LOITER_RADIUS_M, style });
        if (w.action.kind === "recon") o.circles.push({ center: w.position, radiusM: w.action.radiusM, style });
      });
      break;
    }
    case "returnToBase":
      break;
  }
  return o;
}

export function combine(...os: Overlay[]): Overlay {
  return os.reduce(merge, emptyOverlay());
}
