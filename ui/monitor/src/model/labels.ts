// IMP-MON-005: 열거값 표시 이름과 엔티티 분류 (REQ-UI-005, PRP-UI-002)
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { DropReason } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";

/** 키의 `<iface>` 이름 (docs/10_contracts.md §3.3) */
export const IFACE_KEY: Record<L1Interface, string> = {
  [L1Interface.UNSPECIFIED]: "?",
  [L1Interface.C2]: "c2",
  [L1Interface.VI]: "vi",
  [L1Interface.MS]: "ms",
  [L1Interface.MP]: "mp",
  [L1Interface.MD]: "md",
  [L1Interface.P2P]: "p2p",
};
export const IFACES: readonly L1Interface[] = [
  L1Interface.C2,
  L1Interface.VI,
  L1Interface.MS,
  L1Interface.MP,
  L1Interface.MD,
  L1Interface.P2P,
];

export function ifaceFromKey(s: string): L1Interface {
  const hit = IFACES.find((i) => IFACE_KEY[i] === s);
  return hit ?? L1Interface.UNSPECIFIED;
}

/** 손실 사유 표시 순서. REQ-UI-005: 재밍·가시선·거리·버스트·큐·고장 */
export const DROP_REASONS: readonly DropReason[] = [
  DropReason.JAMMED,
  DropReason.NO_LOS,
  DropReason.OUT_OF_RANGE,
  DropReason.BURST_LOSS,
  DropReason.QUEUE_OVERFLOW,
  DropReason.FAULT_INJECTED,
  DropReason.NODE_DEAD,
  DropReason.NONE,
];
/** 집계 배열 크기. 계약에 없는 값은 NONE 칸(기타)에 넣는다 */
export const REASON_SLOTS = 8;
export function reasonSlot(r: number): number {
  return r > 0 && r < REASON_SLOTS ? r : 0;
}

export const DROP_LABEL: Record<DropReason, string> = {
  [DropReason.NONE]: "기타",
  [DropReason.JAMMED]: "재밍",
  [DropReason.NO_LOS]: "가시선",
  [DropReason.OUT_OF_RANGE]: "거리",
  [DropReason.BURST_LOSS]: "버스트",
  [DropReason.QUEUE_OVERFLOW]: "큐",
  [DropReason.NODE_DEAD]: "노드",
  [DropReason.FAULT_INJECTED]: "고장",
};

export const DROP_COLOR: Record<DropReason, string> = {
  [DropReason.NONE]: "#9aa0a6",
  [DropReason.JAMMED]: "#e8453c",
  [DropReason.NO_LOS]: "#b07cff",
  [DropReason.OUT_OF_RANGE]: "#f29900",
  [DropReason.BURST_LOSS]: "#f6c026",
  [DropReason.QUEUE_OVERFLOW]: "#ff7ab8",
  [DropReason.NODE_DEAD]: "#6d6d6d",
  [DropReason.FAULT_INJECTED]: "#00bcd4",
};

export type EntityClass = "air" | "ground" | "unknown";

export function entityClass(k: EntityKind): EntityClass {
  switch (k) {
    case EntityKind.UAV:
    case EntityKind.FPV:
    case EntityKind.AIR_TARGET:
    case EntityKind.MISSILE:
      return "air";
    case EntityKind.GCS:
    case EntityKind.GROUND_TARGET:
    case EntityKind.JAMMER_SITE:
      return "ground";
    default:
      return "unknown";
  }
}

export const CLASS_LABEL: Record<EntityClass, string> = { air: "비행체", ground: "지상체", unknown: "미확인" };

export const SIDE_LABEL: Record<Side, string> = {
  [Side.UNSPECIFIED]: "진영 미상",
  [Side.BLUE]: "청군",
  [Side.RED]: "적군",
  [Side.NEUTRAL]: "중립",
};

export const KIND_LABEL: Record<EntityKind, string> = {
  [EntityKind.UNSPECIFIED]: "?",
  [EntityKind.UAV]: "UAV",
  [EntityKind.GCS]: "GCS",
  [EntityKind.GROUND_TARGET]: "지상표적",
  [EntityKind.AIR_TARGET]: "공중표적",
  [EntityKind.MISSILE]: "발사체",
  [EntityKind.FPV]: "FPV",
  [EntityKind.JAMMER_SITE]: "재밍기지",
};

/** `swarm.v1.PeerStatus` → `PeerStatus` */
export function shortType(t: string): string {
  const i = t.lastIndexOf(".");
  return i < 0 ? t : t.slice(i + 1);
}
