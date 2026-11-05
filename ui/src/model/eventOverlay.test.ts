// TC-UI-048: 이벤트 전시 명세 — 구역 색·투명도·라벨·상한 없음, 궤적 색·회색 처리, 생성·종료 마커, 살상반경 원, FOV 선 (IMP-UI-064)
import { create } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { TruthEventSchema } from "../gen/swarm/v1/truth_pb";
import type { EntityView, FrameView } from "./entityView";
import { ENDED_COLOR, eventOverlay, FOV_COLOR, IMPACT_COLOR, sensorDraws, trackDraws, ZONE_OPEN_TOP_M, zoneDraws } from "./eventOverlay";
import type { SensorView } from "./sensorFov";
import { sideColor } from "./symbology";
import { TruthEventStore } from "./truthEvents";

const S = 1_000_000n;
const ev = (tS: number, event: MessageInitShape<typeof TruthEventSchema>["event"]) =>
  create(TruthEventSchema, { header: { simTimeUs: BigInt(tS) * S }, event });
const ent = (id: string, o: Partial<EntityView> = {}): EntityView => ({
  id, kind: EntityKind.UAV, side: Side.BLUE, alive: true, lat: 37, lon: 127, alt: 1000,
  vn: 0, ve: 0, vd: 0, speed: 0, heading: 0, attitude: { w: 1, x: 0, y: 0, z: 0 }, euler: { roll: 0, pitch: 0, yaw: 0 }, energy: 1, ...o,
} as EntityView);
const frame = (tS: number, entities: EntityView[]): FrameView => ({ frame: BigInt(tS), simTimeUs: BigInt(tS) * S, entities });
const circle = { center: { latDeg: 37, lonDeg: 127, altM: 0 }, radiusM: 1000 };

