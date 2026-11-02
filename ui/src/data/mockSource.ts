// IMP-UI-010: 목 데이터 소스. Core 없이 MockScenario로 truth/state와 sim/ctrl/status를 흉내 낸다 (REQ-UI-001, DEC-005)
// sim/ctrl/cmd 중 Start·Pause·Resume·StepFrames·SetRate·Reset을 처리한다.
// IMP-UI-029: C2 TaskCommand에는 대상 기체마다 TaskStatus(ACCEPTED)를 rx로 돌려준다.
// IMP-UI-041: 대상 UAV는 임무대로 비행하고(MockScenario.command), 구간 진행·완료를 TaskStatus(EXECUTING·COMPLETED)로 보낸다.
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import type { OutgoingC2 } from "../model/commands";
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
  readonly gcs = "gcs-01";
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

  sendC2(out: OutgoingC2): void {
    const env = out.envelope;
    if (env.msgType !== TaskCommandSchema.typeName) return;
    const cmd = fromBinary(TaskCommandSchema, env.payload);
    const rejected = new Set(this.scenario.command(cmd, Number(this.simTimeUs()) / 1e6));
    for (const id of cmd.assignees) {
      const state = cmd.cancel ? CommandState.CANCELLED : rejected.has(id) ? CommandState.REJECTED : CommandState.ACCEPTED;
      this.reply(id, cmd.taskId, state, 0, rejected.has(id) ? "목 소스: 다룰 수 없는 임무" : "목 소스: 수락");
    }
  }

  private reply(id: string, taskId: string, state: CommandState, progress: number, reason: string): void {
    const simTimeUs = this.simTimeUs();
    const st = create(TaskStatusSchema, {
      header: { simTimeUs, frame: this.frame, source: id, correlationId: taskId },
      taskId,
      state,
      progress,
      reason,
    });
    const reply = create(LinkEnvelopeSchema, {
      header: { simTimeUs, frame: this.frame, source: id },
      dst: [this.gcs],
      iface: L1Interface.C2,
      msgType: TaskStatusSchema.typeName,
      payload: toBinary(TaskStatusSchema, st),
      rxTimeUs: simTimeUs,
    });
    this.handlers.rx(`swarm/${this.gcs}/rx/c2/TaskStatus`, reply);
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
    for (const r of this.scenario.takeReports()) this.reply(r.entityId, r.taskId, r.state, r.progress, r.reason);
  }
}
