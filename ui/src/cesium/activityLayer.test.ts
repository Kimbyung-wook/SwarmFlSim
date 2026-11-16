// TC-UI-070: 행동 도형 전시 — 같은 내용이면 Entity를 그대로 두고, 대시선 시작점은 매 프레임 기체 위치를 따른다.
// 100대에서도 재동기화가 Entity를 새로 만들지 않는다 (IMP-UI-081)
import { Cartographic, Entity, JulianDate } from "cesium";
import type { Cartesian3, Viewer } from "cesium";
import { describe, expect, it } from "vitest";
import type { GeoPoint } from "../model/commands";
import type { ActivityShape } from "../model/activity";
import { ActivityLayer } from "./activityLayer";

function fakeViewer() {
  const live: Entity[] = [];
  let adds = 0;
  let removes = 0;
  const viewer = {
    scene: { requestRender: () => {} },
    entities: {
      add: (o: Entity.ConstructorOptions) => {
        adds++;
        const e = new Entity(o);
        live.push(e);
        return e;
      },
      remove: (e: Entity) => {
        const i = live.indexOf(e);
        if (i >= 0) {
          live.splice(i, 1);
          removes++;
        }
        return i >= 0;
      },
    },
  };
  return { viewer: viewer as unknown as Viewer, live, counts: () => ({ adds, removes }) };
}

const t = JulianDate.now();
const DEG = 180 / Math.PI;
const at = (latDeg: number, lonDeg = 127, altM = 1000): GeoPoint => ({ latDeg, lonDeg, altM });
const lat = (c: Cartesian3) => Cartographic.fromCartesian(c).latitude * DEG;

const moveTo = (id: string, dest: GeoPoint): ActivityShape => ({
  entityId: id, taskId: `m-${id}`, kind: "moveTo", label: "이동", lead: dest, marks: [{ pos: dest, glyph: "o" }], circles: [], paths: [], estimated: false,
});
const hold = (id: string, c: GeoPoint, r = 300): ActivityShape => ({
  entityId: id, taskId: `h-${id}`, kind: "hold", label: "선회", lead: c, marks: [{ pos: c, glyph: "o" }], circles: [{ center: c, radiusM: r }], paths: [], estimated: false,
});
const strike = (id: string, p: GeoPoint): ActivityShape => ({
  entityId: id, taskId: `s-${id}`, kind: "strike", label: "타격", lead: p, marks: [{ pos: p, glyph: "x" }], circles: [], paths: [], estimated: false,
});

describe("ActivityLayer (TC-UI-070)", () => {
  it("대시선 시작점은 posNow를 매 프레임 읽는다. 같은 내용 재동기화는 Entity를 만들거나 지우지 않는다", () => {
    const { viewer, live, counts } = fakeViewer();
    let here = at(37.0);
    const layer = new ActivityLayer(viewer, () => here);
    layer.sync([moveTo("uav-001", at(37.5))], new Set());
    const first = [...live];
    const c0 = counts();
    for (let i = 0; i < 5; i++) layer.sync([moveTo("uav-001", at(37.5))], new Set());
    expect(counts()).toEqual(c0);
    expect(live).toEqual(first);
    const lead = live.find((e) => e.polyline)!;
    expect(lat((lead.polyline!.positions!.getValue(t) as Cartesian3[])[0])).toBeCloseTo(37.0, 6);
    here = at(37.1); // 기체가 움직였다: 재동기화 없이도 선이 따라간다
    expect(lat((lead.polyline!.positions!.getValue(t) as Cartesian3[])[0])).toBeCloseTo(37.1, 6);
    expect(lead.polyline!.positions!.isConstant).toBe(false);
  });

  it("o는 속 빈 점, x는 글자. 목적지가 바뀌면 같은 Entity의 위치만 바꾼다", () => {
    const { viewer, live, counts } = fakeViewer();
    const layer = new ActivityLayer(viewer, () => at(37.0));
    layer.sync([moveTo("uav-001", at(37.5))], new Set());
    const mark = live.find((e) => e.point && e.label?.text?.getValue(t) === "✕")!;
    expect(mark.point!.show!.getValue(t)).toBe(true);
    expect(mark.label!.show!.getValue(t)).toBe(false);
    const c0 = counts();
    layer.sync([moveTo("uav-001", at(37.6))], new Set());
    expect(counts()).toEqual(c0);
    expect(lat(mark.position!.getValue(t)!)).toBeCloseTo(37.6, 6);
    layer.sync([strike("uav-001", at(37.7, 127, 50))], new Set());
    expect(counts()).toEqual(c0);
    expect(mark.point!.show!.getValue(t)).toBe(false);
    expect(mark.label!.show!.getValue(t)).toBe(true);
  });

  it("선회원은 반경·중심이 바뀔 때만 다시 만든다. 기체가 빠지면 그 기체 도형을 모두 지운다", () => {
    const { viewer, live, counts } = fakeViewer();
    const layer = new ActivityLayer(viewer, () => at(37.0));
    layer.sync([hold("uav-001", at(37.5)), moveTo("uav-002", at(37.4))], new Set());
    expect(live.filter((e) => e.ellipse)).toHaveLength(1);
    const c0 = counts();
    layer.sync([hold("uav-001", at(37.5)), moveTo("uav-002", at(37.4))], new Set());
    expect(counts()).toEqual(c0);
    layer.sync([hold("uav-001", at(37.5), 500), moveTo("uav-002", at(37.4))], new Set());
    expect(counts()).toEqual({ adds: c0.adds + 1, removes: c0.removes + 1 });
    layer.sync([moveTo("uav-002", at(37.4))], new Set());
    expect(layer.entityCount).toBe(3);
    expect(live).toHaveLength(3);
    layer.clear();
    expect(live).toHaveLength(0);
  });

  it("선택 기체만 글(기체 ID·행동)을 보인다", () => {
    const { viewer, live } = fakeViewer();
    const layer = new ActivityLayer(viewer, () => at(37.0));
    layer.sync([moveTo("uav-001", at(37.5))], new Set());
    const tag = live.find((e) => e.label && !e.point)!;
    expect(tag.label!.show!.getValue(t)).toBe(false);
    layer.sync([moveTo("uav-001", at(37.5))], new Set(["uav-001"]));
    expect(tag.label!.show!.getValue(t)).toBe(true);
    expect(tag.label!.text!.getValue(t)).toBe("uav-001 이동");
  });

  it("100대: 처음 한 번만 만들고, 대상이 움직여도 재동기화는 Entity를 새로 만들지 않는다", () => {
    const { viewer, counts } = fakeViewer();
    const layer = new ActivityLayer(viewer, () => at(37.0));
    const shapes = (k: number) =>
      Array.from({ length: 100 }, (_, i) => (i % 2 ? moveTo(`uav-${i}`, at(37.5 + k * 1e-4 + i * 1e-3)) : hold(`uav-${i}`, at(37.2 + i * 1e-3))));
    layer.sync(shapes(0), new Set());
    const c0 = counts();
    expect(layer.entityCount).toBe(50 * 4 + 50 * 3);
    const t0 = performance.now();
    for (let k = 1; k <= 20; k++) layer.sync(shapes(k), new Set());
    const ms = (performance.now() - t0) / 20;
    expect(counts()).toEqual(c0);
    expect(ms).toBeLessThan(20); // 4 Hz 재동기화 한 번이 한 프레임 예산 안
  });
});
