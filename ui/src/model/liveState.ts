// IMP-UI-015: 수신 상태 보관소. 프레임마다 React를 다시 그리지 않도록 최신 프레임·궤적을 여기에 두고
// 지도는 렌더 루프에서, 패널은 낮은 주기로 읽는다 (REQ-UI-001)
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import type { FrameView } from "./entityView";
import { toFrameView } from "./entityView";
import type { TrailOptions } from "./trails";
import { TrailStore } from "./trails";

/** Core가 이 시간 넘게 truth·status를 모두 보내지 않으면 정지로 본다 (IMP-UI-055, QA-015) */
export const STALL_MS = 3000;

/**
 * 마지막 수신 후 STALL_MS 넘게 조용하면 true. 일시정지는 status가 계속 오므로 해당하지 않는다.
 * lastRxMs가 null이면 아직 아무것도 받지 않은 것이라 정지가 아니다.
 */
export function isStalled(nowMs: number, lastRxMs: number | null, thresholdMs = STALL_MS): boolean {
  return lastRxMs !== null && nowMs - lastRxMs > thresholdMs;
}

export class LiveState {
  frame: FrameView = { frame: 0n, simTimeUs: 0n, entities: [] };
  status: SimStatus | null = null;
  readonly trails: TrailStore;
  /** 프레임을 받을 때마다 1 증가 */
  version = 0;
  /** 마지막으로 truth 또는 status를 받은 벽시계 시각(ms) */
  lastRxMs: number | null = null;
  private byId = new Map<string, FrameView["entities"][number]>();

  constructor(trail?: TrailOptions) {
    this.trails = new TrailStore(trail);
  }

  onTruth(f: TruthFrame, nowMs = Date.now()): void {
    this.lastRxMs = nowMs;
    this.frame = toFrameView(f);
    this.byId = new Map(this.frame.entities.map((e) => [e.id, e]));
    this.trails.update(this.frame);
    this.version++;
  }

  onStatus(s: SimStatus, nowMs = Date.now()): void {
    this.lastRxMs = nowMs;
    this.status = s;
  }

  stalled(nowMs = Date.now()): boolean {
    return isStalled(nowMs, this.lastRxMs);
  }

  get(id: string) {
    return this.byId.get(id);
  }

  ids(): ReadonlySet<string> {
    return new Set(this.byId.keys());
  }
}
