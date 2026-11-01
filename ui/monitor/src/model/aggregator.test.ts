// TC-MON-004: 엔티티별 집계 (빈도·크기·지연·손실률·사유) (IMP-MON-006)
import { describe, expect, it } from "vitest";
import { DropReason } from "../gen/swarm/v1/link_pb";
import { Aggregator, BUCKET_US, latencyBin, RateWindow, WINDOW_BUCKETS } from "./aggregator";
import { outcome } from "./testutil";

describe("Aggregator", () => {
  it("송신자 tx, 수신자 rx로 나눠 센다", () => {
    const a = new Aggregator();
    a.addOutcome(outcome({ src: "uav-001", dst: "uav-002", size: 80 }));
    a.addOutcome(outcome({ src: "uav-001", dst: "gcs-01", reason: DropReason.JAMMED, size: 80 }));
    a.addOutcome(outcome({ src: "gcs-01", dst: "uav-001", reason: DropReason.NO_LOS }));
    const u1 = a.entity("uav-001");
    expect([u1.tx.total, u1.tx.delivered, u1.tx.dropped, u1.tx.bytes]).toEqual([2, 1, 1, 160]);
    expect(u1.tx.drops[DropReason.JAMMED]).toBe(1);
    expect(u1.rx.total).toBe(1);
    expect(u1.rx.drops[DropReason.NO_LOS]).toBe(1);
    expect(u1.tx.lossRate()).toBeCloseTo(0.5);
    expect(a.entity("uav-002").rx.delivered).toBe(1);
    expect(a.all.total).toBe(3);
    expect(a.pairs.get("uav-001>gcs-01")).toMatchObject({ total: 1, dropped: 1, lastReason: DropReason.JAMMED });
  });

  it("손실 사유 모두를 따로 센다(계약 밖 값은 기타)", () => {
    const a = new Aggregator();
    const rs = [
      DropReason.JAMMED,
      DropReason.NO_LOS,
      DropReason.OUT_OF_RANGE,
      DropReason.BURST_LOSS,
      DropReason.QUEUE_OVERFLOW,
      DropReason.FAULT_INJECTED,
      DropReason.NODE_DEAD,
    ];
    rs.forEach((r, i) => {
      for (let k = 0; k <= i; k++) a.addOutcome(outcome({ reason: r }));
    });
    a.addOutcome(outcome({ reason: 42 as DropReason }));
    const d = a.entity("uav-001").tx.drops;
    rs.forEach((r, i) => expect(d[r]).toBe(i + 1));
    expect(d[DropReason.NONE]).toBe(1);
  });

  it("지연 평균·분위수·최대", () => {
    const a = new Aggregator();
    for (let i = 1; i <= 100; i++) a.addOutcome(outcome({ lat: i * 1000 }));
    const tx = a.entity("uav-001").tx;
    expect(tx.latMeanUs()).toBeCloseTo(50_500);
    expect(tx.latMaxUs).toBe(100_000);
    const p50 = tx.latQuantileUs(0.5);
    const p95 = tx.latQuantileUs(0.95);
    // 버킷 폭 2^(1/4) ≈ 19%
    expect(p50).toBeGreaterThanOrEqual(50_000);
    expect(p50).toBeLessThan(50_000 * 1.2);
    expect(p95).toBeGreaterThanOrEqual(95_000);
    expect(p95).toBeLessThanOrEqual(100_000);
    expect(latencyBin(0)).toBe(0);
    expect(latencyBin(1e12)).toBe(103);
  });

  it("빈도는 시뮬레이션 시각 이동 창(5 s)으로 계산한다", () => {
    const a = new Aggregator();
    // 10 s 동안 초당 50건, 그중 1/5 손실
    for (let i = 0; i < 500; i++) {
      a.addOutcome(outcome({ t: i * 20_000, size: 100, reason: i % 5 === 0 ? DropReason.BURST_LOSS : undefined }));
    }
    const r = a.entity("uav-001").tx.window.rates(10_000_000);
    expect(r.perS).toBeCloseTo(50);
    expect(r.bytesPerS).toBeCloseTo(5000);
    expect(r.dropPerS).toBeCloseTo(10);
    expect(a.entity("uav-001").tx.window.rates(30_000_000).perS).toBe(0);
  });

  it("RateWindow: 진행 중인 버킷은 빼고, 덮인 과거 버킷은 무시한다", () => {
    const w = new RateWindow();
    w.add(0, 10, false);
    w.add(BUCKET_US * (WINDOW_BUCKETS + 1), 10, false);
    w.add(0, 10, false);
    expect(w.rates(BUCKET_US * (WINDOW_BUCKETS + 1)).perS).toBe(0);
    expect(w.rates(BUCKET_US * (WINDOW_BUCKETS + 2)).perS).toBeCloseTo(1 / 5);
  });

  it("메시지 타입별·엔벨로프 수를 센다", () => {
    const a = new Aggregator();
    a.addOutcome(outcome({ msgType: "swarm.v1.TaskStatus" }));
    a.addOutcome(outcome({ msgType: "swarm.v1.TaskStatus", reason: DropReason.QUEUE_OVERFLOW }));
    a.addEnvelope("tx", "uav-001", 1_000_000, 50);
    a.addEnvelope("rx", "uav-001", 2_000_000, 50);
    const e = a.entity("uav-001");
    expect(e.txTypes.get("swarm.v1.TaskStatus")).toMatchObject({ total: 2, dropped: 1 });
    expect(a.entity("gcs-01").rxTypes.get("swarm.v1.TaskStatus")!.total).toBe(2);
    expect([e.envTx, e.envRx]).toEqual([1, 1]);
    expect(a.nowUs).toBe(2_000_000);
    a.clear();
    expect(a.entities.size + a.all.total + a.nowUs).toBe(0);
  });
});
