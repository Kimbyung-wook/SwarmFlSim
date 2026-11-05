// TC-UI-052: QA-023 회귀 — 이벤트 층 갱신을 여러 번 해도 polyline의 Material이 destroy되지 않는다 (IMP-UI-066, IMP-UI-065)
// 실제 Cesium PolylineCollection·Polyline·Material을 쓰고 viewer만 가짜로 둔다(WebGL 없이 객체 수명 주기만 본다)
import type { Polyline, PolylineCollection, Viewer } from "cesium";
import { beforeAll, describe, expect, it } from "vitest";
import type { EventOverlay, LineDraw } from "../model/eventOverlay";
import { EventLayer } from "./eventLayer";

// node 환경에서 Material이 uniform 종류를 판별할 때 instanceof로 보는 DOM 클래스만 둔다
beforeAll(() => {
  const g = globalThis as Record<string, unknown>;
  for (const n of ["HTMLCanvasElement", "HTMLImageElement", "HTMLVideoElement", "ImageBitmap", "OffscreenCanvas"])
    if (!(n in g)) g[n] = class {};
});

function fakeViewer() {
  const prims: unknown[] = [];
  const entities: unknown[] = [];
  const viewer = {
    scene: {
      primitives: {
        add: <T>(p: T) => (prims.push(p), p),
        remove: (p: unknown) => {
          const i = prims.indexOf(p);
          if (i >= 0) prims.splice(i, 1);
          (p as { destroy?: () => void }).destroy?.();
          return i >= 0;
        },
      },
      globe: { getHeight: () => undefined },
    },
    entities: {
      add: (e: unknown) => (entities.push(e), e),
      remove: (e: unknown) => {
        const i = entities.indexOf(e);
        if (i >= 0) entities.splice(i, 1);
        return i >= 0;
      },
    },
  };
  return { viewer: viewer as unknown as Viewer, prims, entities };
}

const line = (lat: number, color = "#fb923c", alpha = 0.95): LineDraw => ({
  positions: [{ lat, lon: 127, alt: 1000 }, { lat: lat + 0.01, lon: 127, alt: 1100 }],
  color,
  alpha,
  width: 2.5,
});
const overlay = (lines: LineDraw[]): EventOverlay => ({ zones: [], lines, points: [], rings: [] });

function polylines(prims: unknown[]): Polyline[] {
  const c = prims.find((p) => (p as { constructor: { name: string } }).constructor.name === "PolylineCollection") as PolylineCollection;
  const out: Polyline[] = [];
  for (let i = 0; i < c.length; i++) out.push(c.get(i));
  return out;
}

describe("EventLayer (Cesium 수명 주기)", () => {
  it("같은 색 polyline을 여러 번 갱신해도 Material이 살아 있고 polyline을 지우지 않고 재사용한다", () => {
    const { viewer, prims } = fakeViewer();
    const layer = new EventLayer(viewer);
    layer.update(overlay([line(37), line(37.1)]));
    const first = polylines(prims);
    expect(first).toHaveLength(2);
    for (let k = 0; k < 5; k++) {
      layer.update(overlay([line(37 + k * 0.001), line(37.1), line(37.2, "#9ca3af", 0.6)]));
      for (const p of polylines(prims)) expect(p.material.isDestroyed()).toBe(false);
    }
    // 처음 만든 polyline이 그대로 있다
    expect(polylines(prims).slice(0, 2)).toEqual(first);
    // Material을 polyline끼리 나눠 쓰지 않는다
    const ms = polylines(prims).map((p) => p.material);
    expect(new Set(ms).size).toBe(ms.length);
    // 줄면 숨기고, 늘면 다시 쓴다. 색은 uniform으로 바뀐다
    layer.update(overlay([line(37, "#9ca3af", 0.6)]));
    expect(layer.lineStats).toEqual({ shown: 1, pooled: 3 });
    const c = polylines(prims)[0].material.uniforms.color;
    expect([c.red, c.alpha]).toEqual([0x9c / 255, 0.6]);
    layer.update(overlay([line(37), line(37.1), line(37.2), line(37.3)]));
    expect(layer.lineStats).toEqual({ shown: 4, pooled: 4 });
    for (const p of polylines(prims)) expect(p.material.isDestroyed()).toBe(false);
    layer.destroy();
    expect(prims).toHaveLength(0);
  });
});
