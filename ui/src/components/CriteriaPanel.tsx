// IMP-UI-091: 교전 기준 배포 (L1 MP, swarm/<gcs>/tx/mp/EngagementCriteria). 기본 MA는 실행 중 받은 기준으로 바꿔
// 이후 타격의 승인 필요 여부(require_approval)와 진영·무기 사용 영역·타격 금지 영역 판단에 쓴다 (common.py needs_approval·engagement_reason).
// 영역은 원으로, 중심은 마지막으로 우클릭한 지도 지점이다.
import { useState } from "react";
import { Side } from "../gen/swarm/v1/entity_pb";
import type { AreaSpec, CriteriaSpec, GeoPoint } from "../model/commands";
import { sideLabel } from "../model/entityView";

interface Props {
  value: CriteriaSpec;
  onChange(c: CriteriaSpec): void;
  /** 영역 중심으로 쓸 지점 (마지막 우클릭). 없으면 영역을 더할 수 없다 */
  point: GeoPoint | null;
  /** 받을 기체 수와 그 설명 */
  dstCount: number;
  dstLabel: string;
  disabledReason: string | null;
  onSend(): void;
}

const SIDES = [Side.RED, Side.BLUE, Side.NEUTRAL, Side.UNSPECIFIED];

function AreaList(p: { title: string; areas: AreaSpec[]; onChange(a: AreaSpec[]): void; point: GeoPoint | null }) {
  const [r, setR] = useState(3000);
  return (
    <div className="crit-areas">
      <div className="cmd-row">
        <span>{p.title} {p.areas.length}</span>
        <input type="number" min={100} step={500} value={r} onChange={(e) => setR(Math.max(100, Number(e.target.value) || 0))} title="반경(m)" />
        <span className="muted">m</span>
        <button
          disabled={!p.point}
          title={p.point ? "마지막 우클릭 지점을 중심으로 원 영역을 더한다" : "지도를 우클릭해 중심을 찍는다"}
          onClick={() => p.point && p.onChange([...p.areas, { center: p.point, radiusM: r }])}
        >
          추가
        </button>
      </div>
      {p.areas.map((a, i) => (
        <div key={i} className="crit-area muted">
          {a.center.latDeg.toFixed(4)}, {a.center.lonDeg.toFixed(4)} r{a.radiusM.toFixed(0)}
          <button className="link" onClick={() => p.onChange(p.areas.filter((_, j) => j !== i))}>삭제</button>
        </div>
      ))}
    </div>
  );
}

export function CriteriaPanel(p: Props) {
  const c = p.value;
  const toggle = (s: Side) =>
    p.onChange({ ...c, hostileSides: c.hostileSides.includes(s) ? c.hostileSides.filter((x) => x !== s) : [...c.hostileSides, s] });
  return (
    <details className="tester">
      <summary>
        교전 기준 배포 <span className="muted">tx/mp</span>
      </summary>
      <div className="cmd-row" title="hostile_sides: 표적 ID가 있는 타격은 표적 진영이 이 안이어야 한다. 비우면 보지 않는다">
        <span className="muted">적대 진영</span>
        {SIDES.map((s) => (
          <label key={s} className="check">
            <input type="checkbox" checked={c.hostileSides.includes(s)} onChange={() => toggle(s)} /> {sideLabel(s)}
          </label>
        ))}
      </div>
      <div className="cmd-row">
        <label className="check" title="require_approval: 타격 전 GCS 승인(ApprovalRequest)을 받는다">
          <input type="checkbox" checked={c.requireApproval} onChange={(e) => p.onChange({ ...c, requireApproval: e.target.checked })} /> 타격 전 승인 필요
        </label>
      </div>
      <AreaList title="무기 사용 영역" areas={c.weaponsFree} point={p.point} onChange={(weaponsFree) => p.onChange({ ...c, weaponsFree })} />
      <AreaList title="타격 금지 영역" areas={c.noStrike} point={p.point} onChange={(noStrike) => p.onChange({ ...c, noStrike })} />
      <div className="cmd-row">
        <button className="primary" disabled={p.disabledReason !== null || p.dstCount === 0} title={p.disabledReason ?? p.dstLabel} onClick={p.onSend}>
          배포 ({p.dstCount}대)
        </button>
        <span className="muted">{p.dstLabel}</span>
      </div>
    </details>
  );
}
