// IMP-UI-033: 데이터 소스 설정. URL 쿼리 > 환경변수 > 기본값 (DEC-027)
// ?source=mock|bus  ?bridge=ws://host:8765/bus  ?gcs=gcs-01
import { BRIDGE_DEFAULT_URL } from "./bridgeFrame";

export type SourceKind = "mock" | "bus";

export interface SourceConfig {
  kind: SourceKind;
  bridgeUrl: string;
  /** null이면 C2 명령을 보내지 않는다(관찰만) */
  gcs: string | null;
  /** 목 소스 UAV 수 (?uavs=N, 성능 확인용). null이면 기본 24대 */
  mockUavs: number | null;
}

/** 목 소스 UAV 수 → 편대 배치. 편대당 최대 10대 (IMP-UI-082) */
export function mockLayout(n: number): { flights: number; perFlight: number } {
  const perFlight = Math.min(10, Math.max(1, n));
  return { flights: Math.ceil(n / perFlight), perFlight };
}

const ENTITY_ID = /^[a-z][a-z0-9]*(-[a-z0-9]+)+$/;

export function defaultBridgeUrl(hostname: string | undefined): string {
  return hostname ? `ws://${hostname}:8765/bus` : BRIDGE_DEFAULT_URL;
}

export function parseSourceConfig(
  search: string,
  env: { VITE_BRIDGE_URL?: string; VITE_GCS?: string } = {},
  hostname?: string,
): SourceConfig {
  const q = new URLSearchParams(search);
  const kind: SourceKind = q.get("source") === "bus" ? "bus" : "mock";
  const bridgeUrl = q.get("bridge") || env.VITE_BRIDGE_URL || defaultBridgeUrl(hostname);
  const g = q.has("gcs") ? q.get("gcs")! : (env.VITE_GCS ?? "gcs-01");
  const gcs = g && g.length <= 32 && ENTITY_ID.test(g) ? g : null;
  const u = Number(q.get("uavs"));
  const mockUavs = Number.isInteger(u) && u >= 1 && u <= 200 ? u : null;
  return { kind, bridgeUrl, gcs, mockUavs };
}

/** 소스를 바꾼 URL 쿼리. 다른 쿼리는 그대로 둔다 */
export function withSource(search: string, kind: SourceKind): string {
  const q = new URLSearchParams(search);
  q.set("source", kind);
  return `?${q.toString()}`;
}
