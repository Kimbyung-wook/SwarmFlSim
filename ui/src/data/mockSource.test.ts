// TC-UI-006: 목 데이터 소스의 sim/ctrl/cmd 처리 (IMP-UI-010)
import { create } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { SimCommandSchema, SimRunState } from "../gen/swarm/v1/sim_pb";
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
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
