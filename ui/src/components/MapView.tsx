// IMP-UI-016: 지도 뷰. Viewer 생성, 렌더 루프에서 엔티티 갱신, 클릭·드래그 박스 선택 입력 (REQ-UI-001, REQ-UI-002)
// IMP-UI-032: 우클릭(끌지 않음) 지점을 MoveTo 목적지로 넘기고 잠시 표시한다 (REQ-UI-003)
// IMP-UI-065: truth 이벤트(재밍 구역·생성 엔티티·impact·kill)와 센서 시야를 렌더 루프에서 갱신한다 (DEC-046)
// IMP-UI-037: 우클릭 → 임무 메뉴, Ctrl+우클릭 → 항로점 추가, 항로점 손잡이 왼쪽 끌기 → 위치 변경 (DEC-033)
import { useEffect, useRef, useState } from "react";
import type { Viewer } from "cesium";
import { Cartesian2, Cartographic, Math as CesiumMath, SceneMode } from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { EntityLayer } from "../cesium/entityLayer";
import { EventLayer } from "../cesium/eventLayer";
import { eventOverlay } from "../model/eventOverlay";
import { MissionLayer } from "../cesium/missionLayer";
import type { MapDataStatus } from "../cesium/viewer";
import { createViewer } from "../cesium/viewer";
import type { CameraMode } from "../model/camera";
import type { LiveState } from "../model/liveState";
import type { MapPoint, RightClick } from "../model/mapInput";
import { classifyRightClick, pickHandle } from "../model/mapInput";
import type { Overlay } from "../model/missionOverlay";
import type { Rect, SelectMode } from "../model/selection";
import { isDrag, modeFromModifiers, normalizeRect, pickAt, pickInRect } from "../model/selection";

export type ViewMode = "3d" | "2d" | "columbus";

export interface MapApi {
  fitAll(): void;
  flyTo(id: string): void;
}

interface Props {
  live: LiveState;
  selection: readonly string[];
  onSelect(hits: string[], mode: SelectMode): void;
  viewMode: ViewMode;
  cameraMode: CameraMode;
  followId: string | null;
  onReady(api: MapApi, status: MapDataStatus): void;
  /** 명령 대상 기체가 있는지 (우클릭 임무 메뉴 조건) */
  hasTargets: boolean;
  /** 우클릭(끌지 않음) 판정 결과 */
  onRightClick(rc: RightClick): void;
  /** 임무 도형 (편집 중 항로·메뉴 지점·보낸 임무) */
  overlay: Overlay;
  /** 항로점 손잡이를 끄는 중. done이면 놓았다 */
  onWaypointDrag(index: number, point: MapPoint, done: boolean): void;
}

/** 화면 좌표 → 지면(지형이 있으면 지형, 없으면 타원체) 위경도 */
function pickGround(viewer: Viewer, x: number, y: number): MapPoint | null {
  const scene = viewer.scene;
  const ray = viewer.camera.getPickRay(new Cartesian2(x, y));
  const p = (ray && scene.mode === SceneMode.SCENE3D ? scene.globe.pick(ray, scene) : undefined) ??
    viewer.camera.pickEllipsoid(new Cartesian2(x, y), scene.globe.ellipsoid);
  if (!p) return null;
  const c = Cartographic.fromCartesian(p);
  return { latDeg: CesiumMath.toDegrees(c.latitude), lonDeg: CesiumMath.toDegrees(c.longitude), heightM: Math.max(0, c.height) };
}

const MORPH_S = 0.8;

