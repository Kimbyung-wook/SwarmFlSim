// IMP-MON-007: 필터 (엔티티·인터페이스·메시지 타입·결과) (REQ-UI-005, PRP-UI-002)
// 빈 집합은 "전부"다. 타임라인과 메시지 echo에 적용하고, 통계 표에는 엔티티 필터만 적용한다.
import type { LinkEnvelope, LinkOutcome } from "../gen/swarm/v1/link_pb";
import { DropReason, LinkOutcomeKind } from "../gen/swarm/v1/link_pb";
import type { L1Interface } from "../gen/swarm/v1/options_pb";

/** 결과 필터 값: "delivered" 또는 손실 사유 */
export type OutcomeKey = "delivered" | DropReason;

export interface Filter {
  entities: ReadonlySet<string>;
  /** 엔티티 필터 해석: any = src 또는 dst, src = 송신자만, dst = 수신자만 */
  entityMode: "any" | "src" | "dst";
  ifaces: ReadonlySet<L1Interface>;
  msgTypes: ReadonlySet<string>;
  outcomes: ReadonlySet<OutcomeKey>;
}

export const EMPTY_FILTER: Filter = {
  entities: new Set(),
  entityMode: "any",
  ifaces: new Set(),
  msgTypes: new Set(),
  outcomes: new Set(),
};

export function isEmptyFilter(f: Filter): boolean {
  return f.entities.size + f.ifaces.size + f.msgTypes.size + f.outcomes.size === 0;
}

function entityOk(f: Filter, src: string, dst: string): boolean {
  if (f.entities.size === 0) return true;
  switch (f.entityMode) {
    case "src":
      return f.entities.has(src);
    case "dst":
      return f.entities.has(dst);
    default:
      return f.entities.has(src) || f.entities.has(dst);
  }
}

export function outcomeKey(o: LinkOutcome): OutcomeKey | undefined {
  if (o.outcome === LinkOutcomeKind.DELIVERED) return "delivered";
  if (o.outcome === LinkOutcomeKind.DROPPED) return o.reason;
  return undefined;
}

export function matchOutcome(f: Filter, o: LinkOutcome): boolean {
  if (!entityOk(f, o.src, o.dst)) return false;
  if (f.ifaces.size && !f.ifaces.has(o.iface)) return false;
  if (f.msgTypes.size && !f.msgTypes.has(o.msgType)) return false;
  if (f.outcomes.size) {
    const k = outcomeKey(o);
    if (k === undefined || !f.outcomes.has(k)) return false;
  }
  return true;
}

/**
 * 엔벨로프: tx는 src = 송신자, dst = 목적지 목록(비면 브로드캐스트), rx는 dst = 수신 엔티티.
 * 브로드캐스트 tx는 any 모드에서 송신자로만 판정한다(다른 기체가 보낸 것은 rx 기록으로 보인다).
 * 결과 필터는 rx(전달됨)에만 의미가 있다. 손실 사유만 고르면 rx는 걸러지고 tx는 남긴다.
 */
export function matchEnvelope(f: Filter, dir: "tx" | "rx", entity: string, env: LinkEnvelope): boolean {
  const src = env.header?.source || (dir === "tx" ? entity : "");
  if (f.entities.size) {
    const dsts = dir === "rx" ? [entity] : env.dst;
    const srcOk = f.entities.has(src);
    // tx 브로드캐스트는 수신자를 모른다. dst 모드에서만 통과시키고, any 모드에서는 수신 쪽 rx 기록으로 본다
    const dstOk = dir === "tx" && dsts.length === 0 ? f.entityMode === "dst" : dsts.some((d) => f.entities.has(d));
    const ok = f.entityMode === "src" ? srcOk : f.entityMode === "dst" ? dstOk : srcOk || dstOk;
    if (!ok) return false;
  }
  if (f.ifaces.size && !f.ifaces.has(env.iface)) return false;
  if (f.msgTypes.size && !f.msgTypes.has(env.msgType)) return false;
  if (f.outcomes.size && dir === "rx" && !f.outcomes.has("delivered")) return false;
  return true;
}

/** 집합 토글 (불변 갱신) */
export function toggle<T>(s: ReadonlySet<T>, v: T): Set<T> {
  const n = new Set(s);
  if (n.has(v)) n.delete(v);
  else n.add(v);
  return n;
}
