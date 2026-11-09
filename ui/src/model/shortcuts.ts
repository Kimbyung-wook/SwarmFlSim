// IMP-UI-074: 입력 칸에 포커스가 있을 때의 단축키 범위 (REQ-UI-003)
// 숫자·글자 단축키는 입력 칸에서 입력과 겹치므로 무시한다. Esc는 입력과 겹치지 않고 화면 안내("Esc 닫기")대로 늘 동작한다.

const TEXT_ENTRY_TAGS = new Set(["INPUT", "SELECT"]);

/** 이 키 입력을 전역 단축키로 처리하지 않아야 하면 true */
export function ignoresShortcut(key: string, target: EventTarget | null): boolean {
  if (key === "Escape") return false;
  return TEXT_ENTRY_TAGS.has((target as { tagName?: string } | null)?.tagName ?? "");
}
