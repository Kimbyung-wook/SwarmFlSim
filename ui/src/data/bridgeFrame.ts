// IMP-UI-023: 브리지 프로토콜 v1 프레임 (docs/10_contracts.md §3.5, DEC-027)
// 바이너리: uint16 키 길이 | 키 | uint16 인코딩 길이 | 인코딩 | 페이로드 (little-endian). 텍스트: JSON 제어 프레임
export const BRIDGE_PROTOCOL = 1;
export const BRIDGE_DEFAULT_URL = "ws://localhost:8765/bus";

export interface BusFrame {
  key: string;
  encoding: string;
  payload: Uint8Array;
}

export type BridgeRole = "control" | "observer";
export type BridgeErrorCode = "bad_request" | "forbidden" | "unsupported";

export type ClientMessage =
  | { op: "hello"; client: string; role: BridgeRole; gcs?: string }
  | { op: "sub"; id: number; key: string; max_hz: number }
  | { op: "unsub"; id: number };

export type ServerMessage =
  | { op: "welcome"; protocol: number; contract: string }
  | { op: "error"; code: BridgeErrorCode; msg: string };

const utf8 = new TextEncoder();
const utf8d = new TextDecoder("utf-8", { fatal: true });

export function encodeFrame(key: string, encoding: string, payload: Uint8Array): Uint8Array<ArrayBuffer> {
  const k = utf8.encode(key);
  const e = utf8.encode(encoding);
  if (k.length > 0xffff || e.length > 0xffff) throw new Error("키 또는 인코딩이 65535바이트를 넘는다");
  const out = new Uint8Array(4 + k.length + e.length + payload.length);
  const dv = new DataView(out.buffer);
  dv.setUint16(0, k.length, true);
  out.set(k, 2);
  dv.setUint16(2 + k.length, e.length, true);
  out.set(e, 4 + k.length);
  out.set(payload, 4 + k.length + e.length);
  return out;
}

export function decodeFrame(data: ArrayBuffer | Uint8Array): BusFrame {
  const u8 = data instanceof Uint8Array ? data : new Uint8Array(data);
  const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
  if (u8.length < 4) throw new Error("프레임이 짧다");
  const klen = dv.getUint16(0, true);
  if (2 + klen + 2 > u8.length) throw new Error("프레임이 짧다");
  const elen = dv.getUint16(2 + klen, true);
  const end = 4 + klen + elen;
  if (end > u8.length) throw new Error("프레임이 짧다");
  const key = utf8d.decode(u8.subarray(2, 2 + klen));
  if (!key) throw new Error("빈 키");
  return { key, encoding: utf8d.decode(u8.subarray(4 + klen, end)), payload: u8.subarray(end) };
}

/** 서버 텍스트 프레임 해석. 형식이 틀리면 null */
export function parseServerMessage(text: string): ServerMessage | null {
  try {
    const m = JSON.parse(text) as { op?: unknown };
    if (m && (m.op === "welcome" || m.op === "error")) return m as ServerMessage;
  } catch {
    /* 무시 */
  }
  return null;
}

/** Zenoh 키 표현식 일치. `*`는 한 마디, `**`는 0개 이상 마디 (swarm_api.keys.keyexpr_matches와 같음) */
export function keyexprMatches(expr: string, key: string): boolean {
  const e = expr.split("/");
  const k = key.split("/");
  const match = (i: number, j: number): boolean => {
    if (i === e.length) return j === k.length;
    if (e[i] === "**") {
      for (let jj = j; jj <= k.length; jj++) if (match(i + 1, jj)) return true;
      return false;
    }
    if (j === k.length) return false;
    return (e[i] === "*" || e[i] === k[j]) && match(i + 1, j + 1);
  };
  return match(0, 0);
}
