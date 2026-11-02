// IMP-MON-014: 시퀀스 타임라인 질의·배치 (src→dst 화살표, 손실 표시) (REQ-UI-005, PRP-UI-002)
// 그리기(캔버스)와 분리한 순수 계산. 시간축은 시뮬레이션 시각이다.
import type { LinkOutcome } from "../gen/swarm/v1/link_pb";
import { LinkOutcomeKind } from "../gen/swarm/v1/link_pb";
import type { Filter } from "./filter";
import { matchOutcome } from "./filter";
import { Ring } from "./ring";

export interface TimelineQuery {
  filter: Filter;
  /** 창 끝 시각(µs) */
  endUs: number;
  windowUs: number;
  maxItems: number;
}

/** 창 안에서 필터에 맞는 최신 outcome. 도착 순서가 조금 어긋나도 되도록 창 앞 1 s까지 훑는다 */
export function queryTimeline(ring: Ring<LinkOutcome>, q: TimelineQuery): LinkOutcome[] {
  const start = q.endUs - q.windowUs;
  const out: LinkOutcome[] = [];
  ring.forEachNewest((o) => {
    const t = Number(o.txTimeUs);
    if (t < start - 1_000_000) return false;
    if (t >= start && t <= q.endUs && matchOutcome(q.filter, o)) out.push(o);
    return out.length < q.maxItems;
  });
  return out;
}

/** 화면 정지용 사본. 정지 중에도 원본 버퍼는 계속 덮이므로 최근 sinceUs 이후를 복사해 둔다 */
export function snapshotTimeline(ring: Ring<LinkOutcome>, sinceUs: number, limit = 100_000): Ring<LinkOutcome> {
  const items: LinkOutcome[] = [];
  ring.forEachNewest((o) => {
    if (Number(o.txTimeUs) < sinceUs - 1_000_000) return false;
    items.push(o);
    return items.length < limit;
  });
  const snap = new Ring<LinkOutcome>(Math.max(1, items.length));
  for (let i = items.length - 1; i >= 0; i--) snap.push(items[i]);
  return snap;
}

/** 레인 순서: 고정 목록(필터 엔티티) → GCS → 나머지 사전순. 최대 maxLanes */
export function laneOrder(items: readonly LinkOutcome[], pinned: Iterable<string>, maxLanes = 40): string[] {
  const set = new Set<string>();
  for (const o of items) {
    set.add(o.src);
    set.add(o.dst);
  }
  const first = [...pinned].filter((id) => set.has(id));
  const rest = [...set].filter((id) => !first.includes(id));
  rest.sort((a, b) => {
    const ga = a.startsWith("gcs-") ? 0 : 1;
    const gb = b.startsWith("gcs-") ? 0 : 1;
    return ga - gb || a.localeCompare(b);
  });
  return [...first, ...rest].slice(0, maxLanes);
}

export interface Arrow {
  o: LinkOutcome;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  dropped: boolean;
}

export interface Layout {
  lanes: string[];
  laneX: number[];
  arrows: Arrow[];
  y: (tUs: number) => number;
}

/** 시간은 위에서 아래로 흐른다(아래가 최신). 손실은 수신 레인까지 수평에 가깝게 긋고 끝에 ✕를 그린다 */
export function layoutTimeline(
  items: readonly LinkOutcome[],
  lanes: string[],
  box: { left: number; right: number; top: number; bottom: number },
  endUs: number,
  windowUs: number,
): Layout {
  const n = lanes.length;
  const step = n > 1 ? (box.right - box.left) / (n - 1) : 0;
  const laneX = lanes.map((_, i) => (n > 1 ? box.left + i * step : (box.left + box.right) / 2));
  const idx = new Map(lanes.map((id, i) => [id, i]));
  const h = box.bottom - box.top;
  const y = (tUs: number) => box.top + ((tUs - (endUs - windowUs)) / windowUs) * h;
  const arrows: Arrow[] = [];
  for (const o of items) {
    const a = idx.get(o.src);
    const b = idx.get(o.dst);
    if (a === undefined || b === undefined) continue;
    const dropped = o.outcome === LinkOutcomeKind.DROPPED;
    const y1 = y(Number(o.txTimeUs));
    const y2 = dropped ? y1 + 3 : Math.min(box.bottom, y(Number(o.rxTimeUs)));
    arrows.push({ o, x1: laneX[a], y1, x2: laneX[b], y2, dropped });
  }
  return { lanes, laneX, arrows, y };
}

/** 선분까지 거리가 tol 이하인 화살표 중 가장 가까운 것 */
export function hitArrow(arrows: readonly Arrow[], px: number, py: number, tol = 6): Arrow | undefined {
  let best: Arrow | undefined;
  let bd = tol;
  for (const a of arrows) {
    const dx = a.x2 - a.x1;
    const dy = a.y2 - a.y1;
    const l2 = dx * dx + dy * dy;
    const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - a.x1) * dx + (py - a.y1) * dy) / l2));
    const d = Math.hypot(px - (a.x1 + t * dx), py - (a.y1 + t * dy));
    if (d <= bd) {
      bd = d;
      best = a;
    }
  }
  return best;
}
