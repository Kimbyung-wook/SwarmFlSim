// IMP-UI-071: 로컬 지도 자료 출처 표기 (DEC-057, REQ-SIM-003)
// IMP-UI-073: 영상은 AWS 공개 Copernicus Sentinel-2 L2A 장면을 자체 합성한 타일(DEC-059, scripts/make_s2_composite_tiles.py).
//   표기는 Copernicus Sentinel 데이터 법적 고지(EU Reg. 1159/2013)의 수정본 문구 "Contains modified Copernicus Sentinel data [Year]".
//   연도는 합성에 쓴 장면 연도(data/tiles/imagery/source.json의 credit). 다시 만들어 연도가 바뀌면 VITE_IMAGERY_CREDIT로 바꾼다.
// 지형: Copernicus DEM GLO-90 — 라이선스가 요구하는 저작권 문구.

export const IMAGERY_CREDIT =
  "Contains modified Copernicus Sentinel data 2025-2026 (Sentinel-2 L2A composite)";

export const TERRAIN_CREDIT =
  "Copernicus DEM GLO-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 " +
  "provided under COPERNICUS by the European Union and ESA; all rights reserved";

export interface MapSources {
  imagery: "local" | "builtin";
  terrain: "local" | "ellipsoid";
}

/** 화면에 띄울 출처 문구. 내장 Natural Earth II는 Cesium이 스스로 표기한다 */
export function mapCredits(s: MapSources, imageryCredit: string = IMAGERY_CREDIT): string[] {
  const out: string[] = [];
  if (s.imagery === "local" && imageryCredit.trim() !== "") out.push(imageryCredit.trim());
  if (s.terrain === "local") out.push(TERRAIN_CREDIT);
  return out;
}
