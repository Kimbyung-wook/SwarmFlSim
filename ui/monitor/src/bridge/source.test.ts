// TC-MON-002: 브리지 클라이언트 접속 절차·구독·재접속 (IMP-MON-003)
import { afterEach, describe, expect, it, vi } from "vitest";
import { encodeFrame } from "./frame";
import type { BusFrame } from "./frame";
import type { SourceStatus, WebSocketLike } from "./source";
import { BridgeSource, MONITOR_SUBSCRIPTIONS } from "./source";

class FakeSocket implements WebSocketLike {
  binaryType = "blob";
  readyState = 0;
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code?: number; reason?: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  sent: unknown[] = [];
  closed = false;
  send(d: string) {
    this.sent.push(JSON.parse(d));
  }
  close() {
    this.closed = true;
  }
}

function setup(reconnectMs = 0) {
  const sockets: FakeSocket[] = [];
  const frames: BusFrame[] = [];
  const status: SourceStatus[] = [];
  const src = new BridgeSource({
    url: "ws://x/bus",
    client: "monitor-1",
    reconnectMs,
    createSocket: () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    },
  });
  src.onFrame((f) => frames.push(f));
  src.onStatus((s) => status.push(s));
  return { src, sockets, frames, status };
}

afterEach(() => vi.useRealTimers());

describe("BridgeSource", () => {
  it("observer로 hello를 보내고 welcome 뒤에 모니터 키를 구독한다", () => {
    const { src, sockets, status } = setup();
    src.connect();
    const s = sockets[0];
    expect(s.binaryType).toBe("arraybuffer");
    s.onopen!({});
    expect(s.sent[0]).toEqual({ op: "hello", client: "monitor-1", role: "observer" });
    s.onmessage!({ data: '{"op":"welcome","protocol":1,"contract":"0.2.0"}' });
    const subs = s.sent.slice(1) as { op: string; id: number; key: string; max_hz: number }[];
    expect(subs.map((m) => m.key)).toEqual(MONITOR_SUBSCRIPTIONS.map((m) => m.key));
    expect(new Set(subs.map((m) => m.id)).size).toBe(subs.length);
    expect(subs.find((m) => m.key === "link/outcome/**")!.max_hz).toBe(0);
    expect(status.at(-1)).toMatchObject({ state: "open", contract: "0.2.0" });
  });

  it("바이너리 프레임을 전달하고 깨진 프레임은 센다", () => {
    const { src, sockets, frames } = setup();
    src.connect();
    const b = encodeFrame({ key: "truth/state", encoding: "e", payload: new Uint8Array([5]) });
    sockets[0].onmessage!({ data: b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) });
    sockets[0].onmessage!({ data: new Uint8Array([1]).buffer });
    expect(frames).toHaveLength(1);
    expect(frames[0].key).toBe("truth/state");
    expect(src.badFrames).toBe(1);
  });

  it("프로토콜 버전이 다르면 오류로 끊는다", () => {
    const { src, sockets, status } = setup();
    src.connect();
    sockets[0].onmessage!({ data: '{"op":"welcome","protocol":2,"contract":"9"}' });
    expect(sockets[0].closed).toBe(true);
    expect(status.at(-1)!.state).toBe("error");
    expect(sockets[0].sent).toHaveLength(0);
  });

  it("error 프레임을 상태로 알린다", () => {
    const { src, sockets, status } = setup();
    src.connect();
    sockets[0].onmessage!({ data: '{"op":"error","code":"bad_request","msg":"m"}' });
    expect(status.at(-1)).toEqual({ state: "error", detail: "bad_request: m" });
  });

  it("끊기면 다시 붙고, close 뒤에는 붙지 않는다", () => {
    vi.useFakeTimers();
    const { src, sockets } = setup(1000);
    src.connect();
    sockets[0].onclose!({ code: 1006 });
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(2);
    src.close();
    sockets[1].onclose!({ code: 1000 });
    vi.advanceTimersByTime(5000);
    expect(sockets).toHaveLength(2);
  });
});
