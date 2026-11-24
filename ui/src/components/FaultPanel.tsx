// IMP-UI-087: 시험 진행자 메뉴 — 고장 주입 (DEC-014). C2 명령 패널과 분리된 시뮬레이션 통제(sim/ctrl/cmd)다.
// 대상은 선택한 엔티티(진영 무관). 관찰 전용 UI(GCS 미지정)에서도 쓸 수 있다 (model/faults.ts 결정 참고).
import { useState } from "react";
import { FaultKind } from "../gen/swarm/v1/sim_pb";
import type { FaultEntry } from "../model/faults";
import { FAULT_KINDS, faultLabel } from "../model/faults";

interface Props {
  /** 선택한 엔티티 */
  ids: readonly string[];
  /** 보낼 수 없으면 그 이유 (브리지 미연결) */
  disabledReason: string | null;
  active: (FaultEntry & { remainingS: number | null })[];
  onInject(ids: readonly string[], kind: FaultKind, durationS: number): void;
  onClear(id: string, kind: FaultKind): void;
}

export function FaultPanel(p: Props) {
  const [kind, setKind] = useState(FaultKind.GCS_LINK_CUT);
  const [dur, setDur] = useState(0);
  const off = p.disabledReason !== null || p.ids.length === 0;
  const hint = FAULT_KINDS.find((f) => f.kind === kind)?.hint ?? "";
  return (
    <details className="tester">
      <summary>
        시험 진행자: 고장 주입 <span className="muted">sim/ctrl/cmd{p.active.length ? ` · ${p.active.length}건` : ""}</span>
      </summary>
      <div className="cmd-row">
        <select value={kind} onChange={(e) => setKind(Number(e.target.value) as FaultKind)} title={hint}>
          {FAULT_KINDS.map((f) => (
            <option key={f.kind} value={f.kind}>{f.label}</option>
          ))}
        </select>
        {kind !== FaultKind.KILL && (
          <>
            <input
              type="number"
              min={0}
              step={5}
              value={dur}
              onChange={(e) => setDur(Math.max(0, Number(e.target.value) || 0))}
              title="지속 시간(모의 s, duration_s). 0이면 해제까지"
            />
            <span className="muted">s</span>
          </>
        )}
        <button
          className={kind === FaultKind.KILL ? "danger" : undefined}
          disabled={off}
          title={p.disabledReason ?? (p.ids.length === 0 ? "지도에서 엔티티를 선택한다" : `${p.ids.join(", ")}: ${hint}`)}
          onClick={() => p.onInject(p.ids, kind, kind === FaultKind.KILL ? 0 : dur)}
        >
          주입 ({p.ids.length})
        </button>
      </div>
      <div className="muted hint">{hint}{kind !== FaultKind.KILL && !dur ? " · 해제까지 유지" : ""}</div>
      {p.active.length > 0 && (
        <ul className="fault-list">
          {p.active.map((f) => (
            <li key={`${f.entityId}|${f.fault}`}>
              <b>{f.entityId}</b>
              <span>{faultLabel(f.fault)}</span>
              <span className="muted">{f.fault === FaultKind.KILL ? "" : f.remainingS === null ? "해제까지" : `남은 ${f.remainingS.toFixed(0)} s`}</span>
              {f.fault !== FaultKind.KILL && (
                <button className="link" disabled={p.disabledReason !== null} onClick={() => p.onClear(f.entityId, f.fault)} title="InjectFault(clear=true)">
                  해제
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
