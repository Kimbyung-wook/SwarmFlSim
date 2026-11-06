// TC-UI-057: 로컬 지도 자료 출처 표기 — 로컬 영상·지형일 때만, 표기 문구 필수 요소, 덮어쓰기 (IMP-UI-071)
// TC-UI-059: 영상 표기가 Copernicus 법적 고지 수정본 문구이고 EOX 표기가 없음 (IMP-UI-073, DEC-059)
import { describe, expect, it } from "vitest";
import { IMAGERY_CREDIT, mapCredits, TERRAIN_CREDIT } from "./mapCredits";

describe("mapCredits", () => {
  it("로컬 영상·지형이면 둘 다, 내장·타원체면 없음", () => {
    expect(mapCredits({ imagery: "local", terrain: "local" })).toEqual([IMAGERY_CREDIT, TERRAIN_CREDIT]);
    expect(mapCredits({ imagery: "builtin", terrain: "local" })).toEqual([TERRAIN_CREDIT]);
    expect(mapCredits({ imagery: "local", terrain: "ellipsoid" })).toEqual([IMAGERY_CREDIT]);
    expect(mapCredits({ imagery: "builtin", terrain: "ellipsoid" })).toEqual([]);
  });

  it("라이선스가 요구하는 문구를 담는다", () => {
    expect(IMAGERY_CREDIT).toMatch(/^Contains modified Copernicus Sentinel data \d{4}(-\d{4})? /);
    expect(TERRAIN_CREDIT).toContain("Copernicus DEM");
    expect(TERRAIN_CREDIT).toContain("provided under COPERNICUS by the European Union and ESA");
  });

  it("TC-UI-059: 자체 합성 영상 표기에 EOX(cloudless) 문구가 없다", () => {
    expect(IMAGERY_CREDIT).not.toMatch(/EOX|cloudless/i);
  });

  it("영상 표기를 바꿀 수 있고, 빈 문자열이면 영상 표기를 뺀다", () => {
    expect(mapCredits({ imagery: "local", terrain: "ellipsoid" }, " My tiles ")).toEqual(["My tiles"]);
    expect(mapCredits({ imagery: "local", terrain: "ellipsoid" }, "")).toEqual([]);
  });
});
