// IMP-UI-013: 오프라인 Cesium Viewer (DEC-003, DEC-004, DEC-016, REQ-SIM-003)
// Cesium ion 등 외부 서비스를 쓰지 않는다. 로컬 이미지 타일·quantized-mesh 지형을 찾고, 없으면
// Cesium 내장 Natural Earth II 저해상도 영상과 기본 타원체로 동작한다.
import {
  buildModuleUrl,
  CameraEventType,
  CesiumTerrainProvider,
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  KeyboardEventModifier,
  TileMapServiceImageryProvider,
  UrlTemplateImageryProvider,
  Viewer,
} from "cesium";
import type { ImageryProvider, TerrainProvider } from "cesium";

export interface MapDataConfig {
  /** TMS 디렉터리(tilemapresource.xml 포함) 또는 {z}/{x}/{y} 템플릿 URL */
  imageryUrl: string;
  /** quantized-mesh 지형 디렉터리(layer.json 포함) */
  terrainUrl: string;
}

export const defaultMapConfig: MapDataConfig = {
  imageryUrl: import.meta.env.VITE_IMAGERY_URL ?? "/data/tiles/imagery",
  terrainUrl: import.meta.env.VITE_TERRAIN_URL ?? "/data/tiles/terrain",
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

async function imageryProvider(cfg: MapDataConfig): Promise<[ImageryProvider, MapDataStatus["imagery"]]> {
  if (cfg.imageryUrl.includes("{z}")) {
    return [new UrlTemplateImageryProvider({ url: cfg.imageryUrl, maximumLevel: 12 }), "local"];
  }
  if (await exists(`${cfg.imageryUrl}/tilemapresource.xml`)) {
    return [await TileMapServiceImageryProvider.fromUrl(cfg.imageryUrl), "local"];
  }
  return [await TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII")), "builtin"];
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
  const [[imagery, imageryKind], [terrain, terrainKind]] = await Promise.all([imageryProvider(cfg), terrainProvider(cfg)]);
  const viewer = new Viewer(container, {
    baseLayer: new ImageryLayer(imagery),
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
  configureCameraInput(viewer);
  return { viewer, status: { imagery: imageryKind, terrain: terrainKind } };
}
