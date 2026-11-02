// IMP-UI-031: 명령 패널. 선택한 기체에 Hold·RTB TaskCommand, 편대 FormationCommand, 부대 그룹 지정·호출 (REQ-UI-002~004)
// 지도 임무는 우클릭 임무 창(IMP-UI-039). 보낸 항로는 여기서 다시 편집한다(IMP-UI-040). 명령 상태는 swarm/<gcs>/rx/**의 TaskStatus로 표시한다.
import { useState } from "react";
import { FormationShape } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import type { GroupSlot } from "../model/groups";
import type { TaskEntry } from "../model/taskLog";
import { commandStateLabel } from "../model/taskLog";
import type { RxView } from "../model/taskLog";

/** 거부·실패는 사유를 툴팁이 아니라 본문에 보인다 */
const isBad = (s: CommandState) => s === CommandState.REJECTED || s === CommandState.FAILED;

interface Props {
  /** 명령 대상(선택 중 아군 기체) */
  targets: readonly string[];
  /** 명령을 보낼 수 있는지와, 없으면 그 이유 */
  disabledReason: string | null;
  groups: [GroupSlot, readonly string[]][];
  tasks: TaskEntry[];
  rx: readonly RxView[];
  onHold(): void;
  onRtb(): void;
  onFormation(shape: FormationShape, spacingM: number): void;
  onAssignGroup(slot: GroupSlot): void;
  onRecallGroup(slot: GroupSlot): void;
  /** 보낸 항로를 다시 편집 */
  onEditRoute(t: TaskEntry): void;
}

const SHAPES: [FormationShape, string][] = [
  [FormationShape.LINE, "횡대"],
  [FormationShape.COLUMN, "종대"],
  [FormationShape.WEDGE, "쐐기"],
  [FormationShape.ECHELON, "제형"],
  [FormationShape.CIRCLE, "원형"],
];

function fmtSim(us: bigint): string {
  return `${(Number(us / 1000n) / 1000).toFixed(1)} s`;
}

export function CommandPanel(p: Props) {
  const [shape, setShape] = useState(FormationShape.WEDGE);
  const [spacing, setSpacing] = useState(150);
  const off = p.disabledReason !== null || p.targets.length === 0;
  const title = p.disabledReason ?? (p.targets.length === 0 ? "아군 기체를 선택한다" : `${p.targets.length}대`);
  return (
    <section className="cmd">
      <header className="panel-head">
        <span>명령 {p.targets.length ? `· ${p.targets.length}대` : ""}</span>
        {p.disabledReason && <span className="muted">{p.disabledReason}</span>}
      </header>
      <div className="cmd-row">
        <button disabled={off} title={title} onClick={p.onHold}>대기(Hold)</button>
        <button disabled={off} title={title} onClick={p.onRtb}>귀환(RTB)</button>
        <span className="muted">임무: 지도 우클릭 · 항로: Ctrl+우클릭</span>
      </div>
      <div className="cmd-row">
        <select value={shape} onChange={(e) => setShape(Number(e.target.value) as FormationShape)}>
          {SHAPES.map(([s, l]) => (
            <option key={s} value={s}>{l}</option>
          ))}
        </select>
        <input
          type="number"
          min={10}
          step={10}
          value={spacing}
          onChange={(e) => setSpacing(Math.max(10, Number(e.target.value) || 0))}
          title="간격(m)"
        />
        <span className="muted">m</span>
        <button disabled={off || p.targets.length < 2} title={title} onClick={() => p.onFormation(shape, spacing)}>
          편대 지정
        </button>
      </div>
      <div className="cmd-row groups" title="Ctrl/Alt+숫자: 선택을 그룹으로 지정, 숫자: 호출">
        {p.groups.length === 0 ? (
          <span className="muted">그룹: Ctrl(또는 Alt)+숫자로 지정, 숫자로 호출</span>
        ) : (
          p.groups.map(([slot, m]) => (
            <button key={slot} onClick={() => p.onRecallGroup(slot)} title={m.join(", ")}>
              {slot} <span className="muted">({m.length})</span>
            </button>
          ))
        )}
        {p.targets.length > 0 && p.disabledReason === null && (
          <select
            value=""
            onChange={(e) => e.target.value && p.onAssignGroup(e.target.value as GroupSlot)}
            title="선택을 그룹으로 지정"
          >
            <option value="">그룹 지정…</option>
            {(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"] as GroupSlot[]).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}
      </div>
      <ul className="task-list">
        {p.tasks.map((t) => (
          <li key={t.id} className={t.error ? "task-err" : undefined}>
            <div className="task-head">
              <b>{t.summary}</b>
              <span className="muted">{t.assignees.length}대</span>
              <span className="muted task-id">{t.id}</span>
              {t.mission?.kind === "route" && !t.error && (
                <button className="link" onClick={() => p.onEditRoute(t)} title="항로를 다시 편집해 같은 task_id로 보낸다">편집</button>
              )}
            </div>
            {t.error ? (
              <div className="task-reports">전송 실패: {t.error}</div>
            ) : (
              <div className="task-reports">
                {t.reports.size === 0 ? (
                  <span className="muted">응답 없음</span>
                ) : (
                  [...t.reports].map(([src, r]) => (
                    <span key={src} className={isBad(r.state) ? "task-bad" : undefined} title={`${r.reason} @${fmtSim(r.simTimeUs)}`}>
                      {src} {commandStateLabel(r.state)}
                      {r.progress > 0 ? ` ${(r.progress * 100).toFixed(0)}%` : ""}
                      {isBad(r.state) && r.reason ? ` (${r.reason})` : ""}
                    </span>
                  ))
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {p.rx.length > 0 && (
        <details className="rx-log">
          <summary>수신 {p.rx.length}</summary>
          <ul>
            {p.rx.map((r, i) => (
              <li key={i}>
                <span>{r.source}</span> <span className="muted">{r.msgType.replace("swarm.v1.", "")} {r.size} B · {fmtSim(r.simTimeUs)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
