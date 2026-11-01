// IMP-UI-019: GCS 화면 구성 (REQ-UI-001, REQ-UI-002, REQ-UI-007)
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { create } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { SimCommandSchema } from "./gen/swarm/v1/sim_pb";
import { BusSource, UnimplementedTransport } from "./data/busSource";
import { MockSource } from "./data/mockSource";
import type { DataSource } from "./data/source";
import type { MapDataStatus } from "./cesium/viewer";
import type { MapApi, ViewMode } from "./components/MapView";
import { MapView } from "./components/MapView";
import { SelectionPanel } from "./components/SelectionPanel";
import { Toolbar } from "./components/Toolbar";
import type { CameraMode } from "./model/camera";
import { LiveState } from "./model/liveState";
import type { SelectMode } from "./model/selection";
import { applySelection, isControllable, pruneSelection } from "./model/selection";

/** UI 인스턴스 ID (DEC-020: 여러 UI 동시 접속). 엔티티 ID 규칙을 따른다 */
const UI_ID = `ui-${Math.random().toString(36).slice(2, 8)}`;
const PANEL_REFRESH_MS = 250;

function makeSource(): DataSource {
  const kind = new URLSearchParams(location.search).get("source") ?? "mock";
  return kind === "bus" ? new BusSource(new UnimplementedTransport()) : new MockSource();
}

export function App() {
  const source = useMemo(makeSource, []);
  const live = useMemo(() => new LiveState(), []);
  const [selection, setSelection] = useState<readonly string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("3d");
  const [camera, setCamera] = useState<{ id: string | null; mode: CameraMode }>({ id: null, mode: "free" });
  const [mapStatus, setMapStatus] = useState<MapDataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, refresh] = useReducer((n: number) => n + 1, 0);
  const api = useRef<MapApi | null>(null);

  useEffect(() => {
    const unsub = source.subscribe({ truth: (f) => live.onTruth(f), status: (s) => live.onStatus(s) });
    source.connect().catch((e: unknown) => setError(String(e instanceof Error ? e.message : e)));
    return () => {
      unsub();
      source.close();
    };
  }, [source, live]);

  // 패널·도구 막대는 낮은 주기로 다시 그린다. 사라진 엔티티는 선택에서 뺀다
  useEffect(() => {
    const h = setInterval(() => {
      const present = live.ids();
      setSelection((s) => (present.size === 0 ? s : pruneSelection(s, present)));
      refresh();
    }, PANEL_REFRESH_MS);
    return () => clearInterval(h);
  }, [live]);

  const send = useCallback(
    (cmd: MessageInitShape<typeof SimCommandSchema>["cmd"]) => source.send(create(SimCommandSchema, { issuer: UI_ID, cmd })),
    [source],
  );

  const onSelect = useCallback((hits: string[], mode: SelectMode) => setSelection((s) => applySelection(s, hits, mode)), []);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.target instanceof HTMLInputElement) return;
      if (ev.key === "Escape") {
        setSelection([]);
        setCamera({ id: null, mode: "free" });
      } else if (ev.key.toLowerCase() === "a" && (ev.ctrlKey || ev.metaKey)) {
        ev.preventDefault();
        setSelection(live.frame.entities.filter((e) => e.alive && isControllable(e)).map((e) => e.id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [live]);

  // 추종 대상이 선택에서 빠지면 자유 시점으로 돌아간다
  useEffect(() => {
    if (camera.id && !selection.includes(camera.id)) setCamera({ id: null, mode: "free" });
  }, [selection, camera.id]);

  return (
    <div className="app">
      <Toolbar
        source={source.name}
        status={live.status}
        simTimeUs={live.frame.simTimeUs}
        frame={live.frame.frame}
        entityCount={live.frame.entities.length}
        mapStatus={mapStatus}
        viewMode={viewMode}
        onViewMode={setViewMode}
        onPause={() => send({ case: "pause", value: {} })}
        onResume={() => send({ case: "resume", value: {} })}
        onRate={(rate) => send({ case: "setRate", value: { rate } })}
        onFit={() => {
          setCamera({ id: null, mode: "free" });
          api.current?.fitAll();
        }}
      />
      {error && <div className="error">데이터 소스 연결 실패: {error}</div>}
      <div className="main">
        <MapView
          live={live}
          selection={selection}
          onSelect={onSelect}
          viewMode={viewMode}
          cameraMode={camera.mode}
          followId={camera.id}
          onReady={(a, s) => {
            api.current = a;
            setMapStatus(s);
          }}
        />
        <SelectionPanel
          ids={selection}
          entities={selection.map((id) => live.get(id))}
          followId={camera.id}
          cameraMode={camera.mode}
          onFocus={(id) => {
            setCamera({ id: null, mode: "free" });
            api.current?.flyTo(id);
          }}
          onRemove={(id) => setSelection((s) => s.filter((x) => x !== id))}
          onClear={() => setSelection([])}
          onCamera={(id, mode) => setCamera({ id, mode })}
        />
      </div>
    </div>
  );
}
