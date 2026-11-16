// TC-UI-006: 목 데이터 소스의 sim/ctrl/cmd 처리 (IMP-UI-010)
import { create } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { SimCommandSchema, SimRunState } from "../gen/swarm/v1/sim_pb";
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import { NavigationReportSchema } from "../gen/swarm/v1/vi_pb";
import { ActivityStore } from "../model/activity";
import { C2Commander } from "../model/commands";
import { distanceBearing } from "../model/racetrack";
import { GUIDE_DEFAULT_RADIUS_M } from "./mockGuidance";
import type { MockClock } from "./mockSource";
import { MockSource } from "./mockSource";

class FakeClock implements MockClock {
  t = 0;
  private fn: (() => void) | null = null;
  now = () => this.t;
  setInterval(fn: () => void) {
    this.fn = fn;
    return 1;
  }
  clearInterval() {
    this.fn = null;
  }
  get running() {
    return this.fn !== null;
  }
  advance(ms: number, stepMs = 20) {
    for (let e = 0; e < ms; e += stepMs) {
      this.t += stepMs;
      this.fn?.();
    }
  }
}

const cmd = (c: MessageInitShape<typeof SimCommandSchema>["cmd"]) => create(SimCommandSchema, { issuer: "ui-test", cmd: c });

function setup(autoStart = true) {
  const clock = new FakeClock();
  const src = new MockSource({ frameHz: 50, autoStart }, clock);
  const frames: TruthFrame[] = [];
  const statuses: SimStatus[] = [];
  src.subscribe({ truth: (f) => frames.push(f), status: (s) => statuses.push(s) });
  const last = () => frames[frames.length - 1].header!.frame;
  return { clock, src, frames, statuses, last };
}

describe("MockSource", () => {
  it("연결하면 0번 프레임을 발행하고 실시간으로 진행한다", async () => {
    const { clock, src, frames, last } = setup();
    await src.connect();
    expect(frames[0].header?.frame).toBe(0n);
    expect(frames[0].entities.length).toBe(src.entityCount);
    clock.advance(1000);
    expect(last()).toBe(50n);
    expect(src.status().state).toBe(SimRunState.RUNNING);
  });

  it("배속을 바꾸면 같은 실제 시간에 더 많은 프레임이 지난다", async () => {
    const { clock, src, last } = setup();
    await src.connect();
    src.send(cmd({ case: "setRate", value: { rate: 4 } }));
    clock.advance(1000);
    expect(last()).toBe(200n);
    expect(src.status().rateTarget).toBe(4);
  });

  it("일시정지 중에는 진행하지 않고, 스텝은 지정 프레임만큼 진행한다", async () => {
    const { clock, src, last, statuses } = setup();
    await src.connect();
    clock.advance(200);
    src.send(cmd({ case: "pause", value: {} }));
    expect(statuses[statuses.length - 1].state).toBe(SimRunState.PAUSED);
    const at = last();
    clock.advance(1000);
    expect(last()).toBe(at);
    src.send(cmd({ case: "step", value: { frames: 3 } }));
    expect(last()).toBe(at + 3n);
    src.send(cmd({ case: "resume", value: {} }));
    clock.advance(200);
    expect(last()).toBe(at + 3n + 10n);
  });

  it("리셋하면 0번 프레임으로 돌아가 LOADED가 된다", async () => {
    const { clock, src, last } = setup();
    await src.connect();
    clock.advance(500);
    src.send(cmd({ case: "reset", value: {} }));
    expect(last()).toBe(0n);
    expect(src.status().state).toBe(SimRunState.LOADED);
    expect(clock.running).toBe(false);
    src.send(cmd({ case: "start", value: { rate: 1 } }));
    clock.advance(100);
    expect(last()).toBe(5n);
  });

  it("autoStart가 꺼져 있으면 LOADED에서 기다린다", async () => {
    const { clock, src, last } = setup(false);
    await src.connect();
    clock.advance(1000);
    expect(last()).toBe(0n);
    expect(src.status().state).toBe(SimRunState.LOADED);
  });

  it("한 번에 따라잡는 프레임 수를 제한한다", async () => {
    const { clock, src, last } = setup();
    await src.connect();
    clock.advance(10_000, 10_000);
    expect(last()).toBe(25n);
  });
});

