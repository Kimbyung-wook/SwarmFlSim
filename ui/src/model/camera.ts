// IMP-UI-007: 카메라 시점 구조 (REQ-UI-007). 엔티티 자세 쿼터니언으로 카메라 자세를 만든다.
// 짐벌 각은 아직 계약에 없으므로(SensorActivity 연동은 다음 단계) 인자로만 받는다.
import type { EntityView } from "./entityView";
import { wrap2Pi } from "./attitude";

export type CameraMode = "free" | "chase" | "fpv" | "gimbal";

/** Cesium Camera.setView 규약: heading 북쪽 기준 시계방향, pitch 아래 −, roll 오른쪽 +. rad */
export interface CameraPose {
  lat: number;
  lon: number;
  alt: number;
  heading: number;
  pitch: number;
  roll: number;
}

export interface ChaseOptions {
  backM: number;
  upM: number;
}

export interface GimbalAngles {
  pan: number;  // 기체 기수 기준, 오른쪽 +
  tilt: number; // 아래 −
}

const R_EARTH = 6378137;

/** 진행 방향 기준 (전방 f, 오른쪽 r, 위 u) m 만큼 옮긴 위치 */
export function offsetLocal(e: Pick<EntityView, "lat" | "lon" | "alt">, yaw: number, f: number, r: number, u: number) {
  const n = f * Math.cos(yaw) - r * Math.sin(yaw);
  const east = f * Math.sin(yaw) + r * Math.cos(yaw);
  const latRad = (e.lat * Math.PI) / 180;
  return {
    lat: e.lat + (n / R_EARTH) * (180 / Math.PI),
    lon: e.lon + (east / (R_EARTH * Math.cos(latRad))) * (180 / Math.PI),
    alt: e.alt + u,
  };
}

/** free 모드에서는 null (사용자가 카메라를 직접 조작) */
export function cameraPose(
  e: EntityView,
  mode: CameraMode,
  chase: ChaseOptions = { backM: 120, upM: 40 },
  gimbal: GimbalAngles = { pan: 0, tilt: -0.5 },
): CameraPose | null {
  const { yaw, pitch, roll } = e.euler;
  switch (mode) {
    case "free":
      return null;
    case "fpv":
      return { lat: e.lat, lon: e.lon, alt: e.alt, heading: wrap2Pi(yaw), pitch, roll };
    case "gimbal":
      // 안정화 짐벌: 기체 롤·피치와 무관하게 수평 기준으로 pan/tilt
      return { lat: e.lat, lon: e.lon, alt: e.alt, heading: wrap2Pi(yaw + gimbal.pan), pitch: gimbal.tilt, roll: 0 };
    case "chase": {
      // 지상 진행 방향 기준 뒤·위에서 기체를 내려다본다
      const p = offsetLocal(e, e.heading, -chase.backM, 0, chase.upM);
      return { ...p, heading: e.heading, pitch: -Math.atan2(chase.upM, chase.backM), roll: 0 };
    }
  }
}
