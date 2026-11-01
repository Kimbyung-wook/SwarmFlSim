// TC-UI-007: 카메라 시점 구조 (IMP-UI-007)
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { DEG, eulerToQuat, quatToEuler } from "./attitude";
import { cameraPose, offsetLocal } from "./camera";
import type { EntityView } from "./entityView";

function uav(yaw: number, pitch: number, roll: number): EntityView {
  const attitude = eulerToQuat({ yaw, pitch, roll });
  return {
    id: "uav-001", kind: EntityKind.UAV, side: Side.BLUE, alive: true, lat: 36.6, lon: 127.5, alt: 1500,
    vn: 30 * Math.cos(yaw), ve: 30 * Math.sin(yaw), vd: 0, speed: 30, heading: yaw < 0 ? yaw + 2 * Math.PI : yaw,
    attitude, euler: quatToEuler(attitude), energy: 1,
  };
}

describe("camera", () => {
  it("free는 카메라를 건드리지 않는다", () => {
    expect(cameraPose(uav(0, 0, 0), "free")).toBeNull();
  });

  it("1인칭은 기체 위치와 쿼터니언 자세를 그대로 쓴다", () => {
    const p = cameraPose(uav(-30 * DEG, 5 * DEG, 20 * DEG), "fpv")!;
    expect(p.heading).toBeCloseTo(330 * DEG, 9);
    expect(p.pitch).toBeCloseTo(5 * DEG, 9);
    expect(p.roll).toBeCloseTo(20 * DEG, 9);
    expect([p.lat, p.lon, p.alt]).toEqual([36.6, 127.5, 1500]);
  });

  it("추적은 진행 방향 뒤·위에서 내려다본다", () => {
    const p = cameraPose(uav(90 * DEG, 0, 30 * DEG), "chase", { backM: 100, upM: 100 })!;
    expect(p.lon).toBeLessThan(127.5); // 동쪽으로 가므로 카메라는 서쪽
    expect(p.lat).toBeCloseTo(36.6, 9);
    expect(p.alt).toBe(1600);
    expect(p.pitch).toBeCloseTo(-45 * DEG, 9);
    expect(p.roll).toBe(0);
  });

  it("짐벌은 수평 안정화된 pan/tilt", () => {
    const p = cameraPose(uav(0, 10 * DEG, 30 * DEG), "gimbal", undefined, { pan: 90 * DEG, tilt: -20 * DEG })!;
    expect(p.heading).toBeCloseTo(90 * DEG, 9);
    expect(p.pitch).toBeCloseTo(-20 * DEG, 9);
    expect(p.roll).toBe(0);
  });

  it("국지 오프셋: 북쪽 1 km ≈ 위도 0.009°", () => {
    const p = offsetLocal({ lat: 36.6, lon: 127.5, alt: 0 }, 0, 1000, 0, 0);
    expect(p.lat - 36.6).toBeCloseTo(1000 / 6378137 / DEG, 9);
    expect(p.lon).toBeCloseTo(127.5, 12);
  });
});
