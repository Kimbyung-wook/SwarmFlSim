// IMP-MON-016, IMP-MON-024: 머리줄. 연결 상태, 실시간/재생(MCAP) 표시(SimStatus.replay), 시뮬레이션 시각, 처리 부하 (REQ-UI-005, PRP-UI-002)
import type { SourceStatus } from "../bridge/source";
import { RunMode, SimRunState } from "../gen/swarm/v1/sim_pb";
import { fmtRate, fmtSimTime } from "../model/format";
import type { MonitorStore, ViewSource } from "../model/store";

export interface Load {
  framesPerS: number;
  busyPct: number;
}

const STATE_LABEL: Record<SimRunState, string> = {
  [SimRunState.UNSPECIFIED]: "?",
  [SimRunState.IDLE]: "대기",
  [SimRunState.LOADED]: "적재",
  [SimRunState.RUNNING]: "실행",
  [SimRunState.PAUSED]: "일시정지",
  [SimRunState.STOPPED]: "정지",
};
const MODE_LABEL: Record<RunMode, string> = {
  [RunMode.UNSPECIFIED]: "?",
  [RunMode.REALTIME]: "실시간",
  [RunMode.LOCKSTEP]: "lockstep",
  [RunMode.FREERUN]: "free-run",
};
const VIEW_SOURCE_LABEL: Record<ViewSource, string> = {
  status: "SimStatus.replay 기준",
  query: "SimStatus 수신 전, ?replay=1 기준",
  manual: "수동 전환. SimStatus.replay가 바뀌면 자동으로 돌아간다",
};
const CONN_LABEL: Record<SourceStatus["state"], string> = {
  idle: "대기",
  connecting: "연결 중",
  open: "연결됨",
  closed: "끊김",
  error: "오류",
};

export function Header(props: {
  store: MonitorStore;
  sourceName: string;
  status: SourceStatus;
  load: Load;
  frozen: boolean;
  onFreeze: () => void;
  onClear: () => void;
  onToggleView: () => void;
  onMockRestart?: () => void;
}) {
  const { store, status, load } = props;
  const st = store.status;
  const replay = store.view === "replay";
  return (
    <header className="header">
      <span className="title">Traffic Monitor</span>
      <button className={`badge ${replay ? "badge-replay" : "badge-live"}`} onClick={props.onToggleView} title={`실시간/재생 표시 전환 (${VIEW_SOURCE_LABEL[store.viewSource]})`}>
        {replay ? "▶ 재생 (MCAP)" : "● 실시간"}
      </button>
      <span className={`conn conn-${status.state}`} title={status.detail}>
        {props.sourceName === "mock" ? "목" : "브리지"} · {CONN_LABEL[status.state]}
        {status.contract ? ` · 계약 ${status.contract}` : ""}
      </span>
      <span className="sep" />
      <span className="kv">
        sim <b>{fmtSimTime(store.clockUs || store.agg.nowUs)}</b>
      </span>
      {st && (
        <span className="kv">
          {STATE_LABEL[st.state]} · {MODE_LABEL[st.mode]} · {st.frameHz} Hz · ×{st.rateActual.toFixed(2)}
          {st.scenarioName ? ` · ${st.scenarioName}` : ""}
        </span>
      )}
      {store.rewinds > 0 && <span className="kv warn">되감기 {store.rewinds}회</span>}
      {store.missedFrames > 0 && (
        <span className="kv warn" title="truth/state 프레임 번호의 공백. MCAP 재생은 배압이 없어 고배속에서 프레임 누락을 허용한다(DEC-042)">
          프레임 누락 {store.missedFrames}
        </span>
      )}
      {st && st.waitingParticipants.length > 0 && (
        <span className="kv warn" title="lockstep에서 FrameDone이 5 s 넘게 없는 참여자(DEC-041)">
          응답 없음 {st.waitingParticipants.join(", ")}
        </span>
      )}
      {store.linkLagUs > 1_000_000 && (
        <span className="kv warn" title="outcome을 받은 순간의 (sim 시각 − 그 outcome의 tx 시각). 둘 다 sim 시각이라 재생 배속과 무관하다. outcome이 없는 구간은 지연으로 보지 않는다">
          링크 지연 {(store.linkLagUs / 1e6).toFixed(1)} s
        </span>
      )}
      <span className="sep" />
      <span className="kv" title="수신 프레임 처리율과 처리에 쓴 시간 비율(벽시계)">
        {fmtRate(load.framesPerS)} 프레임/s · 처리 {load.busyPct.toFixed(1)}%
      </span>
      {store.ignored > 0 && (
        <span className="kv warn" title={store.lastIgnored}>
          무시 {store.ignored}
        </span>
      )}
      <button onClick={props.onFreeze} className={props.frozen ? "on" : ""}>
        {props.frozen ? "화면 재개" : "화면 정지"}
      </button>
      <button onClick={props.onClear}>통계 초기화</button>
      {props.onMockRestart && (
        <button onClick={props.onMockRestart} title="목 생성기를 0 s부터 다시 시작(재생 되감기 흉내)">
          목 되감기
        </button>
      )}
    </header>
  );
}
