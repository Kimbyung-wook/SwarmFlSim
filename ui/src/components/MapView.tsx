// IMP-UI-016: 지도 뷰. Viewer 생성, 렌더 루프에서 엔티티 갱신, 클릭·드래그 박스 선택 입력 (REQ-UI-001, REQ-UI-002)
import { useEffect, useRef, useState } from "react";
import type { Viewer } from "cesium";
import { SceneMode } from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { EntityLayer } from "../cesium/entityLayer";
import type { MapDataStatus } from "../cesium/viewer";
import { createViewer } from "../cesium/viewer";
import type { CameraMode } from "../model/camera";
import type { LiveState } from "../model/liveState";
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
}

const MORPH_S = 0.8;

export function MapView({ live, selection, onSelect, viewMode, cameraMode, followId, onReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const layerRef = useRef<EntityLayer | null>(null);
  const follow = useRef({ id: followId, mode: cameraMode });
  const onSelectRef = useRef(onSelect);
  const onReadyRef = useRef(onReady);
  const [box, setBox] = useState<Rect | null>(null);

  follow.current = { id: followId, mode: cameraMode };
  onSelectRef.current = onSelect;
  onReadyRef.current = onReady;

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
      layerRef.current = layer;      let seen = -1;
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
      const down = (ev: PointerEvent) => {
        if (ev.button !== 0) return;
        start = pos(ev);
        rect = { x0: start.x, y0: start.y, x1: start.x, y1: start.y };
      };
      const move = (ev: PointerEvent) => {
        if (!start || !rect) return;
        const p = pos(ev);
        rect = { ...rect, x1: p.x, y1: p.y };
        setBox(isDrag(rect) ? normalizeRect(rect) : null);
      };
      const up = (ev: PointerEvent) => {
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
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        viewer.scene.preRender.removeEventListener(onPreRender);
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
