// IMP-UI-064: truth 이벤트·센서 시야 → 전시 도형 명세 (DEC-003, DEC-046). Cesium과 무관한 순수 함수라 시험한다.
// - 재밍 구역: 진영색 반투명 기둥(min_alt~max_alt, 상한 없음은 ZONE_OPEN_TOP_M까지 그리고 라벨에 적음). 꺼짐은 회색·옅게
// - 생성 엔티티: 비행 중 궤적(미사일 주황, FPV 자홍), 생성 마커(흰 점), 종료 후 궤적·위치 회색, 종료 마커 라벨(ID·원인)
// - impact: 살상반경 원(빨강), kill(추적 대상 아님): 회색 점·라벨
// - 센서: FOV 사각뿔 모서리 4개 + 먼 쪽 외곽선(지면에 닿으면 풋프린트로 굵게)
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import type { FovGeometry, SensorView } from "./sensorFov";
import { fovGeometry } from "./sensorFov";
import { sideColor } from "./symbology";
import type { GeoPos, SimEntityTrack, TruthEventStore, ZoneShape } from "./truthEvents";
import { endCauseLabel } from "./truthEvents";

/** 상한 없는 구역(max_alt_m=0)을 그릴 높이 */
export const ZONE_OPEN_TOP_M = 8000;
export const ENDED_COLOR = "#9ca3af";
export const FOV_COLOR = "#22d3ee";
export const IMPACT_COLOR = "#ef4444";

export interface ZoneDraw {
  key: string;
  shape: ZoneShape;
  bottomM: number;
  topM: number;
  color: string;
  fillAlpha: number;
  outlineAlpha: number;
  label: string;
}

export interface LineDraw {
  positions: GeoPos[];
  color: string;
  alpha: number;
  width: number;
}

export interface PointDraw {
  pos: GeoPos;
  color: string;
  size: number;
  outline: string;
  label?: string;
}

export interface RingDraw {
  key: string;
  center: GeoPos;
  radiusM: number;
  color: string;
  label: string;
}

export interface EventOverlay {
  zones: ZoneDraw[];
  lines: LineDraw[];
  points: PointDraw[];
  rings: RingDraw[];
}

export function zoneDraws(store: TruthEventStore): ZoneDraw[] {
  return store.jamZones().map((z) => {
    const open = !(z.maxAltM > z.minAltM);
    const color = z.active ? (z.side === Side.UNSPECIFIED ? "#f97316" : sideColor(z.side)) : ENDED_COLOR;
    const band = open ? `${Math.round(z.minAltM)} m~상한 없음` : `${Math.round(z.minAltM)}~${Math.round(z.maxAltM)} m`;
    return {
      key: `zone/${z.owner}`,
      shape: z.shape,
      bottomM: z.minAltM,
      topM: open ? Math.max(z.minAltM, 0) + ZONE_OPEN_TOP_M : z.maxAltM,
      color,
      fillAlpha: z.active ? 0.18 : 0.05,
      outlineAlpha: z.active ? 0.9 : 0.4,
      label: `재밍 ${z.owner}${z.active ? "" : " (꺼짐)"} · ${band}`,
    };
  });
}

export function trackColor(t: SimEntityTrack): string {
  if (t.end) return ENDED_COLOR;
  if (t.kind === EntityKind.FPV) return "#e879f9";
  return "#fb923c";
}

/** 생성 엔티티의 궤적·생성/종료 마커 */
export function trackDraws(tracks: readonly SimEntityTrack[]): { lines: LineDraw[]; points: PointDraw[] } {
  const lines: LineDraw[] = [];
  const points: PointDraw[] = [];
  for (const t of tracks) {
    const color = trackColor(t);
    const path = t.end ? [...t.trail, t.end.pos] : t.last ? [...t.trail, t.last] : t.trail;
    if (path.length >= 2) lines.push({ positions: path, color, alpha: t.end ? 0.6 : 0.95, width: t.end ? 1.5 : 2.5 });
    if (t.start) {
      const how = t.start.shooter ? `발사 ${t.start.shooter}${t.start.target ? `→${t.start.target}` : ""}` : "생성";
      points.push({ pos: t.start.pos, color: "#ffffff", size: 7, outline: color, label: t.end ? undefined : `${t.id} ${how}` });
    }
    if (t.end) {
      points.push({ pos: t.end.pos, color: ENDED_COLOR, size: 11, outline: "#000000", label: `${t.id} · ${endCauseLabel(t.end.cause)}` });
    }
  }
  return { lines, points };
}

export function sensorDraws(
  sensors: readonly SensorView[],
  platformPos: (id: string) => GeoPos | undefined,
  groundAlt: (p: GeoPos) => number = () => 0,
): { lines: LineDraw[]; geoms: FovGeometry[] } {
  const lines: LineDraw[] = [];
  const geoms: FovGeometry[] = [];
  for (const s of sensors) {
    if (!s.active) continue;
    const p = platformPos(s.platform);
    if (!p) continue;
    const g = fovGeometry(p, s, groundAlt(p));
    if (!g) continue;
    geoms.push(g);
    for (const c of g.corners) lines.push({ positions: [g.apex, c], color: FOV_COLOR, alpha: 0.55, width: 1 });
    lines.push({ positions: g.outline, color: FOV_COLOR, alpha: 0.9, width: g.onGround ? 2.5 : 1.5 });
  }
  return { lines, geoms };
}

export function eventOverlay(
  store: TruthEventStore,
  sensors: readonly SensorView[],
  platformPos: (id: string) => GeoPos | undefined,
  groundAlt?: (p: GeoPos) => number,
): EventOverlay {
  const tr = trackDraws(store.entityTracks());
  const sv = sensorDraws(sensors, platformPos, groundAlt);
  const rings: RingDraw[] = store
    .impacts()
    .filter((i) => i.radiusM > 0)
    .map((i) => ({
      key: `impact/${i.weapon}/${i.timeUs}`,
      center: i.pos,
      radiusM: i.radiusM,
      color: IMPACT_COLOR,
      label: `${i.weapon} 살상반경 ${Math.round(i.radiusM)} m${i.killed.length ? ` · 파괴 ${i.killed.join(", ")}` : ""}`,
    }));
  const kills: PointDraw[] = store
    .kills()
    .map((k) => ({ pos: k.pos, color: ENDED_COLOR, size: 9, outline: IMPACT_COLOR, label: `${k.id} · ${endCauseLabel(k.cause)}` }));
  return { zones: zoneDraws(store), lines: [...tr.lines, ...sv.lines], points: [...tr.points, ...kills], rings };
}
