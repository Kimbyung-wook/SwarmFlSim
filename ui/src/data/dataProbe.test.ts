// TC-UI-074: 로컬 지도 자료 탐지가 404를 내지 않고 결과는 예전과 같다 (IMP-UI-084, QA O-7)
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { offlineDataHandler } from "../server/offlineData";
import type { FetchLike } from "./dataProbe";
import { dataExists, probeUrl } from "./dataProbe";

interface Reply {
  status: number;
  headers: Record<string, string>;
  body: string;
}

/** 미들웨어를 직접 불러 응답을 받는다. next로 넘기면 SPA 폴백(200 text/html)을 흉내 낸다 */
function serve(handler: ReturnType<typeof offlineDataHandler>, url: string): Promise<Reply> {
  return new Promise((resolve) => {
    const headers: Record<string, string> = {};
    const chunks: Buffer[] = [];
    const res = {
      statusCode: 200,
      setHeader: (k: string, v: string) => void (headers[k.toLowerCase()] = v),
      write: (c: Buffer | string) => void chunks.push(Buffer.from(c)),
      on: () => res,
      once: () => res,
      emit: () => true,
      end: (c?: Buffer | string) => {
        if (c) chunks.push(Buffer.from(c));
        resolve({ status: res.statusCode, headers, body: Buffer.concat(chunks).toString("utf8") });
      },
    };
    handler({ url } as never, res as never, () => resolve({ status: 200, headers: { "content-type": "text/html" }, body: "<!doctype html>" }));
  });
}

/** 미들웨어를 fetch처럼 쓴다. 받은 URL과 상태를 남긴다 */
function fetchVia(handler: ReturnType<typeof offlineDataHandler>, log: string[]): FetchLike {
  return async (url) => {
    const r = await serve(handler, url);
    log.push(`${r.status} ${url}`);
    return {
      ok: r.status >= 200 && r.status < 300,
      headers: new Headers(r.headers),
      json: async () => JSON.parse(r.body),
    };
  };
}

let full: string;
let empty: string;

beforeAll(() => {
  full = mkdtempSync(join(tmpdir(), "swarm-data-"));
  empty = mkdtempSync(join(tmpdir(), "swarm-empty-"));
  mkdirSync(join(full, "tiles", "imagery"), { recursive: true });
  mkdirSync(join(full, "tiles", "terrain"), { recursive: true });
  writeFileSync(join(full, "tiles", "imagery", "tilemapresource.xml"), "<TileMap/>");
  writeFileSync(join(full, "tiles", "terrain", "layer.json"), "{}");
});
afterAll(() => {
  rmSync(full, { recursive: true, force: true });
  rmSync(empty, { recursive: true, force: true });
});

const IMG = "/data/tiles/imagery/tilemapresource.xml";
const TER = "/data/tiles/terrain/layer.json";

describe("지도 자료 탐지 (TC-UI-074)", () => {
  it("탐지 엔드포인트는 있든 없든 200 JSON, 데이터 디렉터리 밖은 없음으로 답한다", async () => {
    const h = offlineDataHandler(full);
    const yes = await serve(h, probeUrl(IMG)!);
    expect(yes.status).toBe(200);
    expect(yes.headers["content-type"]).toBe("application/json");
    expect(JSON.parse(yes.body)).toEqual({ exists: true });
    const no = await serve(offlineDataHandler(empty), probeUrl(IMG)!);
    expect(no.status).toBe(200);
    expect(JSON.parse(no.body)).toEqual({ exists: false });
    for (const p of ["../package.json", "tiles", ""]) {
      expect(JSON.parse((await serve(h, `/data/.probe?path=${encodeURIComponent(p)}`)).body)).toEqual({ exists: false });
    }
    // 파일 제공은 그대로: 있으면 200, 없으면 404
    expect((await serve(h, IMG)).status).toBe(200);
    expect((await serve(offlineDataHandler(empty), IMG)).status).toBe(404);
  });

  it("타일이 없을 때 탐지는 404 요청 없이 없음, 있을 때는 있음 (결과는 직접 GET과 같다)", async () => {
    for (const [dir, want] of [[empty, false], [full, true]] as const) {
      const log: string[] = [];
      const f = fetchVia(offlineDataHandler(dir), log);
      expect(await dataExists(IMG, f)).toBe(want);
      expect(await dataExists(TER, f)).toBe(want);
      expect(log.every((l) => l.startsWith("200 /data/.probe?"))).toBe(true);
      expect(log).toHaveLength(2);
    }
  });

  it("탐지 엔드포인트가 없는 배포(정적 서버·SPA 폴백)에서는 직접 GET으로 같은 결과", async () => {
    const statics = (files: Set<string>, spa: boolean): FetchLike => async (url) => {
      const hit = files.has(url);
      const ct = hit ? "application/xml" : spa ? "text/html" : "text/plain";
      return { ok: hit || spa, headers: new Headers({ "content-type": ct }), json: async () => ({}) };
    };
    expect(await dataExists(IMG, statics(new Set([IMG]), false))).toBe(true);
    expect(await dataExists(IMG, statics(new Set(), false))).toBe(false);
    expect(await dataExists(IMG, statics(new Set(), true))).toBe(false); // SPA 폴백 HTML은 없음
    const down: FetchLike = async () => {
      throw new TypeError("network");
    };
    expect(await dataExists(IMG, down)).toBe(false);
  });

  it("/data/ 밖 URL은 탐지 엔드포인트를 쓰지 않는다. 인코딩된 경로는 한 번만 인코드한다", () => {
    expect(probeUrl("http://tiles.example/imagery/tilemapresource.xml")).toBeNull();
    expect(probeUrl("/other/layer.json")).toBeNull();
    expect(probeUrl("/data/tiles/a%20b/layer.json")).toBe("/data/.probe?path=tiles%2Fa%20b%2Flayer.json");
    expect(probeUrl("/data/%E0%A4%A")).toBeNull();
  });
});
