// IMP-MON-019: 엔티티별 송수신 통계 표 (빈도·크기·지연·손실률·손실 사유별) (REQ-UI-005, PRP-UI-002)
import { useState } from "react";
import type { DirStats, EntityStats } from "../model/aggregator";
import type { Filter } from "../model/filter";
import { fmtBytes, fmtMs, fmtPct, fmtRate } from "../model/format";
import { DROP_COLOR, DROP_LABEL, DROP_REASONS, KIND_LABEL } from "../model/labels";
import type { MonitorStore } from "../model/store";

type Dir = "tx" | "rx";
type SortKey = "id" | "rate" | "loss" | "lat";

interface Row {
  id: string;
  kind: string;
  dead: boolean;
  env: number;
  d: DirStats;
  perS: number;
  bytesPerS: number;
}

function row(store: MonitorStore, e: EntityStats, dir: Dir): Row {
  const now = store.agg.nowUs;
  const d = e[dir];
  const r = d.window.rates(now);
  const info = store.entities.get(e.id);
  return {
    id: e.id,
    kind: info ? KIND_LABEL[info.kind] : "?",
    dead: info ? !info.alive : false,
    env: (dir === "tx" ? e.envTxWin : e.envRxWin).rates(now).perS,
    d,
    perS: r.perS,
    bytesPerS: r.bytesPerS,
  };
}

export function StatsTable(props: { store: MonitorStore; filter: Filter; selected?: string; onSelect: (id: string) => void }) {
  const { store, filter } = props;
  const [dir, setDir] = useState<Dir>("tx");
  const [sort, setSort] = useState<SortKey>("id");
  let rows = [...store.agg.entities.values()]
    .filter((e) => filter.entities.size === 0 || filter.entities.has(e.id))
    .filter((e) => e[dir].total > 0 || (dir === "tx" ? e.envTx : e.envRx) > 0)
    .map((e) => row(store, e, dir));
  const cmp: Record<SortKey, (a: Row, b: Row) => number> = {
    id: (a, b) => a.id.localeCompare(b.id),
    rate: (a, b) => b.perS - a.perS,
    loss: (a, b) => b.d.lossRate() - a.d.lossRate(),
    lat: (a, b) => b.d.latMeanUs() - a.d.latMeanUs(),
  };
  rows = rows.sort(cmp[sort]);
  const all = store.agg.all;
  const allR = all.window.rates(store.agg.nowUs);
  const th = (k: SortKey, label: string, title?: string) => (
    <th className={`sortable ${sort === k ? "sorted" : ""}`} onClick={() => setSort(k)} title={title}>
      {label}
    </th>
  );
  const cells = (d: DirStats, perS: number, bytesPerS: number) => (
    <>
      <td>{fmtRate(perS)}</td>
      <td>{fmtBytes(bytesPerS)}/s</td>
      <td>{fmtMs(d.latMeanUs())}</td>
      <td>{fmtMs(d.latQuantileUs(0.95))}</td>
      <td className={d.lossRate() > 0.2 ? "bad" : d.lossRate() > 0.05 ? "warn" : ""}>{fmtPct(d.lossRate())}</td>
      {DROP_REASONS.map((r) => (
        <td key={r} className={d.drops[r] ? "reason" : "zero"} style={d.drops[r] ? { color: DROP_COLOR[r] } : undefined}>
          {d.drops[r] || "·"}
        </td>
      ))}
    </>
  );
  return (
    <div className="stats">
      <div className="panel-title">
        엔티티별 통계
        <span className="tabs">
          <button className={dir === "tx" ? "on" : ""} onClick={() => setDir("tx")}>
            송신 기준
          </button>
          <button className={dir === "rx" ? "on" : ""} onClick={() => setDir("rx")}>
            수신 기준
          </button>
        </span>
        <span className="muted small">빈도·크기: 최근 5 s(sim) · 지연·손실: 누적 · 손실 사유: 누적 건수</span>
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              {th("id", "엔티티")}
              <th>종류</th>
              <th title={dir === "tx" ? "swarm/<id>/tx/** 엔벨로프/s (브로드캐스트 1건 = 1)" : "swarm/<id>/rx/** 엔벨로프/s"}>msg/s</th>
              {th("rate", "outcome/s", "LinkOutcome/s (수신자 한 명당 1)")}
              <th>크기</th>
              {th("lat", "지연 평균 ms")}
              <th>p95 ms</th>
              {th("loss", "손실률")}
              {DROP_REASONS.map((r) => (
                <th key={r} style={{ color: DROP_COLOR[r] }}>
                  {DROP_LABEL[r]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={`${props.selected === r.id ? "sel" : ""} ${r.dead ? "dead" : ""}`} onClick={() => props.onSelect(r.id)}>
                <td className="id">{r.id}</td>
                <td>{r.kind}</td>
                <td>{fmtRate(r.env)}</td>
                {cells(r.d, r.perS, r.bytesPerS)}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>전체</td>
              <td />
              <td />
              {cells(all, allR.perS, allR.bytesPerS)}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
