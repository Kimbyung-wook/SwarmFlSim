// IMP-UI-060: truth/event/** 보관소 (DEC-003, DEC-046, DEC-009, DEC-012, DEC-030)
// - 재밍 구역: JamZoneEvent를 owner별 최신 상태로 둔다(active=false도 남겨 꺼짐을 보인다). area가 없으면 폐기 예정 zone(원)을 읽는다
// - 생성 엔티티: launch·spawn 이벤트나 발사체 ID(`wpn-`)·종류(missile/fpv)로 추적한다. truth/state에서 궤적을 따로 쌓는다.
//   Core는 alive=false를 한 번만 내고 엔티티를 지우며 UI는 truth를 다운샘플하므로, 프레임에서 사라져도 종료로 본다
// - 종료: impact(위치·살상반경), kill(원인), alive=false, 프레임에서 사라짐. 종료된 것은 keepEndedUs 동안 남긴다
// sim 시각이 거꾸로 가면(Reset·재생 되감기) 모두 지운다.
import type { Area, Geodetic } from "../gen/swarm/v1/common_pb";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import type { EntityState } from "../gen/swarm/v1/entity_pb";
import type { TruthEvent } from "../gen/swarm/v1/truth_pb";
import type { FrameView } from "./entityView";

export interface GeoPos {
  lat: number;
  lon: number;
  alt: number;
}

export type ZoneShape =
  | { kind: "circle"; center: GeoPos; radiusM: number }
  | { kind: "polygon"; vertices: GeoPos[] };

export interface JamZoneView {
  owner: string;
  active: boolean;
  /** owner 엔티티의 진영(truth/state에서 본 값). 모르면 UNSPECIFIED */
  side: Side;
  shape: ZoneShape;
  minAltM: number;
  /** 0이면 상한 없음 */
  maxAltM: number;
  timeUs: bigint;
}

export interface TrackStart {
  pos: GeoPos;
  timeUs: bigint;
  /** launch 이벤트로 알았으면 발사 기체·표적 */
  shooter?: string;
  target?: string;
}

/** impact | collision | ground | fault (KillEvent.cause), alive=false만 보면 "dead", 프레임에서 사라지면 "gone" */
export type EndCause = string;

export interface TrackEnd {
  pos: GeoPos;
  timeUs: bigint;
  cause: EndCause;
  /** ImpactEvent.lethal_radius_m. 없으면 0 */
  radiusM: number;
}

export interface SimEntityTrack {
  id: string;
  kind: EntityKind;
  side: Side;
  trail: GeoPos[];
  /** 마지막으로 본 위치 */
  last: GeoPos | null;
  start: TrackStart | null;
  end: TrackEnd | null;
}

export interface ImpactView {
  weapon: string;
  pos: GeoPos;
  radiusM: number;
  killed: string[];
  timeUs: bigint;
}

/** 추적 대상이 아닌 엔티티(UAV·표적 등)의 kill 위치 */
export interface KillMark {
  id: string;
  pos: GeoPos;
  cause: string;
  timeUs: bigint;
}

export interface TruthEventOptions {
  /** 궤적 점 간격(sim µs) */
  trailIntervalUs: bigint;
  trailMaxPoints: number;
  /** 종료된 엔티티·impact·kill 표시를 남기는 시간(sim µs) */
  keepEndedUs: bigint;
}

const DEFAULTS: TruthEventOptions = { trailIntervalUs: 200_000n, trailMaxPoints: 600, keepEndedUs: 60_000_000n };

/** 이벤트로 생기는 엔티티인지 (ID 관례 `wpn-<발사기체>-<순번>`, 종류 missile/fpv) */
export function isEventEntity(id: string, kind: EntityKind): boolean {
  return id.startsWith("wpn-") || kind === EntityKind.MISSILE || kind === EntityKind.FPV;
}

const geo = (g: Geodetic | undefined): GeoPos | null => (g ? { lat: g.latDeg, lon: g.lonDeg, alt: g.altM } : null);

