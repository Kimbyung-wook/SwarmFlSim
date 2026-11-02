// IMP-UI-019: GCS 화면 구성 (REQ-UI-001, REQ-UI-002, REQ-UI-007)
// IMP-UI-034: 버스 소스(브리지) 선택, C2 명령 전송·상태 표시, 부대 그룹 단축키 (REQ-UI-002~004, DEC-027)
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { create } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import type { FormationShape } from "./gen/swarm/v1/c2_pb";
import { SimCommandSchema } from "./gen/swarm/v1/sim_pb";
import { BridgeTransport } from "./data/bridgeTransport";
import type { BridgeState } from "./data/bridgeTransport";
import { BusSource } from "./data/busSource";
import { MockSource } from "./data/mockSource";
import type { DataSource } from "./data/source";
import type { SourceConfig, SourceKind } from "./data/sourceConfig";
import { parseSourceConfig, withSource } from "./data/sourceConfig";
import type { MapDataStatus } from "./cesium/viewer";
import type { MapApi, ViewMode } from "./components/MapView";
import { MapView } from "./components/MapView";
import { CommandPanel } from "./components/CommandPanel";
import { SelectionPanel } from "./components/SelectionPanel";
import { Toolbar } from "./components/Toolbar";
import type { CameraMode } from "./model/camera";
import type { OutgoingC2, TaskKind } from "./model/commands";
import { C2Commander } from "./model/commands";
import type { GroupSlot } from "./model/groups";
import { GroupStore, groupId, slotFromKey } from "./model/groups";
import { isAirborneKind } from "./model/entityView";
import { LiveState } from "./model/liveState";
import type { SelectMode } from "./model/selection";
import { applySelection, isControllable, pruneSelection } from "./model/selection";
import { TaskLog } from "./model/taskLog";

/** UI 인스턴스 ID (DEC-020: 여러 UI 동시 접속). 엔티티 ID 규칙을 따른다 */
const UI_ID = `ui-${Math.random().toString(36).slice(2, 8)}`;
const PANEL_REFRESH_MS = 250;
const NOTICE_MS = 4000;
const RECALL_DOUBLE_MS = 400;

interface Conn {
  state: BridgeState;
  detail: string;
}

function makeSource(cfg: SourceConfig, onConn: (c: Conn) => void, onNotice: (m: string) => void): DataSource {
  if (cfg.kind !== "bus") return new MockSource();
  const transport = new BridgeTransport({
    url: cfg.bridgeUrl,
    client: UI_ID,
    role: "control",
    gcs: cfg.gcs ?? undefined,
    onState: (state, detail) => onConn({ state, detail: detail ?? "" }),
    onError: (code, msg) => onNotice(`브리지 ${code}: ${msg}`),
  });
  return new BusSource(transport, { gcs: cfg.gcs, onDecodeError: (k, e) => console.warn("decode", k, e) });
}

function errText(e: unknown): string {
  return String(e instanceof Error ? e.message : e);
}

