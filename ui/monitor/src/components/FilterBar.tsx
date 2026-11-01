// IMP-MON-017: 필터 막대 (엔티티 모드·인터페이스·메시지 타입·결과) (REQ-UI-005, PRP-UI-002)
import type { Filter, OutcomeKey } from "../model/filter";
import { EMPTY_FILTER, isEmptyFilter, toggle } from "../model/filter";
import { DROP_COLOR, DROP_LABEL, DROP_REASONS, IFACE_KEY, IFACES, shortType } from "../model/labels";
import type { MonitorStore } from "../model/store";

export function FilterBar(props: { store: MonitorStore; filter: Filter; onChange: (f: Filter) => void }) {
  const { filter: f, onChange } = props;
  const types = [...props.store.msgTypes].sort((a, b) => shortType(a).localeCompare(shortType(b)));
  const chip = (on: boolean, label: string, onClick: () => void, color?: string) => (
    <button key={label} className={`chip ${on ? "on" : ""}`} onClick={onClick} style={color && on ? { borderColor: color, color } : undefined}>
      {color && <i className="dot" style={{ background: color }} />}
      {label}
    </button>
  );
  const oc = (k: OutcomeKey) => () => onChange({ ...f, outcomes: toggle(f.outcomes, k) });
  return (
    <div className="filterbar">
      <span className="group">
        <label>엔티티</label>
        {f.entities.size === 0 ? (
          <span className="muted">전체 (트리에서 체크)</span>
        ) : (
          <>
            <span className="muted">{[...f.entities].join(", ")}</span>
            <select value={f.entityMode} onChange={(e) => onChange({ ...f, entityMode: e.target.value as Filter["entityMode"] })}>
              <option value="any">송신 또는 수신</option>
              <option value="src">송신자</option>
              <option value="dst">수신자</option>
            </select>
          </>
        )}
      </span>
      <span className="group">
        <label>인터페이스</label>
        {IFACES.map((i) => chip(f.ifaces.has(i), IFACE_KEY[i], () => onChange({ ...f, ifaces: toggle(f.ifaces, i) })))}
      </span>
      <span className="group">
        <label>메시지</label>
        <select
          value=""
          onChange={(e) => e.target.value && onChange({ ...f, msgTypes: toggle(f.msgTypes, e.target.value) })}
        >
          <option value="">{f.msgTypes.size ? `${f.msgTypes.size}개 선택` : "전체"}</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {f.msgTypes.has(t) ? "✓ " : ""}
              {shortType(t)}
            </option>
          ))}
        </select>
        {[...f.msgTypes].map((t) => chip(true, `${shortType(t)} ✕`, () => onChange({ ...f, msgTypes: toggle(f.msgTypes, t) })))}
      </span>
      <span className="group">
        <label>결과</label>
        {chip(f.outcomes.has("delivered"), "전달", oc("delivered"), "#4caf50")}
        {DROP_REASONS.map((r) => chip(f.outcomes.has(r), DROP_LABEL[r], oc(r), DROP_COLOR[r]))}
      </span>
      {!isEmptyFilter(f) && <button onClick={() => onChange(EMPTY_FILTER)}>필터 해제</button>}
    </div>
  );
}
