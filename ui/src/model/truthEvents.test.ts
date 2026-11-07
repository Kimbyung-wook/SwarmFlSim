// TC-UI-046: truth 이벤트 보관소 — 재밍 구역(원·다각형·폐기 예정 zone·끄기), 생성 엔티티 시작·궤적·종료, impact·kill, 보관·되감기 (IMP-UI-060)
import { create } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { TruthEventSchema } from "../gen/swarm/v1/truth_pb";
import type { EntityView, FrameView } from "./entityView";
import { endCauseLabel, isEventEntity, TruthEventStore, zoneShape } from "./truthEvents";

const S = 1_000_000n;
const ev = (tS: number, event: MessageInitShape<typeof TruthEventSchema>["event"]) =>
  create(TruthEventSchema, { header: { simTimeUs: BigInt(tS) * S }, event });

const ent = (id: string, o: Partial<EntityView> = {}): EntityView => ({
  id, kind: EntityKind.UAV, side: Side.BLUE, alive: true, lat: 37, lon: 127, alt: 1000,
  vn: 0, ve: 0, vd: 0, speed: 0, heading: 0, attitude: { w: 1, x: 0, y: 0, z: 0 }, euler: { roll: 0, pitch: 0, yaw: 0 }, energy: 1, ...o,
} as EntityView);
const frame = (tS: number, entities: EntityView[]): FrameView => ({ frame: BigInt(tS), simTimeUs: BigInt(tS) * S, entities });

describe("zoneShape", () => {
  it("area 원·다각형을 읽고, 없으면 폐기 예정 zone(원)을 읽는다", () => {
    const c = zoneShape(
      { shape: { case: "circle", value: { center: { latDeg: 37, lonDeg: 127, altM: 0 }, radiusM: 4000 } }, minAltM: 100, maxAltM: 3000 } as never,
      undefined,
    );
    expect(c).toMatchObject({ shape: { kind: "circle", radiusM: 4000 }, minAltM: 100, maxAltM: 3000 });
    const p = zoneShape(
      { shape: { case: "polygon", value: { vertices: [{ latDeg: 0, lonDeg: 0 }, { latDeg: 1, lonDeg: 0 }, { latDeg: 0, lonDeg: 1 }] } }, minAltM: 0, maxAltM: 0 } as never,
      undefined,
    );
    expect(p?.shape.kind).toBe("polygon");
    expect(zoneShape(undefined, { center: { latDeg: 1, lonDeg: 2, altM: 0 } as never, radiusM: 500 })).toMatchObject({
      shape: { kind: "circle", center: { lat: 1, lon: 2 }, radiusM: 500 }, minAltM: 0, maxAltM: 0,
    });
    // 꼭짓점 3개 미만·반경 0·도형 없음
    expect(zoneShape({ shape: { case: "polygon", value: { vertices: [{ latDeg: 0, lonDeg: 0 }] } }, minAltM: 0, maxAltM: 0 } as never, undefined)).toBeNull();
    expect(zoneShape(undefined, { center: { latDeg: 1, lonDeg: 2, altM: 0 } as never, radiusM: 0 })).toBeNull();
    expect(zoneShape(undefined, undefined)).toBeNull();
  });

  it("발사체 판정: wpn- 접두어 또는 missile/fpv", () => {
    expect(isEventEntity("wpn-uav-001-01", EntityKind.UNSPECIFIED)).toBe(true);
    expect(isEventEntity("x", EntityKind.FPV)).toBe(true);
    expect(isEventEntity("x", EntityKind.MISSILE)).toBe(true);
    expect(isEventEntity("uav-001", EntityKind.UAV)).toBe(false);
    expect(endCauseLabel("impact")).toBe("도달");
    expect(endCauseLabel("gone")).toBe("소멸");
  });
});

