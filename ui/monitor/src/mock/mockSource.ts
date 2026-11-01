// IMP-MON-011: 목 프레임 소스. MockTraffic을 벽시계에 맞춰 진행한다 (REQ-UI-005)
import type { BusFrame } from "../bridge/frame";
import type { FrameSource, SourceStatus } from "../bridge/source";
import type { MockOptions } from "./mockTraffic";
import { MockTraffic } from "./mockTraffic";

export interface MockSourceOptions extends MockOptions {
  /** 배속. 타이머 한 번에 진행할 프레임 수를 늘린다 */
  rate?: number;
}

export class MockSource implements FrameSource {
  readonly name = "mock";
  private frameCb: (f: BusFrame) => void = () => {};
  private statusCb: (s: SourceStatus) => void = () => {};
  private timer: ReturnType<typeof setInterval> | null = null;
  private traffic: MockTraffic;
  private startWall = 0;
  private startFrame = 0;
  readonly rate: number;

  constructor(private readonly opts: MockSourceOptions = {}) {
    this.rate = opts.rate ?? 1;
    this.traffic = new MockTraffic((f) => this.frameCb(f), { wire: true, ...opts });
  }

  get generator(): MockTraffic {
    return this.traffic;
  }

  onFrame(cb: (f: BusFrame) => void): void {
    this.frameCb = cb;
  }

  onStatus(cb: (s: SourceStatus) => void): void {
    this.statusCb = cb;
  }

  connect(): void {
    if (this.timer) return;
    this.startWall = Date.now();
    this.startFrame = this.traffic.frame;
    this.statusCb({ state: "open", detail: "목 트래픽", contract: "0.2.0" });
    this.timer = setInterval(() => this.tick(), 1000 / this.traffic.frameHz);
  }

  /** 벽시계 기준 목표 프레임까지 진행한다. 밀리면 한 번에 최대 1초분만 따라잡는다 */
  private tick(): void {
    const target = this.startFrame + Math.floor(((Date.now() - this.startWall) / 1000) * this.traffic.frameHz * this.rate);
    const n = Math.min(target - this.traffic.frame, this.traffic.frameHz * Math.max(1, this.rate));
    for (let i = 0; i < n; i++) this.traffic.stepFrame();
    if (target - this.traffic.frame > this.traffic.frameHz) {
      this.startWall = Date.now();
      this.startFrame = this.traffic.frame;
    }
  }

  /** 재생 되감기 흉내: 생성기를 처음부터 다시 시작한다 */
  restart(): void {
    this.traffic = new MockTraffic((f) => this.frameCb(f), { wire: true, ...this.opts });
    this.startWall = Date.now();
    this.startFrame = 0;
  }

  close(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.statusCb({ state: "closed" });
  }
}
