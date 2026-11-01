// IMP-UI-012: 종류·진영별 아이콘 (REQ-UI-001). SVG 데이터 URL을 만든다. 외부 이미지에 의존하지 않는다.
// 색은 진영(청/적/중립/미상), 모양은 종류. 공중 종류는 북쪽(위)을 향하게 그리고 전시할 때 진행 방향으로 돌린다.
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { isAirborneKind } from "./entityView";

export const ICON_SIZE = 32;

export function sideColor(s: Side): string {
  switch (s) {
    case Side.BLUE: return "#38bdf8";
    case Side.RED: return "#f43f5e";
    case Side.NEUTRAL: return "#4ade80";
    default: return "#facc15";
  }
}

function shape(k: EntityKind): string {
  switch (k) {
    case EntityKind.UAV:
      // 고정익 실루엣
      return '<path d="M16 3 L18 13 L29 18 L29 20 L18 18 L17.5 25 L21 28 L21 29.5 L16 28 L11 29.5 L11 28 L14.5 25 L14 18 L3 20 L3 18 L14 13 Z"/>';
    case EntityKind.FPV:
      return '<path d="M16 6 L25 26 L16 21 L7 26 Z"/>';
    case EntityKind.MISSILE:
      return '<path d="M16 2 L18 8 L18 24 L21 29 L11 29 L14 24 L14 8 Z"/>';
    case EntityKind.AIR_TARGET:
      // 적 공중: 화살촉
      return '<path d="M16 3 L27 27 L16 20 L5 27 Z"/>';
    case EntityKind.GCS:
      return '<rect x="7" y="13" width="18" height="13" rx="1"/><path d="M16 13 L16 6 M11 4 Q16 9 21 4" fill="none" stroke-width="2.2"/>';
    case EntityKind.GROUND_TARGET:
      return '<path d="M16 4 L28 16 L16 28 L4 16 Z"/><circle cx="16" cy="16" r="3" fill="#000" fill-opacity="0.55" stroke="none"/>';
    case EntityKind.JAMMER_SITE:
      return '<circle cx="16" cy="16" r="11"/><path d="M8 17 L12 12 L15 20 L18 12 L21 20 L24 15" fill="none" stroke="#000" stroke-opacity="0.65" stroke-width="2"/>';
    default:
      return '<circle cx="16" cy="16" r="8"/>';
  }
}

/** 아이콘 SVG 문자열 */
export function iconSvg(kind: EntityKind, side: Side, selected = false, alive = true): string {
  const c = alive ? sideColor(side) : "#6b7280";
  const ring = selected
    ? '<circle cx="16" cy="16" r="15" fill="none" stroke="#fde047" stroke-width="2" stroke-dasharray="4 2.5"/>'
    : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${ICON_SIZE}" height="${ICON_SIZE}" viewBox="0 0 32 32">` +
    ring +
    `<g fill="${c}" stroke="${c}" stroke-linejoin="round" stroke-width="1" style="filter:drop-shadow(0 0 1px #000)">${shape(kind)}</g>` +
    "</svg>"
  );
}

const cache = new Map<string, string>();

/** 아이콘 데이터 URL (캐시) */
export function iconUrl(kind: EntityKind, side: Side, selected = false, alive = true): string {
  const key = `${kind}|${side}|${selected ? 1 : 0}|${alive ? 1 : 0}`;
  let url = cache.get(key);
  if (!url) {
    url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(iconSvg(kind, side, selected, alive))}`;
    cache.set(key, url);
  }
  return url;
}

/** 아이콘을 진행 방향으로 돌릴지 */
export function isDirectional(kind: EntityKind): boolean {
  return isAirborneKind(kind);
}
