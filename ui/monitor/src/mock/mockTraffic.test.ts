// TC-MON-007: 목 트래픽(프레임 형식, 결정론, 손실 사유 분포, rx 엔벨로프) (IMP-MON-011)
import { describe, expect, it } from "vitest";
import type { BusFrame } from "../bridge/frame";
import { DropReason } from "../gen/swarm/v1/link_pb";
import { decodeBusFrame } from "../model/decode";
import { MonitorStore } from "../model/store";
import { MockTraffic } from "./mockTraffic";

function run(seconds: number, opts = {}) {
  const frames: BusFrame[] = [];
  const g = new MockTraffic((f) => frames.push(f), { wire: true, ...opts });
  for (let i = 0; i < seconds * g.frameHz; i++) g.stepFrame();
  return { g, frames };
}

describe("MockTraffic", () => {
  it("모든 프레임이 계약의 키·인코딩으로 해석된다", () => {
    const { frames } = run(3);
    const kinds = new Map<string, number>();
    for (const f of frames) {
      const ev = decodeBusFrame(f);
      expect(ev.kind, f.key).not.toBe("ignored");
      kinds.set(ev.kind, (kinds.get(ev.kind) ?? 0) + 1);
    }
    for (const k of ["outcome", "envelope", "truth", "status", "linkState"]) expect(kinds.get(k)).toBeGreaterThan(0);
  });

  it("시드가 같으면 같은 프레임열", () => {
    const a = run(2, { seed: 7 }).frames;
    const b = run(2, { seed: 7 }).frames;
    const c = run(2, { seed: 8 }).frames;
    const sig = (fs: BusFrame[]) => fs.map((f) => `${f.key}:${f.payload.join(",")}`).join("|");
    expect(sig(a)).toBe(sig(b));
    expect(sig(a)).not.toBe(sig(c));
  });

  it("95 s 동안 손실 사유가 모두 나오고, 전달 수 = rx 엔벨로프 수", { timeout: 60_000 }, () => {
    const store = new MonitorStore({ noTiming: true });
    const g = new MockTraffic((f) => store.handleFrame(f), { wire: true });
    for (let i = 0; i < 95 * g.frameHz; i++) g.stepFrame();
    const d = store.agg.all.drops;
    for (const r of [
      DropReason.JAMMED,
      DropReason.NO_LOS,
      DropReason.OUT_OF_RANGE,
      DropReason.BURST_LOSS,
      DropReason.QUEUE_OVERFLOW,
      DropReason.FAULT_INJECTED,
      DropReason.NODE_DEAD,
    ]) {
      expect(d[r], DropReason[r]).toBeGreaterThan(0);
    }
    expect(store.agg.all.delivered).toBe(g.counts.rx);
    expect(store.agg.all.total).toBe(g.counts.outcome);
    // 고장 주입 대상은 FAULT_INJECTED, 파괴된 기체는 NODE_DEAD
    expect(store.agg.entity("uav-007").tx.drops[DropReason.FAULT_INJECTED]).toBeGreaterThan(0);
    expect(store.agg.entity("uav-020").rx.drops[DropReason.NODE_DEAD]).toBeGreaterThan(0);
    expect(store.entities.get("uav-020")!.alive).toBe(false);
  });

  it("rx 엔벨로프에 rx_time_us가 실리고 지연이 양수다", () => {
    const { frames } = run(1);
    const rx = frames.map(decodeBusFrame).find((e) => e.kind === "envelope" && e.dir === "rx");
    expect(rx && rx.kind === "envelope").toBe(true);
    if (rx?.kind !== "envelope") return;
    expect(rx.env.rxTimeUs).toBeGreaterThan(rx.env.header!.simTimeUs);
  });

  it("브로드캐스트 1건은 수신자마다 outcome 하나", () => {
    const { g, frames } = run(1, { uavs: 4 });
    const comm = g.nodes.filter((n) => n.comm).length;
    const first = frames.map(decodeBusFrame).find((e) => e.kind === "envelope" && e.dir === "tx" && e.env.dst.length === 0);
    if (first?.kind !== "envelope") throw new Error("브로드캐스트 없음");
    const src = first.env.header!.source;
    const seq = first.env.header!.seq;
    const n = frames
      .map(decodeBusFrame)
      .filter((e) => e.kind === "outcome" && e.outcome.src === src && e.outcome.seq === seq && e.outcome.msgType === first.env.msgType).length;
    expect(n).toBe(comm - 1);
  });
});

// TC-MON-013: 목 브로드캐스트 수신 대상은 같은 편 무전기 엔티티 전원 (IMP-MON-025, DEC-032)
describe("MockTraffic 브로드캐스트 (DEC-032)", () => {
  it("PeerStatus 1건마다 송신자를 뺀 같은 편 무전기 수만큼 outcome", () => {
    const store = new MonitorStore({ noTiming: true });
    const g = new MockTraffic((f) => store.handleFrame(f), { wire: true, uavs: 4, seed: 3 });
    for (let i = 0; i < 2 * g.frameHz; i++) g.stepFrame();
    const peer = store.timeline.newest(1e6, (o) => o.msgType === "swarm.v1.PeerStatus");
    const bySeq = new Map<string, Set<string>>();
    for (const o of peer) {
      const k = `${o.src}#${o.seq}`;
      if (!bySeq.has(k)) bySeq.set(k, new Set());
      bySeq.get(k)!.add(o.dst);
    }
    expect(bySeq.size).toBeGreaterThan(0);
    // 무전기: gcs-01 + uav 4대, 모두 BLUE. 적 엔티티는 수신 대상이 아니다
    for (const [k, dsts] of bySeq) {
      expect(dsts.size, k).toBe(4);
      for (const d of dsts) expect(d.startsWith("uav-") || d === "gcs-01", d).toBe(true);
    }
  });
});
