// IMP-UI-067: 지도 모드(2D·2.5D·3D) 전환 시 화면 중심·보이는 폭 유지 계산 (REQ-UI-001, DEC-003)
// IMP-UI-068: 맞춤 뷰 범위 계산과 맞춤 시점 판정(첫 엔티티 수신, 시나리오 교체) (REQ-UI-001, DEC-003)

export type MapMode = "3d" | "2d" | "columbus";

/** 전환 직전 화면 상태. widthM은 화면 가로로 보이는 지면 폭(m) */
export interface ViewMemo {
  lat: number;
  lon: number;
  widthM: number;
  heading: number;
}

/** 보이는 폭 하한·상한 (m). 너무 가깝거나 지구 전체를 넘지 않게 한다 */
export const MIN_WIDTH_M = 200;
export const MAX_WIDTH_M = 2.0e7;

const clampWidth = (w: number) => Math.min(MAX_WIDTH_M, Math.max(MIN_WIDTH_M, Number.isFinite(w) ? w : MAX_WIDTH_M));

/**
 * 원근 카메라(3D·2.5D)에서 중심까지 거리와 가로 시야각으로 보이는 폭.
 * 중심을 못 찾으면(하늘을 봄) 높이를 거리로 쓰고 수직으로 내려다본 것으로 본다.
 */
export function perspectiveWidth(rangeM: number, fovRad: number): number {
  return clampWidth(2 * rangeM * Math.tan(fovRad / 2));
}

/**
 * 새 모드에서 같은 폭이 보이게 하는 카메라 높이(수직 내려다봄).
 * 2D는 Cesium setView가 높이를 정사영 폭으로 쓰므로 폭 그대로다.
 */
export function heightForWidth(mode: MapMode, widthM: number, fovRad: number): number {
  const w = clampWidth(widthM);
  return mode === "2d" ? w : w / (2 * Math.tan(fovRad / 2));
}

export interface LatLon {
  lat: number;
  lon: number;
}

export interface FitRect {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** 위치가 비었거나(0,0) 숫자가 아니면 맞춤 범위에서 뺀다 */
export function usablePoint(p: LatLon): boolean {
  return Number.isFinite(p.lat) && Number.isFinite(p.lon) && Math.abs(p.lat) <= 90 && !(p.lat === 0 && p.lon === 0);
}

const R = 6378137;
const D = Math.PI / 180;

/**
 * 모든 점을 담는 위경도 사각형. 각 변에 폭·높이의 margin만큼 여백을 두고,
 * 한 변이 minSpanM보다 좁으면(엔티티 1개 등) 중심 기준으로 minSpanM까지 넓힌다.
 */
export function fitRect(points: readonly LatLon[], margin = 0.15, minSpanM = 5000): FitRect | null {
  const ps = points.filter(usablePoint);
  if (ps.length === 0) return null;
  let s = Infinity, n = -Infinity, w = Infinity, e = -Infinity;
  for (const p of ps) {
    s = Math.min(s, p.lat);
    n = Math.max(n, p.lat);
    w = Math.min(w, p.lon);
    e = Math.max(e, p.lon);
  }
  const midLat = (s + n) / 2, midLon = (w + e) / 2;
  const minDLat = minSpanM / (R * D);
  const minDLon = minSpanM / (R * D * Math.max(Math.cos(midLat * D), 0.01));
  let dLat = (n - s) * (1 + 2 * margin), dLon = (e - w) * (1 + 2 * margin);
  dLat = Math.max(dLat, minDLat);
  dLon = Math.max(dLon, minDLon);
  return {
    west: midLon - dLon / 2,
    east: midLon + dLon / 2,
    south: Math.max(-89.9, midLat - dLat / 2),
    north: Math.min(89.9, midLat + dLat / 2),
  };
}

/**
 * 맞춤 시점 판정. 처음 엔티티가 보일 때 한 번, 시나리오 이름이 바뀌면(새로 적재) 다시 한 번.
 * 그 밖의 상태 갱신에서는 사용자가 움직인 카메라를 건드리지 않는다.
 * 이름을 아직 모르다가(빈 문자열) 처음 알게 된 것은 교체로 보지 않는다.
 */
export class FitGate {
  private armed = true;
  private name = "";

  /** 이번 갱신에서 맞춰야 하면 true (그 뒤로는 다시 무장될 때까지 false) */
  check(entityCount: number, scenarioName: string | undefined): boolean {
    const nm = scenarioName ?? "";
    if (nm !== "" && nm !== this.name) {
      if (this.name !== "") this.armed = true;
      this.name = nm;
    }
    if (this.armed && entityCount > 0) {
      this.armed = false;
      return true;
    }
    return false;
  }

  /** 맞추지 못했으면(쓸 만한 위치 없음) 다음 갱신에서 다시 시도한다 */
  rearm(): void {
    this.armed = true;
  }
}
