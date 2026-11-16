// TC-UI-067: 대상 선택 해제 시 미전송 편집 정리 규칙 (IMP-UI-079)
import { describe, expect, it } from "vitest";
import { onTargetsChange } from "./deselect";

describe("onTargetsChange", () => {
  it("대상이 있다가 0이 되면 임무 창을 닫고, 보낸 적 없는 항로 초안을 버린다", () => {
    expect(onTargetsChange(3, 0, null)).toEqual({ closeMenu: true, dropDraft: false });
    expect(onTargetsChange(1, 0, { taskId: null })).toEqual({ closeMenu: true, dropDraft: true });
  });

  it("보낸 항로를 고치는 초안은 남긴다", () => {
    expect(onTargetsChange(2, 0, { taskId: "ui-ab-3" })).toEqual({ closeMenu: true, dropDraft: false });
  });

  it("대상 수가 바뀌기만 하거나 처음부터 0이면 아무것도 지우지 않는다", () => {
    for (const [a, b] of [[0, 0], [2, 1], [0, 2], [1, 3]]) {
      expect(onTargetsChange(a, b, { taskId: null })).toEqual({ closeMenu: false, dropDraft: false });
    }
  });
});
