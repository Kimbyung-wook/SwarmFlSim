// IMP-UI-079: 명령 대상이 없어지면 보내지 않은 임무 편집을 지운다 (REQ-UI-003)
// 대상이 있다가 0이 된 순간에만 작동한다. 처음부터 대상 없이 연 편집(보낸 항로 다시 편집)은 건드리지 않는다.
import type { RouteDraft } from "./routeDraft";

export interface DeselectEffect {
  /** 우클릭 임무 창(찍은 지점·미리보기 도형)을 닫는다 */
  closeMenu: boolean;
  /** 아직 한 번도 보내지 않은 항로 초안을 버린다. 보낸 항로를 고치는 초안은 할당 기체가 있어 남긴다 */
  dropDraft: boolean;
}

export function onTargetsChange(prevCount: number, count: number, draft: Pick<RouteDraft, "taskId"> | null): DeselectEffect {
  const cleared = prevCount > 0 && count === 0;
  return { closeMenu: cleared, dropDraft: cleared && draft !== null && draft.taskId === null };
}
