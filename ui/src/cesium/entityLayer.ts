// IMP-UI-014: truth/state 엔티티 전시 레이어 (REQ-UI-001, REQ-UI-007)
// Billboard(아이콘·진행 방향), Polyline(궤적 꼬리), Label(선택 엔티티 ID)을 프리미티브로 직접 관리한다.
import {
  BillboardCollection,
  Cartesian2,
  Cartesian3,
  Color,
  EllipsoidalOccluder,
  Ellipsoid,
  HorizontalOrigin,
  LabelCollection,
  LabelStyle,
  Material,
  NearFarScalar,
  PolylineCollection,
  SceneMode,
  SceneTransforms,
  VerticalOrigin,
} from "cesium";
import type { Billboard, Label, Polyline, Scene } from "cesium";
import type { CameraMode } from "../model/camera";
import { cameraPose } from "../model/camera";
import { fitRect } from "../model/viewKeep";
import { fitTo } from "./cameraView";
import type { EntityView, FrameView } from "../model/entityView";
import type { ScreenEntity } from "../model/selection";
import { ICON_SIZE, iconUrl, isDirectional, sideColor } from "../model/symbology";
import type { TrailStore } from "../model/trails";

interface Item {
  view: EntityView;
  position: Cartesian3;
  billboard: Billboard;
  trail: Polyline;
  label: Label;
}

const scratch = new Cartesian2();
const scratchAhead = new Cartesian2();
const scratchPoint = new Cartesian3();

/** 진행 방향 쪽 AHEAD_M 앞의 점을 화면에 투영해 아이콘 회전각을 구한다 (기울어진 3D 시점에서도 맞도록) */
const AHEAD_M = 50;

/** 지구 고정 좌표계에서 진행 방향(heading, 수평) 단위벡터 */
function headingVector(latDeg: number, lonDeg: number, heading: number, out: Cartesian3): Cartesian3 {
  const lat = (latDeg * Math.PI) / 180, lon = (lonDeg * Math.PI) / 180;
  const n = Math.cos(heading), e = Math.sin(heading);
  return Cartesian3.fromElements(
    -n * Math.sin(lat) * Math.cos(lon) - e * Math.sin(lon),
    -n * Math.sin(lat) * Math.sin(lon) + e * Math.cos(lon),
    n * Math.cos(lat),
    out,
  );
}

export class EntityLayer {
  private readonly billboards: BillboardCollection;
  private readonly trails: PolylineCollection;
  private readonly labels: LabelCollection;
  private readonly items = new Map<string, Item>();
  private selected: ReadonlySet<string> = new Set();

  constructor(private readonly scene: Scene) {
    this.trails = scene.primitives.add(new PolylineCollection());
    this.billboards = scene.primitives.add(new BillboardCollection({ scene }));
    this.labels = scene.primitives.add(new LabelCollection({ scene }));
  }

  update(frame: FrameView, trails: TrailStore): void {
    const seen = new Set<string>();
    for (const e of frame.entities) {
      seen.add(e.id);
      const position = Cartesian3.fromDegrees(e.lon, e.lat, e.alt);
      let it = this.items.get(e.id);
      if (!it) {
        it = this.create(e, position);
        this.items.set(e.id, it);
      }
      const sel = this.selected.has(e.id);
      if (it.view.alive !== e.alive || it.view.kind !== e.kind || it.view.side !== e.side) {
        it.billboard.image = iconUrl(e.kind, e.side, sel, e.alive);
      }
      it.view = e;
      it.position = position;
      it.billboard.position = position;
      it.label.position = position;

      const pts = trails.get(e.id);
      if (pts.length >= 1 && e.alive) {
        const positions = pts.map((p) => Cartesian3.fromDegrees(p.lon, p.lat, p.alt));
        positions.push(position);
        it.trail.positions = positions;
        it.trail.show = true;
      } else {
        it.trail.show = false;
      }
    }
    for (const [id, it] of this.items) {
      if (seen.has(id)) continue;
      this.billboards.remove(it.billboard);
      this.trails.remove(it.trail);
      this.labels.remove(it.label);
      this.items.delete(id);
    }
  }

  setSelection(sel: ReadonlySet<string>): void {
    this.selected = sel;
    for (const [id, it] of this.items) {
      const s = sel.has(id);
      it.billboard.image = iconUrl(it.view.kind, it.view.side, s, it.view.alive);
      it.label.show = s;
      it.trail.width = s ? 2.5 : 1.5;
    }
  }

