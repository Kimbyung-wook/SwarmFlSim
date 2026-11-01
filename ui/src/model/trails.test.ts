// TC-UI-003: 궤적 꼬리 (IMP-UI-005)
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import type { EntityView, FrameView } from "./entityView";
import { TrailStore } from "./trails";

function ent(id: string, lat: number, alive = true): EntityView {
  return {
    id, kind: EntityKind.UAV, side: Side.BLUE, alive, lat, lon: 127, alt: 1000,
    vn: 0, ve: 0, vd: 0, speed: 0, heading: 0,
    attitude: { w: 1, x: 0, y: 0, z: 0 }, euler: { yaw: 0, pitch: 0, roll: 0 }, energy: 1,
  };
}

const frame = (us: number, entities: EntityView[]): FrameView => ({ frame: BigInt(us), simTimeUs: BigInt(us), entities });

describe("TrailStore", () => {
  it("간격마다 한 점씩 남기고 최대 개수를 넘으면 오래된 점을 버린다", () => {
    const t = new TrailStore({ maxPoints: 3, intervalUs: 100n });
    for (let us = 0; us <= 1000; us += 50) t.update(frame(us, [ent("uav-001", us)]));
    const pts = t.get("uav-001");
    expect(pts.map((p) => p.lat)).toEqual([800, 900, 1000]);
  });

  it("사라진 엔티티의 궤적을 지우고, 죽은 엔티티는 더 늘리지 않는다", () => {
    const t = new TrailStore({ maxPoints: 10, intervalUs: 1n });
    t.update(frame(0, [ent("uav-001", 0), ent("uav-002", 0)]));
    t.update(frame(10, [ent("uav-001", 1, false)]));
    expect(t.get("uav-001")).toHaveLength(1);
    expect(t.get("uav-002")).toHaveLength(0);
    expect([...t.ids()]).toEqual(["uav-001"]);
  });

  it("시각이 거꾸로 가면 궤적을 새로 시작한다", () => {
    const t = new TrailStore({ maxPoints: 10, intervalUs: 1n });
    t.update(frame(100, [ent("uav-001", 1)]));
    t.update(frame(200, [ent("uav-001", 2)]));
    t.update(frame(0, [ent("uav-001", 3)]));
    expect(t.get("uav-001").map((p) => p.lat)).toEqual([3]);
  });
});
