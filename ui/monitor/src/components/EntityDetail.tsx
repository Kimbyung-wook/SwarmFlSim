// IMP-MON-022: 엔티티 상세. 메시지 타입별 송수신, 상대별 손실, 링크 상태 (REQ-UI-005, PRP-UI-002, PRP-LNK-002)
import { LinkStateKind } from "../gen/swarm/v1/link_pb";
import type { TypeStats } from "../model/aggregator";
import { fmtBytes, fmtPct } from "../model/format";
import { DROP_COLOR, DROP_LABEL, IFACE_KEY, KIND_LABEL, SIDE_LABEL, shortType } from "../model/labels";
import type { MonitorStore } from "../model/store";

const LINK_LABEL: Record<LinkStateKind, string> = {
  [LinkStateKind.UNSPECIFIED]: "?",
  [LinkStateKind.UP]: "UP",
  [LinkStateKind.DEGRADED]: "DEGRADED",
  [LinkStateKind.DOWN]: "DOWN",
};

function TypeTable({ title, m }: { title: string; m: Map<string, TypeStats> }) {
  const rows = [...m.values()].sort((a, b) => b.total - a.total);
  return (
    <>
      <div className="echo-h">{title}</div>
      <table>
        <thead>
          <tr>
            <th>메시지</th>
            <th>if</th>
            <th>건수</th>
            <th>크기</th>
            <th>손실률</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.msgType}>
              <td>{shortType(t.msgType)}</td>
              <td>{IFACE_KEY[t.iface]}</td>
              <td>{t.total}</td>
              <td>{fmtBytes(t.bytes)}</td>
              <td className={t.dropped / t.total > 0.2 ? "bad" : ""}>{fmtPct(t.dropped / t.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function EntityDetail(props: { store: MonitorStore; id: string; onClose: () => void }) {
  const { store, id } = props;
  const info = store.entities.get(id);
  const st = store.agg.entities.get(id);
  const links = [...store.linkStates.values()].filter((s) => s.a === id || s.b === id).sort((x, y) => x.state - y.state || x.a.localeCompare(y.a));
  const pairs = [...store.agg.pairs.values()].filter((p) => p.src === id || p.dst === id).filter((p) => p.dropped > 0);
  pairs.sort((a, b) => b.dropped / b.total - a.dropped / a.total);
  return (
    <div className="detail">
      <div className="panel-title">
        {id}{" "}
        <span className="muted small">
          {info ? `${KIND_LABEL[info.kind]} · ${SIDE_LABEL[info.side]}${info.alive ? "" : " · 파괴"}${info.fromTruth ? "" : " · truth 미확인"}` : ""}
        </span>
        <button className="right-btn" onClick={props.onClose}>
          ✕
        </button>
      </div>
      <div className="detail-body">
        {st ? (
          <>
            <TypeTable title="송신 (메시지 타입별 outcome)" m={st.txTypes} />
            <TypeTable title="수신 (메시지 타입별 outcome)" m={st.rxTypes} />
          </>
        ) : (
          <div className="muted pad">트래픽 없음</div>
        )}
        {pairs.length > 0 && (
          <>
            <div className="echo-h">손실이 있는 상대 (누적)</div>
            <table>
              <tbody>
                {pairs.slice(0, 20).map((p) => (
                  <tr key={`${p.src}>${p.dst}`}>
                    <td className="id">
                      {p.src} → {p.dst}
                    </td>
                    <td>
                      {p.dropped}/{p.total}
                    </td>
                    <td>{fmtPct(p.dropped / p.total)}</td>
                    <td style={{ color: DROP_COLOR[p.lastReason as keyof typeof DROP_COLOR] }}>최근 {DROP_LABEL[p.lastReason as keyof typeof DROP_LABEL] ?? "?"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {links.length > 0 && (
          <>
            <div className="echo-h">링크 상태 (link/state)</div>
            <table>
              <thead>
                <tr>
                  <th>상대</th>
                  <th>상태</th>
                  <th>SNR dB</th>
                  <th>손실률</th>
                  <th>LOS</th>
                  <th>재밍</th>
                </tr>
              </thead>
              <tbody>
                {links.map((s) => (
                  <tr key={`${s.a}|${s.b}`}>
                    <td className="id">{s.a === id ? s.b : s.a}</td>
                    <td className={`link-${s.state}`}>{LINK_LABEL[s.state]}</td>
                    <td>{s.snrDb.toFixed(1)}</td>
                    <td>{fmtPct(s.lossRate)}</td>
                    <td>{s.los ? "○" : <span className="bad">✕</span>}</td>
                    <td>{s.jammed ? <span className="bad">●</span> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
