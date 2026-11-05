// IMP-UI-010: 목 데이터 소스. Core 없이 MockScenario로 truth/state와 sim/ctrl/status를 흉내 낸다 (REQ-UI-001, DEC-005)
// sim/ctrl/cmd 중 Start·Pause·Resume·StepFrames·SetRate·Reset을 처리한다.
// IMP-UI-029: C2 TaskCommand에는 대상 기체마다 TaskStatus(ACCEPTED)를 rx로 돌려준다.
// IMP-UI-046: UAV마다 동역학·FA·MA 매개변수(EntityParams)를 sim/param으로 내고, set_params를 검사해 적용·거부한다 (DEC-035).
// IMP-UI-063: truth/event/<kind>와 SensorActivity(rx/ms)를 각본(MockEvents)으로 낸다. 발사체는 truth/state에 함께 싣는다 (DEC-046).
// IMP-UI-041: 대상 UAV는 임무대로 비행하고(MockScenario.command), 구간 진행·완료를 TaskStatus(EXECUTING·COMPLETED)로 보낸다.
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { EntityKind } from "../gen/swarm/v1/entity_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import type { OutgoingC2 } from "../model/commands";
import type { SimCommand, SimStatus } from "../gen/swarm/v1/sim_pb";
import { RunMode, SimRunState, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import type { DataHandlers, DataSource } from "./source";
import { HandlerSet } from "./source";
import type { MockScenarioOptions } from "./mockScenario";
import { MockScenario } from "./mockScenario";
import { MOCK_OWNERS, MockParams } from "./mockParams";
import { MockEvents } from "./mockEvents";

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
  /** 실행 모드. realtime은 배속이 고정이다(DEC-005). 목 소스는 배속 시연을 위해 기본 lockstep */
  mode: RunMode;
  /** 한 번의 타이머 호출에서 따라잡을 최대 프레임 수 (탭 비활성 후 폭주 방지) */
  maxCatchUp: number;
  scenario?: MockScenarioOptions;
  /** 각본 truth 이벤트·센서 시야를 낸다 */
  events: boolean;
}

const DEFAULTS: MockSourceOptions = { frameHz: 50, rate: 1, autoStart: true, mode: RunMode.LOCKSTEP, maxCatchUp: 25, events: true };

export class MockSource implements DataSource {
  readonly name = "mock";
  readonly gcs = "gcs-01";
  private readonly handlers = new HandlerSet();
  private readonly opts: MockSourceOptions;
  private readonly scenario: MockScenario;
  private params = new MockParams();
  private frame = 0n;
  private state = SimRunState.IDLE;
  private rate: number;
  private mode: RunMode;
  private timer: unknown = null;
  private lastMs = 0;
  private carry = 0; // 다음 호출로 넘기는 프레임 소수부
  private rateActual = 0;
  private readonly events: MockEvents | null;
  /** 마지막으로 발행한 프레임의 sim 시각(s). 이벤트 구간 (prev, now] 계산용 */
  private lastPubS = -1;

  constructor(opts: Partial<MockSourceOptions> = {}, private readonly clock: MockClock = browserClock) {
    this.opts = { ...DEFAULTS, ...opts };
    this.rate = this.opts.rate;
    this.mode = this.opts.mode;
    this.scenario = new MockScenario(this.opts.scenario);
    this.events = this.opts.events ? new MockEvents(this.gcs) : null;
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
    this.publishParams();
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
        if (c.value.mode !== RunMode.UNSPECIFIED) this.mode = c.value.mode;
        this.mode === RunMode.REALTIME ? (this.rate = 1) : c.value.rate > 0 && (this.rate = c.value.rate);
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
        if (this.mode !== RunMode.REALTIME && c.value.rate > 0) this.rate = c.value.rate;
        break;
      case "reset":
        this.halt();
        this.frame = 0n;
        this.state = SimRunState.LOADED;
        this.params = new MockParams();
        this.events?.reset();
        this.lastPubS = -1;
        this.publish();
        this.publishParams();
        break;
      case "setParams": {
        // 다음 프레임 시작에 적용하는 것을 즉시 적용으로 흉내 낸다. 거부는 EntityParams.rejected로 돌려준다
        const v = c.value;
        if (!this.scenario.actors.some((a) => a.id === v.entityId && a.kind === EntityKind.UAV)) return;
        this.params.apply(v.entityId, v.owner, v.values ?? {});
        this.handlers.params(this.params.snapshot(v.entityId, v.owner, this.simTimeUs()));
        return;
      }
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
      mode: this.mode,
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
    if (this.frame % BigInt(this.opts.frameHz) < BigInt(n)) {
      this.handlers.status(this.status());
      this.publishParams();
    }
  }

  private advance(): void {
    this.frame += 1n;
    this.publish();
  }

  /** UAV마다 소유자별 EntityParams. 적재 직후와 1초마다 */
  private publishParams(): void {
    const t = this.simTimeUs();
    for (const a of this.scenario.actors)
      if (a.kind === EntityKind.UAV) for (const o of MOCK_OWNERS) this.handlers.params(this.params.snapshot(a.id, o, t));
  }

  private publish(): void {
    const f = this.scenario.frameAt(this.frame, this.opts.frameHz);
    const nowS = Number(this.simTimeUs()) / 1e6;
    const evs = this.events && nowS > this.lastPubS ? this.events.step(this.lastPubS, nowS, f) : [];
    this.handlers.truth(f);
    for (const e of evs) this.handlers.event(`truth/event/${eventKind(e.event.case)}`, e);
    const act = this.events?.sensor(nowS, f);
    if (act) this.handlers.rx(`swarm/${this.gcs}/rx/ms/SensorActivity`, act);
    this.lastPubS = nowS;
    for (const r of this.scenario.takeReports()) this.reply(r.entityId, r.taskId, r.state, r.progress, r.reason);
  }
}

/** TruthEvent oneof → 키 끝 (docs/10_contracts.md §3.2) */
function eventKind(c: string | undefined): string {
  return c === "jamZone" ? "jam_zone" : (c ?? "unknown");
}