describe("TruthEventStore", () => {
  it("재밍 구역: owner별 최신 상태, 진영은 truth/state에서, 도형 없는 끄기는 이전 도형을 꺼짐으로", () => {
    const s = new TruthEventStore();
    s.onFrame(frame(1, [ent("site-01", { kind: EntityKind.JAMMER_SITE, side: Side.RED })]));
    const area = { shape: { case: "circle" as const, value: { center: { latDeg: 37, lonDeg: 127, altM: 0 }, radiusM: 4000 } }, minAltM: 0, maxAltM: 3000 };
    s.onEvent(ev(2, { case: "jamZone", value: { owner: "site-01", active: true, area } }));
    expect(s.jamZones()).toHaveLength(1);
    expect(s.jamZones()[0]).toMatchObject({ owner: "site-01", active: true, side: Side.RED, minAltM: 0, maxAltM: 3000 });
    const v = s.version;
    s.onEvent(ev(3, { case: "jamZone", value: { owner: "site-01", active: false } }));
    expect(s.version).toBeGreaterThan(v);
    expect(s.jamZones()[0]).toMatchObject({ active: false, shape: { kind: "circle", radiusM: 4000 } });
    // 모르는 owner의 도형 없는 이벤트는 무시
    s.onEvent(ev(3, { case: "jamZone", value: { owner: "nobody", active: false } }));
    expect(s.jamZones()).toHaveLength(1);
  });

  it("launch+spawn으로 시작 마커(발사 기체·표적), 프레임으로 궤적, impact로 종료·살상반경", () => {
    const s = new TruthEventStore({ trailIntervalUs: 0n });
    const id = "wpn-uav-001-01";
    s.onFrame(frame(10, [ent("uav-001")]));
    s.onEvent(ev(10, { case: "launch", value: { shooter: "uav-001", weaponEntity: id, targetId: "tgt-001" } }));
    s.onEvent(ev(10, { case: "spawn", value: { entity: { id, kind: EntityKind.MISSILE, side: Side.BLUE, alive: true, kinematics: { position: { latDeg: 37, lonDeg: 127, altM: 1000 } } } } }));
    let tr = s.getTrack(id)!;
    expect(tr.kind).toBe(EntityKind.MISSILE);
    expect(tr.start).toMatchObject({ shooter: "uav-001", target: "tgt-001", timeUs: 10n * S });
    for (let t = 11; t <= 14; t++) s.onFrame(frame(t, [ent("uav-001"), ent(id, { kind: EntityKind.MISSILE, lat: 37 + (t - 10) * 0.01 })]));
    tr = s.getTrack(id)!;
    expect(tr.trail).toHaveLength(4);
    expect(tr.end).toBeNull();
    s.onEvent(ev(15, { case: "impact", value: { weaponEntity: id, position: { latDeg: 37.05, lonDeg: 127, altM: 120 }, lethalRadiusM: 30, killed: ["tgt-001"] } }));
    s.onEvent(ev(15, { case: "kill", value: { entityId: id, cause: "impact" } }));
    tr = s.getTrack(id)!;
    expect(tr.end).toMatchObject({ cause: "impact", radiusM: 30, pos: { lat: 37.05, alt: 120 } });
    expect(s.impacts()).toHaveLength(1);
    expect(s.impacts()[0]).toMatchObject({ weapon: id, radiusM: 30, killed: ["tgt-001"] });
    // 종료 후 프레임은 궤적을 늘리지 않는다
    s.onFrame(frame(16, [ent(id, { kind: EntityKind.MISSILE, alive: false })]));
    expect(s.getTrack(id)!.trail).toHaveLength(4);
    expect(s.getTrack(id)!.end!.cause).toBe("impact");
  });

  it("alive=false는 dead, 프레임에서 사라지면 gone, 뒤이은 kill은 원인만 바꾼다", () => {
    const s = new TruthEventStore();
    s.onFrame(frame(1, [ent("wpn-a-01", { kind: EntityKind.FPV }), ent("wpn-b-01", { kind: EntityKind.MISSILE })]));
    s.onFrame(frame(2, [ent("wpn-a-01", { kind: EntityKind.FPV, alive: false, lat: 38 })]));
    expect(s.getTrack("wpn-a-01")!.end).toMatchObject({ cause: "dead", pos: { lat: 38 } });
    expect(s.getTrack("wpn-b-01")!.end).toMatchObject({ cause: "gone", pos: { lat: 37 } });
    s.onEvent(ev(2, { case: "kill", value: { entityId: "wpn-a-01", cause: "ground" } }));
    expect(s.getTrack("wpn-a-01")!.end).toMatchObject({ cause: "ground", pos: { lat: 38 } });
    // 일반 UAV는 추적하지 않고, kill은 위치 마커로 남긴다
    s.onFrame(frame(3, [ent("uav-005", { lat: 36 })]));
    expect(s.getTrack("uav-005")).toBeUndefined();
    s.onEvent(ev(3, { case: "kill", value: { entityId: "uav-005", cause: "collision" } }));
    expect(s.kills()).toEqual([{ id: "uav-005", pos: { lat: 36, lon: 127, alt: 1000 }, cause: "collision", timeUs: 3n * S }]);
  });

  it("종료된 것은 keepEndedUs 뒤에 지우고, 시각이 거꾸로 가면 모두 지운다", () => {
    const s = new TruthEventStore({ keepEndedUs: 5n * S });
    s.onFrame(frame(1, [ent("wpn-a-01", { kind: EntityKind.FPV }), ent("site-01")]));
    s.onEvent(ev(1, { case: "jamZone", value: { owner: "site-01", active: true, zone: { center: { latDeg: 37, lonDeg: 127, altM: 0 }, radiusM: 100 } } }));
    s.onFrame(frame(2, [ent("site-01")]));
    expect(s.getTrack("wpn-a-01")!.end!.cause).toBe("gone");
    s.onFrame(frame(7, [ent("site-01")]));
    expect(s.getTrack("wpn-a-01")).toBeDefined();
    s.onFrame(frame(8, [ent("site-01")]));
    expect(s.getTrack("wpn-a-01")).toBeUndefined();
    expect(s.jamZones()).toHaveLength(1);
    s.onFrame(frame(0, [ent("site-01")]));
    expect(s.jamZones()).toHaveLength(0);
    // 이벤트 시각이 1 s 넘게 뒤로 가도 새로 시작한다
    s.onFrame(frame(20, [ent("site-01")]));
    s.onEvent(ev(20, { case: "jamZone", value: { owner: "site-01", active: true, zone: { center: { latDeg: 37, lonDeg: 127, altM: 0 }, radiusM: 100 } } }));
    s.onEvent(ev(5, { case: "kill", value: { entityId: "x", cause: "fault" } }));
    expect(s.jamZones()).toHaveLength(0);
  });

  it("궤적 점 간격과 최대 점 수를 지킨다", () => {
    const s = new TruthEventStore({ trailIntervalUs: 2n * S, trailMaxPoints: 3 });
    for (let t = 0; t <= 10; t++) s.onFrame(frame(t, [ent("wpn-a-01", { kind: EntityKind.MISSILE, lat: 37 + t })]));
    const tr = s.getTrack("wpn-a-01")!;
    expect(tr.trail.map((p) => p.lat)).toEqual([43, 45, 47]);
    expect(tr.last!.lat).toBe(47);
  });
});
