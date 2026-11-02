// TC-MON-008: 시퀀스 타임라인 질의·레인 순서·배치·선택 (IMP-MON-014)
import { describe, expect, it } from "vitest";
import type { LinkOutcome } from "../gen/swarm/v1/link_pb";
import { DropReason } from "../gen/swarm/v1/link_pb";
import { EMPTY_FILTER } from "./filter";
import { Ring } from "./ring";
import { outcome } from "./testutil";
import { hitArrow, laneOrder, layoutTimeline, queryTimeline, snapshotTimeline } from "./timeline";

describe("timeline", () => {
  const ring = new Ring<LinkOutcome>(100);
  for (let i = 0; i < 50; i++) {
    ring.push(outcome({ src: "uav-002", dst: i % 2 ? "gcs-01" : "uav-001", seq: i, t: i * 100_000, reason: i % 10 === 0 ? DropReason.JAMMED : undefined }));
  }

  it("창 안·필터에 맞는 최신 항목을 최대 개수만큼", () => {
    const all = queryTimeline(ring, { filter: EMPTY_FILTER, endUs: 4_900_000, windowUs: 1_000_000, maxItems: 1000 });
    expect(all.map((o) => o.seq)).toEqual([49, 48, 47, 46, 45, 44, 43, 42, 41, 40, 39]);
    const lim = queryTimeline(ring, { filter: EMPTY_FILTER, endUs: 4_900_000, windowUs: 1_000_000, maxItems: 3 });
    expect(lim).toHaveLength(3);
    const dropped = queryTimeline(ring, {
      filter: { ...EMPTY_FILTER, outcomes: new Set([DropReason.JAMMED]) },
      endUs: 4_900_000,
      windowUs: 5_000_000,
      maxItems: 1000,
    });
    expect(dropped.map((o) => o.seq)).toEqual([40, 30, 20, 10, 0]);
  });

  it("정지 사본은 원본이 덮여도 남는다", () => {
    const src = new Ring<LinkOutcome>(10);
    for (let i = 0; i < 10; i++) src.push(outcome({ seq: i, t: i * 1_000_000 }));
    const snap = snapshotTimeline(src, 6_000_000);
    for (let i = 10; i < 20; i++) src.push(outcome({ seq: i, t: i * 1_000_000 }));
    expect(snap.newest(100).map((o) => o.seq)).toEqual([9, 8, 7, 6, 5]);
  });

  it("레인: 고정 → GCS → 사전순", () => {
    const items = [outcome({ src: "uav-003", dst: "uav-001" }), outcome({ src: "gcs-01", dst: "uav-002" })];
    expect(laneOrder(items, ["uav-002", "uav-999"])).toEqual(["uav-002", "gcs-01", "uav-001", "uav-003"]);
    expect(laneOrder(items, [], 2)).toEqual(["gcs-01", "uav-001"]);
  });

  it("배치: 전달은 rx 시각까지 기울고, 손실은 수평에 가깝다. 클릭 판정", () => {
    const items = [
      outcome({ src: "uav-001", dst: "uav-002", t: 500_000, lat: 100_000 }),
      outcome({ src: "uav-002", dst: "uav-001", t: 800_000, reason: DropReason.NO_LOS }),
    ];
    const L = layoutTimeline(items, ["uav-001", "uav-002"], { left: 0, right: 100, top: 0, bottom: 1000 }, 1_000_000, 1_000_000);
    expect(L.laneX).toEqual([0, 100]);
    const [d, x] = L.arrows;
    expect([d.x1, d.y1, d.x2, d.y2, d.dropped]).toEqual([0, 500, 100, 600, false]);
    expect([x.x1, x.x2, x.dropped]).toEqual([100, 0, true]);
    expect(x.y2 - x.y1).toBeLessThan(5);
    expect(hitArrow(L.arrows, 50, 550)?.o.seq).toBe(d.o.seq);
    expect(hitArrow(L.arrows, 50, 802)?.dropped).toBe(true);
    expect(hitArrow(L.arrows, 50, 300)).toBeUndefined();
  });
});
