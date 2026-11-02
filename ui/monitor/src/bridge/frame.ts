// IMP-MON-002: 브리지 프로토콜 v1 프레임 (docs/10_contracts.md §3.5, DEC-027)
// 바이너리: uint16 키 길이 | 키 | uint16 인코딩 길이 | 인코딩 | 페이로드 (little-endian)
// 텍스트(JSON): hello / welcome / sub / unsub / error

export const BRIDGE_PROTOCOL = 1;
export const DEFAULT_BRIDGE_URL = "ws://localhost:8765/bus";
export const PROTOBUF_ENCODING_PREFIX = "application/protobuf;";

export interface BusFrame {
  key: string;
  encoding: string;
  payload: Uint8Array;
}

const enc = new TextEncoder();
const dec = new TextDecoder("utf-8", { fatal: true });

export function encodeFrame(f: BusFrame): Uint8Array {
  const k = enc.encode(f.key);
  const e = enc.encode(f.encoding);
  if (k.length > 0xffff || e.length > 0xffff) throw new RangeError("키·인코딩은 65535바이트 이하");
  const out = new Uint8Array(4 + k.length + e.length + f.payload.length);
  const dv = new DataView(out.buffer);
  dv.setUint16(0, k.length, true);
  out.set(k, 2);
  dv.setUint16(2 + k.length, e.length, true);
  out.set(e, 4 + k.length);
  out.set(f.payload, 4 + k.length + e.length);
  return out;
}

export class FrameError extends Error {}

/** 페이로드는 입력 버퍼를 공유한다(복사하지 않음) */
export function decodeFrame(buf: Uint8Array): BusFrame {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  if (buf.length < 4) throw new FrameError("프레임이 짧다");
  const kl = dv.getUint16(0, true);
  if (2 + kl + 2 > buf.length) throw new FrameError("키 길이가 프레임을 넘는다");
  const el = dv.getUint16(2 + kl, true);
  const p = 4 + kl + el;
  if (p > buf.length) throw new FrameError("인코딩 길이가 프레임을 넘는다");
  try {
    return {
      key: dec.decode(buf.subarray(2, 2 + kl)),
      encoding: dec.decode(buf.subarray(4 + kl, p)),
      payload: buf.subarray(p),
    };
  } catch {
    throw new FrameError("UTF-8이 아니다");
  }
}

/** `application/protobuf;swarm.v1.LinkOutcome` → `swarm.v1.LinkOutcome`. 형식이 다르면 undefined */
export function protobufTypeName(encoding: string): string | undefined {
  return encoding.startsWith(PROTOBUF_ENCODING_PREFIX) ? encoding.slice(PROTOBUF_ENCODING_PREFIX.length) : undefined;
}

// ---- 텍스트 프레임

export type ClientRole = "control" | "observer";

export interface HelloMsg {
  op: "hello";
  client: string;
  role: ClientRole;
  gcs?: string;
}
export interface SubMsg {
  op: "sub";
  id: number;
  key: string;
  max_hz: number;
}
export interface UnsubMsg {
  op: "unsub";
  id: number;
}
export interface WelcomeMsg {
  op: "welcome";
  protocol: number;
  contract: string;
}
export interface ErrorMsg {
  op: "error";
  code: "bad_request" | "forbidden" | "unsupported" | string;
  msg: string;
}

export type ClientMsg = HelloMsg | SubMsg | UnsubMsg;
export type ServerMsg = WelcomeMsg | ErrorMsg;

export function parseServerMsg(text: string): ServerMsg {
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch {
    throw new FrameError("JSON이 아니다");
  }
  if (typeof v !== "object" || v === null) throw new FrameError("객체가 아니다");
  const o = v as Record<string, unknown>;
  if (o.op === "welcome" && typeof o.protocol === "number") {
    return { op: "welcome", protocol: o.protocol, contract: String(o.contract ?? "") };
  }
  if (o.op === "error") return { op: "error", code: String(o.code ?? ""), msg: String(o.msg ?? "") };
  throw new FrameError(`알 수 없는 op: ${String(o.op)}`);
}
