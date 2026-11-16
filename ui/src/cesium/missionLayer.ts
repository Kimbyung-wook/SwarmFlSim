// IMP-UI-038: 임무 도형 전시 (REQ-UI-003, REQ-UI-004, DEC-033)
// Overlay(점·선·원)를 Cesium Entity로 그린다. 편집 중 항로점 손잡이의 화면 좌표를 돌려준다.
// IMP-UI-077: 점은 지면에 붙인 표지(라벨·손잡이)로 그리고, 명령 고도에는 작은 점과 수직선만 둔다.
//   찍은 지점이 원근 화면에서도 커서 아래에 보인다. 손잡이 화면 좌표도 지면 표지 기준이다.
// IMP-UI-078: 깜빡임 방지. 도형을 매번 지우고 다시 만들지 않는다.
//   점·선은 순번 풀을 두고 값만 바꾼다(선 위치는 CallbackProperty라 비동기 형상 재생성이 없다).
//   원은 내용이 같으면 그대로 두고 바뀐 것만 다시 만든다.
import {
  CallbackProperty,
  Cartesian2,
  Cartesian3,
  Cartographic,
  Color,
  ColorMaterialProperty,
  HeightReference,
  HorizontalOrigin,
  LabelStyle,
  PolylineDashMaterialProperty,
  SceneTransforms,
  VerticalOrigin,
} from "cesium";
import type { Entity, MaterialProperty, Viewer } from "cesium";
import type { Overlay, OverlayCircle, OverlayLine, OverlayPoint, OverlayStyle } from "../model/missionOverlay";
import type { GeoPoint } from "../model/commands";

const COLOR: Record<OverlayStyle, Color> = {
  draft: Color.YELLOW,
  pending: Color.ORANGE,
  sent: Color.CYAN,
};

const cart = (p: GeoPoint) => Cartesian3.fromDegrees(p.lonDeg, p.latDeg, p.altM);
const scratch = new Cartesian2();

interface PointSlot {
  data: OverlayPoint;
  /** 지면 표지: 커서로 찍은 곳. 라벨·손잡이 */
  anchor: Entity;
  /** 명령 고도의 작은 점 */
  aloft: Entity;
  /** 지면 → 명령 고도 수직선 */
  stem: Entity;
}

interface LineSlot {
  data: OverlayLine;
  entity: Entity;
}

export class MissionLayer {
  private points: PointSlot[] = [];
  private lines: LineSlot[] = [];
  private circles = new Map<string, Entity>();
  private handles: { index: number; pos: GeoPoint }[] = [];

  constructor(private readonly viewer: Viewer) {}

  /** 지면 높이(MSL m). 지형이 없거나 아직 안 받았으면 0 */
  groundM(p: { latDeg: number; lonDeg: number }): number {
    return this.viewer.scene.globe.getHeight(Cartographic.fromDegrees(p.lonDeg, p.latDeg)) ?? 0;
  }

  private groundCart(p: GeoPoint): Cartesian3 {
    return Cartesian3.fromDegrees(p.lonDeg, p.latDeg, this.groundM(p));
  }

  set(o: Overlay): void {
    this.setCircles(o.circles);
    this.setLines(o.lines);
    this.setPoints(o.points);
    this.handles = o.points.filter((p) => p.handle !== undefined).map((p) => ({ index: p.handle!, pos: p.pos }));
    this.viewer.scene.requestRender?.();
  }

  private setCircles(cs: OverlayCircle[]): void {
    const next = new Map<string, Entity>();
    for (const c of cs) {
      let key = JSON.stringify(c);
      while (next.has(key)) key += "+"; // 같은 원이 둘이면 따로 둔다
      const kept = this.circles.get(key);
      if (kept) {
        this.circles.delete(key);
        next.set(key, kept);
        continue;
      }
      const color = COLOR[c.style];
      next.set(
        key,
        this.viewer.entities.add({
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
        }),
      );
    }
    for (const e of this.circles.values()) this.viewer.entities.remove(e);
    this.circles = next;
  }

  private lineLook(l: OverlayLine): { width: number; material: MaterialProperty } {
    const color = COLOR[l.style];
    return {
      width: l.style === "draft" ? 2.5 : 2,
      material: l.style === "draft" ? new ColorMaterialProperty(color) : new PolylineDashMaterialProperty({ color, dashLength: 16 }),
    };
  }