/** JamZoneEvent의 영역. area가 우선이고 없으면 폐기 예정 zone(원). 둘 다 없거나 도형이 비면 null */
export function zoneShape(area: Area | undefined, legacy: { center?: Geodetic; radiusM: number } | undefined): {
  shape: ZoneShape;
  minAltM: number;
  maxAltM: number;
} | null {
  if (area && area.shape.case) {
    const s = area.shape;
    if (s.case === "circle") {
      const c = geo(s.value.center);
      if (!c || !(s.value.radiusM > 0)) return null;
      return { shape: { kind: "circle", center: c, radiusM: s.value.radiusM }, minAltM: area.minAltM, maxAltM: area.maxAltM };
    }
    const v = s.value.vertices.map((g) => ({ lat: g.latDeg, lon: g.lonDeg, alt: g.altM }));
    if (v.length < 3) return null;
    return { shape: { kind: "polygon", vertices: v }, minAltM: area.minAltM, maxAltM: area.maxAltM };
  }
  const c = geo(legacy?.center);
  if (!c || !legacy || !(legacy.radiusM > 0)) return null;
  return { shape: { kind: "circle", center: c, radiusM: legacy.radiusM }, minAltM: 0, maxAltM: 0 };
}

export class TruthEventStore {
  /** 무언가 바뀔 때마다 1 증가 */
  version = 0;
  private readonly opts: TruthEventOptions;
  private readonly zones = new Map<string, JamZoneView>();
  private readonly tracks = new Map<string, SimEntityTrack & { lastSampleUs: bigint }>();
  private impactList: ImpactView[] = [];
  private killList: KillMark[] = [];
  /** 모든 엔티티의 마지막 위치·진영 (kill 위치, 구역 owner 진영) */
  private readonly seen = new Map<string, { pos: GeoPos; side: Side }>();
  private nowUs = -1n;

  constructor(opts: Partial<TruthEventOptions> = {}) {
    this.opts = { ...DEFAULTS, ...opts };
  }

  onEvent(ev: TruthEvent): void {
    const t = ev.header?.simTimeUs ?? (this.nowUs < 0n ? 0n : this.nowUs);
    if (this.nowUs >= 0n && t < this.nowUs - 1_000_000n) {
      // 되감기 전에 발행된 이벤트가 늦게 온 경우가 아니라 시각이 크게 뒤로 가면 새로 시작한다
      this.clear();
    }
    const e = ev.event;
    switch (e.case) {
      case "jamZone": {
        const z = zoneShape(e.value.area, e.value.zone);
        const prev = this.zones.get(e.value.owner);
        if (!z) {
          // 도형이 없는 끄기 이벤트는 이전 도형을 꺼짐으로 바꾼다
          if (prev && !e.value.active) this.zones.set(prev.owner, { ...prev, active: false, timeUs: t });
          else return;
        } else {
          this.zones.set(e.value.owner, {
            owner: e.value.owner,
            active: e.value.active,
            side: this.seen.get(e.value.owner)?.side ?? prev?.side ?? Side.UNSPECIFIED,
            ...z,
            timeUs: t,
          });
        }
        break;
      }
      case "launch": {
        const v = e.value;
        const tr = this.track(v.weaponEntity, EntityKind.UNSPECIFIED, this.seen.get(v.shooter)?.side ?? Side.UNSPECIFIED);
        const pos = this.seen.get(v.weaponEntity)?.pos ?? this.seen.get(v.shooter)?.pos ?? tr.start?.pos ?? null;
        if (pos) tr.start = { ...tr.start, pos, timeUs: tr.start?.timeUs ?? t, shooter: v.shooter, target: v.targetId };
        break;
      }
      case "spawn": {
        const s = e.value.entity;
        if (!s) return;
        const tr = this.track(s.id, s.kind, s.side);
        const pos = geo(s.kinematics?.position);
        if (pos) {
          tr.start = { ...tr.start, pos, timeUs: tr.start?.timeUs ?? t };
          tr.last ??= pos;
        }
        this.observe(s);
        break;
      }
      case "impact": {
        const v = e.value;
        const pos = geo(v.position) ?? this.seen.get(v.weaponEntity)?.pos;
        if (!pos) return;
        this.impactList.push({ weapon: v.weaponEntity, pos, radiusM: v.lethalRadiusM, killed: [...v.killed], timeUs: t });
        // 추적 전이라도(launch·spawn·프레임을 놓쳤어도) 종료 위치를 남긴다
        const tr = this.track(v.weaponEntity, EntityKind.UNSPECIFIED, Side.UNSPECIFIED);
        tr.last ??= pos;
        tr.end = { pos, timeUs: t, cause: "impact", radiusM: v.lethalRadiusM };
        break;
      }
      case "kill": {
        const v = e.value;
        const tr = this.tracks.get(v.entityId);
        const pos = this.seen.get(v.entityId)?.pos ?? tr?.last ?? null;
        if (tr) {
          // impact가 먼저 왔으면 그대로 둔다. 프레임으로만 안 종료(dead·gone)는 위치를 두고 원인을 바꾼다
          if (tr.end && (tr.end.cause === "dead" || tr.end.cause === "gone")) tr.end = { ...tr.end, cause: v.cause };
          else if (!tr.end && pos) tr.end = { pos, timeUs: t, cause: v.cause, radiusM: 0 };
          else return;
        } else if (pos) {
          this.killList.push({ id: v.entityId, pos, cause: v.cause, timeUs: t });
        } else return;
        break;
      }
      default:
        return;
    }
    this.version++;
  }

