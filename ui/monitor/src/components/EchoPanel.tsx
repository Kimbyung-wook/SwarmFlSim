// IMP-MON-021: 메시지 echo. 최근 tx/rx 엔벨로프 목록과 protobuf 해석 결과 (REQ-UI-005, PRP-UI-002)
// 해석은 고른 항목에만 한다(부하).
import { useMemo, useRef, useState } from "react";
import type { LinkOutcome } from "../gen/swarm/v1/link_pb";
import { LinkOutcomeKind } from "../gen/swarm/v1/link_pb";
import { decodePayload } from "../model/decode";
import type { Filter } from "../model/filter";
import { matchEnvelope } from "../model/filter";
import { fmtMs, fmtSimTime, stringifyJson } from "../model/format";
import { DROP_COLOR, DROP_LABEL, IFACE_KEY, shortType } from "../model/labels";
import type { EnvelopeRecord, MonitorStore } from "../model/store";

const LIST_MAX = 200;

function EnvelopeView({ rec }: { rec: EnvelopeRecord }) {
  const e = rec.env;
  const dec = decodePayload(e.msgType, e.payload);
  const head = {
    key: rec.key,
    header: e.header ? { simTimeUs: e.header.simTimeUs, frame: e.header.frame, source: e.header.source, seq: e.header.seq, correlationId: e.header.correlationId || undefined } : undefined,
    dst: e.dst.length ? e.dst : "(브로드캐스트)",
    iface: IFACE_KEY[e.iface],
    msgType: e.msgType,
    priority: e.priority,
    rxTimeUs: e.rxTimeUs || undefined,
    payloadBytes: e.payload.length,
  };
  return (
    <>
      <div className="echo-h">LinkEnvelope</div>
      <pre>{stringifyJson(head)}</pre>
      <div className="echo-h">payload · {shortType(dec.typeName)}</div>
      {dec.error ? <div className="bad pad">{dec.error}</div> : <pre>{stringifyJson(dec.json)}</pre>}
    </>
  );
}

function OutcomeView({ o }: { o: LinkOutcome }) {
  const dropped = o.outcome === LinkOutcomeKind.DROPPED;
  const lat = dropped ? 0 : Number(o.rxTimeUs - o.txTimeUs);
  return (
    <div className="outcome-box">
      <b>
        {o.src} → {o.dst}
      </b>{" "}
      #{o.seq} · {IFACE_KEY[o.iface]} · {shortType(o.msgType)} · {o.sizeBytes} B
      <br />
      tx {fmtSimTime(o.txTimeUs)} ·{" "}
      {dropped ? (
        <span style={{ color: DROP_COLOR[o.reason] }}>손실: {DROP_LABEL[o.reason]}</span>
      ) : (
        <span className="ok">전달 · 지연 {fmtMs(lat)} ms</span>
      )}
    </div>
  );
}

export function EchoPanel(props: { store: MonitorStore; filter: Filter; frozen: boolean; picked?: LinkOutcome; onClearPick: () => void }) {
  const { store, filter, picked } = props;
  const [sel, setSel] = useState<EnvelopeRecord | undefined>();
  const [dirs, setDirs] = useState<"all" | "tx" | "rx">("tx");
  const snapshot = useRef<EnvelopeRecord[]>([]);
  if (!props.frozen) {
    snapshot.current = store.echo.newest(LIST_MAX, (r) => (dirs === "all" || r.dir === dirs) && matchEnvelope(filter, r.dir, r.entity, r.env));
  }
  const list = snapshot.current;
  // 고른 순간에 찾아 둔다(화면 정지 중에 보관분에서 밀려나도 보이도록)
  const pickedEnv = useMemo(() => (picked ? store.envelopeFor(picked) : undefined), [store, picked]);
  const shown = picked ? pickedEnv : sel;
  return (
    <div className="echo">
      <div className="panel-title">
        메시지 echo
        <span className="tabs">
          {(["tx", "rx", "all"] as const).map((d) => (
            <button key={d} className={dirs === d ? "on" : ""} onClick={() => setDirs(d)}>
              {d === "all" ? "전체" : d}
            </button>
          ))}
        </span>
        <span className="muted small">최근 {list.length}건</span>
      </div>
      <div className="echo-list">
        <table>
          <tbody>
            {list.map((r, i) => (
              <tr
                key={`${r.key}#${r.seq}#${r.entity}#${i}`}
                className={sel === r && !picked ? "sel" : ""}
                onClick={() => {
                  props.onClearPick();
                  setSel(r);
                }}
              >
                <td className="mono">{fmtSimTime(r.tUs).slice(3)}</td>
                <td className={r.dir}>{r.dir}</td>
                <td className="id">{r.dir === "tx" ? r.src : `${r.src}→${r.entity}`}</td>
                <td>{IFACE_KEY[r.iface]}</td>
                <td>{shortType(r.msgType)}</td>
                <td className="mono">#{r.seq}</td>
                <td className="mono">{r.bytes} B</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="echo-detail">
        {picked && (
          <>
            <div className="echo-h">
              타임라인에서 고른 전송 <button onClick={props.onClearPick}>✕</button>
            </div>
            <OutcomeView o={picked} />
            {!pickedEnv && <div className="muted pad">송신 엔벨로프가 보관분에 없다(밀려났거나 tx를 받지 못함)</div>}
          </>
        )}
        {shown ? <EnvelopeView rec={shown} /> : !picked && <div className="muted pad">목록이나 타임라인 화살표를 고르면 내용을 해석해 보여준다</div>}
      </div>
    </div>
  );
}
