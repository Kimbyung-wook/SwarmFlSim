// TC-UI-005: 목 시나리오 (IMP-UI-009)
import { describe, expect, it } from "vitest";
import { EntityKind } from "../gen/swarm/v1/entity_pb";
import { toFrameView } from "../model/entityView";
import { DEG, wrapPi } from "../model/attitude";
import { MockScenario } from "./mockScenario";

const ID_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)+$/;
const R = 6378137;

function distM(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const dn = (b.lat - a.lat) * DEG * R;
  const de = (b.lon - a.lon) * DEG * R * Math.cos(a.lat * DEG);
  return { dn, de, d: Math.hypot(dn, de) };
}

describe("MockScenario", () => {
  const sc = new MockScenario();

  it("UAV 20대 이상과 GCS·표적을 포함하고 ID가 규칙을 따른다", () => {
    const f = toFrameView(sc.frameAt(0n, 50));
    const uavs = f.entities.filter((e) => e.kind === EntityKind.UAV);
    expect(uavs.length).toBeGreaterThanOrEqual(20);
    expect(f.entities.some((e) => e.kind === EntityKind.GCS)).toBe(true);
    expect(f.entities.some((e) => e.kind === EntityKind.GROUND_TARGET)).toBe(true);
    for (const e of f.entities) expect(e.id).toMatch(ID_RE);
    expect(new Set(f.entities.map((e) => e.id)).size).toBe(f.entities.length);
  });

  it("헤더 시각은 frame / frameHz", () => {
    const f = sc.frameAt(150n, 50);
    expect(f.header?.frame).toBe(150n);
    expect(f.header?.simTimeUs).toBe(3_000_000n);
  });

  it("결정론적이다", () => {
    expect(sc.frameAt(777n, 50)).toEqual(new MockScenario().frameAt(777n, 50));
  });

  it("1초 동안의 위치 변화가 보고 속도·진행 방향과 맞는다", () => {
    const a = toFrameView(sc.frameAt(500n, 50));
    const b = toFrameView(sc.frameAt(501n, 50));
    for (let i = 0; i < a.entities.length; i++) {
      const ea = a.entities[i], eb = b.entities[i];
      const { dn, de, d } = distM(ea, eb);
      const dt = 0.02;
      if (ea.kind === EntityKind.UAV) {
        expect(d / dt).toBeCloseTo(ea.speed, 0);
        expect(Math.abs(wrapPi(Math.atan2(de, dn) - ea.heading))).toBeLessThan(0.01);
      }
      if (ea.kind === EntityKind.GCS || ea.kind === EntityKind.GROUND_TARGET) expect(d).toBe(0);
    }
  });

  it("선회 UAV의 뱅크각은 협조선회식 tanφ = v·ω/g 를 따른다", () => {
    const dt = 0.02;
    const a = toFrameView(sc.frameAt(1000n, 50)).entities.find((e) => e.id === "uav-001")!;
    const b = toFrameView(sc.frameAt(1001n, 50)).entities.find((e) => e.id === "uav-001")!;
    const omega = wrapPi(b.heading - a.heading) / dt;
    expect(Math.tan(a.euler.roll)).toBeCloseTo((a.speed * omega) / 9.80665, 3);
  });
});
