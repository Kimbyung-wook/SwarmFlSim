// IMP-UI-038: 임무 도형 전시 (REQ-UI-003, REQ-UI-004, DEC-033)
// Overlay(점·선·원)를 Cesium Entity로 그린다. 편집 중 항로점 손잡이의 화면 좌표를 돌려준다.
import {
  Cartesian2,
  Cartesian3,
  Color,
  ColorMaterialProperty,
  HorizontalOrigin,
  LabelStyle,
  PolylineDashMaterialProperty,
  SceneTransforms,
  VerticalOrigin,
} from "cesium";
import type { Entity, Viewer } from "cesium";
import type { Overlay, OverlayStyle } from "../model/missionOverlay";

const COLOR: Record<OverlayStyle, Color> = {
  draft: Color.YELLOW,
  pending: Color.ORANGE,
  sent: Color.CYAN,
};

const cart = (p: { latDeg: number; lonDeg: number; altM: number }) => Cartesian3.fromDegrees(p.lonDeg, p.latDeg, p.altM);
const scratch = new Cartesian2();

export class MissionLayer {
  private entities: Entity[] = [];
  private handles: { index: number; position: Cartesian3 }[] = [];

  constructor(private readonly viewer: Viewer) {}

  set(o: Overlay): void {
    this.clear();
    const add = (e: Entity.ConstructorOptions) => this.entities.push(this.viewer.entities.add(e));
    for (const c of o.circles) {
      const color = COLOR[c.style];
      add({
        position: cart(c.center),
        ellipse: {
          semiMajorAxis: c.radiusM,
          semiMinorAxis: c.radiusM,
          height: c.center.altM,
          fill: true,
          material: new ColorMaterialProperty(color.withAlpha(0.08)),
          outline: true,
          outlineColor: color,
        },
      });
    }
    for (const l of o.lines) {
      const color = COLOR[l.style];
      add({
        polyline: {
          positions: l.positions.map(cart),
          width: l.style === "draft" ? 2.5 : 2,
          material: l.style === "draft" ? new ColorMaterialProperty(color) : new PolylineDashMaterialProperty({ color, dashLength: 16 }),
        },
      });
    }
    this.handles = [];
    for (const p of o.points) {
      const color = COLOR[p.style];
      const position = cart(p.pos);
      if (p.handle !== undefined) this.handles.push({ index: p.handle, position });
      add({
        position,
        point: {
          pixelSize: p.handle !== undefined ? 14 : 10,
          color: color.withAlpha(p.handle !== undefined ? 0.85 : 0.3),
          outlineColor: p.handle !== undefined ? Color.BLACK : color,
          outlineWidth: 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: p.label
          ? {
              text: p.label,
              font: p.handle !== undefined ? "bold 12px sans-serif" : "12px sans-serif",
              fillColor: p.handle !== undefined ? Color.BLACK : color,
              outlineColor: p.handle !== undefined ? Color.TRANSPARENT : Color.BLACK,
              outlineWidth: 3,
              style: LabelStyle.FILL_AND_OUTLINE,
              horizontalOrigin: p.handle !== undefined ? HorizontalOrigin.CENTER : HorizontalOrigin.LEFT,
              verticalOrigin: VerticalOrigin.CENTER,
              pixelOffset: p.handle !== undefined ? new Cartesian2(0, 0) : new Cartesian2(10, 0),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            }
          : undefined,
      });
    }
    this.viewer.scene.requestRender();
  }

  /** 편집 중 항로점 손잡이의 화면 좌표 (번호 순). 화면 밖이면 null */
  projectHandles(): ({ x: number; y: number } | null)[] {
    const out: ({ x: number; y: number } | null)[] = [];
    for (const h of this.handles) {
      const w = SceneTransforms.worldToWindowCoordinates(this.viewer.scene, h.position, scratch);
      out[h.index] = w ? { x: w.x, y: w.y } : null;
    }
    return out;
  }

  clear(): void {
    for (const e of this.entities) this.viewer.entities.remove(e);
    this.entities = [];
  }

  destroy(): void {
    this.clear();
  }
}
