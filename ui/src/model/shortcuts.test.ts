// TC-UI-061: 입력 칸 포커스 중 단축키 범위 — Esc만 동작, 나머지는 무시 (IMP-UI-074)
import { describe, expect, it } from "vitest";
import { ignoresShortcut } from "./shortcuts";

const on = (tagName: string) => ({ tagName }) as unknown as EventTarget;

describe("ignoresShortcut", () => {
  it("입력 칸·선택 상자에 포커스가 있어도 Esc는 처리한다", () => {
    expect(ignoresShortcut("Escape", on("INPUT"))).toBe(false);
    expect(ignoresShortcut("Escape", on("SELECT"))).toBe(false);
  });

  it("입력 칸·선택 상자에서 다른 단축키는 무시한다", () => {
    for (const key of ["1", "h", "H", "a"]) {
      expect(ignoresShortcut(key, on("INPUT"))).toBe(true);
      expect(ignoresShortcut(key, on("SELECT"))).toBe(true);
    }
  });

  it("입력 칸 밖에서는 모든 단축키를 처리한다", () => {
    for (const key of ["Escape", "1", "h", "a"]) {
      expect(ignoresShortcut(key, on("CANVAS"))).toBe(false);
      expect(ignoresShortcut(key, on("BUTTON"))).toBe(false);
      expect(ignoresShortcut(key, null)).toBe(false);
    }
  });
});
