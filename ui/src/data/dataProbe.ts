// IMP-UI-084: 로컬 지도 자료 탐지. /data/ 아래 URL은 dev·preview 서버의 탐지 엔드포인트(늘 200)에 먼저 묻는다.
// 없는 타일 디렉터리를 직접 GET하면 404가 브라우저 콘솔 오류로 남기 때문이다 (QA O-7).
// 탐지 엔드포인트가 없는 배포(정적 웹 서버)에서는 예전처럼 직접 GET으로 확인한다. 결과는 같다.

export const DATA_PREFIX = "/data/";
export const PROBE_PATH = "/data/.probe";

export type FetchLike = (url: string, init?: RequestInit) => Promise<Pick<Response, "ok" | "headers" | "json">>;

const isJson = (r: Pick<Response, "headers">) => (r.headers.get("content-type") ?? "").includes("application/json");
const isHtml = (r: Pick<Response, "headers">) => (r.headers.get("content-type") ?? "").includes("text/html");

/** 탐지 엔드포인트 URL. /data/ 밖(다른 호스트·경로)이면 null */
export function probeUrl(url: string): string | null {
  if (!url.startsWith(DATA_PREFIX)) return null;
  try {
    // 쿼리 인자로 넘길 때 다시 인코드하므로 URL 경로의 인코딩을 한 번 푼다
    const rel = decodeURIComponent(url.slice(DATA_PREFIX.length).split("?")[0]);
    return `${PROBE_PATH}?path=${encodeURIComponent(rel)}`;
  } catch {
    return null;
  }
}

/** url이 존재하고 HTML(SPA 폴백)이 아닌 응답을 주는지 */
export async function dataExists(url: string, fetchFn: FetchLike = (u, i) => fetch(u, i)): Promise<boolean> {
  const p = probeUrl(url);
  if (p) {
    try {
      const r = await fetchFn(p, { method: "GET", cache: "no-store" });
      if (r.ok && isJson(r)) {
        const j: unknown = await r.json();
        if (j && typeof j === "object" && typeof (j as { exists?: unknown }).exists === "boolean") return (j as { exists: boolean }).exists;
      }
    } catch {
      // 탐지 엔드포인트가 없거나 실패하면 직접 확인한다
    }
  }
  try {
    const r = await fetchFn(url, { method: "GET", cache: "no-store" });
    return r.ok && !isHtml(r);
  } catch {
    return false;
  }
}
