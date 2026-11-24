// IMP-UI-090: GCS가 받은 상황 정보 (REQ-UI-003, DEC-088, DEC-013). Cesium에 의존하지 않는다.
// swarm/<gcs>/rx/**로 받은 것만 쓴다. truth/**는 쓰지 않는다.
// - TrackShare(rx/p2p, MA_Entity): 기체가 공유한 표적 트랙. 출처 기체·트랙별 최근 것
// - StoreLoadout(rx/ms): 기체별 탑재물 잔량(count)
// - LeaderUpdate(rx/p2p): 편대 리더(term이 큰 것). PeerStatus.group_id(rx/p2p): 기체의 편대
// - 지정 편대: 이 GCS가 보낸 FormationCommand(tx/c2)의 리더·구성원. 보고가 없을 때 "지정"으로 보인다
import { fromBinary } from "@bufbuild/protobuf";
import { FormationCommandSchema } from "../gen/swarm/v1/c2_pb";
import type { EntityKind, PayloadSpec } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { StoreLoadoutSchema } from "../gen/swarm/v1/ms_pb";
import { LeaderUpdateSchema, PeerStatusSchema, TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import type { GeoPoint } from "./commands";

/** 이보다 오래된 트랙은 그리지 않는다 (모의 시간) */
export const TRACK_MAX_AGE_S = 30;

export interface SharedTrack {
  /** 공유한 기체 */
  source: string;
  trackId: string;
  targetId: string;
  pos: GeoPoint;
  kind: EntityKind;
  observedUs: bigint;
}

export interface GroupView {
  groupId: string;
  leader: string;
  /** "report": LeaderUpdate로 받은 리더, "command": 이 GCS가 지정한 리더 */
  from: "report" | "command";
}

const name = (env: LinkEnvelope) => env.msgType.slice(env.msgType.lastIndexOf(".") + 1);

export class GcsPicture {
  private readonly tracks = new Map<string, SharedTrack>();
  private readonly loadouts = new Map<string, PayloadSpec[]>();
  private readonly leaders = new Map<string, { leader: string; term: bigint }>();
  private readonly groupOf = new Map<string, string>();
  private readonly commanded = new Map<string, { leader: string; members: string[] }>();
  version = 0;

  onRx(_key: string, env: LinkEnvelope): void {
    const src = env.header?.source ?? "";
    try {
      switch (name(env)) {
        case "TrackShare": {
          const t = fromBinary(TrackShareSchema, env.payload);
          const p = t.position;
          const from = t.header?.source || src;
          if (!p || !from) return;
          const id = t.trackId || t.targetId;
          const k = `${from}|${id}`;
          const prev = this.tracks.get(k);
          if (prev && prev.observedUs > t.observedTimeUs) return;
          this.tracks.set(k, {
            source: from,
            trackId: t.trackId,
            targetId: t.targetId,
            pos: { latDeg: p.latDeg, lonDeg: p.lonDeg, altM: p.altM },
            kind: t.kind,
            observedUs: t.observedTimeUs || t.header?.simTimeUs || 0n,
          });
          break;
        }
        case "StoreLoadout": {
          const l = fromBinary(StoreLoadoutSchema, env.payload);
          const from = l.header?.source || src;
          if (!from) return;
          this.loadouts.set(from, [...l.stores]);
          break;
        }
        case "LeaderUpdate": {
          const u = fromBinary(LeaderUpdateSchema, env.payload);
          if (!u.groupId) return;
          const prev = this.leaders.get(u.groupId);
          if (prev && prev.term > u.term) return;
          this.leaders.set(u.groupId, { leader: u.leader, term: u.term });
          if (u.leader) this.groupOf.set(u.leader, u.groupId);
          break;
        }
        case "PeerStatus": {
          const s = fromBinary(PeerStatusSchema, env.payload);
          const from = s.header?.source || src;
          if (!from) return;
          if (s.groupId) this.groupOf.set(from, s.groupId);
          else if (this.groupOf.has(from)) this.groupOf.delete(from);
          else return;
          break;
        }
        default:
          return;
      }
    } catch {
      return;
    }
    this.version++;
  }

  /** swarm/<gcs>/tx/** : 지정 편대 */
  onTx(_key: string, env: LinkEnvelope): void {
    if (env.msgType !== FormationCommandSchema.typeName) return;
    try {
      const f = fromBinary(FormationCommandSchema, env.payload);
      if (!f.groupId) return;
      const members = [...f.members];
      // 리더를 비우면 기본 formation MA는 members 사전순 첫 기체를 쓴다 (formation.py pick_leader)
      const leader = f.leader || [...members].sort()[0] || "";
      this.commanded.delete(f.groupId); // 최근 지정이 뒤로 가도록
      this.commanded.set(f.groupId, { leader, members });
    } catch {
      return;
    }
    this.version++;
  }

  /** 지금(모의 us) 기준 maxAgeS 안의 트랙. 출처·트랙 ID 순 */
  sharedTracks(nowUs: bigint | null, maxAgeS = TRACK_MAX_AGE_S): SharedTrack[] {
    const lim = BigInt(Math.round(maxAgeS * 1e6));
    return [...this.tracks.values()]
      .filter((t) => nowUs === null || nowUs - t.observedUs <= lim)
      .sort((a, b) => (a.source + a.trackId).localeCompare(b.source + b.trackId));
  }

  loadout(id: string): PayloadSpec[] | undefined {
    return this.loadouts.get(id);
  }

  /** 기체의 편대와 리더. 보고(LeaderUpdate·PeerStatus)를 지정(FormationCommand)보다 먼저 쓴다 */
  group(id: string): GroupView | null {
    const g = this.groupOf.get(id);
    if (g) {
      const l = this.leaders.get(g);
      if (l) return { groupId: g, leader: l.leader, from: "report" };
      const c = this.commanded.get(g);
      return { groupId: g, leader: c?.leader ?? "", from: c ? "command" : "report" };
    }
    for (const [gid, c] of [...this.commanded].reverse()) if (c.members.includes(id)) {
      const l = this.leaders.get(gid);
      return l ? { groupId: gid, leader: l.leader, from: "report" } : { groupId: gid, leader: c.leader, from: "command" };
    }
    return null;
  }

  clear(): void {
    this.tracks.clear();
    this.loadouts.clear();
    this.leaders.clear();
    this.groupOf.clear();
    this.commanded.clear();
    this.version++;
  }
}
