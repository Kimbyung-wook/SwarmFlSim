// IMP-UI-067: 모드 전환 전 화면 중심·폭을 읽고, 전환 뒤 새 모드에서 같은 중심·폭으로 카메라를 놓는다 (REQ-UI-001, DEC-003)
// IMP-UI-068: 맞춤 뷰 사각형으로 카메라를 놓는다
import { Cartesian2, Cartesian3, Math as CesiumMath, Rectangle, SceneMode } from "cesium";
import type { Camera, Scene } from "cesium";
import type { FitRect, MapMode, ViewMemo } from "../model/viewKeep";
import { heightForWidth, perspectiveWidth } from "../model/viewKeep";

const DEFAULT_FOV = CesiumMath.toRadians(60);

const fovOf = (camera: Camera): number => {
  const f = (camera.frustum as { fov?: number }).fov;
  return typeof f === "number" && f > 0 ? f : DEFAULT_FOV;
};

export function modeOf(scene: Scene): MapMode {
  return scene.mode === SceneMode.SCENE2D ? "2d" : scene.mode === SceneMode.COLUMBUS_VIEW ? "columbus" : "3d";
}

/** 지금 화면의 중심(지면)과 가로로 보이는 폭. 모드 전환 중이면 null */
export function captureView(scene: Scene): ViewMemo | null {
  if (scene.mode === SceneMode.MORPHING) return null;
  const camera = scene.camera;
  const heading = camera.heading;
  const below = camera.positionCartographic;
  if (scene.mode === SceneMode.SCENE2D) {
    const f = camera.frustum as { right?: number; left?: number };
    const w = (f.right ?? 0) - (f.left ?? 0);
    return { lat: CesiumMath.toDegrees(below.latitude), lon: CesiumMath.toDegrees(below.longitude), widthM: w, heading: 0 };
  }
  const canvas = scene.canvas;
  const mid = new Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2);
  const hit = camera.pickEllipsoid(mid, scene.globe.ellipsoid);
  const fov = fovOf(camera);
  if (!hit) {
    // 하늘을 향한 기울어진 시점: 카메라 바로 아래 지점과 높이
    return {
      lat: CesiumMath.toDegrees(below.latitude),
      lon: CesiumMath.toDegrees(below.longitude),
      widthM: perspectiveWidth(Math.max(below.height, 1), fov),
      heading,
    };
  }
  const c = scene.globe.ellipsoid.cartesianToCartographic(hit);
  // 3D는 실제 거리, 2.5D는 좌표계가 투영 평면이라 높이/sin(내려다보는 각)으로 근사
  const range =
    scene.mode === SceneMode.SCENE3D
      ? Cartesian3.distance(camera.positionWC, hit)
      : below.height / Math.max(Math.sin(-camera.pitch), 0.2);
  return { lat: CesiumMath.toDegrees(c.latitude), lon: CesiumMath.toDegrees(c.longitude), widthM: perspectiveWidth(range, fov), heading };
}

/** 지금 모드에서 memo의 중심을 수직으로 내려다보며 같은 폭이 보이게 놓는다 */
export function restoreView(scene: Scene, memo: ViewMemo): void {
  const mode = modeOf(scene);
  const h = heightForWidth(mode, memo.widthM, fovOf(scene.camera));
  scene.camera.setView({
    destination: Cartesian3.fromDegrees(memo.lon, memo.lat, h),
    orientation: { heading: mode === "2d" ? 0 : memo.heading, pitch: -CesiumMath.PI_OVER_TWO, roll: 0 },
  });
}

export function fitTo(scene: Scene, r: FitRect): void {
  scene.camera.setView({ destination: Rectangle.fromDegrees(r.west, r.south, r.east, r.north) });
}
