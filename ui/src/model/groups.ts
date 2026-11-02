// IMP-UI-026: 부대 그룹 지정·호출 (REQ-UI-002, PRP-UI-001). Ctrl+숫자 지정, 숫자 호출
export const GROUP_SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"] as const;
export type GroupSlot = (typeof GROUP_SLOTS)[number];

export function groupId(slot: GroupSlot): string {
  return `grp-${slot}`;
}

export function slotFromKey(key: string): GroupSlot | null {
  return (GROUP_SLOTS as readonly string[]).includes(key) ? (key as GroupSlot) : null;
}

export class GroupStore {
  private readonly groups = new Map<GroupSlot, readonly string[]>();

  get(slot: GroupSlot): readonly string[] {
    return this.groups.get(slot) ?? [];
  }

  /** 지정. 한 기체는 한 그룹에만 속한다(다른 그룹에서 뺀다). 바뀐 그룹 목록을 돌려준다 */
  assign(slot: GroupSlot, ids: readonly string[]): { slot: GroupSlot; members: readonly string[]; previous: readonly string[] }[] {
    const changed: { slot: GroupSlot; members: readonly string[]; previous: readonly string[] }[] = [];
    const set = new Set(ids);
    for (const [s, m] of this.groups) {
      if (s === slot) continue;
      const kept = m.filter((id) => !set.has(id));
      if (kept.length !== m.length) {
        changed.push({ slot: s, members: kept, previous: m });
        if (kept.length) this.groups.set(s, kept);
        else this.groups.delete(s);
      }
    }
    const previous = this.get(slot);
    if (ids.length) this.groups.set(slot, [...ids]);
    else this.groups.delete(slot);
    changed.push({ slot, members: [...ids], previous });
    return changed;
  }

  /** 사라진 엔티티를 뺀 구성원 */
  recall(slot: GroupSlot, present?: ReadonlySet<string>): string[] {
    const m = this.get(slot);
    return present ? m.filter((id) => present.has(id)) : [...m];
  }

  slotOf(id: string): GroupSlot | null {
    for (const [s, m] of this.groups) if (m.includes(id)) return s;
    return null;
  }

  entries(): [GroupSlot, readonly string[]][] {
    return GROUP_SLOTS.filter((s) => this.groups.has(s)).map((s) => [s, this.groups.get(s)!]);
  }
}
