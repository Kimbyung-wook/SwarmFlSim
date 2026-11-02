// IMP-MON-015: 화면 구성, 데이터 소스 선택(?source=mock|bridge), 실시간·재생 표시 (REQ-UI-005, PRP-UI-002, DEC-027)
// 프레임마다 React를 다시 그리지 않는다. 보관소가 동기 처리하고 화면은 250 ms마다 읽는다.
import { useEffect, useMemo, useRef, useState } from "react";
import type { FrameSource, SourceStatus } from "./bridge/source";
import { BridgeSource } from "./bridge/source";
import { DEFAULT_BRIDGE_URL } from "./bridge/frame";
import { EchoPanel } from "./components/EchoPanel";
import { EntityDetail } from "./components/EntityDetail";
import { EntityTree } from "./components/EntityTree";
import { FilterBar } from "./components/FilterBar";
import { Header } from "./components/Header";
import type { Load } from "./components/Header";
import { StatsTable } from "./components/StatsTable";
import { Timeline } from "./components/Timeline";
import type { LinkOutcome } from "./gen/swarm/v1/link_pb";
import { MockSource } from "./mock/mockSource";
import type { Filter } from "./model/filter";
import { EMPTY_FILTER } from "./model/filter";
import type { RunView } from "./model/store";
import { MonitorStore } from "./model/store";

const REFRESH_MS = 250;

export interface AppConfig {
  source: "mock" | "bridge";
  url: string;
  view: RunView;
  uavs: number;
  peerHz: number;
  rate: number;
}

export function readConfig(search: string): AppConfig {
  const p = new URLSearchParams(search);
  const num = (k: string, d: number) => {
    const v = Number(p.get(k));
    return Number.isFinite(v) && v > 0 ? v : d;
  };
  return {
    source: p.get("source") === "bridge" ? "bridge" : "mock",
    url: p.get("url") ?? DEFAULT_BRIDGE_URL,
    view: p.get("replay") === "1" ? "replay" : "live",
    uavs: num("uavs", 20),
    peerHz: num("hz", 10),
    rate: num("rate", 1),
  };
}

function clientId(): string {
  return `monitor-${Math.random().toString(36).slice(2, 8)}`;
}

export function App() {
  const cfg = useMemo(() => readConfig(window.location.search), []);
  const store = useMemo(() => {
    const s = new MonitorStore();
    s.viewHint = cfg.view;
    return s;
  }, [cfg]);
  const sourceRef = useRef<FrameSource | null>(null);
  const [status, setStatus] = useState<SourceStatus>({ state: "idle" });
  const [, setTick] = useState(0);
  const [frozen, setFrozen] = useState(false);
  const [filter, setFilter] = useState<Filter>(EMPTY_FILTER);
  const [selected, setSelected] = useState<string | undefined>();
  const [picked, setPicked] = useState<LinkOutcome | undefined>();
  const [load, setLoad] = useState<Load>({ framesPerS: 0, busyPct: 0 });

  useEffect(() => {
    const src: FrameSource =
      cfg.source === "bridge"
        ? new BridgeSource({ url: cfg.url, client: clientId() })
        : new MockSource({ uavs: cfg.uavs, peerHz: cfg.peerHz, rate: cfg.rate, replay: cfg.view === "replay" });
    sourceRef.current = src;
    src.onFrame((f) => store.handleFrame(f));
    src.onStatus(setStatus);
    src.connect();
    return () => src.close();
  }, [cfg, store]);

  useEffect(() => {
    let last = { t: performance.now(), frames: store.frames, busy: store.busyMs };
    const timer = setInterval(() => {
      setTick((n) => n + 1);
      const t = performance.now();
      if (t - last.t >= 1000) {
        const dt = (t - last.t) / 1000;
        setLoad({ framesPerS: (store.frames - last.frames) / dt, busyPct: ((store.busyMs - last.busy) / (t - last.t)) * 100 });
        last = { t, frames: store.frames, busy: store.busyMs };
      }
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [store]);

  const toggleView = () => {
    store.toggleView();
    setTick((n) => n + 1);
  };

  return (
    <div className={`app ${store.view === "replay" ? "replay" : ""}`}>
      <Header
        store={store}
        sourceName={cfg.source}
        status={status}
        load={load}
        frozen={frozen}
        onFreeze={() => setFrozen((v) => !v)}
        onClear={() => {
          store.clearStats();
          setPicked(undefined);
        }}
        onToggleView={toggleView}
        onMockRestart={sourceRef.current instanceof MockSource ? () => (sourceRef.current as MockSource).restart() : undefined}
      />
      <FilterBar store={store} filter={filter} onChange={setFilter} />
      <div className="main">
        <aside className="left">
          <EntityTree store={store} filter={filter} selected={selected} onSelect={setSelected} onFilter={setFilter} />
        </aside>
        <section className="center">
          <StatsTable store={store} filter={filter} selected={selected} onSelect={setSelected} />
          <Timeline store={store} filter={filter} frozen={frozen} picked={picked} onPick={setPicked} />
        </section>
        <aside className="right">
          {selected && <EntityDetail store={store} id={selected} onClose={() => setSelected(undefined)} />}
          <EchoPanel store={store} filter={filter} frozen={frozen} picked={picked} onClearPick={() => setPicked(undefined)} />
        </aside>
      </div>
    </div>
  );
}
