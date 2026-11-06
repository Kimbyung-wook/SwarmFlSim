// IMP-UI-071: 로컬 지도 자료 출처 표기 (DEC-057, REQ-SIM-003)
// 영상: EOxCloudless(Sentinel-2 cloudless) CC BY-NC-SA 4.0 — EOX가 요구하는 표기. 연도판이 바뀌면 VITE_IMAGERY_CREDIT로 바꾼다.
// 지형: Copernicus DEM GLO-90 — 라이선스가 요구하는 저작권 문구.

export const IMAGERY_CREDIT =
  "Sentinel-2 cloudless by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2025)";

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
