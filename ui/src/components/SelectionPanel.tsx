// IMP-UI-017: 선택 목록 패널 (REQ-UI-002). 명령은 CommandPanel(IMP-UI-031)
import type { CameraMode } from "../model/camera";
import type { EntityView } from "../model/entityView";
import { isAirborneKind, kindLabel, sideLabel } from "../model/entityView";
import { iconUrl } from "../model/symbology";

interface Props {
  entities: (EntityView | undefined)[];
  ids: readonly string[];
  followId: string | null;
  cameraMode: CameraMode;
  onFocus(id: string): void;
  onRemove(id: string): void;
  onClear(): void;
  onCamera(id: string | null, mode: CameraMode): void;
}

const CAMERA_LABEL: Record<CameraMode, string> = { free: "자유", chase: "추적", fpv: "1인칭", gimbal: "짐벌" };

function fmtHeading(rad: number): string {
  return `${String(Math.round((rad * 180) / Math.PI) % 360).padStart(3, "0")}°`;
}

export function SelectionPanel({ entities, ids, followId, cameraMode, onFocus, onRemove, onClear, onCamera }: Props) {
  return (
    <section className="sel">
      <header className="panel-head">
        <span>선택 {ids.length}</span>
        <button disabled={ids.length === 0} onClick={onClear}>해제</button>
      </header>
      {ids.length === 0 ? (
        <p className="panel-empty">클릭 또는 왼쪽 드래그로 선택. Shift 추가, Ctrl 토글, Esc 해제.</p>
      ) : (
        <ul className="sel-list">
          {ids.map((id, i) => {
            const e = entities[i];
            const following = followId === id && cameraMode !== "free";
            return (
              <li key={id} className={following ? "following" : undefined}>
                <div className="sel-row" onClick={() => onFocus(id)} title="지도에서 보기">
                  {e && <img src={iconUrl(e.kind, e.side, false, e.alive)} width={18} height={18} alt="" />}
                  <b>{id}</b>
                  <span className="muted">{e ? `${kindLabel(e.kind)} · ${sideLabel(e.side)}` : "사라짐"}</span>
                  <button className="x" onClick={(ev) => { ev.stopPropagation(); onRemove(id); }} title="선택에서 빼기">×</button>
                </div>
                {e && (
                  <div className="sel-detail">
                    <span>고도 {e.alt.toFixed(0)} m</span>
                    <span>속도 {e.speed.toFixed(1)} m/s</span>
                    <span>방향 {fmtHeading(e.heading)}</span>
                    {e.energy < 1 && <span>잔량 {(e.energy * 100).toFixed(0)}%</span>}
                  </div>
                )}
                {e && isAirborneKind(e.kind) && (
                  <div className="sel-camera">
                    {(["chase", "fpv"] as const).map((m) => (
                      <button
                        key={m}
                        className={following && cameraMode === m ? "on" : undefined}
                        onClick={() => onCamera(following && cameraMode === m ? null : id, following && cameraMode === m ? "free" : m)}
                      >
                        {CAMERA_LABEL[m]}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
