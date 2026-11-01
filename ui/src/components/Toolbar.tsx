// IMP-UI-018: 상단 도구 막대. 2D/3D 전환(REQ-UI-001), 시뮬레이션 상태와 일시정지·배속(sim/ctrl/cmd, DEC-014)
// IMP-UI-030: 시작·스텝·리셋, 데이터 소스 선택(목/버스), 브리지 연결 상태
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import { SimRunState } from "../gen/swarm/v1/sim_pb";
import type { MapDataStatus } from "../cesium/viewer";
import type { BridgeState } from "../data/bridgeTransport";
import type { SourceKind } from "../data/sourceConfig";
import type { ViewMode } from "./MapView";

type ConnState = BridgeState;

interface Props {
  source: SourceKind;
  onSource(k: SourceKind): void;
  /** 버스 소스의 브리지 연결 상태 */
  conn: { state: ConnState; detail: string } | null;
  gcs: string | null;
  status: SimStatus | null;
  /** 최신 truth/state 기준 (status는 1 Hz로 오므로 시각 표시는 truth를 쓴다) */
  simTimeUs: bigint;
  frame: bigint;
  entityCount: number;
  mapStatus: MapDataStatus | null;
  viewMode: ViewMode;
  onViewMode(m: ViewMode): void;
  onStart(): void;
  onPause(): void;
  onResume(): void;
  onStep(): void;
  onReset(): void;
  onRate(r: number): void;
  onFit(): void;
}

const VIEW_LABEL: Record<ViewMode, string> = { "3d": "3D", columbus: "2.5D", "2d": "2D" };
const RATES = [1, 2, 5, 10];

const STATE_LABEL: Partial<Record<SimRunState, string>> = {
  [SimRunState.IDLE]: "대기",
  [SimRunState.LOADED]: "적재",
  [SimRunState.RUNNING]: "실행",
  [SimRunState.PAUSED]: "정지",
  [SimRunState.STOPPED]: "종료",
};

function fmtTime(us: bigint): string {
  const s = Number(us / 1000n) / 1000;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${sec.toFixed(1).padStart(4, "0")}`;
}

const CONN_LABEL: Record<ConnState, string> = { connecting: "연결 중", open: "연결", closed: "끊김" };

export function Toolbar(p: Props) {
  const { source, onSource, conn, gcs, status, simTimeUs, frame, entityCount, mapStatus, viewMode, onViewMode, onRate, onFit } = p;
  const state = status?.state;
  const running = state === SimRunState.RUNNING;
  const loaded = state === SimRunState.LOADED;
  const paused = state === SimRunState.PAUSED;
  return (
    <div className="toolbar">
      <strong className="brand">Swarm GCS</strong>
      <div className="group">
        {(Object.keys(VIEW_LABEL) as ViewMode[]).map((m) => (
          <button key={m} className={viewMode === m ? "on" : undefined} onClick={() => onViewMode(m)}>
            {VIEW_LABEL[m]}
          </button>
        ))}
        <button onClick={onFit} title="전체 보기">전체</button>
      </div>
      <div className="group">
        {loaded ? (
          <button onClick={p.onStart}>시작</button>
        ) : (
          <button onClick={running ? p.onPause : p.onResume} disabled={!running && !paused}>{running ? "일시정지" : "재개"}</button>
        )}
        <button onClick={p.onStep} disabled={!paused} title="한 프레임 진행">스텝</button>
        <button onClick={p.onReset} disabled={!status || state === SimRunState.IDLE} title="처음 상태로">리셋</button>
        {RATES.map((r) => (
          <button key={r} className={status?.rateTarget === r ? "on" : undefined} onClick={() => onRate(r)} disabled={!status}>
            ×{r}
          </button>
        ))}
      </div>
      <div className="group">
        <select value={source} onChange={(e) => onSource(e.target.value as SourceKind)} title="데이터 소스">
          <option value="mock">목 소스</option>
          <option value="bus">버스(브리지)</option>
        </select>
      </div>
      <div className="stat">
        {conn && <span className={`conn conn-${conn.state}`} title={conn.detail}>{CONN_LABEL[conn.state]}</span>}
        {gcs && <span className="muted">{gcs}</span>}
        <span>{status ? STATE_LABEL[status.state] ?? "?" : "-"}</span>
        <span>T {fmtTime(simTimeUs)}</span>
        <span>F {frame.toString()}</span>
        <span>엔티티 {entityCount}</span>
        {mapStatus && (
          <span className="muted">
            지도 {mapStatus.imagery === "local" ? "로컬" : "내장"} · 지형 {mapStatus.terrain === "local" ? "DEM" : "타원체"}
          </span>
        )}
      </div>
    </div>
  );
}