  private setLines(ls: OverlayLine[]): void {
    ls.forEach((l, i) => {
      const slot = this.lines[i];
      if (!slot) {
        const s: LineSlot = { data: l, entity: undefined as unknown as Entity };
        s.entity = this.viewer.entities.add({
          polyline: { positions: new CallbackProperty(() => s.data.positions.map(cart), false), ...this.lineLook(l) },
        });
        this.lines.push(s);
        return;
      }
      if (slot.data.style !== l.style) {
        const look = this.lineLook(l);
        slot.entity.polyline!.width = look.width as never;
        slot.entity.polyline!.material = look.material;
      }
      slot.data = l; // 위치는 다음 프레임에 콜백이 읽는다
    });
    for (const s of this.lines.splice(ls.length)) this.viewer.entities.remove(s.entity);
  }

  private setPoints(ps: OverlayPoint[]): void {
    ps.forEach((p, i) => {
      const slot = this.points[i];
      if (!slot) {
        this.points.push(this.addPoint(p));
      } else if (JSON.stringify(slot.data) !== JSON.stringify(p)) {
        this.stylePoint(slot, p);
      }
    });
    for (const s of this.points.splice(ps.length)) for (const e of [s.anchor, s.aloft, s.stem]) this.viewer.entities.remove(e);
  }

  private addPoint(p: OverlayPoint): PointSlot {
    const slot = { data: p } as PointSlot;
    slot.anchor = this.viewer.entities.add({
      point: { heightReference: HeightReference.CLAMP_TO_GROUND, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      label: {
        outlineWidth: 3,
        style: LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: VerticalOrigin.CENTER,
        heightReference: HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    slot.aloft = this.viewer.entities.add({
      point: { pixelSize: 5, outlineWidth: 1, outlineColor: Color.BLACK, disableDepthTestDistance: Number.POSITIVE_INFINITY },
    });
    slot.stem = this.viewer.entities.add({
      polyline: {
        positions: new CallbackProperty(() => [this.groundCart(slot.data.pos), cart(slot.data.pos)], false),
        width: 1,
        material: new ColorMaterialProperty(Color.WHITE.withAlpha(0.6)),
      },
    });
    this.stylePoint(slot, p);
    return slot;
  }

  /** 슬롯을 지우지 않고 값만 바꾼다. Cesium의 Entity 속성 setter는 원시 값을 ConstantProperty로 감싼다(형 선언은 Property라 as never) */
  private stylePoint(slot: PointSlot, p: OverlayPoint): void {
    slot.data = p;
    const color = COLOR[p.style];
    const isHandle = p.handle !== undefined;
    const ground = Cartesian3.fromDegrees(p.pos.lonDeg, p.pos.latDeg, 0); // 높이는 CLAMP_TO_GROUND가 정한다
    const a = slot.anchor;
    a.position = ground as never;
    a.point!.pixelSize = (isHandle ? 14 : 10) as never;
    a.point!.color = color.withAlpha(isHandle ? 0.85 : 0.3) as never;
    a.point!.outlineColor = (isHandle ? Color.BLACK : color) as never;
    a.label!.show = (p.label !== "") as never;
    a.label!.text = p.label as never;
    a.label!.font = (isHandle ? "bold 12px sans-serif" : "12px sans-serif") as never;
    a.label!.fillColor = (isHandle ? Color.BLACK : color) as never;
    a.label!.outlineColor = (isHandle ? Color.TRANSPARENT : Color.BLACK) as never;
    a.label!.horizontalOrigin = (isHandle ? HorizontalOrigin.CENTER : HorizontalOrigin.LEFT) as never;
    a.label!.pixelOffset = (isHandle ? new Cartesian2(0, 0) : new Cartesian2(10, 0)) as never;
    slot.aloft.position = cart(p.pos) as never;
    slot.aloft.point!.color = color as never;
  }

  /** 편집 중 항로점 손잡이(지면 표지)의 화면 좌표 (번호 순). 화면 밖이면 null */
  projectHandles(): ({ x: number; y: number } | null)[] {
    const out: ({ x: number; y: number } | null)[] = [];
    for (const h of this.handles) {
      const w = SceneTransforms.worldToWindowCoordinates(this.viewer.scene, this.groundCart(h.pos), scratch);
      out[h.index] = w ? { x: w.x, y: w.y } : null;
    }
    return out;
  }

  /** 시험·점검용: 지금 그리고 있는 Entity 수 */
  get entityCount(): number {
    return this.points.length * 3 + this.lines.length + this.circles.size;
  }

  clear(): void {
    this.set({ points: [], lines: [], circles: [] });
  }

  destroy(): void {
    this.clear();
  }
}
