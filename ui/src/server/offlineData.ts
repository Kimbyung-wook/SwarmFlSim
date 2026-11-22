// IMP-UI-002: /data/** → dataDir/** 정적 제공. dev·preview 서버 전용. 빌드 배포 시에는 웹 서버가 같은 경로로 제공한다.
// IMP-UI-084: /data/.probe?path=<상대 경로>는 파일이 있든 없든 200 {"exists": bool}을 돌려준다.
// 로컬 타일 탐지가 404를 내지 않아 브라우저 콘솔에 오류가 남지 않는다 (QA O-7).
// 이 파일은 vite.config.ts(Node)만 가져다 쓴다. 앱 번들에는 들어가지 않는다.
import { closeSync, createReadStream, existsSync, openSync, readSync, statSync } from "node:fs";
import { extname, join, normalize, sep } from "node:path";
import type { Connect, Plugin } from "vite";
import { DATA_PREFIX, PROBE_PATH } from "../data/dataProbe";

const contentTypes: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".xml": "application/xml",
  ".json": "application/json",
  ".terrain": "application/vnd.quantized-mesh",
};

/** dataDir 안의 파일 경로(rel은 디코드된 상대 경로). dataDir 밖이거나 파일이 아니면 null */
export function dataFile(dataDir: string, rel: string): string | null {
  if (rel === "") return null;
  const file = normalize(join(dataDir, rel));
  if (!file.startsWith(dataDir + sep) || !existsSync(file) || !statSync(file).isFile()) return null;
  return file;
}

function decoded(s: string): string | null {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
}

export function offlineDataHandler(dataDir: string): Connect.NextHandleFunction {
  return (req, res, next) => {
    const [url, query = ""] = (req.url ?? "").split("?");
    if (url === PROBE_PATH) {
      // URLSearchParams가 디코드한 상대 경로
      const exists = dataFile(dataDir, new URLSearchParams(query).get("path") ?? "") !== null;
      res.statusCode = 200;
      res.setHeader("Content-Type", "application/json");
      res.setHeader("Cache-Control", "no-store");
      res.end(JSON.stringify({ exists }));
      return;
    }
    if (!url.startsWith(DATA_PREFIX)) return next();
    const rel = decoded(url.slice(DATA_PREFIX.length));
    const file = rel === null ? null : dataFile(dataDir, rel);
    if (!file) {
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
}

export function offlineData(dataDir: string): Plugin {
  const handler = offlineDataHandler(dataDir);
  return {
    name: "swarm-offline-data",
    configureServer: (server) => void server.middlewares.use(handler),
    configurePreviewServer: (server) => void server.middlewares.use(handler),
  };
}
