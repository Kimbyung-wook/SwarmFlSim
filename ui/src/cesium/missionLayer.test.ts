// TC-UI-065: 임무 도형 깜빡임 방지 — 같은 내용이면 Entity를 그대로 두고, 바뀐 값만 제자리에서 고친다 (IMP-UI-078)
// TC-UI-066: 찍은 점은 지면 표지(CLAMP_TO_GROUND)로, 명령 고도에는 작은 점과 지면→고도 수직선 (IMP-UI-077)
// 실제 Cesium Entity를 쓰고 viewer만 가짜로 둔다(WebGL 없이 Entity 수명·속성만 본다)
import { Cartographic, Entity, HeightReference, JulianDate } from "cesium";
import type { Cartesian3, Viewer } from "cesium";
import { describe, expect, it } from "vitest";
import type { GeoPoint } from "../model/commands";
import type { Overlay } from "../model/missionOverlay";
import { MissionLayer } from "./missionLayer";

function fakeViewer(groundM: number | undefined = undefined) {
  const live: Entity[] = [];
  let adds = 0;
  let removes = 0;
  const viewer = {
    scene: { globe: { getHeight: () => groundM }, requestRender: () => {} },
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
/** 우클릭 이동 미리보기: 기체 평균 위치 → 목적지 점선, 목적지 점, 선회 원 */
const preview = (fromLat: number, label = "이동", radiusM = 600): Overlay => ({
  lines: [{ positions: [at(fromLat), at(37.5)], style: "pending" }],
  points: [{ pos: at(37.5), label, style: "pending" }],
  circles: [{ center: at(37.5), radiusM, style: "pending" }],
});
const toCarto = (c: Cartesian3) => Cartographic.fromCartesian(c);

describe("MissionLayer 깜빡임 방지 (TC-UI-065)", () => {
  it("같은 도형을 거듭 set해도 Entity를 지우거나 새로 만들지 않는다", () => {
    const { viewer, live, counts } = fakeViewer();
    const m = new MissionLayer(viewer);
    m.set(preview(37.4));
    const first = [...live];
    const c0 = counts();
    for (let i = 0; i < 5; i++) m.set(preview(37.4));
    expect(counts()).toEqual(c0);
    expect(live).toEqual(first);
  });

  it("기체가 움직여 점선 시작점이 바뀌면 선 Entity는 그대로이고 위치만 바뀐다. 원·점도 그대로", () => {
    const { viewer, live, counts } = fakeViewer();
    const m = new MissionLayer(viewer);
    m.set(preview(37.4));
    const first = [...live];
    const c0 = counts();
    m.set(preview(37.41));
    m.set(preview(37.42));
    expect(counts()).toEqual(c0);
    expect(live).toEqual(first);
    const line = live.find((e) => e.polyline && e.polyline.width?.getValue(t) === 2)!;
    const ps = line.polyline!.positions!.getValue(t) as Cartesian3[];
    expect(toCarto(ps[0]).latitude * DEG).toBeCloseTo(37.42, 6);
  });

  it("라벨(진행률 등)이 바뀌면 같은 표지 Entity의 글만 바꾼다", () => {
    const { viewer, live, counts } = fakeViewer();
    const m = new MissionLayer(viewer);
    m.set(preview(37.4, "이동 · 수행 10%"));
    const c0 = counts();
    m.set(preview(37.4, "이동 · 수행 20%"));
    expect(counts()).toEqual(c0);
    expect(live.some((e) => e.label?.text?.getValue(t) === "이동 · 수행 20%")).toBe(true);
  });

  it("원은 반경이 바뀔 때만 그 원만 다시 만든다. 도형이 줄면 남는 Entity를 지운다", () => {
    const { viewer, live, counts } = fakeViewer();
    const m = new MissionLayer(viewer);
    m.set(preview(37.4, "이동", 600));
    const c0 = counts();
    m.set(preview(37.4, "이동", 800));
    expect(counts()).toEqual({ adds: c0.adds + 1, removes: c0.removes + 1 });
    m.set({ points: [], lines: [], circles: [] });
    expect(live).toEqual([]);
    expect(m.entityCount).toBe(0);
  });
});

describe("MissionLayer 지면 표지 (TC-UI-066)", () => {
  it("표지는 지면에 붙고(위경도는 찍은 곳), 명령 고도 점과 지면→고도 수직선이 따로 있다", () => {
    const { viewer, live } = fakeViewer(120);
    const m = new MissionLayer(viewer);
    m.set({ lines: [], circles: [], points: [{ pos: at(37.5, 127.2, 1000), label: "이동", style: "pending" }] });
    expect(live.length).toBe(3);
    const anchor = live.find((e) => e.label)!;
    expect(anchor.point!.heightReference!.getValue(t)).toBe(HeightReference.CLAMP_TO_GROUND);
    expect(anchor.label!.heightReference!.getValue(t)).toBe(HeightReference.CLAMP_TO_GROUND);
    const a = toCarto(anchor.position!.getValue(t)!);
    expect(a.latitude * DEG).toBeCloseTo(37.5, 9);
    expect(a.longitude * DEG).toBeCloseTo(127.2, 9);
    const aloft = live.find((e) => e.point && !e.label)!;
    expect(toCarto(aloft.position!.getValue(t)!).height).toBeCloseTo(1000, 3);
    const stem = live.find((e) => e.polyline)!;
    const [g, h] = (stem.polyline!.positions!.getValue(t) as Cartesian3[]).map(toCarto);
    expect(g.height).toBeCloseTo(120, 3);
    expect(h.height).toBeCloseTo(1000, 3);
    expect(g.latitude).toBeCloseTo(h.latitude, 12);
  });

  it("지형이 없으면 지면 높이는 0", () => {
    const { viewer } = fakeViewer(undefined);
    expect(new MissionLayer(viewer).groundM({ latDeg: 37.5, lonDeg: 127 })).toBe(0);
  });
});
