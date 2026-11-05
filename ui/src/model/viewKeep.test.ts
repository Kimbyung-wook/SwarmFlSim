// TC-UI-054: 모드 전환 폭 유지 계산 — 원근 폭 ↔ 높이 왕복, 2D 높이 = 폭, 상·하한 (IMP-UI-067)
// TC-UI-055: 맞춤 뷰 — 범위·여백·최소 범위·(0,0) 제외, 맞춤 시점(첫 엔티티·시나리오 교체·재시도) (IMP-UI-068)
import { describe, expect, it } from "vitest";
import { FitGate, fitRect, heightForWidth, MAX_WIDTH_M, MIN_WIDTH_M, perspectiveWidth } from "./viewKeep";

const FOV = (60 * Math.PI) / 180;
const R = 6378137, D = Math.PI / 180;

describe("모드 전환 폭 유지", () => {
  it("3D·2.5D: 거리 → 폭 → 높이가 왕복하고, 2D는 높이가 곧 폭", () => {
    const w = perspectiveWidth(10_000, FOV);
    expect(w).toBeCloseTo(2 * 10_000 * Math.tan(FOV / 2), 6);
    expect(heightForWidth("3d", w, FOV)).toBeCloseTo(10_000, 6);
    expect(heightForWidth("columbus", w, FOV)).toBeCloseTo(10_000, 6);
    expect(heightForWidth("2d", w, FOV)).toBeCloseTo(w, 6);
    // 2D 폭 → 3D 높이 → 다시 폭
    expect(perspectiveWidth(heightForWidth("3d", 42_000, FOV), FOV)).toBeCloseTo(42_000, 6);
  });

  it("폭은 상·하한으로 자르고 숫자가 아니면 상한", () => {
    expect(perspectiveWidth(1, FOV)).toBe(MIN_WIDTH_M);
    expect(perspectiveWidth(1e9, FOV)).toBe(MAX_WIDTH_M);
    expect(heightForWidth("2d", Number.NaN, FOV)).toBe(MAX_WIDTH_M);
  });
});

describe("fitRect", () => {
  it("모든 점을 담고 각 변에 여백을 둔다", () => {
    const r = fitRect([{ lat: 37, lon: 127 }, { lat: 37.5, lon: 128 }], 0.1)!;
    expect(r.south).toBeCloseTo(37 - 0.05, 9);
    expect(r.north).toBeCloseTo(37.5 + 0.05, 9);
    expect(r.west).toBeCloseTo(127 - 0.1, 9);
    expect(r.east).toBeCloseTo(128 + 0.1, 9);
  });

  it("엔티티 1개면 최소 범위(m)로 중심에 맞추고, (0,0)·NaN은 빼며 없으면 null", () => {
    const r = fitRect([{ lat: 37, lon: 127 }, { lat: 0, lon: 0 }, { lat: Number.NaN, lon: 1 }], 0.15, 5000)!;
    expect((r.north - r.south) * D * R).toBeCloseTo(5000, 3);
    expect((r.east - r.west) * D * R * Math.cos(37 * D)).toBeCloseTo(5000, 3);
    expect((r.north + r.south) / 2).toBeCloseTo(37, 9);
    expect((r.east + r.west) / 2).toBeCloseTo(127, 9);
    expect(fitRect([{ lat: 0, lon: 0 }])).toBeNull();
    expect(fitRect([])).toBeNull();
  });
});

describe("FitGate", () => {
  it("엔티티가 처음 생길 때 한 번만 맞춘다", () => {
    const g = new FitGate();
    expect(g.check(0, "")).toBe(false);
    expect(g.check(3, "")).toBe(true);
    expect(g.check(3, "")).toBe(false);
    // 처음 이름을 알게 된 것은 교체가 아니다
    expect(g.check(3, "demo")).toBe(false);
    expect(g.check(5, "demo")).toBe(false);
  });

  it("시나리오 이름이 바뀌면 다시 한 번, 엔티티가 생길 때까지 기다린다", () => {
    const g = new FitGate();
    expect(g.check(2, "a")).toBe(true);
    expect(g.check(0, "b")).toBe(false);
    expect(g.check(4, "b")).toBe(true);
    expect(g.check(4, "b")).toBe(false);
    // 이름 정보가 잠시 빠져도(status 없음) 교체가 아니다
    expect(g.check(4, undefined)).toBe(false);
    expect(g.check(4, "b")).toBe(false);
  });

  it("rearm 뒤 다음 갱신에서 다시 맞춘다", () => {
    const g = new FitGate();
    expect(g.check(1, "")).toBe(true);
    g.rearm();
    expect(g.check(1, "")).toBe(true);
  });
});