export function MapView(props: Props) {
  const { live, selection, onSelect, viewMode, cameraMode, followId, onReady, overlay } = props;
  const host = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const layerRef = useRef<EntityLayer | null>(null);
  const missionRef = useRef<MissionLayer | null>(null);
  const follow = useRef({ id: followId, mode: cameraMode });
  const onSelectRef = useRef(onSelect);
  const onReadyRef = useRef(onReady);
  const propsRef = useRef(props);
  const [box, setBox] = useState<Rect | null>(null);

  follow.current = { id: followId, mode: cameraMode };
  onSelectRef.current = onSelect;
  onReadyRef.current = onReady;
  propsRef.current = props;

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    const el = host.current!;
    createViewer(el).then(({ viewer, status }) => {
      if (disposed) {
        viewer.destroy();
        return;
      }
      viewerRef.current = viewer;
      const layer = new EntityLayer(viewer.scene);
      layerRef.current = layer;
      const missions = new MissionLayer(viewer);
      missionRef.current = missions;
      missions.set(propsRef.current.overlay);
      const events = new EventLayer(viewer);
      let seenEv = "";
      let seen = -1;
      let fitted = false;
      const onPreRender = () => {
        if (live.version !== seen) {
          seen = live.version;
          layer.update(live.frame, live.trails);
          if (!fitted && live.frame.entities.length > 0) {
            layer.fitAll();
            fitted = true;
          }
        }
        const ev = `${live.version}/${live.events.version}/${live.sensors.version}`;
        if (ev !== seenEv) {
          seenEv = ev;
          events.update(
            eventOverlay(live.events, live.sensors.active(), (id) => live.get(id), events.groundAlt),
          );
        }
        layer.follow(follow.current.id, follow.current.mode);
        layer.orient();
      };
      viewer.scene.preRender.addEventListener(onPreRender);

      // 왼쪽 버튼: 짧게 누르면 클릭 선택, 끌면 박스 선택
      const canvas = viewer.scene.canvas;
      let start: { x: number; y: number } | null = null;
      let rect: Rect | null = null;
      // 캔버스 밖에서 버튼을 놓아도 받도록 move·up은 window에서 듣는다
      const pos = (ev: PointerEvent) => {
        const r = canvas.getBoundingClientRect();
        return { x: ev.clientX - r.left, y: ev.clientY - r.top };
      };
      // 오른쪽 버튼: 끌면 카메라(viewer.ts), 끌지 않으면 임무 메뉴 또는 (Ctrl) 항로점
      let rstart: { x: number; y: number } | null = null;
      const noMenu = (ev: Event) => ev.preventDefault();
      const rdown = (ev: PointerEvent) => {
        if (ev.button === 2) rstart = pos(ev);
      };
      const rup = (ev: PointerEvent) => {
        if (ev.button !== 2 || !rstart) return;
        const p = pos(ev);
        const r = { x0: rstart.x, y0: rstart.y, x1: p.x, y1: p.y };
        rstart = null;
        const point = isDrag(r) ? null : pickGround(viewer, p.x, p.y);
        const entityId = point ? pickAt(layer.project(), p.x, p.y) : null;
        const rc = classifyRightClick(r, ev, point, { hasTargets: propsRef.current.hasTargets, entityId });
        if (rc.kind !== "none") propsRef.current.onRightClick(rc);
      };
      canvas.addEventListener("contextmenu", noMenu);
      canvas.addEventListener("pointerdown", rdown);
      window.addEventListener("pointerup", rup);

      // 항로점 손잡이 끌기. 끄는 동안 카메라 입력을 끈다
      let dragging: number | null = null;
      const camera = viewer.scene.screenSpaceCameraController;
      const dragTo = (ev: PointerEvent, done: boolean) => {
        const p = pos(ev);
        const g = pickGround(viewer, p.x, p.y);
        if (g && dragging !== null) propsRef.current.onWaypointDrag(dragging, g, done);
      };

      const down = (ev: PointerEvent) => {
        if (ev.button !== 0) return;
        const p0 = pos(ev);
        const h = pickHandle(missions.projectHandles(), p0.x, p0.y);
        if (h !== null) {
          dragging = h;
          camera.enableInputs = false;
          return;
        }
        start = p0;
        rect = { x0: start.x, y0: start.y, x1: start.x, y1: start.y };
      };
      const move = (ev: PointerEvent) => {
        if (dragging !== null) {
          dragTo(ev, false);
          return;
        }
        if (!start || !rect) return;
        const p = pos(ev);
        rect = { ...rect, x1: p.x, y1: p.y };
        setBox(isDrag(rect) ? normalizeRect(rect) : null);
      };
      const up = (ev: PointerEvent) => {
        if (ev.button === 0 && dragging !== null) {
          dragTo(ev, true);
          dragging = null;
          camera.enableInputs = true;
          return;
        }
        if (ev.button !== 0 || !start || !rect) return;
        const p = pos(ev);
        rect = { ...rect, x1: p.x, y1: p.y };
        const ents = layer.project();
        const mode = modeFromModifiers(ev);
        if (isDrag(rect)) {
          onSelectRef.current(pickInRect(ents, rect), mode);
        } else {
          const id = pickAt(ents, rect.x1, rect.y1);
          // 빈 곳 클릭: replace 모드면 선택 해제, 나머지는 유지
          onSelectRef.current(id ? [id] : [], mode);
        }
        start = null;
        rect = null;
        setBox(null);
      };
      canvas.addEventListener("pointerdown", down);
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);

      onReadyRef.current({ fitAll: () => layer.fitAll(), flyTo: (id) => layer.flyTo(id) }, status);

      cleanup = () => {
        canvas.removeEventListener("pointerdown", down);
        canvas.removeEventListener("contextmenu", noMenu);
        canvas.removeEventListener("pointerdown", rdown);
        window.removeEventListener("pointerup", rup);
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        viewer.scene.preRender.removeEventListener(onPreRender);
        events.destroy();
        missions.destroy();
        missionRef.current = null;
        layer.destroy();
        viewer.destroy();
        viewerRef.current = null;
        layerRef.current = null;
      };
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [live]);

  useEffect(() => {
    layerRef.current?.setSelection(new Set(selection));
  }, [selection]);

  useEffect(() => {
    missionRef.current?.set(overlay);
  }, [overlay]);

  useEffect(() => {
    const v = viewerRef.current;
    if (!v) return;
    const target = viewMode === "2d" ? SceneMode.SCENE2D : viewMode === "columbus" ? SceneMode.COLUMBUS_VIEW : SceneMode.SCENE3D;
    if (v.scene.mode === target) return;
    if (target === SceneMode.SCENE2D) v.scene.morphTo2D(MORPH_S);
    else if (target === SceneMode.COLUMBUS_VIEW) v.scene.morphToColumbusView(MORPH_S);
    else v.scene.morphTo3D(MORPH_S);
  }, [viewMode]);

  return (
    <div className="map">
      <div ref={host} className="map-host" />
      {box && (
        <div
          className="select-box"
          style={{ left: box.x0, top: box.y0, width: box.x1 - box.x0, height: box.y1 - box.y0 }}
        />
      )}
    </div>
  );
}
