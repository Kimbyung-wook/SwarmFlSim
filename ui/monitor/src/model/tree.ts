// IMP-MON-010: 엔티티 트리 (비행체/지상체 → 진영 → 엔티티) (REQ-UI-005, PRP-UI-002)
import { Side } from "../gen/swarm/v1/entity_pb";
import type { EntityClass } from "./labels";
import { entityClass } from "./labels";
import type { EntityInfo } from "./store";

export interface SideGroup {
  side: Side;
  entities: EntityInfo[];
}

export interface ClassGroup {
  cls: EntityClass;
  sides: SideGroup[];
  count: number;
}

const CLASS_ORDER: EntityClass[] = ["air", "ground", "unknown"];
const SIDE_ORDER: Side[] = [Side.BLUE, Side.RED, Side.NEUTRAL, Side.UNSPECIFIED];

export function buildTree(entities: Iterable<EntityInfo>): ClassGroup[] {
  const by = new Map<EntityClass, Map<Side, EntityInfo[]>>();
  for (const e of entities) {
    const c = entityClass(e.kind);
    let m = by.get(c);
    if (!m) by.set(c, (m = new Map()));
    let l = m.get(e.side);
    if (!l) m.set(e.side, (l = []));
    l.push(e);
  }
  const out: ClassGroup[] = [];
  for (const cls of CLASS_ORDER) {
    const m = by.get(cls);
    if (!m) continue;
    const sides: SideGroup[] = [];
    let count = 0;
    for (const side of SIDE_ORDER) {
      const l = m.get(side);
      if (!l) continue;
      l.sort((a, b) => a.kind - b.kind || a.id.localeCompare(b.id));
      sides.push({ side, entities: l });
      count += l.length;
    }
    out.push({ cls, sides, count });
  }
  return out;
}
