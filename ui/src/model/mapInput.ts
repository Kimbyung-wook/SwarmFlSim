// IMP-UI-037: 지도 우클릭·Ctrl+우클릭·항로점 끌기 입력 판정 (REQ-UI-003, DEC-033)
// Cesium에 의존하지 않는다. MapView가 화면 좌표와 수식키를 넘기면 할 일을 정한다.
import type { Rect } from "./selection";
import { isDrag } from "./selection";

export interface MapPoint {
  latDeg: number;
  lonDeg: number;
  /** 지면 높이(MSL m). 모르면 0 */
  heightM: number;
}

export type RightClick =
  | { kind: "none" }
  /** 선택 기체가 있을 때: 그 지점의 임무 메뉴. entityId는 커서 아래 엔티티 */
  | { kind: "menu"; point: MapPoint; entityId: string | null }
  /** Ctrl+우클릭: 항로점 추가 */
  | { kind: "waypoint"; point: MapPoint };

/**
 * 오른쪽 버튼을 놓았을 때. 끌었으면 카메라 조작이므로 무시한다.
 * Ctrl(또는 Cmd)+우클릭은 선택과 상관없이 항로점을 추가한다(전송할 때 대상을 고른다).
 */
export function classifyRightClick(
  r: Rect,
  mods: { ctrlKey: boolean; metaKey?: boolean },
  point: MapPoint | null,
  ctx: { hasTargets: boolean; entityId: string | null },
): RightClick {
  if (isDrag(r) || !point) return { kind: "none" };
  if (mods.ctrlKey || mods.metaKey) return { kind: "waypoint", point };
  if (!ctx.hasTargets) return { kind: "none" };
  return { kind: "menu", point, entityId: ctx.entityId };
}

export const HANDLE_RADIUS_PX = 12;

/** 왼쪽 버튼을 누른 곳에 항로점 손잡이가 있으면 그 번호. 겹치면 가까운 것, 같으면 나중 것 */
export function pickHandle(handles: readonly ({ x: number; y: number } | null)[], x: number, y: number, radius = HANDLE_RADIUS_PX): number | null {
  let best: number | null = null;
  let bestD = radius;
  handles.forEach((h, i) => {
    if (!h) return;
    const d = Math.hypot(h.x - x, h.y - y);
    if (d <= bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}
