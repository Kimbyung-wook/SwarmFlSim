// IMP-UI-075: 타격 지정의 종류 선택 라벨을 매뉴얼과 같은 "유도 객체 종류"로 (식별자·proto 필드는 그대로)
// IMP-UI-044: 레이스트랙 선회 대기(반경·직선 길이·축 방향·방향·시간), 항로점 선회의 원형/레이스트랙 선택 (DEC-034)
// IMP-UI-039: 임무 창. 우클릭 지점의 임무 메뉴(이동·선회 대기·타격·정찰)와 Ctrl+우클릭 항로점 편집 (REQ-UI-003, REQ-UI-004, DEC-033)
import { useEffect, useState } from "react";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";
import type { MissionSpec, WaypointAction, WeaponType } from "../model/commands";
import { WEAPON_TYPES } from "../model/commands";
import type { MapPoint } from "../model/mapInput";
import { DEFAULT_LOITER_RADIUS_M } from "../model/missionOverlay";
import type { RouteDraft } from "../model/routeDraft";

export type MenuKind = "moveTo" | "hold" | "racetrack" | "strike" | "search";

export interface MenuState {
  point: MapPoint;
  /** 커서 아래 적 엔티티 (타격 표적) */
  targetId: string | null;
}

const KINDS: [MenuKind, string][] = [
  ["moveTo", "이동"],
  ["hold", "선회 대기"],
  ["racetrack", "레이스트랙 선회"],
  ["strike", "타격 지정"],
  ["search", "정찰"],
];

const DIRS: [TurnDirection, string][] = [
  [TurnDirection.UNSPECIFIED, "자동"],
  [TurnDirection.CW, "시계"],
  [TurnDirection.CCW, "반시계"],
];

const WEAPON_LABEL: Record<WeaponType, string> = { aam_short: "단거리 공대공", agm_short: "단거리 공대지", fpv: "FPV 자폭" };

function fmtPoint(p: { latDeg: number; lonDeg: number }) {
  return `${p.latDeg.toFixed(5)}°N ${p.lonDeg.toFixed(5)}°E`;
}

/** 숫자 입력. 비우면 0 */
function Num(p: { value: number; onChange(v: number): void; min?: number; step?: number; title: string; unit?: string; width?: number }) {
  return (
    <label className="num" title={p.title}>
      <input
        type="number"
        min={p.min ?? 0}
        step={p.step ?? 1}
        value={Number.isFinite(p.value) ? p.value : 0}
        style={p.width ? { width: p.width } : undefined}
        onChange={(e) => p.onChange(Math.max(p.min ?? 0, Number(e.target.value) || 0))}
      />
      {p.unit && <span className="muted">{p.unit}</span>}
    </label>
  );
}

function DirSelect(p: { value: TurnDirection; onChange(d: TurnDirection): void }) {
  return (
    <select value={p.value} onChange={(e) => p.onChange(Number(e.target.value) as TurnDirection)} title="선회 방향">
      {DIRS.map(([d, l]) => (
        <option key={d} value={d}>{l}</option>
      ))}
    </select>
  );
}

interface MenuProps {
  menu: MenuState;
  targetCount: number;
  disabledReason: string | null;
  /** 기본 고도: 대상 기체 평균 */
  defaultAltM: number;
  /** 지도 미리보기용 현재 내용 */
  onPreview(spec: MissionSpec | null): void;
  onSend(spec: MissionSpec): void;
  onClose(): void;
}

