// IMP-UI-018: 상단 도구 막대. 2D/3D 전환(REQ-UI-001), 시뮬레이션 상태와 일시정지·배속(sim/ctrl/cmd, DEC-014)
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import { SimRunState } from "../gen/swarm/v1/sim_pb";
import type { MapDataStatus } from "../cesium/viewer";
import type { ViewMode } from "./MapView";

interface Props {
  source: string;
  status: SimStatus | null;
  /** 최신 truth/state 기준 (status는 1 Hz로 오므로 시각 표시는 truth를 쓴다) */
  simTimeUs: bigint;
  frame: bigint;
  entityCount: number;
  mapStatus: MapDataStatus | null;
  viewMode: ViewMode;
  onViewMode(m: ViewMode): void;
  onPause(): void;
  onResume(): void;
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

export function Toolbar({ source, status, simTimeUs, frame, entityCount, mapStatus, viewMode, onViewMode, onPause, onResume, onRate, onFit }: Props) {
  const running = status?.state === SimRunState.RUNNING;
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
        <button onClick={running ? onPause : onResume} disabled={!status}>{running ? "일시정지" : "재개"}</button>
        {RATES.map((r) => (
          <button key={r} className={status?.rateTarget === r ? "on" : undefined} onClick={() => onRate(r)} disabled={!status}>
            ×{r}
          </button>
        ))}
      </div>
      <div className="stat">
        <span>{source}</span>
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
