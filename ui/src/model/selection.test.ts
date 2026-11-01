// TC-UI-004: RTS 선택 로직 (IMP-UI-006)
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import type { ScreenEntity } from "./selection";
import {
  applySelection, isDrag, modeFromModifiers, normalizeRect, pickAt, pickInRect, pruneSelection,
} from "./selection";

const s = (id: string, x: number, y: number, kind = EntityKind.UAV, side = Side.BLUE, alive = true): ScreenEntity =>
  ({ id, x, y, kind, side, alive });

const ents: ScreenEntity[] = [
  s("uav-001", 10, 10),
  s("uav-002", 20, 20),
  s("uav-003", 200, 200),
  s("tgt-001", 15, 15, EntityKind.GROUND_TARGET, Side.RED),
  s("gcs-01", 300, 300, EntityKind.GCS),
  s("uav-004", 12, 12, EntityKind.UAV, Side.BLUE, false),
];

describe("selection", () => {
  it("수정키 → 선택 모드", () => {
    expect(modeFromModifiers({ shiftKey: false, ctrlKey: false })).toBe("replace");
    expect(modeFromModifiers({ shiftKey: true, ctrlKey: false })).toBe("add");
    expect(modeFromModifiers({ shiftKey: true, ctrlKey: true })).toBe("toggle");
    expect(modeFromModifiers({ shiftKey: false, ctrlKey: false, metaKey: true })).toBe("toggle");
  });

  it("짧게 움직이면 클릭, 길게 끌면 드래그", () => {
    expect(isDrag({ x0: 0, y0: 0, x1: 3, y1: 3 })).toBe(false);
    expect(isDrag({ x0: 0, y0: 0, x1: 10, y1: 0 })).toBe(true);
    expect(normalizeRect({ x0: 10, y0: 5, x1: 0, y1: 20 })).toEqual({ x0: 0, y0: 5, x1: 10, y1: 20 });
  });

  it("클릭은 반경 안의 가장 가까운 생존 엔티티를 고른다", () => {
    expect(pickAt(ents, 14, 14)).toBe("tgt-001");
    expect(pickAt(ents, 11, 11)).toBe("uav-001"); // uav-004(12,12)는 죽어서 제외
    expect(pickAt(ents, 100, 100)).toBeNull();
  });

  it("박스 안에 아군 기체가 있으면 그것만, 없으면 모두 고른다", () => {
    expect(pickInRect(ents, { x0: 30, y0: 30, x1: 0, y1: 0 })).toEqual(["uav-001", "uav-002"]);
    expect(pickInRect(ents, { x0: 250, y0: 250, x1: 350, y1: 350 })).toEqual(["gcs-01"]);
    expect(pickInRect(ents, { x0: 14, y0: 14, x1: 16, y1: 16 })).toEqual(["tgt-001"]);
    expect(pickInRect(ents, { x0: 500, y0: 500, x1: 600, y1: 600 })).toEqual([]);
  });

  it("replace·add·toggle 결합", () => {
    const prev = ["a-1", "b-1"];
    expect(applySelection(prev, ["c-1", "c-1"], "replace")).toEqual(["c-1"]);
    expect(applySelection(prev, ["b-1", "c-1"], "add")).toEqual(["a-1", "b-1", "c-1"]);
    expect(applySelection(prev, ["b-1", "c-1"], "toggle")).toEqual(["a-1", "c-1"]);
    expect(applySelection(prev, [], "replace")).toEqual([]);
    expect(applySelection(prev, [], "add")).toEqual(prev);
  });

  it("사라진 엔티티를 선택에서 뺀다", () => {
    const sel = ["a-1", "b-1"];
    expect(pruneSelection(sel, new Set(["a-1", "b-1", "c-1"]))).toBe(sel);
    expect(pruneSelection(sel, new Set(["b-1"]))).toEqual(["b-1"]);
  });
});
