// IMP-UI-013: 오프라인 Cesium Viewer (DEC-003, DEC-004, DEC-016, REQ-SIM-003)
// IMP-UI-071: 바탕은 늘 내장 영상, 로컬 고해상도 영상(z13)은 그 위에 겹치고 로컬 자료 출처를 표기한다 (DEC-057)
// Cesium ion 등 외부 서비스를 쓰지 않는다. 로컬 이미지 타일·quantized-mesh 지형을 찾고, 없으면
// Cesium 내장 Natural Earth II 저해상도 영상과 기본 타원체로 동작한다.
import {
  buildModuleUrl,
  CameraEventType,
  CesiumTerrainProvider,
  Credit,
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  KeyboardEventModifier,
  TileMapServiceImageryProvider,
  UrlTemplateImageryProvider,
  Viewer,
} from "cesium";
import type { ImageryProvider, TerrainProvider } from "cesium";
import { IMAGERY_CREDIT, mapCredits } from "../model/mapCredits";

export interface MapDataConfig {
  /** TMS 디렉터리(tilemapresource.xml 포함) 또는 {z}/{x}/{y} 템플릿 URL */
  imageryUrl: string;
  /** quantized-mesh 지형 디렉터리(layer.json 포함) */
  terrainUrl: string;
  /** 로컬 영상 출처 표기 (연도판·출처가 다르면 바꾼다) */
  imageryCredit: string;
}

/** 로컬 영상 최대 줌 (DEC-057: Sentinel-2 cloudless z13 ≈ 19 m/px) */
export const IMAGERY_MAX_LEVEL = 13;

export const defaultMapConfig: MapDataConfig = {
  imageryUrl: import.meta.env.VITE_IMAGERY_URL ?? "/data/tiles/imagery",
  terrainUrl: import.meta.env.VITE_TERRAIN_URL ?? "/data/tiles/terrain",
  imageryCredit: import.meta.env.VITE_IMAGERY_CREDIT ?? IMAGERY_CREDIT,
};

export interface MapDataStatus {
  imagery: "local" | "builtin";
  terrain: "local" | "ellipsoid";
}

/** url이 존재하고 HTML(SPA 폴백)이 아닌 응답을 주는지 */
async function exists(url: string): Promise<boolean> {
  try {
    const r = await fetch(url, { method: "GET", cache: "no-store" });
    return r.ok && !(r.headers.get("content-type") ?? "").includes("text/html");
  } catch {
    return false;
  }
}

/** 로컬 영상. 없으면 null (바탕 내장 영상만 쓴다) */
async function localImagery(cfg: MapDataConfig): Promise<ImageryProvider | null> {
  if (cfg.imageryUrl.includes("{z}")) {
    return new UrlTemplateImageryProvider({ url: cfg.imageryUrl, maximumLevel: IMAGERY_MAX_LEVEL });
  }
  if (await exists(`${cfg.imageryUrl}/tilemapresource.xml`)) {
    // 범위(BoundingBox)는 tilemapresource.xml에서 읽는다. 범위 밖은 바탕 영상이 보인다
    return TileMapServiceImageryProvider.fromUrl(cfg.imageryUrl, { maximumLevel: IMAGERY_MAX_LEVEL });
  }
  return null;
}

async function terrainProvider(cfg: MapDataConfig): Promise<[TerrainProvider, MapDataStatus["terrain"]]> {
  if (await exists(`${cfg.terrainUrl}/layer.json`)) {
    return [await CesiumTerrainProvider.fromUrl(cfg.terrainUrl), "local"];
  }
  return [new EllipsoidTerrainProvider(), "ellipsoid"];
}

/**
 * RTS 입력에 맞춘 카메라 조작: 왼쪽 드래그는 선택 박스로 비우고,
 * 오른쪽 드래그 = 이동/회전, 휠 = 확대, 가운데 드래그 또는 Ctrl+오른쪽 드래그 = 기울이기.
 */
function configureCameraInput(viewer: Viewer): void {
  const c = viewer.scene.screenSpaceCameraController;
  c.rotateEventTypes = CameraEventType.RIGHT_DRAG;
  c.translateEventTypes = CameraEventType.RIGHT_DRAG;
  c.zoomEventTypes = [CameraEventType.WHEEL, CameraEventType.PINCH];
  c.tiltEventTypes = [
    CameraEventType.MIDDLE_DRAG,
    CameraEventType.PINCH,
    { eventType: CameraEventType.RIGHT_DRAG, modifier: KeyboardEventModifier.CTRL },
  ];
  c.lookEventTypes = [{ eventType: CameraEventType.RIGHT_DRAG, modifier: KeyboardEventModifier.SHIFT }];
}

export async function createViewer(
  container: HTMLElement,
  cfg: MapDataConfig = defaultMapConfig,
): Promise<{ viewer: Viewer; status: MapDataStatus }> {
  Ion.defaultAccessToken = "";
  const [base, local, [terrain, terrainKind]] = await Promise.all([
    TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII")),
    localImagery(cfg),
    terrainProvider(cfg),
  ]);
  const viewer = new Viewer(container, {
    baseLayer: new ImageryLayer(base),
    terrainProvider: terrain,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    requestRenderMode: false,
  });
  viewer.scene.globe.depthTestAgainstTerrain = false;
  if (local) viewer.imageryLayers.addImageryProvider(local);
  const status: MapDataStatus = { imagery: local ? "local" : "builtin", terrain: terrainKind };
  for (const text of mapCredits(status, cfg.imageryCredit)) {
    viewer.creditDisplay.addStaticCredit(new Credit(text, true));
  }
  configureCameraInput(viewer);
  return { viewer, status };
}