export function MissionMenu(p: MenuProps) {
  const [kind, setKind] = useState<MenuKind>(p.menu.targetId ? "strike" : "moveTo");
  const [altM, setAlt] = useState(Math.round(p.defaultAltM));
  const [speed, setSpeed] = useState(0);
  const [radius, setRadius] = useState(DEFAULT_LOITER_RADIUS_M);
  const [duration, setDuration] = useState(0);
  const [dir, setDir] = useState(TurnDirection.UNSPECIFIED);
  const [weapon, setWeapon] = useState<WeaponType>("agm_short");
  const [searchR, setSearchR] = useState(1500);
  const [legM, setLegM] = useState(4000);
  const [axisDeg, setAxisDeg] = useState(90);
  const pt = p.menu.point;

  // 새 지점을 우클릭하면 표적 유무에 맞춰 기본 임무를 바꾼다
  useEffect(() => {
    setKind(p.menu.targetId ? "strike" : (k) => (k === "strike" ? "moveTo" : k));
  }, [p.menu]);

  const center = { latDeg: pt.latDeg, lonDeg: pt.lonDeg, altM };
  const spec: MissionSpec =
    kind === "moveTo"
      ? { kind, destination: center, speedMps: speed || undefined }
      : kind === "hold" || kind === "racetrack"
        ? {
            kind: "hold",
            center,
            radiusM: radius,
            durationS: duration || undefined,
            direction: dir,
            racetrack: kind === "racetrack" ? { legLengthM: legM, axisHeadingDeg: axisDeg } : undefined,
          }
        : kind === "strike"
          ? p.menu.targetId
            ? { kind, weapon, targetId: p.menu.targetId }
            : { kind, weapon, aimPoint: { latDeg: pt.latDeg, lonDeg: pt.lonDeg, altM: pt.heightM } }
          : { kind: "search", center, radiusM: searchR };

  const key = JSON.stringify(spec);
  useEffect(() => {
    p.onPreview(spec);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useEffect(() => () => p.onPreview(null), []); // eslint-disable-line react-hooks/exhaustive-deps

  const off = p.disabledReason !== null || p.targetCount === 0;
  return (
    <section className="mission">
      <header className="panel-head">
        <span>임무 · {p.targetCount}대</span>
        <button className="link" onClick={p.onClose} title="닫기 (Esc)">닫기</button>
      </header>
      <div className="mission-point">
        <span>{fmtPoint(pt)}</span>
        <span className="muted">지면 {pt.heightM.toFixed(0)} m</span>
        {p.menu.targetId && <span className="tgt">표적 {p.menu.targetId}</span>}
      </div>
      <div className="mission-kinds" role="radiogroup">
        {KINDS.map(([k, l]) => (
          <button key={k} className={k === kind ? "on" : undefined} role="radio" aria-checked={k === kind} onClick={() => setKind(k)}>
            {l}
          </button>
        ))}
      </div>
      <div className="mission-form">
        {kind !== "strike" && (
          <div className="row">
            <span>고도</span>
            <Num value={altM} onChange={setAlt} step={50} unit="m" title="목표 고도(MSL)" />
          </div>
        )}
        {kind === "moveTo" && (
          <div className="row">
            <span>속력</span>
            <Num value={speed} onChange={setSpeed} unit="m/s" title="0이면 기체 기본" />
          </div>
        )}
        {(kind === "hold" || kind === "racetrack") && (
          <>
            <div className="row">
              <span>반경</span>
              <Num value={radius} onChange={setRadius} min={50} step={50} unit="m" title="선회 반경" />
              <DirSelect value={dir} onChange={setDir} />
            </div>
            {kind === "racetrack" && (
              <div className="row">
                <span>직선</span>
                <Num value={legM} onChange={setLegM} min={100} step={500} unit="m" title="직선 구간 길이 = 두 원 중심 간 거리" />
                <span>축</span>
                <Num value={axisDeg} onChange={(v) => setAxisDeg(v % 360)} step={15} unit="°" title="축 방향 (진북 기준 시계 방향)" width={56} />
              </div>
            )}
            <div className="row">
              <span>시간</span>
              <Num value={duration} onChange={setDuration} step={30} unit="s" title="0이면 다음 명령까지" />
              <span className="muted">{duration ? "" : "다음 명령까지"}</span>
            </div>
          </>
        )}
        {kind === "strike" && (
          <>
            <div className="row">
              <span>유도 객체 종류</span>
              <select value={weapon} onChange={(e) => setWeapon(e.target.value as WeaponType)}>
                {WEAPON_TYPES.map((w) => (
                  <option key={w} value={w}>{WEAPON_LABEL[w]} ({w})</option>
                ))}
              </select>
            </div>
            <div className="row muted">
              {p.menu.targetId ? `표적 ${p.menu.targetId} (target_id)` : "조준점: 이 지점 (aim_point). 적 위를 우클릭하면 표적 지정"}
            </div>
          </>
        )}
        {kind === "search" && (
          <div className="row">
            <span>반경</span>
            <Num value={searchR} onChange={setSearchR} min={100} step={100} unit="m" title="정찰 원 반경" />
          </div>
        )}
      </div>
      <div className="cmd-row">
        <button className="primary" disabled={off} title={p.disabledReason ?? ""} onClick={() => p.onSend(spec)}>
          전송 ({p.targetCount}대)
        </button>
        <span className="muted">Esc 닫기</span>
      </div>
    </section>
  );
}

type ActionKind = WaypointAction["kind"];

function defaultAction(k: ActionKind): WaypointAction {
  if (k === "loiter") return { kind: "loiter", durationS: 120, radiusM: DEFAULT_LOITER_RADIUS_M, direction: TurnDirection.UNSPECIFIED };
  if (k === "recon") return { kind: "recon", radiusM: 1000 };
  return { kind: "none" };
}

interface RouteProps {
  draft: RouteDraft;
  targetCount: number;
  disabledReason: string | null;
  /** 선택 기체 중 flocking MA (Route 미지원, 전송은 막지 않는다. DEC-039) */
  flocking?: readonly string[];
  onAltitude(i: number, altM: number): void;
  onSpeed(i: number, v: number): void;
  onAction(i: number, a: WaypointAction): void;
  onRemove(i: number): void;
  onReorder(from: number, to: number): void;
  onLoop(loop: boolean): void;
  onSend(): void;
  onCancel(): void;
}

export function RouteEditor(p: RouteProps) {
  const n = p.draft.waypoints.length;
  const count = p.targetCount || p.draft.assignees.length;
  const off = p.disabledReason !== null || count === 0 || n === 0;
  return (
    <section className="mission route">
      <header className="panel-head">
        <span>항로 {n}점{p.draft.taskId ? ` · ${p.draft.taskId}` : ""}</span>
        <button className="link" onClick={p.onCancel} title="편집 버리기 (Esc)">취소</button>
      </header>
      <div className="muted hint">Ctrl+우클릭: 항로점 추가 · 점을 끌어 위치 변경</div>
      {p.flocking && p.flocking.length > 0 && (
        <div className="route-flock-note" title="flocking MA는 Route를 지원하지 않아 Agent가 unsupported task route로 거부한다. 거부 사유는 명령 패널에 표시된다">
          flocking 기체 {p.flocking.length}대는 항로를 지원하지 않아 거부될 수 있다
        </div>
      )}
      <ol className="wp-list">
        {p.draft.waypoints.map((w, i) => (
          <li key={i}>
            <div className="wp-head">
              <b className="wp-no">{i + 1}</b>
              <span className="muted">{fmtPoint(w.position)}</span>
              <span className="wp-tools">
                <button disabled={i === 0} onClick={() => p.onReorder(i, i - 1)} title="앞으로">↑</button>
                <button disabled={i === n - 1} onClick={() => p.onReorder(i, i + 1)} title="뒤로">↓</button>
                <button onClick={() => p.onRemove(i)} title="삭제">✕</button>
              </span>
            </div>
            <div className="row">
              <Num value={w.position.altM} onChange={(v) => p.onAltitude(i, v)} step={50} unit="m" title="고도(MSL)" width={64} />
              <Num value={w.speedMps ?? 0} onChange={(v) => p.onSpeed(i, v)} unit="m/s" title="이 항로점까지 속력. 0이면 기본" width={48} />
              <select
                value={w.action.kind}
                onChange={(e) => p.onAction(i, defaultAction(e.target.value as ActionKind))}
                title="항로점 행위"
              >
                <option value="none">통과</option>
                <option value="loiter">선회 대기</option>
                <option value="recon">정찰</option>
              </select>
            </div>
            {w.action.kind === "loiter" && (
              <div className="row sub">
                {(() => {
                  const a = w.action;
                  return (
                    <>
                      <select
                        value={a.racetrack ? "race" : "circle"}
                        onChange={(e) => p.onAction(i, { ...a, racetrack: e.target.value === "race" ? { legLengthM: 4000, axisHeadingDeg: 90 } : undefined })}
                        title="선회 모양"
                      >
                        <option value="circle">원형</option>
                        <option value="race">레이스트랙</option>
                      </select>
                      <Num value={a.durationS} onChange={(v) => p.onAction(i, { ...a, durationS: v })} step={30} unit="s" title="선회 시간" width={56} />
                      <Num value={a.radiusM ?? 0} onChange={(v) => p.onAction(i, { ...a, radiusM: v || undefined })} step={50} unit="m" title="반경. 0이면 기본" width={56} />
                      <DirSelect value={a.direction} onChange={(d) => p.onAction(i, { ...a, direction: d })} />
                      {a.racetrack && (
                        <>
                          <Num value={a.racetrack.legLengthM} onChange={(v) => p.onAction(i, { ...a, racetrack: { ...a.racetrack!, legLengthM: v } })} min={100} step={500} unit="m 직선" title="직선 구간 길이" width={60} />
                          <Num value={a.racetrack.axisHeadingDeg} onChange={(v) => p.onAction(i, { ...a, racetrack: { ...a.racetrack!, axisHeadingDeg: v % 360 } })} step={15} unit="° 축" title="축 방향 (진북 기준 시계 방향)" width={50} />
                        </>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
            {w.action.kind === "recon" && (
              <div className="row sub">
                {(() => {
                  const a = w.action;
                  return (
                    <>
                      <Num value={a.radiusM} onChange={(v) => p.onAction(i, { ...a, radiusM: v })} min={100} step={100} unit="m" title="정찰 반경" width={64} />
                      <Num value={a.durationS ?? 0} onChange={(v) => p.onAction(i, { ...a, durationS: v || undefined })} step={30} unit="s" title="0이면 탐색을 마칠 때까지" width={56} />
                    </>
                  );
                })()}
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="cmd-row">
        <label className="check">
          <input type="checkbox" checked={p.draft.loop} onChange={(e) => p.onLoop(e.target.checked)} /> 반복
        </label>
        <button className="primary" disabled={off} title={p.disabledReason ?? (count === 0 ? "기체를 선택한다" : p.flocking?.length ? "flocking MA 기체는 항로를 거부할 수 있다" : "")} onClick={p.onSend}>
          {p.draft.taskId ? "다시 전송" : "전송"} ({count}대)
        </button>
      </div>
    </section>
  );
}