  /** 공중 엔티티 아이콘을 화면상 진행 방향으로 돌린다. 카메라가 움직이므로 매 렌더마다 부른다 */
  orient(): void {
    for (const it of this.items.values()) {
      if (!isDirectional(it.view.kind)) continue;
      const v = it.view;
      const ahead = Cartesian3.add(
        it.position,
        Cartesian3.multiplyByScalar(headingVector(v.lat, v.lon, v.heading, scratchPoint), AHEAD_M, scratchPoint),
        scratchPoint,
      );
      const p0 = SceneTransforms.worldToWindowCoordinates(this.scene, it.position, scratch);
      const p1 = p0 && SceneTransforms.worldToWindowCoordinates(this.scene, ahead, scratchAhead);
      if (!p0 || !p1) continue;
      const dx = p1.x - p0.x, dy = p1.y - p0.y;
      // 아이콘은 위쪽을 향해 그려져 있고 rotation은 반시계방향 +
      if (Math.hypot(dx, dy) > 1e-3) it.billboard.rotation = Math.atan2(-dx, -dy);
    }
  }

  /** 화면에 보이는 엔티티의 캔버스 좌표 (선택 판정용) */
  project(): ScreenEntity[] {
    const out: ScreenEntity[] = [];
    const occluder =
      this.scene.mode === SceneMode.SCENE3D ? new EllipsoidalOccluder(Ellipsoid.WGS84, this.scene.camera.positionWC) : null;
    for (const it of this.items.values()) {
      if (!it.billboard.show) continue;
      if (occluder && !occluder.isPointVisible(it.position)) continue;
      const w = SceneTransforms.worldToWindowCoordinates(this.scene, it.position, scratch);
      if (!w) continue;
      out.push({ id: it.view.id, x: w.x, y: w.y, kind: it.view.kind, side: it.view.side, alive: it.view.alive });
    }
    return out;
  }

  get(id: string): EntityView | undefined {
    return this.items.get(id)?.view;
  }

  /** 카메라 추종. free가 아니면 대상 기체의 자세로 카메라를 놓는다. 1인칭에서는 대상 아이콘을 숨긴다 */
  follow(targetId: string | null, mode: CameraMode): void {
    for (const it of this.items.values()) it.billboard.show = !(mode === "fpv" && it.view.id === targetId);
    if (!targetId || mode === "free") return;
    const e = this.get(targetId);
    if (!e) return;
    const pose = cameraPose(e, mode);
    if (!pose) return;
    this.scene.camera.setView({
      destination: Cartesian3.fromDegrees(pose.lon, pose.lat, pose.alt),
      orientation: { heading: pose.heading, pitch: pose.pitch, roll: pose.roll },
    });
  }

  /** 엔티티 전체가 보이도록 카메라를 놓는다 (IMP-UI-068). 맞출 엔티티가 없으면 false */
  fitAll(margin = 0.15): boolean {
    const r = fitRect([...this.items.values()].map((i) => i.view), margin);
    if (!r) return false;
    fitTo(this.scene, r);
    return true;
  }

  flyTo(id: string): void {
    const e = this.get(id);
    if (!e) return;
    this.scene.camera.flyTo({ destination: Cartesian3.fromDegrees(e.lon, e.lat, e.alt + 6000), duration: 0.8 });
  }

  destroy(): void {
    this.scene.primitives.remove(this.billboards);
    this.scene.primitives.remove(this.trails);
    this.scene.primitives.remove(this.labels);
    this.items.clear();
  }

  private create(e: EntityView, position: Cartesian3): Item {
    const color = Color.fromCssColorString(sideColor(e.side));
    const sel = this.selected.has(e.id);
    return {
      view: e,
      position,
      billboard: this.billboards.add({
        position,
        image: iconUrl(e.kind, e.side, sel, e.alive),
        width: ICON_SIZE,
        height: ICON_SIZE,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new NearFarScalar(2e3, 1.2, 4e5, 0.7),
        id: e.id,
      }),
      trail: this.trails.add({
        positions: [position, position],
        width: 1.5,
        material: Material.fromType("Color", { color: color.withAlpha(0.6) }),
        show: false,
      }),
      label: this.labels.add({
        position,
        text: e.id,
        font: "12px sans-serif",
        fillColor: Color.WHITE,
        outlineColor: Color.BLACK,
        outlineWidth: 3,
        style: LabelStyle.FILL_AND_OUTLINE,
        horizontalOrigin: HorizontalOrigin.LEFT,
        verticalOrigin: VerticalOrigin.CENTER,
        pixelOffset: new Cartesian2(ICON_SIZE / 2 + 4, 0),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        show: sel,
      }),
    };
  }
}
