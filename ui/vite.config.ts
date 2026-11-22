// IMP-UI-002: Vite 설정. Cesium 정적 자산과 오프라인 지도 데이터를 로컬에서 제공한다 (DEC-003, DEC-004, DEC-016)
import { join, resolve } from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";
import { offlineData } from "./src/server/offlineData";

const cesiumBuild = "node_modules/cesium/Build/Cesium";
const cesiumBaseUrl = "cesium";

// 저장소 루트의 data/ (gitignore 대상). SWARM_DATA_DIR로 바꿀 수 있다.
// /data/** 제공과 탐지 엔드포인트는 src/server/offlineData.ts (IMP-UI-084)
const dataDir = resolve(process.env.SWARM_DATA_DIR ?? join(import.meta.dirname, "..", "data"));

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify(`/${cesiumBaseUrl}`),
  },
  plugins: [
    react(),
    viteStaticCopy({
      // node_modules/cesium/Build/Cesium/<dir>/** → /cesium/<dir>/**
      targets: ["ThirdParty", "Workers", "Assets", "Widgets"].map((d) => ({
        src: `${cesiumBuild}/${d}/**/*`,
        dest: cesiumBaseUrl,
        rename: { stripBase: 4 },
      })),
    }),
    offlineData(dataDir),
  ],
  build: {
    chunkSizeWarningLimit: 6000,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
