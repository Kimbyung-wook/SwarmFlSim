// TC-UI-047: 센서 시야 — 카메라 축, FOV 사각뿔·지면 풋프린트, SensorActivity 수신·만료·꺼짐 (IMP-UI-061)
import { create, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { SensorActivitySchema } from "../gen/swarm/v1/ms_pb";
import type { SensorView } from "./sensorFov";
import { cameraAxes, fovGeometry, offsetNed, SensorStore } from "./sensorFov";

const R = 6378137, D = Math.PI / 180;
/** 두 지점의 국지 NED 차 (m) */
const ned = (a: { lat: number; lon: number; alt: number }, b: { lat: number; lon: number; alt: number }) => [
  (b.lat - a.lat) * D * R,
  (b.lon - a.lon) * D * R * Math.cos(a.lat * D),
  a.alt - b.alt,
];
const sv = (o: Partial<SensorView>): SensorView => ({
  platform: "uav-001", payloadId: "cam0", active: true, boresight: [0, 0, 1], hfovDeg: 40, vfovDeg: 30, maxRangeM: 6000, timeUs: 0n, ...o,
});
const P = { lat: 37, lon: 127, alt: 1000 };

describe("cameraAxes", () => {
  it("전방·오른쪽·아래가 직교 단위이고 오른쪽은 수평이다", () => {
    for (const b of [[1, 0, 0], [0.6, 0.3, 0.7], [0, 0, 1], [0, -1, -0.2]] as [number, number, number][]) {
      const a = cameraAxes(b)!;
      const dot = (x: number[], y: number[]) => x[0] * y[0] + x[1] * y[1] + x[2] * y[2];
      expect(dot(a.f, a.r)).toBeCloseTo(0, 9);
      expect(dot(a.f, a.d)).toBeCloseTo(0, 9);
      expect(dot(a.r, a.d)).toBeCloseTo(0, 9);
      expect(Math.hypot(...a.r)).toBeCloseTo(1, 9);
      expect(a.r[2]).toBeCloseTo(0, 9);
    }
    // 북쪽을 보면 오른쪽은 동쪽, 아래는 아래
    const n = cameraAxes([1, 0, 0])!;
    expect(n.r[1]).toBeCloseTo(1, 9);
    expect(n.d[2]).toBeCloseTo(1, 9);
    // 수직 아래면 오른쪽 = 동쪽
    expect(cameraAxes([0, 0, 1])!.r[1]).toBeCloseTo(1, 9);
    expect(cameraAxes([0, 0, 0])).toBeNull();
  });

  it("offsetNed는 평면 근사로 m를 도로 바꾼다", () => {
    const q = offsetNed(P, 1000, -500, 200);
    const [n, e, d] = ned(P, q);
    expect(n).toBeCloseTo(1000, 3);
    expect(e).toBeCloseTo(-500, 3);
    expect(d).toBeCloseTo(200, 6);
  });
});

describe("fovGeometry", () => {
  it("수직 아래: 풋프린트가 높이×tan(fov/2)인 사각형이고 지면에 닿는다", () => {
    const g = fovGeometry(P, sv({}), 0)!;
    expect(g.onGround).toBe(true);
    expect(g.outline).toHaveLength(33);
    expect(g.outline[0]).toEqual(g.outline[32]);
    const hx = 1000 * Math.tan(20 * D), hy = 1000 * Math.tan(15 * D);
    for (const c of g.corners) {
      const [n, e] = ned(P, c);
      expect(c.alt).toBeCloseTo(0, 6);
      expect(Math.abs(e)).toBeCloseTo(hx, 3);
      expect(Math.abs(n)).toBeCloseTo(hy, 3);
    }
    // 오른쪽(동쪽) 모서리가 앞 두 개
    expect(ned(P, g.corners[0])[1]).toBeGreaterThan(0);
    expect(ned(P, g.corners[2])[1]).toBeLessThan(0);
    const [cn, ce] = ned(P, g.center);
    expect(Math.hypot(cn, ce)).toBeCloseTo(0, 3);
  });

  it("지면 고도를 빼고, 거리 제한을 넘거나 수평이면 지면에 닿지 않는다", () => {
    const g = fovGeometry(P, sv({}), 500)!;
    expect(g.corners[0].alt).toBeCloseTo(500, 6);
    expect(Math.abs(ned(P, g.corners[0])[1])).toBeCloseTo(500 * Math.tan(20 * D), 3);

    const far = fovGeometry(P, sv({ maxRangeM: 800 }), 0)!;
    expect(far.onGround).toBe(false);

    const level = fovGeometry(P, sv({ boresight: [1, 0, 0] }), 0)!;
    expect(level.onGround).toBe(false);
    const [n, e, d] = ned(P, level.center);
    expect(n).toBeCloseTo(6000, 1);
    expect(e).toBeCloseTo(0, 3);
    expect(d).toBeCloseTo(0, 6);
    // 아래쪽 모서리(오른쪽 아래)는 시야 아래로 기운다
    expect(ned(P, level.corners[1])[2]).toBeGreaterThan(0);

    expect(fovGeometry(P, sv({ maxRangeM: 0 }))).toBeNull();
    expect(fovGeometry(P, sv({ boresight: [0, 0, 0] }))).toBeNull();
  });
});

describe("SensorStore", () => {
  const env = (tS: number, active = true, msgType: string = SensorActivitySchema.typeName) =>
    create(LinkEnvelopeSchema, {
      header: { simTimeUs: BigInt(tS) * 1_000_000n, source: "uav-003" },
      msgType,
      payload: toBinary(SensorActivitySchema, create(SensorActivitySchema, {
        payloadId: "cam0", active, boresightNed: { x: 0, y: 0, z: 1 }, hfovDeg: 30, vfovDeg: 20, maxRangeM: 5000,
      })),
      rxTimeUs: BigInt(tS) * 1_000_000n,
    });

  it("rx의 SensorActivity만 받고, 송신 기체·장비별 최신값을 둔다", () => {
    const s = new SensorStore();
    expect(s.onRx("swarm/gcs-01/rx/c2/TaskStatus", env(1, true, "swarm.v1.TaskStatus"))).toBe(false);
    expect(s.onRx("swarm/gcs-01/rx/ms/SensorActivity", env(1))).toBe(true);
    expect(s.onRx("swarm/gcs-01/rx/ms/SensorActivity", env(2))).toBe(true);
    expect(s.list()).toHaveLength(1);
    expect(s.list()[0]).toMatchObject({ platform: "uav-003", payloadId: "cam0", boresight: [0, 0, 1], hfovDeg: 30, maxRangeM: 5000, timeUs: 2_000_000n });
    expect(s.active()).toHaveLength(1);
    s.onRx("swarm/gcs-01/rx/ms/SensorActivity", env(3, false));
    expect(s.list()).toHaveLength(1);
    expect(s.active()).toHaveLength(0);
  });

  it("staleUs 넘게 소식이 없으면 지우고, 시각이 거꾸로 가면 비운다", () => {
    const s = new SensorStore({ staleUs: 2_000_000n });
    s.onRx("k", env(1));
    s.tick(3_000_000n);
    expect(s.list()).toHaveLength(1);
    s.tick(3_000_001n);
    expect(s.list()).toHaveLength(0);
    s.onRx("k", env(10));
    s.tick(10_000_000n);
    const v = s.version;
    s.tick(1_000_000n);
    expect(s.list()).toHaveLength(0);
    expect(s.version).toBeGreaterThan(v);
  });
});