export function App() {
  const cfg = useMemo(() => parseSourceConfig(location.search, import.meta.env, location.hostname), []);
  const [conn, setConn] = useState<Conn | null>(cfg.kind === "bus" ? { state: "connecting", detail: cfg.bridgeUrl } : null);
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flash = useCallback((m: string) => {
    setNotice(m);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), NOTICE_MS);
  }, []);
  const source = useMemo(() => makeSource(cfg, setConn, flash), [cfg, flash]);
  const live = useMemo(() => new LiveState(), []);
  const tasks = useMemo(() => new TaskLog(), []);
  const groups = useMemo(() => new GroupStore(), []);
  const commander = useMemo(() => (source.gcs ? new C2Commander(source.gcs, UI_ID, () => live.frame) : null), [source, live]);
  const [selection, setSelection] = useState<readonly string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("3d");
  const [camera, setCamera] = useState<{ id: string | null; mode: CameraMode }>({ id: null, mode: "free" });
  const [mapStatus, setMapStatus] = useState<MapDataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, refresh] = useReducer((n: number) => n + 1, 0);
  const api = useRef<MapApi | null>(null);
  const lastRecall = useRef<{ slot: GroupSlot; at: number } | null>(null);

  useEffect(() => {
    const unsub = source.subscribe({
      truth: (f) => live.onTruth(f),
      status: (s) => live.onStatus(s),
      rx: (k, env) => tasks.received(k, env),
    });
    source
      .connect()
      .then(() => setError(null))
      .catch((e: unknown) => setError(errText(e)));
    return () => {
      unsub();
      source.close();
    };
  }, [source, live, tasks]);

  useEffect(() => {
    if (conn?.state === "open") setError(null);
  }, [conn?.state]);

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
    (cmd: MessageInitShape<typeof SimCommandSchema>["cmd"]) => {
      try {
        source.send(create(SimCommandSchema, { issuer: UI_ID, cmd }));
      } catch (e) {
        flash(`sim/ctrl/cmd 전송 실패: ${errText(e)}`);
      }
    },
    [source, flash],
  );

  /** 명령 대상: 선택 중 살아 있는 아군 비행체 */
  const targets = selection.filter((id) => {
    const e = live.get(id);
    return e !== undefined && e.alive && isControllable(e) && isAirborneKind(e.kind);
  });
  const targetsRef = useRef(targets);
  targetsRef.current = targets;

  const issue = useCallback(
    (make: (c: C2Commander) => OutgoingC2) => {
      if (!commander) {
        flash("GCS가 지정되지 않아 명령을 보낼 수 없다 (?gcs=)");
        return;
      }
      let out: OutgoingC2;
      try {
        out = make(commander);
      } catch (e) {
        flash(errText(e));
        return;
      }
      try {
        source.sendC2(out);
        tasks.sent(out);
      } catch (e) {
        tasks.sent(out, errText(e));
        flash(`명령 전송 실패: ${errText(e)}`);
      }
      refresh();
    },
    [commander, source, tasks, flash],
  );

  const task = useCallback(
    (kind: TaskKind) => issue((c) => c.task(kind, targetsRef.current)),
    [issue],
  );

  const moveTo = useCallback(
    (latDeg: number, lonDeg: number) => {
      const ids = targetsRef.current;
      if (ids.length === 0) return;
      // 목적지 고도: 대상 기체 평균 고도(MSL)
      const alts = ids.map((id) => live.get(id)?.alt ?? 0);
      const altM = Math.round(alts.reduce((a, b) => a + b, 0) / alts.length);
      issue((c) => c.task("moveTo", ids, { latDeg, lonDeg, altM }));
    },
    [issue, live],
  );

  const formation = useCallback(
    (shape: FormationShape, spacingM: number) => {
      const ids = targetsRef.current;
      // 선택이 그룹 하나와 같으면 그 그룹 ID를, 아니면 첫 기체 기준 ID를 쓴다
      const slot = groups.slotOf(ids[0] ?? "");
      const same = slot !== null && groups.get(slot).length === ids.length && ids.every((id) => groups.slotOf(id) === slot);
      const gid = same ? groupId(slot) : `fmn-${ids[0] ?? "x"}`;
      issue((c) => c.formation(gid, ids, shape, spacingM));
    },
    [issue, groups],
  );

  const assignGroup = useCallback(
    (slot: GroupSlot) => {
      const ids = targetsRef.current;
      for (const ch of groups.assign(slot, ids)) {
        if (ch.members.length === 0 && ch.previous.length === 0) continue;
        issue((c) => c.group(groupId(ch.slot), ch.members, ch.previous));
      }
      flash(ids.length ? `그룹 ${slot} 지정: ${ids.length}대` : `그룹 ${slot} 해제`);
    },
    [groups, issue, flash],
  );

  const recallGroup = useCallback(
    (slot: GroupSlot) => {
      const ids = groups.recall(slot, live.ids());
      setSelection(ids);
      const now = performance.now();
      const last = lastRecall.current;
      if (last && last.slot === slot && now - last.at < RECALL_DOUBLE_MS && ids.length) api.current?.flyTo(ids[0]);
      lastRecall.current = { slot, at: now };
    },
    [groups, live],
  );

  const onSelect = useCallback((hits: string[], mode: SelectMode) => setSelection((s) => applySelection(s, hits, mode)), []);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.target instanceof HTMLInputElement || ev.target instanceof HTMLSelectElement) return;
      // ev.code(Digit1)로 읽어 Shift·키보드 배치에 상관없이 숫자를 얻는다
      const digit = ev.code.startsWith("Digit") ? slotFromKey(ev.code.slice(5)) : null;
      if (ev.key === "Escape") {
        setSelection([]);
        setCamera({ id: null, mode: "free" });
      } else if (ev.key.toLowerCase() === "a" && (ev.ctrlKey || ev.metaKey)) {
        ev.preventDefault();
        setSelection(live.frame.entities.filter((e) => e.alive && isControllable(e)).map((e) => e.id));
      } else if (digit && (ev.ctrlKey || ev.metaKey || ev.altKey)) {
        // Chrome은 Ctrl+1~9를 탭 전환에 먼저 쓰므로 Alt+숫자도 받는다
        ev.preventDefault();
        assignGroup(digit);
      } else if (digit && !ev.shiftKey) {
        recallGroup(digit);
      } else if (ev.key.toLowerCase() === "h" && !ev.ctrlKey && !ev.altKey) {
        if (targetsRef.current.length) task("hold");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [live, assignGroup, recallGroup, task]);

  // 추종 대상이 선택에서 빠지면 자유 시점으로 돌아간다
  useEffect(() => {
    if (camera.id && !selection.includes(camera.id)) setCamera({ id: null, mode: "free" });
  }, [selection, camera.id]);

  const onSource = (k: SourceKind) => {
    if (k !== cfg.kind) location.search = withSource(location.search, k);
  };

  const disabledReason = !source.gcs
    ? "GCS 미지정"
    : cfg.kind === "bus" && conn?.state !== "open"
      ? "브리지 미연결"
      : null;

  return (
    <div className="app">
      <Toolbar
        source={cfg.kind}
        onSource={onSource}
        conn={conn}
        gcs={source.gcs}
        status={live.status}
        simTimeUs={live.frame.simTimeUs}
        frame={live.frame.frame}
        entityCount={live.frame.entities.length}
        mapStatus={mapStatus}
        viewMode={viewMode}
        onViewMode={setViewMode}
        onStart={() => send({ case: "start", value: { rate: 1 } })}
        onPause={() => send({ case: "pause", value: {} })}
        onResume={() => send({ case: "resume", value: {} })}
        onStep={() => send({ case: "step", value: { frames: 1 } })}
        onReset={() => send({ case: "reset", value: {} })}
        onRate={(rate) => send({ case: "setRate", value: { rate } })}
        onFit={() => {
          setCamera({ id: null, mode: "free" });
          api.current?.fitAll();
        }}
      />
      {error && <div className="error">데이터 소스 연결 실패: {error}</div>}
      {notice && <div className="notice">{notice}</div>}
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
          onCommandPoint={(lat, lon) => {
            if (targetsRef.current.length === 0) return;
            if (disabledReason) flash(`이동 명령 불가: ${disabledReason}`);
            else moveTo(lat, lon);
          }}
        />
        <aside className="panel">
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
          <CommandPanel
            targets={targets}
            disabledReason={disabledReason}
            groups={groups.entries()}
            tasks={tasks.list()}
            rx={tasks.recentRx}
            onHold={() => task("hold")}
            onRtb={() => task("returnToBase")}
            onFormation={formation}
            onAssignGroup={assignGroup}
            onRecallGroup={recallGroup}
          />
        </aside>
      </div>
    </div>
  );
}
