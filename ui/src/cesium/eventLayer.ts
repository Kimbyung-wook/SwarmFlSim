// IMP-UI-065: truth 이벤트·센서 시야 전시 (DEC-003, DEC-046)
// 재밍 구역과 살상반경 원은 드물게 바뀌므로 Entity(extruded ellipse·polygon)로 그리고 도형 서명이 같으면 다시 만들지 않는다.
// 궤적·마커·FOV 선은 프레임마다 바뀌므로 프리미티브 모음을 다시 채운다(동기 갱신, 깜박임 없음). 2D·2.5D·3D 모두 같은 도형을 쓴다.
// IMP-UI-066 (QA-023): Polyline은 지워질 때 자기 Material을 destroy한다(Cesium Polyline._destroy). 그래서 Material을
// polyline끼리 나눠 쓰지 않고, polyline을 지우지 않고 풀로 재사용한다. 각 polyline이 자기 Material을 갖고 색은 uniform으로 바꾼다.
import {
  Cartesian2,
  Cartesian3,
  Cartographic,
  Color,
  ColorMaterialProperty,
  HorizontalOrigin,
  LabelCollection,
  LabelStyle,
  Material,
  PointPrimitiveCollection,
  PolygonHierarchy,
  PolylineCollection,
  VerticalOrigin,
} from "cesium";
import type { Entity, Polyline, Viewer } from "cesium";
import type { EventOverlay, RingDraw, ZoneDraw } from "../model/eventOverlay";
import type { GeoPos } from "../model/truthEvents";

const cart = (p: GeoPos) => Cartesian3.fromDegrees(p.lon, p.lat, p.alt);

export class EventLayer {
  private readonly lines: PolylineCollection;
  private readonly points: PointPrimitiveCollection;
  private readonly labels: LabelCollection;
  private readonly statics = new Map<string, { sig: string; entities: Entity[] }>();
  /** 재사용하는 polyline. 앞에서부터 쓰고 남는 것은 숨긴다 */
  private readonly pool: Polyline[] = [];

  constructor(private readonly viewer: Viewer) {
    const prims = viewer.scene.primitives;
    this.lines = prims.add(new PolylineCollection());
    this.points = prims.add(new PointPrimitiveCollection());
    this.labels = prims.add(new LabelCollection({ scene: viewer.scene }));
  }

  /** 기체 아래 지면 고도(MSL). 지형 타일이 없으면 0 */
  groundAlt = (p: GeoPos): number => this.viewer.scene.globe.getHeight(Cartographic.fromDegrees(p.lon, p.lat)) ?? 0;

  update(o: EventOverlay): void {
    this.points.removeAll();
    this.labels.removeAll();
    o.lines.forEach((l, i) => {
      const color = Color.fromCssColorString(l.color).withAlpha(l.alpha);
      let pl = this.pool[i];
      if (!pl) {
        pl = this.lines.add({ width: l.width, material: Material.fromType("Color", { color }) });
        this.pool.push(pl);
      } else {
        pl.width = l.width;
        pl.material.uniforms.color = color;
      }
      pl.positions = l.positions.map(cart);
      pl.show = true;
    });
    for (let i = o.lines.length; i < this.pool.length; i++) this.pool[i].show = false;
    for (const p of o.points) {
      const position = cart(p.pos);
      this.points.add({
        position,
        pixelSize: p.size,
        color: Color.fromCssColorString(p.color),
        outlineColor: Color.fromCssColorString(p.outline),
        outlineWidth: 2,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      });
      if (p.label) this.label(position, p.label, p.color === "#ffffff" ? "#e5e7eb" : p.color);
    }

    const keep = new Set<string>();
    for (const z of o.zones) this.syncStatic(z.key, JSON.stringify(z), () => this.zone(z), keep);
    for (const r of o.rings) this.syncStatic(r.key, JSON.stringify(r), () => this.ring(r), keep);
    for (const [k, s] of this.statics)
      if (!keep.has(k)) {
        for (const e of s.entities) this.viewer.entities.remove(e);
        this.statics.delete(k);
      }
  }

  destroy(): void {
    const prims = this.viewer.scene.primitives;
    prims.remove(this.lines);
    prims.remove(this.points);
    prims.remove(this.labels);
    for (const s of this.statics.values()) for (const e of s.entities) this.viewer.entities.remove(e);
    this.statics.clear();
    this.pool.length = 0;
  }

  /** 시험용: 쓰는 polyline 수와 풀 크기 */
  get lineStats(): { shown: number; pooled: number } {
    return { shown: this.pool.filter((p) => p.show).length, pooled: this.pool.length };
  }

  private label(position: Cartesian3, text: string, color: string): void {
    this.labels.add({
      position,
      text,
      font: "12px sans-serif",
      fillColor: Color.fromCssColorString(color),
      outlineColor: Color.BLACK,
      outlineWidth: 3,
      style: LabelStyle.FILL_AND_OUTLINE,
      horizontalOrigin: HorizontalOrigin.LEFT,
      verticalOrigin: VerticalOrigin.CENTER,
      pixelOffset: new Cartesian2(10, 0),
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    });
  }

  private syncStatic(key: string, sig: string, make: () => Entity[], keep: Set<string>): void {
    keep.add(key);
    const cur = this.statics.get(key);
    if (cur?.sig === sig) return;
    if (cur) for (const e of cur.entities) this.viewer.entities.remove(e);
    this.statics.set(key, { sig, entities: make() });
  }

  private zone(z: ZoneDraw): Entity[] {
    const color = Color.fromCssColorString(z.color);
    const material = new ColorMaterialProperty(color.withAlpha(z.fillAlpha));
    const outlineColor = color.withAlpha(z.outlineAlpha);
    const common = { height: z.bottomM, extrudedHeight: z.topM, material, outline: true, outlineColor };
    let center: GeoPos;
    let body: Entity;
    if (z.shape.kind === "circle") {
      center = z.shape.center;
      body = this.viewer.entities.add({
        position: Cartesian3.fromDegrees(center.lon, center.lat, z.bottomM),
        ellipse: { semiMajorAxis: z.shape.radiusM, semiMinorAxis: z.shape.radiusM, ...common },
      });
    } else {
      const vs = z.shape.vertices;
      center = { lat: vs.reduce((a, v) => a + v.lat, 0) / vs.length, lon: vs.reduce((a, v) => a + v.lon, 0) / vs.length, alt: 0 };
      body = this.viewer.entities.add({
        polygon: { hierarchy: new PolygonHierarchy(vs.map((v) => Cartesian3.fromDegrees(v.lon, v.lat))), ...common },
      });
    }
    const label = this.viewer.entities.add({
      position: Cartesian3.fromDegrees(center.lon, center.lat, z.topM),
      label: {
        text: z.label,
        font: "12px sans-serif",
        fillColor: outlineColor,
        outlineColor: Color.BLACK,
        outlineWidth: 3,
        style: LabelStyle.FILL_AND_OUTLINE,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    return [body, label];
  }

  private ring(r: RingDraw): Entity[] {
    const color = Color.fromCssColorString(r.color);
    return [
      this.viewer.entities.add({
        position: cart(r.center),
        ellipse: {
          semiMajorAxis: r.radiusM,
          semiMinorAxis: r.radiusM,
          height: r.center.alt,
          material: new ColorMaterialProperty(color.withAlpha(0.2)),
          outline: true,
          outlineColor: color,
        },
        label: {
          text: r.label,
          font: "12px sans-serif",
          fillColor: color,
          outlineColor: Color.BLACK,
          outlineWidth: 3,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(0, -18),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      }),
    ];
  }
}