// TC-UI-072: 목 소스가 Agent 런타임처럼 NavigationReport(1 Hz)를 내고, 보낸 C2 봉투를 tx로 되돌린다.
// RTB 귀환점은 기체 시작 위치(첫 보고)로 행동 표시와 같다 (IMP-UI-082)
describe("MockSource 행동 표시 입력 (TC-UI-072)", () => {
  it("UAV마다 모의 1초에 한 번 NavigationReport, C2 송신은 tx로 되돌린다", async () => {
    const clock = new FakeClock();
    const src = new MockSource({ frameHz: 50, events: false }, clock);
    const nav: string[] = [];
    const tx: string[] = [];
    src.subscribe({
      rx: (k, env) => {
        if (env.msgType === NavigationReportSchema.typeName) nav.push(`${k}|${env.header?.source}`);
      },
      tx: (k, env) => tx.push(`${k}|${env.msgType}`),
    });
    await src.connect();
    const uavs = new Set(nav.map((n) => n.split("|")[1]));
    expect(uavs.size).toBe(24);
    expect(nav[0].startsWith("swarm/gcs-01/rx/vi/NavigationReport|")).toBe(true);
    nav.length = 0;
    clock.advance(2000);
    expect(nav.length).toBe(48);

    const out = new C2Commander("gcs-01", "ui-x").task("returnToBase", ["uav-001"]);
    src.sendC2(out);
    expect(tx).toEqual(["swarm/gcs-01/tx/c2/TaskCommand|swarm.v1.TaskCommand"]);
  });

  it("목 소스 RTB는 첫 보고 위치로 돌아간다", async () => {
    const clock = new FakeClock();
    const src = new MockSource({ frameHz: 50, events: false }, clock);
    const store = new ActivityStore();
    src.subscribe({ rx: (k, e) => store.onRx(k, e, clock.t), tx: (k, e) => store.onTx(k, e), status: (s) => store.onSimStatus(s.simTimeUs, 1, clock.t) });
    let last: TruthFrame | null = null;
    src.subscribe({ truth: (f) => (last = f) });
    await src.connect();
    clock.advance(300_000, 200); // 시작점에서 멀어진 뒤 (5초면 이미 귀환점 안이라 곧바로 COMPLETED)
    src.sendC2(new C2Commander("gcs-01", "ui-x").task("returnToBase", ["uav-001"]));
    clock.advance(1000);
    const home = store.shapeOf("uav-001")?.lead ?? null;
    clock.advance(600_000, 200);
    const p = (last as TruthFrame | null)!.entities.find((e) => e.id === "uav-001")!.kinematics!.position!;
    expect(home).not.toBeNull();
    // 귀환점 둘레를 선회한다 (선회 반경 + 여유)
    expect(distanceBearing(home!, p).distM).toBeLessThan(GUIDE_DEFAULT_RADIUS_M + 400);
  });

  it("중심 없는 Hold는 여러 대여도 각자 그린 선회원(기본 반경) 위를 돈다", async () => {
    const clock = new FakeClock();
    const src = new MockSource({ frameHz: 50, events: false }, clock);
    const store = new ActivityStore();
    let last: TruthFrame | null = null;
    src.subscribe({ truth: (f) => (last = f), rx: (k, e) => store.onRx(k, e, clock.t), tx: (k, e) => store.onTx(k, e), status: (s) => store.onSimStatus(s.simTimeUs, 1, clock.t) });
    await src.connect();
    clock.advance(13_000);
    const ids = ["uav-001", "uav-002", "uav-003", "uav-004"];
    src.sendC2(new C2Commander("gcs-01", "ui-x").task("hold", ids));
    clock.advance(90_000, 100);
    for (const id of ids) {
      const c = store.shapeOf(id)!.circles[0];
      expect(c.radiusM).toBe(GUIDE_DEFAULT_RADIUS_M);
      const p = (last as TruthFrame | null)!.entities.find((e) => e.id === id)!.kinematics!.position!;
      expect(Math.abs(distanceBearing(c.center, p).distM - c.radiusM)).toBeLessThan(60);
    }
  });
});
