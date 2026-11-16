// IMP-UI-081: 기체별 현재 행동 전시 (REQ-UI-003). ActivityShape를 Cesium Entity로 그린다.
// - 향하는 점 o, 타격 표적 x, 기체→목표 대시선, 선회원(옅은 채움), 남은 항로·영역 윤곽(실선)
// - 깜빡임 방지(IMP-UI-078과 같은 방식): 기체별 슬롯을 두고 내용이 바뀐 것만 고친다. 선 위치는 CallbackProperty라
//   비동기 형상 재생성이 없고, 대시선 시작점은 매 프레임 기체 표시 위치(posNow)를 읽는다. 원만 바뀔 때 다시 만든다
import {
  CallbackProperty,
  Cartesian2,
  Cartesian3,
  Color,
  ColorMaterialProperty,
  HorizontalOrigin,
  LabelStyle,
  PolylineDashMaterialProperty,
  VerticalOrigin,
} from "cesium";
import type { Entity, Viewer } from "cesium";
import type { GeoPoint } from "../model/commands";
import type { ActivityMark, ActivityShape } from "../model/activity";

export const ACTIVITY_COLOR = Color.fromCssColorString("#4dd0e1");
export const STRIKE_COLOR = Color.fromCssColorString("#ff5252");

const cart = (p: GeoPoint) => Cartesian3.fromDegrees(p.lonDeg, p.latDeg, p.altM);

interface Slot {
  key: string;
  shape: ActivityShape;
  lead: Entity;
  tag: Entity;
  /** data: 마지막으로 그린 표식·색 */
  marks: { data: string | null; entity: Entity }[];
  paths: { carts: Cartesian3[]; entity: Entity }[];
  circles: Map<string, Entity>;
  labeled: boolean;
}

export class ActivityLayer {
  private readonly slots = new Map<string, Slot>();

  constructor(
    private readonly viewer: Viewer,
    /** 대시선 시작점: 기체 표시 위치. 모르면 null */
    private readonly posNow: (id: string) => GeoPoint | null,
  ) {}

  /** 그릴 행동 전체. labeled는 글을 붙일 기체(선택 기체) */
  sync(shapes: readonly ActivityShape[], labeled: ReadonlySet<string>): void {
    const seen = new Set<string>();
    for (const s of shapes) {
      seen.add(s.entityId);
      const key = JSON.stringify(s);
      let slot = this.slots.get(s.entityId);
      if (!slot) {
        slot = this.addSlot(s);
        this.slots.set(s.entityId, slot);
      } else if (slot.key !== key) {
        this.restyle(slot, s);
      }
      slot.key = key;
      const lab = labeled.has(s.entityId);
      if (slot.labeled !== lab) {
        slot.labeled = lab;
        slot.tag.label!.show = lab as never;
      }
    }
    for (const [id, slot] of this.slots) {
      if (seen.has(id)) continue;
      this.removeSlot(slot);
      this.slots.delete(id);
    }
    this.viewer.scene.requestRender?.();
  }

  private color(s: ActivityShape): Color {
    return s.kind === "strike" ? STRIKE_COLOR : ACTIVITY_COLOR;
  }

