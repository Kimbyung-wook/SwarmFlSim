// IMP-UI-005: 궤적 꼬리 (REQ-UI-001)
// 엔티티별로 sim 시각 간격 intervalUs마다 위치를 하나씩 남기고 maxPoints개를 넘으면 오래된 점을 버린다.
import type { FrameView } from "./entityView";

export interface TrailPoint {
  lat: number;
  lon: number;
  alt: number;
}

export interface TrailOptions {
  maxPoints: number;
  intervalUs: bigint;
}

interface Trail {
  points: TrailPoint[];
  lastUs: bigint;
}

export class TrailStore {
  private readonly trails = new Map<string, Trail>();

  constructor(private readonly opts: TrailOptions = { maxPoints: 120, intervalUs: 500_000n }) {}

  update(frame: FrameView): void {
    const seen = new Set<string>();
    for (const e of frame.entities) {
      seen.add(e.id);
      let t = this.trails.get(e.id);
      if (!t) {
        t = { points: [], lastUs: -1n };
        this.trails.set(e.id, t);
      }
      if (!e.alive) continue;
      // 시각이 거꾸로 가면(리셋·재생 되감기) 궤적을 새로 시작한다
      if (t.lastUs >= 0n && frame.simTimeUs < t.lastUs) {
        t.points = [];
        t.lastUs = -1n;
      }
      if (t.lastUs < 0n || frame.simTimeUs - t.lastUs >= this.opts.intervalUs) {
        t.points.push({ lat: e.lat, lon: e.lon, alt: e.alt });
        if (t.points.length > this.opts.maxPoints) t.points.splice(0, t.points.length - this.opts.maxPoints);
        t.lastUs = frame.simTimeUs;
      }
    }
    for (const id of this.trails.keys()) if (!seen.has(id)) this.trails.delete(id);
  }

  get(id: string): readonly TrailPoint[] {
    return this.trails.get(id)?.points ?? [];
  }

  ids(): IterableIterator<string> {
    return this.trails.keys();
  }

  clear(): void {
    this.trails.clear();
  }
}
