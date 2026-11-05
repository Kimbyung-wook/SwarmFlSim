// IMP-UI-015: 수신 상태 보관소. 프레임마다 React를 다시 그리지 않도록 최신 프레임·궤적을 여기에 두고
// 지도는 렌더 루프에서, 패널은 낮은 주기로 읽는다 (REQ-UI-001)
// IMP-UI-062: truth 이벤트(TruthEventStore)·센서 시야(SensorStore)도 여기서 받는다 (DEC-046)
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import type { TruthEvent, TruthFrame } from "../gen/swarm/v1/truth_pb";
import { FrameGapCounter, waitingWarning } from "./frameGap";
import type { FrameView } from "./entityView";
import { toFrameView } from "./entityView";
import type { TrailOptions } from "./trails";
import { TrailStore } from "./trails";
import { SensorStore } from "./sensorFov";
import { TruthEventStore } from "./truthEvents";

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
  /** DEC-042: 재생 중 빠진 프레임 수 */
  readonly gaps = new FrameGapCounter();
  /** truth/event/** 재밍 구역·생성 엔티티·impact·kill */
  readonly events = new TruthEventStore();
  /** GCS가 받은 SensorActivity */
  readonly sensors = new SensorStore();
  private byId = new Map<string, FrameView["entities"][number]>();

  constructor(trail?: TrailOptions) {
    this.trails = new TrailStore(trail);
  }

  onTruth(f: TruthFrame, nowMs = Date.now()): void {
    this.lastRxMs = nowMs;
    this.frame = toFrameView(f);
    this.byId = new Map(this.frame.entities.map((e) => [e.id, e]));
    this.trails.update(this.frame);
    this.events.onFrame(this.frame);
    this.sensors.tick(this.frame.simTimeUs);
    this.version++;
  }

  onEvent(ev: TruthEvent): void {
    this.events.onEvent(ev);
  }

  /** swarm/<gcs>/rx/**. SensorActivity만 쓴다 */
  onRx(key: string, env: LinkEnvelope): void {
    this.sensors.onRx(key, env);
  }

  onStatus(s: SimStatus, nowMs = Date.now()): void {
    this.lastRxMs = nowMs;
    this.status = s;
  }

  /** truth/state 프레임 번호(다운샘플 전). 재생 중에만 공백을 센다 */
  onFrameSeq(frame: bigint): void {
    this.gaps.feed(frame, this.status?.replay === true);
  }

  get missedFrames(): number {
    return this.status?.replay === true ? this.gaps.missed : 0;
  }

  /** DEC-041: 응답 없는 참여자 경고. 없으면 null */
  waitingWarning(): string | null {
    return waitingWarning(this.status?.waitingParticipants);
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