  private addSlot(s: ActivityShape): Slot {
    const ents = this.viewer.entities;
    const slot = { key: "", shape: s, marks: [], paths: [], circles: new Map(), labeled: false } as unknown as Slot;
    const id = s.entityId;
    slot.lead = ents.add({
      polyline: {
        positions: new CallbackProperty(() => {
          const a = this.posNow(id);
          const b = slot.shape.lead;
          return a && b ? [cart(a), cart(b)] : [];
        }, false),
        width: 1.5,
        material: new PolylineDashMaterialProperty({ color: this.color(s).withAlpha(0.9), dashLength: 12 }),
      },
    });
    slot.tag = ents.add({
      label: {
        show: false,
        font: "11px sans-serif",
        style: LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 3,
        outlineColor: Color.BLACK,
        horizontalOrigin: HorizontalOrigin.LEFT,
        verticalOrigin: VerticalOrigin.CENTER,
        pixelOffset: new Cartesian2(12, -12),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    this.restyle(slot, s);
    return slot;
  }

  private restyle(slot: Slot, s: ActivityShape): void {
    const prev = slot.shape;
    slot.shape = s;
    const color = this.color(s);
    if ((prev.kind === "strike") !== (s.kind === "strike")) {
      slot.lead.polyline!.material = new PolylineDashMaterialProperty({ color: color.withAlpha(0.9), dashLength: 12 });
    }
    const anchor = s.lead ?? s.marks[0]?.pos ?? null;
    slot.tag.position = (anchor ? cart(anchor) : undefined) as never;
    slot.tag.label!.text = `${s.entityId} ${s.label}${s.estimated ? " (추정)" : ""}` as never;
    slot.tag.label!.fillColor = color as never;
    this.setMarks(slot, s.marks, color);
    this.setPaths(slot, s.paths, color);
    this.setCircles(slot, s.circles, color);
  }

  private setMarks(slot: Slot, marks: ActivityMark[], color: Color): void {
    const ents = this.viewer.entities;
    marks.forEach((m, i) => {
      let p = slot.marks[i];
      if (!p) {
        p = {
          data: null,
          entity: ents.add({
            point: { pixelSize: 11, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY },
            label: {
              text: "✕",
              font: "bold 18px sans-serif",
              style: LabelStyle.FILL_AND_OUTLINE,
              outlineWidth: 3,
              outlineColor: Color.BLACK,
              horizontalOrigin: HorizontalOrigin.CENTER,
              verticalOrigin: VerticalOrigin.CENTER,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
          }),
        };
        slot.marks.push(p);
      }
      const key = JSON.stringify(m) + color.toCssColorString();
      if (p.data === key) return;
      p.data = key;
      const e = p.entity;
      e.position = cart(m.pos) as never;
      const o = m.glyph === "o";
      e.point!.show = o as never;
      e.point!.color = color.withAlpha(0.15) as never;
      e.point!.outlineColor = color as never;
      e.label!.show = !o as never;
      e.label!.fillColor = color as never;
    });
    for (const p of slot.marks.splice(marks.length)) this.viewer.entities.remove(p.entity);
  }

  private setPaths(slot: Slot, paths: GeoPoint[][], color: Color): void {
    paths.forEach((ps, i) => {
      const carts = ps.map(cart);
      const p = slot.paths[i];
      if (p) {
        p.carts = carts; // 다음 프레임에 콜백이 읽는다
        return;
      }
      const s = { carts, entity: undefined as unknown as Entity };
      s.entity = this.viewer.entities.add({
        polyline: {
          positions: new CallbackProperty(() => s.carts, false),
          width: 1.5,
          material: new ColorMaterialProperty(color.withAlpha(0.6)),
        },
      });
      slot.paths.push(s);
    });
    for (const p of slot.paths.splice(paths.length)) this.viewer.entities.remove(p.entity);
  }

  private setCircles(slot: Slot, cs: ActivityShape["circles"], color: Color): void {
    const next = new Map<string, Entity>();
    for (const c of cs) {
      let key = JSON.stringify(c);
      while (next.has(key)) key += "+";
      const kept = slot.circles.get(key);
      if (kept) {
        slot.circles.delete(key);
        next.set(key, kept);
        continue;
      }
      next.set(
        key,
        this.viewer.entities.add({
          position: cart(c.center),
          ellipse: {
            semiMajorAxis: c.radiusM,
            semiMinorAxis: c.radiusM,
            height: c.center.altM,
            fill: true,
            material: new ColorMaterialProperty(color.withAlpha(0.1)),
            outline: true,
            outlineColor: color.withAlpha(0.6),
          },
        }),
      );
    }
    for (const e of slot.circles.values()) this.viewer.entities.remove(e);
    slot.circles = next;
  }

  private removeSlot(slot: Slot): void {
    const ents = this.viewer.entities;
    ents.remove(slot.lead);
    ents.remove(slot.tag);
    for (const m of slot.marks) ents.remove(m.entity);
    for (const p of slot.paths) ents.remove(p.entity);
    for (const e of slot.circles.values()) ents.remove(e);
  }

  /** 시험·점검용: 지금 그리고 있는 Entity 수 */
  get entityCount(): number {
    let n = 0;
    for (const s of this.slots.values()) n += 2 + s.marks.length + s.paths.length + s.circles.size;
    return n;
  }

  clear(): void {
    this.sync([], new Set());
  }

  destroy(): void {
    this.clear();
  }
}