  onFrame(f: FrameView): void {
    if (this.nowUs >= 0n && f.simTimeUs < this.nowUs) this.clear();
    this.nowUs = f.simTimeUs;
    const present = new Set<string>();
    let changed = false;
    for (const e of f.entities) {
      const pos = { lat: e.lat, lon: e.lon, alt: e.alt };
      this.seen.set(e.id, { pos, side: e.side });
      if (!this.tracks.has(e.id) && !isEventEntity(e.id, e.kind)) continue;
      present.add(e.id);
      const tr = this.track(e.id, e.kind, e.side);
      tr.kind = e.kind;
      tr.side = e.side;
      if (tr.end) continue;
      tr.last = pos;
      tr.start ??= { pos, timeUs: f.simTimeUs };
      if (!e.alive) {
        tr.end = { pos, timeUs: f.simTimeUs, cause: "dead", radiusM: 0 };
        changed = true;
        continue;
      }
      if (tr.lastSampleUs < 0n || f.simTimeUs - tr.lastSampleUs >= this.opts.trailIntervalUs) {
        tr.trail.push(pos);
        if (tr.trail.length > this.opts.trailMaxPoints) tr.trail.splice(0, tr.trail.length - this.opts.trailMaxPoints);
        tr.lastSampleUs = f.simTimeUs;
      }
      changed = true;
    }
    for (const tr of this.tracks.values()) {
      if (tr.end || present.has(tr.id) || !tr.last) continue;
      tr.end = { pos: tr.last, timeUs: f.simTimeUs, cause: "gone", radiusM: 0 };
      changed = true;
    }
    if (this.prune(f.simTimeUs)) changed = true;
    if (changed) this.version++;
  }

  jamZones(): JamZoneView[] {
    return [...this.zones.values()].map((z) => ({ ...z, side: this.seen.get(z.owner)?.side ?? z.side }));
  }

  entityTracks(): SimEntityTrack[] {
    return [...this.tracks.values()];
  }

  getTrack(id: string): SimEntityTrack | undefined {
    return this.tracks.get(id);
  }

  impacts(): readonly ImpactView[] {
    return this.impactList;
  }

  kills(): readonly KillMark[] {
    return this.killList;
  }

  clear(): void {
    this.zones.clear();
    this.tracks.clear();
    this.impactList = [];
    this.killList = [];
    this.seen.clear();
    this.nowUs = -1n;
    this.version++;
  }

  private track(id: string, kind: EntityKind, side: Side) {
    let tr = this.tracks.get(id);
    if (!tr) {
      tr = { id, kind, side, trail: [], last: null, start: null, end: null, lastSampleUs: -1n };
      this.tracks.set(id, tr);
    } else {
      if (kind !== EntityKind.UNSPECIFIED) tr.kind = kind;
      if (side !== Side.UNSPECIFIED && tr.side === Side.UNSPECIFIED) tr.side = side;
    }
    return tr;
  }

  private observe(s: EntityState): void {
    const pos = geo(s.kinematics?.position);
    if (pos) this.seen.set(s.id, { pos, side: s.side });
  }

  private prune(nowUs: bigint): boolean {
    const keep = this.opts.keepEndedUs;
    let changed = false;
    for (const [id, tr] of this.tracks)
      if (tr.end && nowUs - tr.end.timeUs > keep) {
        this.tracks.delete(id);
        changed = true;
      }
    const n0 = this.impactList.length + this.killList.length;
    this.impactList = this.impactList.filter((i) => nowUs - i.timeUs <= keep);
    this.killList = this.killList.filter((k) => nowUs - k.timeUs <= keep);
    return changed || this.impactList.length + this.killList.length !== n0;
  }
}

/** 종료 원인 표시 문구 */
export function endCauseLabel(c: EndCause): string {
  switch (c) {
    case "impact": return "도달";
    case "collision": return "충돌";
    case "ground": return "지면 충돌";
    case "fault": return "고장";
    case "dead": return "파괴";
    case "gone": return "소멸";
    default: return c || "종료";
  }
}
