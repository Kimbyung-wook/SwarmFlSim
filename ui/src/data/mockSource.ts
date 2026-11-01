// IMP-UI-010: 목 데이터 소스. Core 없이 MockScenario로 truth/state와 sim/ctrl/status를 흉내 낸다 (REQ-UI-001, DEC-005)
// sim/ctrl/cmd 중 Start·Pause·Resume·StepFrames·SetRate·Reset을 처리한다.
import { create } from "@bufbuild/protobuf";
import type { SimCommand, SimStatus } from "../gen/swarm/v1/sim_pb";
import { RunMode, SimRunState, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import type { DataHandlers, DataSource } from "./source";
import { HandlerSet } from "./source";
import type { MockScenarioOptions } from "./mockScenario";
import { MockScenario } from "./mockScenario";

export interface MockClock {
  now(): number; // ms
  setInterval(fn: () => void, ms: number): unknown;
  clearInterval(h: unknown): void;
}

const browserClock: MockClock = {
  now: () => performance.now(),
  setInterval: (fn, ms) => globalThis.setInterval(fn, ms),
  clearInterval: (h) => globalThis.clearInterval(h as ReturnType<typeof setInterval>),
};

export interface MockSourceOptions {
  frameHz: number;
  rate: number;
  autoStart: boolean;
  /** 한 번의 타이머 호출에서 따라잡을 최대 프레임 수 (탭 비활성 후 폭주 방지) */
  maxCatchUp: number;
  scenario?: MockScenarioOptions;
}

const DEFAULTS: MockSourceOptions = { frameHz: 50, rate: 1, autoStart: true, maxCatchUp: 25 };

export class MockSource implements DataSource {
  readonly name = "mock";
  private readonly handlers = new HandlerSet();
  private readonly opts: MockSourceOptions;
  private readonly scenario: MockScenario;
  private frame = 0n;
  private state = SimRunState.IDLE;
  private rate: number;
  private timer: unknown = null;
  private lastMs = 0;
  private carry = 0; // 다음 호출로 넘기는 프레임 소수부
  private rateActual = 0;

  constructor(opts: Partial<MockSourceOptions> = {}, private readonly clock: MockClock = browserClock) {
    this.opts = { ...DEFAULTS, ...opts };
    this.rate = this.opts.rate;
    this.scenario = new MockScenario(this.opts.scenario);
  }

  get entityCount(): number {
    return this.scenario.actors.length;
  }

  subscribe(h: DataHandlers): () => void {
    return this.handlers.add(h);
  }

  async connect(): Promise<void> {
    this.state = SimRunState.LOADED;
    this.publish();
    if (this.opts.autoStart) this.run();
  }

  close(): void {
    this.halt();
    this.state = SimRunState.STOPPED;
    this.handlers.status(this.status());
  }

  send(cmd: SimCommand): void {
    const c = cmd.cmd;
    switch (c.case) {
      case "start":
        if (c.value.rate > 0) this.rate = c.value.rate;
        this.run();
        break;
      case "pause":
        if (this.state === SimRunState.RUNNING) {
          this.halt();
          this.state = SimRunState.PAUSED;
        }
        break;
      case "resume":
        if (this.state === SimRunState.PAUSED) this.run();
        break;
      case "step":
        if (this.state !== SimRunState.RUNNING) {
          for (let i = 0; i < c.value.frames; i++) this.advance();
          this.state = SimRunState.PAUSED;
        }
        break;
      case "setRate":
        if (c.value.rate > 0) this.rate = c.value.rate;
        break;
      case "reset":
        this.halt();
        this.frame = 0n;
        this.state = SimRunState.LOADED;
        this.publish();
        break;
      default:
        // load·shutdown·fault는 목 소스에서 다루지 않는다
        return;
    }
    this.handlers.status(this.status());
  }

  status(): SimStatus {
    return create(SimStatusSchema, {
      state: this.state,
      mode: RunMode.REALTIME,
      simTimeUs: this.simTimeUs(),
      frame: this.frame,
      frameHz: this.opts.frameHz,
      rateTarget: this.rate,
      rateActual: this.state === SimRunState.RUNNING ? this.rateActual : 0,
      entityCount: this.scenario.actors.length,
      scenarioName: "mock",
    });
  }

  private simTimeUs(): bigint {
    return (this.frame * 1_000_000n) / BigInt(this.opts.frameHz);
  }

  private run(): void {
    if (this.timer !== null) return;
    this.state = SimRunState.RUNNING;
    this.lastMs = this.clock.now();
    this.carry = 0;
    this.timer = this.clock.setInterval(() => this.tick(), 1000 / this.opts.frameHz);
  }

  private halt(): void {
    if (this.timer === null) return;
    this.clock.clearInterval(this.timer);
    this.timer = null;
  }

  /** 경과한 실제 시간 × 배속만큼 프레임을 진행하고 마지막 프레임만 발행한다 */
  private tick(): void {
    const now = this.clock.now();
    const due = ((now - this.lastMs) / 1000) * this.opts.frameHz * this.rate + this.carry;
    this.lastMs = now;
    const n = Math.min(Math.floor(due), this.opts.maxCatchUp);
    this.carry = n < this.opts.maxCatchUp ? due - n : 0;
    if (n <= 0) return;
    this.frame += BigInt(n);
    this.rateActual = this.rate;
    this.publish();
    if (this.frame % BigInt(this.opts.frameHz) < BigInt(n)) this.handlers.status(this.status());
  }

  private advance(): void {
    this.frame += 1n;
    this.publish();
  }

  private publish(): void {
    this.handlers.truth(this.scenario.frameAt(this.frame, this.opts.frameHz));
  }
}
