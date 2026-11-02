// IMP-UI-036: 항로점 편집 모델 (REQ-UI-003, REQ-UI-004, DEC-033)
// Ctrl+우클릭으로 추가한 항로점 목록. 추가·위치 이동·삭제·순서 바꾸기·속성 변경을 불변 값으로 다룬다.
// 전송하면 task_id를 기억하고, 같은 task_id로 다시 보내 항로 전체를 바꾼다.
import type { GeoPoint, MissionSpec, WaypointAction, WaypointSpec } from "./commands";

export interface RouteDraft {
  waypoints: WaypointSpec[];
  loop: boolean;
  /** 한 번 보낸 항로면 그 task_id. 다시 보내면 같은 ID로 대체한다 */
  taskId: string | null;
  /** 보낸 항로를 다시 편집할 때 원래 대상 기체 */
  assignees: string[];
}

export function emptyRoute(): RouteDraft {
  return { waypoints: [], loop: false, taskId: null, assignees: [] };
}

/** 새 항로점. 고도·속력이 없으면 직전 항로점 값을 따른다 */
export function addWaypoint(d: RouteDraft, pos: { latDeg: number; lonDeg: number }, defaults: { altM: number; speedMps?: number }): RouteDraft {
  const prev = d.waypoints[d.waypoints.length - 1];
  const wp: WaypointSpec = {
    position: { latDeg: pos.latDeg, lonDeg: pos.lonDeg, altM: prev?.position.altM ?? defaults.altM },
    speedMps: prev ? prev.speedMps : defaults.speedMps,
    action: { kind: "none" },
  };
  return { ...d, waypoints: [...d.waypoints, wp] };
}

function at(d: RouteDraft, i: number): WaypointSpec {
  const w = d.waypoints[i];
  if (!w) throw new RangeError(`항로점 ${i + 1}이 없다`);
  return w;
}

function replace(d: RouteDraft, i: number, w: WaypointSpec): RouteDraft {
  const ws = d.waypoints.slice();
  ws[i] = w;
  return { ...d, waypoints: ws };
}

/** 지도에서 끌어 위치를 바꾼다. 고도는 유지한다 */
export function moveWaypoint(d: RouteDraft, i: number, pos: { latDeg: number; lonDeg: number }): RouteDraft {
  const w = at(d, i);
  return replace(d, i, { ...w, position: { ...w.position, latDeg: pos.latDeg, lonDeg: pos.lonDeg } });
}

export function setAltitude(d: RouteDraft, i: number, altM: number): RouteDraft {
  const w = at(d, i);
  return replace(d, i, { ...w, position: { ...w.position, altM } });
}

export function setSpeed(d: RouteDraft, i: number, speedMps: number | undefined): RouteDraft {
  return replace(d, i, { ...at(d, i), speedMps: speedMps !== undefined && speedMps > 0 ? speedMps : undefined });
}

export function setAction(d: RouteDraft, i: number, action: WaypointAction): RouteDraft {
  return replace(d, i, { ...at(d, i), action });
}

export function removeWaypoint(d: RouteDraft, i: number): RouteDraft {
  at(d, i);
  return { ...d, waypoints: d.waypoints.filter((_, k) => k !== i) };
}

/** from 자리의 항로점을 to 자리로 옮긴다 (나머지 순서 유지) */
export function reorderWaypoint(d: RouteDraft, from: number, to: number): RouteDraft {
  at(d, from);
  if (to < 0 || to >= d.waypoints.length || to === from) return d;
  const ws = d.waypoints.slice();
  const [w] = ws.splice(from, 1);
  ws.splice(to, 0, w);
  return { ...d, waypoints: ws };
}

export function routeSpec(d: RouteDraft): MissionSpec & { kind: "route" } {
  return { kind: "route", waypoints: d.waypoints.map((w) => ({ ...w, position: { ...w.position } })), loop: d.loop };
}

/** 보낸 항로를 다시 편집한다 */
export function draftFromSpec(spec: MissionSpec & { kind: "route" }, taskId: string, assignees: readonly string[]): RouteDraft {
  return { waypoints: routeSpec({ ...emptyRoute(), ...spec }).waypoints, loop: spec.loop, taskId, assignees: [...assignees] };
}

export function waypointPositions(d: RouteDraft): GeoPoint[] {
  return d.waypoints.map((w) => w.position);
}
