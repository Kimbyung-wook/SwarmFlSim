// TC-UI-002: TruthFrame 변환과 protobuf-es 직렬화 (IMP-UI-001, IMP-UI-004)
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { DEG, eulerToQuat } from "./attitude";
import { isAirborneKind, toEntityView, toFrameView } from "./entityView";

function sampleFrame() {
  return create(TruthFrameSchema, {
    header: { simTimeUs: 2_000_000n, frame: 100n, source: "core-0" },
    entities: [
      {
        id: "uav-001", kind: EntityKind.UAV, side: Side.BLUE, alive: true, energyFrac: 0.8,
        kinematics: {
          position: { latDeg: 36.6, lonDeg: 127.5, altM: 1500 },
          velocityNedMps: { x: 0, y: 30, z: -1 },
          attitude: eulerToQuat({ yaw: 90 * DEG, pitch: 2 * DEG, roll: 10 * DEG }),
        },
      },
      {
        id: "gcs-01", kind: EntityKind.GCS, side: Side.BLUE, alive: true,
        kinematics: {
          position: { latDeg: 36.5, lonDeg: 127.4, altM: 80 },
          attitude: eulerToQuat({ yaw: 45 * DEG, pitch: 0, roll: 0 }),
        },
      },
      { id: "tgt-001", kind: EntityKind.GROUND_TARGET, side: Side.RED, alive: false },
    ],
  });
}

describe("entityView", () => {
  it("TruthFrame을 바이너리로 직렬화했다가 되읽어도 같다", () => {
    const f = sampleFrame();
    const back = fromBinary(TruthFrameSchema, toBinary(TruthFrameSchema, f));
    expect(back.header?.frame).toBe(100n);
    expect(back.entities.map((e) => e.id)).toEqual(["uav-001", "gcs-01", "tgt-001"]);
    expect(back.entities[0].kinematics?.velocityNedMps?.y).toBe(30);
  });

  it("움직이는 기체는 속도 방향, 정지체는 자세 yaw를 진행 방향으로 쓴다", () => {
    const v = toFrameView(sampleFrame());
    expect(v.frame).toBe(100n);
    expect(v.simTimeUs).toBe(2_000_000n);
    const [uav, gcs, tgt] = v.entities;
    expect(uav.heading).toBeCloseTo(90 * DEG, 9);
    expect(uav.speed).toBeCloseTo(30, 9);
    expect(uav.alt).toBe(1500);
    expect(uav.euler.roll).toBeCloseTo(10 * DEG, 9);
    expect(uav.energy).toBeCloseTo(0.8, 9);
    expect(gcs.heading).toBeCloseTo(45 * DEG, 9);
    expect(gcs.speed).toBe(0);
    expect(tgt.alive).toBe(false);
  });

  it("자세·위치가 비어 있어도 기본값으로 변환한다", () => {
    const v = toEntityView(create(TruthFrameSchema, { entities: [{ id: "uav-009" }] }).entities[0]);
    expect(v.attitude).toEqual({ w: 1, x: 0, y: 0, z: 0 });
    expect(v.heading).toBe(0);
    expect([v.lat, v.lon, v.alt]).toEqual([0, 0, 0]);
  });

  it("공중 종류 판별", () => {
    expect(isAirborneKind(EntityKind.UAV)).toBe(true);
    expect(isAirborneKind(EntityKind.MISSILE)).toBe(true);
    expect(isAirborneKind(EntityKind.GCS)).toBe(false);
    expect(isAirborneKind(EntityKind.GROUND_TARGET)).toBe(false);
  });
});
