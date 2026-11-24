// IMP-UI-086: 승인 패널 (REQ-UI-003, DEC-075, DEC-088). 대기 중인 ApprovalRequest와 승인·거부, 최근 처리 결과
// 같은 요청에 Gateway(외부 운용자)나 다른 UI가 먼저 응답하면 그 응답이 처리된 것으로 보인다. 늦은 응답은 MA가 버린다.
import type { ApprovalAnswer, ApprovalView } from "../model/approvals";

interface Props {
  pending: ApprovalView[];
  /** 최근 처리된 요청 (응답·결과 있음) */
  recent: ApprovalView[];
  /** 남은 시간(s). null = 무한·모름 */
  remainingS(v: ApprovalView): number | null;
  /** 응답을 보낼 수 없으면 그 이유 (관찰 전용 UI 등) */
  disabledReason: string | null;
  onAnswer(v: ApprovalView, approved: boolean): void;
}

function who(a: ApprovalAnswer): string {
  return a.mine ? "이 UI" : a.by;
}

function Head({ v }: { v: ApprovalView }) {
  return (
    <div className="appr-head">
      <b>{v.requester}</b>
      <span>{v.description || v.taskId}</span>
      {v.targetId && <span className="tgt">표적 {v.targetId}</span>}
      <span className="muted task-id">{v.requestId}</span>
    </div>
  );
}

export function ApprovalPanel(p: Props) {
  if (p.pending.length === 0 && p.recent.length === 0) return null;
  return (
    <section className={`appr${p.pending.length ? " appr-wait" : ""}`}>
      <header className="panel-head">
        <span>승인 요청 {p.pending.length ? `· 대기 ${p.pending.length}` : ""}</span>
        {p.disabledReason && <span className="muted">{p.disabledReason}</span>}
      </header>
      <ul className="appr-list">
        {p.pending.map((v) => {
          const left = p.remainingS(v);
          return (
            <li key={v.requestId}>
              <Head v={v} />
              <div className="appr-row">
                <span className="muted">작업 {v.taskId}</span>
                <span className={left !== null && left < 10 ? "task-bad" : "muted"} title="MA 변수 approval_timeout_s 기준. 넘으면 MA가 REJECTED(approval timeout)">
                  {left === null ? "시간 제한 없음" : `남은 ${left.toFixed(0)} s`}
                </span>
                <span className="appr-btns">
                  <button className="ok" disabled={p.disabledReason !== null} onClick={() => p.onAnswer(v, true)} title={p.disabledReason ?? "ApprovalResponse(approved=true)"}>
                    승인
                  </button>
                  <button className="no" disabled={p.disabledReason !== null} onClick={() => p.onAnswer(v, false)} title={p.disabledReason ?? "ApprovalResponse(approved=false)"}>
                    거부
                  </button>
                </span>
              </div>
            </li>
          );
        })}
        {p.recent.map((v) => (
          <li key={v.requestId} className="appr-done">
            <Head v={v} />
            <div className="appr-row">
              {v.decision ? (
                <span className={v.decision.approved ? "param-ok" : "task-bad"}>
                  {v.decision.approved ? "승인" : "거부"} 처리 ({who(v.decision)})
                </span>
              ) : (
                <span className="muted">응답 없이 끝남</span>
              )}
              {v.outcome && <span className="muted">작업: {v.outcome}</span>}
            </div>
            {v.late.length > 0 && (
              <div className="appr-row muted" title="MA는 처음 받은 응답만 처리한다">
                늦은 응답(무시): {v.late.map((a) => `${who(a)} ${a.approved ? "승인" : "거부"}`).join(", ")}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
