// TC-UI-049: 목 truth 이벤트·SensorActivity 각본 — 키·순서, 발사체 truth 포함·alive=false 한 번, rx 경로, 주기 반복 (IMP-UI-063, IMP-UI-062)
import { create, fromBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { SensorActivitySchema } from "../gen/swarm/v1/ms_pb";
import { SimCommandSchema } from "../gen/swarm/v1/sim_pb";
import type { TruthEvent, TruthFrame } from "../gen/swarm/v1/truth_pb";
import { toFrameView } from "../model/entityView";
import { TruthEventStore } from "../model/truthEvents";
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
  advance(ms: number, stepMs = 20) {
    for (let e = 0; e < ms; e += stepMs) {
      this.t += stepMs;
      this.fn?.();
    }
  }
}

function run(seconds: number, events = true) {
  const clock = new FakeClock();
  const src = new MockSource({ frameHz: 50, events }, clock);
  const evs: { key: string; ev: TruthEvent; frameS: number }[] = [];
  const rx: { key: string; env: LinkEnvelope }[] = [];
  const frames: TruthFrame[] = [];
  const store = new TruthEventStore();
  src.subscribe({
    truth: (f) => {
      frames.push(f);
      store.onFrame(toFrameView(f));
    },
    event: (key, ev) => {
      evs.push({ key, ev, frameS: Number(ev.header!.simTimeUs) / 1e6 });
      store.onEvent(ev);
    },
    rx: (key, env) => rx.push({ key, env }),
  });
  return { clock, src, evs, rx, frames, store, go: async () => (await src.connect(), clock.advance(seconds * 1000)) };
}

describe("MockEvents", () => {
  it("60 s 각본: 재밍 구역 켜고 끄기, 미사일 launch·spawn·impact·kill, FPV spawn·kill을 순서대로 낸다", async () => {
    const r = run(61);
    await r.go();
    const seq = r.evs.filter((e) => e.frameS < 60).map((e) => `${e.key}@${Math.round(e.frameS)}`);
    expect(seq).toEqual([
      "truth/event/jam_zone@2",
      "truth/event/jam_zone@5",
      "truth/event/launch@10",
      "truth/event/spawn@10",
      "truth/event/spawn@15",
      "truth/event/impact@22",
      "truth/event/kill@22",
      "truth/event/kill@27",
      "truth/event/jam_zone@40",
      "truth/event/jam_zone@50",
    ]);
    const launch = r.evs.find((e) => e.ev.event.case === "launch")!.ev.event;
    expect(launch.case === "launch" && launch.value).toMatchObject({ shooter: "uav-001", weaponEntity: "wpn-uav-001-01", targetId: "tgt-001" });
    const impact = r.evs.find((e) => e.ev.event.case === "impact")!.ev.event;
    expect(impact.case === "impact" && impact.value.lethalRadiusM).toBe(30);
    // 60 s 직후에는 아직 다음 주기 이벤트(τ ≥ 2 s)가 없다
    expect(r.evs.some((e) => e.frameS >= 60)).toBe(false);
  });

  it("발사체는 비행 중 truth/state에 실리고 종료 프레임에 alive=false를 한 번 낸 뒤 빠진다", async () => {
    const r = run(30);
    await r.go();
    const has = (f: TruthFrame, id: string) => f.entities.find((e) => e.id === id);
    const missileFrames = r.frames.filter((f) => has(f, "wpn-uav-001-01"));
    expect(missileFrames.length).toBeGreaterThan(500);
    expect(has(missileFrames[0], "wpn-uav-001-01")!.kind).toBe(EntityKind.MISSILE);
    const dead = missileFrames.filter((f) => !has(f, "wpn-uav-001-01")!.alive);
    expect(dead).toHaveLength(1);
    expect(dead[0]).toBe(missileFrames[missileFrames.length - 1]);
    expect(has(r.frames.find((f) => has(f, "wpn-uav-002-01"))!, "wpn-uav-002-01")!.kind).toBe(EntityKind.FPV);
    // 보관소에서 보면 미사일은 도달, FPV는 지면 충돌로 끝난다
    expect(r.store.getTrack("wpn-uav-001-01")!.end).toMatchObject({ cause: "impact", radiusM: 30 });
    expect(r.store.getTrack("wpn-uav-002-01")!.end!.cause).toBe("ground");
    expect(r.store.getTrack("wpn-uav-001-01")!.start!.shooter).toBe("uav-001");
    expect(r.store.jamZones().map((z) => z.owner).sort()).toEqual(["site-01", "uav-019"]);
  });

  it("SensorActivity를 GCS rx/ms로 1 s마다 보내고 τ 30–35 s에는 active=false", async () => {
    const r = run(36);
    await r.go();
    const acts = r.rx.filter((x) => x.key === "swarm/gcs-01/rx/ms/SensorActivity");
    expect(acts.length).toBeGreaterThanOrEqual(35);
    expect(acts.length).toBeLessThanOrEqual(38);
    expect(acts[0].env.header!.source).toBe("uav-001");
    const decode = (e: LinkEnvelope) => fromBinary(SensorActivitySchema, e.payload);
    expect(decode(acts[1].env)).toMatchObject({ payloadId: "cam0", active: true, hfovDeg: 40, vfovDeg: 30, maxRangeM: 6000 });
    const b = decode(acts[1].env).boresightNed!;
    expect(Math.hypot(b.x, b.y, b.z)).toBeCloseTo(1, 9);
    expect(b.z).toBeCloseTo(Math.sin((35 * Math.PI) / 180), 9);
    const offAt = acts.filter((a) => !decode(a.env).active).map((a) => Number(a.env.header!.simTimeUs) / 1e6);
    expect(offAt.length).toBeGreaterThan(0);
    expect(offAt.every((t) => t >= 30 && t < 35)).toBe(true);
  });

  it("events=false이면 이벤트·센서를 내지 않고, Reset 뒤에는 각본을 처음부터 다시 낸다", async () => {
    const off = run(25, false);
    await off.go();
    expect(off.evs).toHaveLength(0);
    expect(off.rx.filter((x) => x.key.endsWith("SensorActivity"))).toHaveLength(0);
    expect(off.frames.some((f) => f.entities.some((e) => e.id.startsWith("wpn-")))).toBe(false);

    const r = run(12);
    await r.go();
    const n = r.evs.length;
    expect(n).toBe(4);
    r.src.send(create(SimCommandSchema, { issuer: "t", cmd: { case: "reset", value: {} } }));
    r.src.send(create(SimCommandSchema, { issuer: "t", cmd: { case: "start", value: { rate: 1 } } }));
    r.clock.advance(12_000);
    expect(r.evs.slice(n).map((e) => e.key)).toEqual(r.evs.slice(0, n).map((e) => e.key));
  });
});