describe("eventOverlay", () => {
  it("재밍 구역: 켜짐은 진영색, 꺼짐은 회색·옅게, 상한 없으면 ZONE_OPEN_TOP_M까지", () => {
    const s = new TruthEventStore();
    s.onFrame(frame(1, [ent("site-01", { side: Side.RED }), ent("uav-019")]));
    s.onEvent(ev(1, { case: "jamZone", value: { owner: "site-01", active: true, area: { shape: { case: "circle", value: circle }, minAltM: 0, maxAltM: 3000 } } }));
    s.onEvent(ev(1, { case: "jamZone", value: { owner: "uav-019", active: true, area: { shape: { case: "circle", value: circle }, minAltM: 500, maxAltM: 0 } } }));
    s.onEvent(ev(1, { case: "jamZone", value: { owner: "x-9", active: true, area: { shape: { case: "circle", value: circle }, minAltM: 0, maxAltM: 100 } } }));
    const z = Object.fromEntries(zoneDraws(s).map((d) => [d.key, d]));
    expect(z["zone/site-01"]).toMatchObject({ color: sideColor(Side.RED), bottomM: 0, topM: 3000, fillAlpha: 0.18, label: "재밍 site-01 · 0~3000 m" });
    expect(z["zone/uav-019"]).toMatchObject({ color: sideColor(Side.BLUE), bottomM: 500, topM: 500 + ZONE_OPEN_TOP_M, label: "재밍 uav-019 · 500 m~상한 없음" });
    expect(z["zone/x-9"].color).toBe("#f97316");
    s.onEvent(ev(2, { case: "jamZone", value: { owner: "site-01", active: false } }));
    const off = zoneDraws(s).find((d) => d.key === "zone/site-01")!;
    expect(off).toMatchObject({ color: ENDED_COLOR, fillAlpha: 0.05, label: "재밍 site-01 (꺼짐) · 0~3000 m" });
  });

  it("생성 엔티티: 비행 중 색·생성 라벨, 종료 후 회색 궤적과 종료 마커, 살상반경 원", () => {
    const s = new TruthEventStore({ trailIntervalUs: 0n });
    const m = "wpn-uav-001-01", f = "wpn-uav-002-01";
    s.onFrame(frame(1, [ent("uav-001"), ent("uav-002")]));
    s.onEvent(ev(1, { case: "launch", value: { shooter: "uav-001", weaponEntity: m, targetId: "tgt-001" } }));
    for (let t = 1; t <= 3; t++)
      s.onFrame(frame(t, [ent("uav-001"), ent("uav-002"), ent(m, { kind: EntityKind.MISSILE, lat: 37 + t * 0.01 }), ent(f, { kind: EntityKind.FPV, lon: 127 + t * 0.01 })]));
    let d = trackDraws(s.entityTracks());
    expect(d.lines.map((l) => l.color).sort()).toEqual(["#e879f9", "#fb923c"]);
    expect(d.points.find((p) => p.label?.startsWith(m))!.label).toBe(`${m} 발사 uav-001→tgt-001`);
    expect(d.points.find((p) => p.label?.startsWith(f))!.label).toBe(`${f} 생성`);

    s.onEvent(ev(4, { case: "impact", value: { weaponEntity: m, position: { latDeg: 37.04, lonDeg: 127, altM: 120 }, lethalRadiusM: 30, killed: ["tgt-001"] } }));
    s.onFrame(frame(4, [ent("uav-001"), ent("uav-002"), ent(f, { kind: EntityKind.FPV, alive: false })]));
    s.onEvent(ev(4, { case: "kill", value: { entityId: f, cause: "ground" } }));
    const o = eventOverlay(s, [], () => undefined);
    expect(o.lines.every((l) => l.color === ENDED_COLOR)).toBe(true);
    const missileLine = o.lines.find((l) => l.positions[l.positions.length - 1].lat === 37.04)!;
    expect(missileLine.positions).toHaveLength(4); // 궤적 3점 + 종료 위치
    const labels = o.points.map((p) => p.label).filter(Boolean);
    expect(labels).toEqual(expect.arrayContaining([`${m} · 명중`, `${f} · 지면 충돌`]));
    // 종료 후 생성 마커는 라벨 없이 남는다
    expect(o.points.filter((p) => p.color === "#ffffff").every((p) => !p.label)).toBe(true);
    expect(o.rings).toEqual([{ key: `impact/${m}/${4n * S}`, center: { lat: 37.04, lon: 127, alt: 120 }, radiusM: 30, color: IMPACT_COLOR, label: `${m} 살상반경 30 m · 파괴 tgt-001` }]);
  });

  it("kill 마커(추적 대상 아님)와 반경 0 impact는 원을 그리지 않는다", () => {
    const s = new TruthEventStore();
    s.onFrame(frame(1, [ent("uav-005")]));
    s.onEvent(ev(1, { case: "kill", value: { entityId: "uav-005", cause: "collision" } }));
    s.onEvent(ev(1, { case: "impact", value: { weaponEntity: "wpn-z-01", position: { latDeg: 37, lonDeg: 127, altM: 0 }, lethalRadiusM: 0 } }));
    const o = eventOverlay(s, [], () => undefined);
    expect(o.rings).toHaveLength(0);
    expect(o.points.find((p) => p.label === "uav-005 · 충돌")).toMatchObject({ color: ENDED_COLOR, outline: IMPACT_COLOR });
  });

  it("FOV: 켜진 센서만, 기체 위치가 있을 때 모서리 4선 + 외곽선, 지면이면 굵게", () => {
    const sv = (o: Partial<SensorView>): SensorView => ({
      platform: "uav-001", payloadId: "cam0", active: true, boresight: [0, 0, 1], hfovDeg: 40, vfovDeg: 30, maxRangeM: 6000, timeUs: 0n, ...o,
    });
    const pos = (id: string) => (id === "uav-001" ? { lat: 37, lon: 127, alt: 1000 } : undefined);
    const r = sensorDraws([sv({}), sv({ active: false }), sv({ platform: "uav-404" })], pos);
    expect(r.geoms).toHaveLength(1);
    expect(r.lines).toHaveLength(5);
    expect(r.lines.every((l) => l.color === FOV_COLOR)).toBe(true);
    expect(r.lines[4].width).toBe(2.5);
    expect(sensorDraws([sv({ boresight: [1, 0, 0] })], pos).lines[4].width).toBe(1.5);
    // 지면 고도 함수가 기체 위치로 불린다
    const calls: number[] = [];
    sensorDraws([sv({})], pos, (p) => (calls.push(p.alt), 900));
    expect(calls).toEqual([1000]);
  });
});
