// IMP-UI-047: 기체별 매개변수 패널 (REQ-CFG-003, DEC-035)
// 선택한 기체의 매개변수를 계층별로 묶어 기본값·현재값과 함께 보이고, 형식·범위를 검사해 set_params로 바꾼다.
// 적용 표시는 EntityParams.values가 바뀐 뒤에만 한다. 보낸 직후에는 "대기"만 보이고, 거부 사유는 항목에 붙는다.
import { useMemo, useState } from "react";
import type { ParamOwner } from "../gen/swarm/v1/sim_pb";
import type { ParamScalar, ParamRow, ParamStore } from "../model/params";
import {
  LAYER_LABEL,
  OWNER_LABEL,
  applied,
  composeGroups,
  formatValue,
  parseInput,
  rangeText,
  rejectLabel,
  resetValue,
} from "../model/params";

interface Props {
  store: ParamStore;
  /** store 갱신 표시(낮은 주기로 다시 그리기 위한 값) */
  version: number;
  ids: readonly string[];
  /** 보낼 수 없는 이유. 없으면 보낼 수 있다 */
  disabledReason: string | null;
  onSet(owner: ParamOwner, ids: readonly string[], values: Record<string, ParamScalar>): void;
}

interface Pending {
  value: ParamScalar;
  /** 보낸 시점의 store.version. 이후 받은 EntityParams에서 판정한다 */
  since: number;
}

type Draft = string | boolean;

function initial(row: ParamRow): Draft {
  if (row.type === "boolean") return row.common === true;
  return row.common === undefined ? "" : String(row.common);
}

export function ParamPanel({ store, version, ids, disabledReason, onSet }: Props) {
  const groups = useMemo(() => composeGroups(store, ids), [store, ids, version]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [pending, setPending] = useState<Record<string, Pending>>({});
  const selKey = ids.join(",");
  const [forSel, setForSel] = useState(selKey);
  if (forSel !== selKey) {
    // 선택이 바뀌면 입력 중이던 값과 대기 표시를 버린다
    setForSel(selKey);
    setDrafts({});
    setPending({});
  }

  const send = (row: ParamRow, value: ParamScalar) => {
    onSet(row.owner, ids, { [row.spec.name]: value });
    setPending((p) => ({ ...p, [row.key]: { value, since: store.version } }));
    setDrafts((d) => {
      const { [row.key]: _gone, ...rest } = d;
      return rest;
    });
  };

  return (
    <section className="params">
      <header className="panel-head">
        <span>매개변수{ids.length > 1 ? ` · ${ids.length}기 공통 항목` : ""}</span>
      </header>
      {groups.length === 0 ? (
        <p className="panel-empty">
          {ids.length === 0 ? "기체를 선택한다." : "선택한 기체가 내보낸 매개변수 선언이 없다 (sim/param). 여러 기체는 이름이 같은 항목만 보인다."}
        </p>
      ) : (
        <div className="params-body">
          {groups.map((g) => (
            <div key={g.layer} className="param-group">
              <h4>{LAYER_LABEL[g.layer] ?? "기타"}</h4>
              {g.rows.map((row) => {
                const pend = pending[row.key];
                const done = pend !== undefined && applied(row, pend.value);
                const answered = pend !== undefined && (done || (row.rejected !== undefined && store.version > pend.since));
                const waiting = pend !== undefined && !answered;
                const draft = drafts[row.key];
                const text = draft ?? initial(row);
                const parsed = parseInput(row.spec, text);
                const edited = draft !== undefined;
                const reset = resetValue(row);
                const blocked = disabledReason !== null || !row.spec.runtime;
                return (
                  <div key={row.key} className={`param-row${row.rejected && !done ? " rejected" : ""}`}>
                    <div className="param-name" title={row.spec.description}>
                      <b>{row.spec.name}</b>
                      <span className="muted">
                        {OWNER_LABEL[row.owner]}
                        {row.spec.unit ? ` · ${row.spec.unit}` : ""}
                        {rangeText(row.spec) ? ` · ${rangeText(row.spec)}` : ""}
                      </span>
                    </div>
                    <div className="param-vals">
                      <span className="muted">기본 {formatValue(row.defaultValue)}</span>
                      <span title={row.mixed ? row.targets.map((t) => `${t.entityId}: ${formatValue(t.value, row.spec.unit)}`).join("\n") : undefined}>
                        현재 {row.mixed ? "혼합" : formatValue(row.common)}
                      </span>
                    </div>
                    <div className="param-edit">
                      {row.type === "boolean" ? (
                        <input
                          type="checkbox"
                          checked={text === true}
                          disabled={blocked}
                          onChange={(e) => setDrafts((d) => ({ ...d, [row.key]: e.target.checked }))}
                        />
                      ) : (
                        <input
                          type="text"
                          inputMode={row.type === "number" ? "decimal" : undefined}
                          value={String(text)}
                          placeholder={row.mixed ? "혼합" : undefined}
                          disabled={blocked}
                          onChange={(e) => setDrafts((d) => ({ ...d, [row.key]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && edited && parsed.ok) send(row, parsed.value);
                          }}
                        />
                      )}
                      <button disabled={blocked || !edited || !parsed.ok} onClick={() => parsed.ok && send(row, parsed.value)} title="적용">
                        적용
                      </button>
                      <button
                        disabled={blocked || reset === null}
                        onClick={() => reset !== null && send(row, reset)}
                        title={`기본값(${formatValue(row.defaultValue, row.spec.unit)})으로`}
                      >
                        기본값
                      </button>
                    </div>
                    {!row.spec.runtime && <div className="param-note muted">실행 중에는 바꿀 수 없다 (시나리오 시작값)</div>}
                    {edited && !parsed.ok && <div className="param-note param-err">{parsed.error}</div>}
                    {waiting && <div className="param-note muted">전송됨 · 적용 확인 대기 ({formatValue(pend.value, row.spec.unit)})</div>}
                    {row.rejected && !done && (
                      <div className="param-note param-err">
                        거부: {rejectLabel(row.rejected.reason)}
                        {ids.length > 1 ? ` (${row.rejected.entityId})` : ""}
                      </div>
                    )}
                    {done && <div className="param-note param-ok">적용됨</div>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
