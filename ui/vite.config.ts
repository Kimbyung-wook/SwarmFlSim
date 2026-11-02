// IMP-UI-002: Vite 설정. Cesium 정적 자산과 오프라인 지도 데이터를 로컬에서 제공한다 (DEC-003, DEC-004, DEC-016)
import { closeSync, createReadStream, existsSync, openSync, readSync, statSync } from "node:fs";
import { extname, join, normalize, resolve, sep } from "node:path";
import type { Connect, Plugin } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";

const cesiumBuild = "node_modules/cesium/Build/Cesium";
const cesiumBaseUrl = "cesium";

// 저장소 루트의 data/ (gitignore 대상). SWARM_DATA_DIR로 바꿀 수 있다.
const dataDir = resolve(process.env.SWARM_DATA_DIR ?? join(import.meta.dirname, "..", "data"));

const contentTypes: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".xml": "application/xml",
  ".json": "application/json",
  ".terrain": "application/vnd.quantized-mesh",
};

// /data/** → dataDir/**. dev·preview 서버 전용. 빌드 배포 시에는 웹 서버가 같은 경로로 제공한다.
function offlineData(): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const url = (req.url ?? "").split("?")[0];
    if (!url.startsWith("/data/")) return next();
    const file = normalize(join(dataDir, decodeURIComponent(url.slice("/data/".length))));
    if (!file.startsWith(dataDir + sep) || !existsSync(file) || !statSync(file).isFile()) {
      res.statusCode = 404;
      res.end();
      return;
    }
    res.setHeader("Content-Type", contentTypes[extname(file).toLowerCase()] ?? "application/octet-stream");
    // cesium-terrain-builder 산출물은 gzip으로 저장된다
    const head = Buffer.alloc(2);
    const fd = openSync(file, "r");
    readSync(fd, head, 0, 2, 0);
    closeSync(fd);
    if (head[0] === 0x1f && head[1] === 0x8b) res.setHeader("Content-Encoding", "gzip");
    createReadStream(file).pipe(res);
  };
  return {
    name: "swarm-offline-data",
    configureServer: (server) => void server.middlewares.use(handler),
    configurePreviewServer: (server) => void server.middlewares.use(handler),
  };
}

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
    offlineData(),
  ],
  build: {
    chunkSizeWarningLimit: 6000,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
