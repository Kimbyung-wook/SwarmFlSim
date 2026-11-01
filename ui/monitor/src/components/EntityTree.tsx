// IMP-MON-018: 엔티티 트리 (비행체/지상체 → 진영). 클릭은 상세 선택, 체크는 엔티티 필터 (REQ-UI-005, PRP-UI-002)
import type { Filter } from "../model/filter";
import { toggle } from "../model/filter";
import { fmtPct, fmtRate } from "../model/format";
import { CLASS_LABEL, KIND_LABEL, SIDE_LABEL } from "../model/labels";
import type { MonitorStore } from "../model/store";
import { buildTree } from "../model/tree";

export function EntityTree(props: {
  store: MonitorStore;
  filter: Filter;
  selected?: string;
  onSelect: (id: string) => void;
  onFilter: (f: Filter) => void;
}) {
  const { store, filter } = props;
  const tree = buildTree(store.entities.values());
  const now = store.agg.nowUs;
  const setGroup = (ids: string[], on: boolean) => {
    const n = new Set(filter.entities);
    for (const id of ids) {
      if (on) n.add(id);
      else n.delete(id);
    }
    props.onFilter({ ...filter, entities: n });
  };
  return (
    <div className="tree">
      <div className="panel-title">엔티티 ({store.entities.size})</div>
      {tree.length === 0 && <div className="muted pad">수신한 엔티티가 없다</div>}
      {tree.map((g) => (
        <div key={g.cls} className="tree-class">
          <div className="tree-head">
            {CLASS_LABEL[g.cls]} <span className="muted">{g.count}</span>
          </div>
          {g.sides.map((s) => {
            const ids = s.entities.map((e) => e.id);
            const all = ids.every((id) => filter.entities.has(id));
            return (
              <div key={s.side} className="tree-side">
                <label className={`tree-sub side-${s.side}`}>
                  <input type="checkbox" checked={all} onChange={() => setGroup(ids, !all)} />
                  {SIDE_LABEL[s.side]} <span className="muted">{ids.length}</span>
                </label>
                {s.entities.map((e) => {
                  const st = store.agg.entities.get(e.id);
                  const txr = st ? st.envTxWin.rates(now).perS : 0;
                  const loss = st ? st.tx.lossRate() : 0;
                  return (
                    <div
                      key={e.id}
                      className={`tree-item ${props.selected === e.id ? "sel" : ""} ${e.alive ? "" : "dead"}`}
                      onClick={() => props.onSelect(e.id)}
                    >
                      <input
                        type="checkbox"
                        checked={filter.entities.has(e.id)}
                        onClick={(ev) => ev.stopPropagation()}
                        onChange={() => props.onFilter({ ...filter, entities: toggle(filter.entities, e.id) })}
                      />
                      <span className="id">{e.id}</span>
                      <span className="kind">{KIND_LABEL[e.kind]}</span>
                      {st && (
                        <span className="mini" title="송신 msg/s · 송신 손실률">
                          {fmtRate(txr)}/s {loss > 0 && <em className={loss > 0.2 ? "bad" : ""}>{fmtPct(loss)}</em>}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
