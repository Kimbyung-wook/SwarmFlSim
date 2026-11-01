// IMP-UI-006: RTS 선택 로직 (REQ-UI-002, PRP-UI-001)
// 화면 좌표로 투영된 엔티티 목록을 받아 클릭·박스 선택 결과를 계산한다. Cesium에 의존하지 않는다.
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";

export interface ScreenEntity {
  id: string;
  x: number; // px, 캔버스 좌상단 기준
  y: number;
  kind: EntityKind;
  side: Side;
  alive: boolean;
}

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** replace: 새로 선택, add: Shift 추가, toggle: Ctrl 토글 */
export type SelectMode = "replace" | "add" | "toggle";

/** 이 거리(px) 이상 끌어야 박스 선택으로 본다. 그보다 짧으면 클릭 */
export const DRAG_THRESHOLD_PX = 5;
export const CLICK_RADIUS_PX = 14;

export function modeFromModifiers(m: { shiftKey: boolean; ctrlKey: boolean; metaKey?: boolean }): SelectMode {
  if (m.ctrlKey || m.metaKey) return "toggle";
  if (m.shiftKey) return "add";
  return "replace";
}

export function normalizeRect(r: Rect): Rect {
  return {
    x0: Math.min(r.x0, r.x1),
    y0: Math.min(r.y0, r.y1),
    x1: Math.max(r.x0, r.x1),
    y1: Math.max(r.y0, r.y1),
  };
}

export function isDrag(r: Rect): boolean {
  return Math.hypot(r.x1 - r.x0, r.y1 - r.y0) >= DRAG_THRESHOLD_PX;
}

/** 통제 가능한 아군 기체: 박스 선택에서 우선한다 */
export function isControllable(e: Pick<ScreenEntity, "kind" | "side">): boolean {
  return e.side === Side.BLUE && (e.kind === EntityKind.UAV || e.kind === EntityKind.FPV);
}

/** 클릭 지점에서 radius 안의 가장 가까운 생존 엔티티 */
export function pickAt(ents: readonly ScreenEntity[], x: number, y: number, radius = CLICK_RADIUS_PX): string | null {
  let best: string | null = null;
  let bestD = radius;
  for (const e of ents) {
    if (!e.alive) continue;
    const d = Math.hypot(e.x - x, e.y - y);
    if (d <= bestD) {
      bestD = d;
      best = e.id;
    }
  }
  return best;
}

/**
 * 박스 안의 생존 엔티티. 박스 안에 통제 가능한 아군 기체가 있으면 그것만 고른다(RTS 관례).
 * 없으면 박스 안의 모든 엔티티를 고른다.
 */
export function pickInRect(ents: readonly ScreenEntity[], rect: Rect): string[] {
  const r = normalizeRect(rect);
  const inside = ents.filter((e) => e.alive && e.x >= r.x0 && e.x <= r.x1 && e.y >= r.y0 && e.y <= r.y1);
  const own = inside.filter(isControllable);
  return (own.length > 0 ? own : inside).map((e) => e.id);
}

/** 기존 선택과 새로 고른 id를 합친다. 순서는 기존 선택 순서를 유지하고 새 항목을 뒤에 붙인다 */
export function applySelection(prev: readonly string[], hits: readonly string[], mode: SelectMode): string[] {
  switch (mode) {
    case "replace":
      return [...new Set(hits)];
    case "add": {
      const out = [...prev];
      const have = new Set(prev);
      for (const h of hits) if (!have.has(h)) { out.push(h); have.add(h); }
      return out;
    }
    case "toggle": {
      const hitSet = new Set(hits);
      const out = prev.filter((p) => !hitSet.has(p));
      const prevSet = new Set(prev);
      for (const h of hitSet) if (!prevSet.has(h)) out.push(h);
      return out;
    }
  }
}

/** 프레임에서 사라진 엔티티를 선택에서 뺀다. 바뀌지 않으면 같은 배열을 돌려준다 */
export function pruneSelection(sel: readonly string[], present: ReadonlySet<string>): readonly string[] {
  return sel.every((id) => present.has(id)) ? sel : sel.filter((id) => present.has(id));
}
