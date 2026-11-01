// IMP-UI-003: 자세·방향 변환. docs/10_contracts.md §2 (NED → 기체 FRD 쿼터니언, w x y z)
// 오일러각은 ZYX 순서(yaw → pitch → roll), rad.

export interface Quat {
  w: number;
  x: number;
  y: number;
  z: number;
}

export interface Euler {
  yaw: number;   // 북쪽 기준 시계방향
  pitch: number; // 기수 들림 +
  roll: number;  // 오른쪽 날개 내림 +
}

export const DEG = Math.PI / 180;

export function wrapPi(a: number): number {
  const t = (a + Math.PI) % (2 * Math.PI);
  return (t < 0 ? t + 2 * Math.PI : t) - Math.PI;
}

/** 0..2π 범위 */
export function wrap2Pi(a: number): number {
  const t = a % (2 * Math.PI);
  return t < 0 ? t + 2 * Math.PI : t;
}

export function eulerToQuat({ yaw, pitch, roll }: Euler): Quat {
  const cy = Math.cos(yaw / 2), sy = Math.sin(yaw / 2);
  const cp = Math.cos(pitch / 2), sp = Math.sin(pitch / 2);
  const cr = Math.cos(roll / 2), sr = Math.sin(roll / 2);
  return {
    w: cr * cp * cy + sr * sp * sy,
    x: sr * cp * cy - cr * sp * sy,
    y: cr * sp * cy + sr * cp * sy,
    z: cr * cp * sy - sr * sp * cy,
  };
}

export function quatToEuler(q: Quat): Euler {
  const n = Math.hypot(q.w, q.x, q.y, q.z) || 1;
  const w = q.w / n, x = q.x / n, y = q.y / n, z = q.z / n;
  const sinp = Math.max(-1, Math.min(1, 2 * (w * y - z * x)));
  return {
    yaw: Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)),
    pitch: Math.asin(sinp),
    roll: Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
  };
}

/** NED 속도의 진행 방향(rad, 북쪽 기준 시계방향 0..2π). 수평 속도가 없으면 null */
export function headingFromVelocity(vn: number, ve: number, minSpeed = 0.5): number | null {
  if (Math.hypot(vn, ve) < minSpeed) return null;
  return wrap2Pi(Math.atan2(ve, vn));
}

/** NED 속도의 상승각(rad, 위 +) */
export function flightPathAngle(vn: number, ve: number, vd: number): number {
  return Math.atan2(-vd, Math.hypot(vn, ve));
}
