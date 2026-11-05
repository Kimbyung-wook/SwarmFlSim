// IMP-UI-061: 센서 시야 (DEC-018, DEC-046, DEC-047)
// GCS가 받은 SensorActivity(swarm/<gcs>/rx/ms/SensorActivity, 송신 기체 = envelope header.source)를 기체·장비별로 두고,
// 기체 위치(truth/state)와 boresight(NED 단위벡터)·hfov·vfov·max_range로 FOV 사각뿔과 지면 풋프린트를 만든다.
// 카메라 축은 Payload(WP8)와 같다: 전방 f, 오른쪽 r = down × f(수평 유지), 아래 = f × r. f가 수직이면 r = 동쪽
import { fromBinary } from "@bufbuild/protobuf";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import type { SensorActivity } from "../gen/swarm/v1/ms_pb";
import { SensorActivitySchema } from "../gen/swarm/v1/ms_pb";
import type { GeoPos } from "./truthEvents";

export interface SensorView {
  platform: string;
  payloadId: string;
  active: boolean;
  /** NED 단위벡터 */
  boresight: [number, number, number];
  hfovDeg: number;
  vfovDeg: number;
  maxRangeM: number;
  timeUs: bigint;
}

type V3 = [number, number, number];
const R_EARTH = 6378137;
const DEG = Math.PI / 180;

const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const unit = (a: V3): V3 | null => {
  const n = Math.hypot(a[0], a[1], a[2]);
  return n > 1e-9 ? [a[0] / n, a[1] / n, a[2] / n] : null;
};

/** 국지 평면 근사로 NED 오프셋(m)을 더한다. 표시용(수십 km 이내) */
export function offsetNed(p: GeoPos, n: number, e: number, d: number): GeoPos {
  return {
    lat: p.lat + (n / R_EARTH) / DEG,
    lon: p.lon + (e / (R_EARTH * Math.cos(p.lat * DEG))) / DEG,
    alt: p.alt - d,
  };
}

/** 카메라 축 (전방 f, 오른쪽 r, 아래 u). boresight가 0이면 null */
export function cameraAxes(boresight: V3): { f: V3; r: V3; d: V3 } | null {
  const f = unit(boresight);
  if (!f) return null;
  let r = unit(cross([0, 0, 1], f)) ?? [0, 1, 0];
  r = unit([r[0] - dot(r, f) * f[0], r[1] - dot(r, f) * f[1], r[2] - dot(r, f) * f[2]]) ?? [0, 1, 0];
  return { f, r, d: cross(f, r) };
}

export interface FovGeometry {
  apex: GeoPos;
  /** 네 모서리 광선 끝(지면에 닿으면 지면, 아니면 max_range). 순서: 오른쪽 위, 오른쪽 아래, 왼쪽 아래, 왼쪽 위 */
  corners: GeoPos[];
  /** FOV 경계를 따라간 광선 끝의 닫힌 고리 (먼 쪽 외곽선) */
  outline: GeoPos[];
  /** 경계 광선이 모두 max_range 안에서 지면에 닿으면 true (outline이 지면 풋프린트) */
  onGround: boolean;
  /** boresight 광선 끝 */
  center: GeoPos;
}

/**
 * 시야 도형. groundAltM은 기체 아래 지면 고도(MSL)로 보고 평면으로 둔다.
 * perEdge는 경계 한 변의 표본 수(외곽선이 거리 제한에 걸려 휘는 것을 보이도록).
 */
export function fovGeometry(pos: GeoPos, s: SensorView, groundAltM = 0, perEdge = 8): FovGeometry | null {
  const ax = cameraAxes(s.boresight);
  if (!ax || !(s.maxRangeM > 0)) return null;
  const th = Math.tan((Math.min(Math.max(s.hfovDeg, 0), 179) * DEG) / 2);
  const tv = Math.tan((Math.min(Math.max(s.vfovDeg, 0), 179) * DEG) / 2);
  const height = pos.alt - groundAltM;
  let allGround = height > 0;
  // (x, y) ∈ [-1, 1]²: x 오른쪽, y 아래
  const ray = (x: number, y: number): GeoPos => {
    const dir = unit([
      ax.f[0] + x * th * ax.r[0] + y * tv * ax.d[0],
      ax.f[1] + x * th * ax.r[1] + y * tv * ax.d[1],
      ax.f[2] + x * th * ax.r[2] + y * tv * ax.d[2],
    ])!;
    let t = s.maxRangeM;
    if (height > 0 && dir[2] > 1e-9 && height / dir[2] <= s.maxRangeM) t = height / dir[2];
    else allGround = false;
    return offsetNed(pos, dir[0] * t, dir[1] * t, dir[2] * t);
  };
  const corners = [ray(1, -1), ray(1, 1), ray(-1, 1), ray(-1, -1)];
  const outline: GeoPos[] = [];
  const edges: [number, number, number, number][] = [
    [1, -1, 1, 1],
    [1, 1, -1, 1],
    [-1, 1, -1, -1],
    [-1, -1, 1, -1],
  ];
  for (const [x0, y0, x1, y1] of edges)
    for (let i = 0; i < perEdge; i++) {
      const k = i / perEdge;
      outline.push(ray(x0 + (x1 - x0) * k, y0 + (y1 - y0) * k));
    }
  outline.push(outline[0]);
  const onGround = allGround;
  const center = ray(0, 0);
  return { apex: pos, corners, outline, onGround, center };
}

export interface SensorStoreOptions {
  /** 이 시간(sim µs) 넘게 새 SensorActivity가 없으면 지운다. Payload는 주기적으로 보낸다 */
  staleUs: bigint;
}

export class SensorStore {
  version = 0;
  private readonly items = new Map<string, SensorView>();
  private nowUs = -1n;

  constructor(private readonly opts: SensorStoreOptions = { staleUs: 5_000_000n }) {}

  /** swarm/<gcs>/rx/** 수신. SensorActivity가 아니면 false */
  onRx(_key: string, env: LinkEnvelope): boolean {
    if (env.msgType !== SensorActivitySchema.typeName) return false;
    const platform = env.header?.source ?? "";
    if (!platform) return false;
    const a = fromBinary(SensorActivitySchema, env.payload);
    this.onActivity(platform, a, env.rxTimeUs || env.header?.simTimeUs || 0n);
    return true;
  }

  onActivity(platform: string, a: SensorActivity, timeUs = a.header?.simTimeUs ?? 0n): void {
    const b = a.boresightNed;
    this.items.set(`${platform}/${a.payloadId}`, {
      platform,
      payloadId: a.payloadId,
      active: a.active,
      boresight: [b?.x ?? 0, b?.y ?? 0, b?.z ?? 0],
      hfovDeg: a.hfovDeg,
      vfovDeg: a.vfovDeg,
      maxRangeM: a.maxRangeM,
      timeUs,
    });
    this.version++;
  }

  /** truth/state 시각마다. 되감기면 비우고, 오래된 항목을 지운다 */
  tick(nowUs: bigint): void {
    if (this.nowUs >= 0n && nowUs < this.nowUs) {
      if (this.items.size) this.version++;
      this.items.clear();
    }
    this.nowUs = nowUs;
    for (const [k, s] of this.items)
      if (nowUs - s.timeUs > this.opts.staleUs) {
        this.items.delete(k);
        this.version++;
      }
  }

  list(): SensorView[] {
    return [...this.items.values()];
  }

  /** 그릴 것만 (active=true). 고장(DEC-047)이나 꺼짐은 그리지 않는다 */
  active(): SensorView[] {
    return this.list().filter((s) => s.active);
  }
}
