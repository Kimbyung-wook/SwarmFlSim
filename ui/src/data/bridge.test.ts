// TC-UI-017: 브리지 프레임 인코딩, 키 표현식, BridgeTransport 접속·구독·재접속 (IMP-UI-023, IMP-UI-024)
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { decodeFrame, encodeFrame, keyexprMatches, parseServerMessage } from "./bridgeFrame";
import type { WebSocketLike } from "./bridgeTransport";
import { BridgeTransport } from "./bridgeTransport";
import { parseSourceConfig, withSource } from "./sourceConfig";

describe("bridgeFrame", () => {
  it("Python swarm_bridge와 같은 바이트 배치 (TC-UI-010 벡터)", () => {
    const f = encodeFrame("a/b", "x", new Uint8Array([7]));
    expect([...f]).toEqual([3, 0, 97, 47, 98, 1, 0, 120, 7]);
    const d = decodeFrame(f.buffer);
    expect(d.key).toBe("a/b");
    expect(d.encoding).toBe("x");
    expect([...d.payload]).toEqual([7]);
  });

  it("UTF-8 키, 빈 페이로드, 오프셋이 있는 Uint8Array", () => {
    const f = encodeFrame("a/가", "application/protobuf;swarm.v1.TruthFrame", new Uint8Array());
    const padded = new Uint8Array(f.length + 3);
    padded.set(f, 3);
    const d = decodeFrame(padded.subarray(3));
    expect(d.key).toBe("a/가");
    expect(d.encoding).toBe("application/protobuf;swarm.v1.TruthFrame");
    expect(d.payload.length).toBe(0);
  });

  it("잘린 프레임과 빈 키는 거부한다", () => {
    for (const b of [[], [5, 0, 97, 98], [2, 0, 97, 98, 9, 0, 120], [0, 0, 0, 0]]) {
      expect(() => decodeFrame(new Uint8Array(b))).toThrow();
    }
  });

  it("키 표현식", () => {
    expect(keyexprMatches("truth/**", "truth/state")).toBe(true);
    expect(keyexprMatches("truth/**", "truth")).toBe(true);
    expect(keyexprMatches("swarm/*/tx/**", "swarm/uav-001/tx/c2/TaskStatus")).toBe(true);
    expect(keyexprMatches("swarm/*/tx/**", "swarm/uav-001/rx/c2/TaskStatus")).toBe(false);
    expect(keyexprMatches("truth/state", "truth/state/x")).toBe(false);
    expect(keyexprMatches("a/**/c", "a/b/b/c")).toBe(true);
  });

  it("서버 제어 프레임", () => {
    expect(parseServerMessage('{"op":"welcome","protocol":1,"contract":"0.2.0"}')).toEqual({ op: "welcome", protocol: 1, contract: "0.2.0" });
    expect(parseServerMessage("x")).toBeNull();
    expect(parseServerMessage('{"op":"sub"}')).toBeNull();
  });
});

class FakeSocket implements WebSocketLike {
  static all: FakeSocket[] = [];
  binaryType = "blob";
  readyState = 0;
  sent: (string | Uint8Array)[] = [];
  closed: { code?: number; reason?: string } | null = null;
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code: number; reason: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.all.push(this);
  }
  send(d: string | Uint8Array) {
    this.sent.push(d);
  }
  close(code?: number, reason?: string) {
    this.closed = { code, reason };
  }
  // 서버 쪽 동작
  accept() {
    this.readyState = 1;
    this.onopen?.({});
  }
  welcome(protocol = 1) {
    this.onmessage?.({ data: JSON.stringify({ op: "welcome", protocol, contract: "0.2.0" }) });
  }
  drop(code = 1006, reason = "") {
    this.readyState = 3;
    this.onclose?.({ code, reason });
  }
  json() {
    return this.sent.filter((s): s is string => typeof s === "string").map((s) => JSON.parse(s));
  }
}

function last(): FakeSocket {
  return FakeSocket.all[FakeSocket.all.length - 1];
}

function make(extra: Partial<ConstructorParameters<typeof BridgeTransport>[0]> = {}) {
  const states: string[] = [];
  const errors: string[] = [];
  const t = new BridgeTransport({
    url: "ws://h:8765/bus",
    client: "ui-test",
    gcs: "gcs-01",
    socketFactory: (u) => new FakeSocket(u),
    onState: (s) => states.push(s),
    onError: (c) => errors.push(c),
    ...extra,
  });
  return { t, states, errors };
}

describe("BridgeTransport", () => {
  beforeEach(() => {
    FakeSocket.all = [];
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("hello → welcome 뒤 구독을 보내고, 받은 프레임을 키 표현식으로 나눈다", async () => {
    const { t, states } = make();
    const got: string[] = [];
    t.subscribe("truth/state", (p, k) => got.push(`A:${k}:${p[0]}`), { maxHz: 20 });
    t.subscribe("swarm/gcs-01/rx/**", (_p, k, e) => got.push(`B:${k}:${e}`));
    const p = t.open();
    const ws = last();
    expect(ws.binaryType).toBe("arraybuffer");
    ws.accept();
    expect(ws.json()).toEqual([{ op: "hello", client: "ui-test", role: "control", gcs: "gcs-01" }]);
    expect(() => t.put("sim/ctrl/cmd", new Uint8Array(), "e")).toThrow();
    ws.welcome();
    await p;
    expect(t.isOpen).toBe(true);
    expect(ws.json().slice(1)).toEqual([
      { op: "sub", id: 1, key: "truth/state", max_hz: 20 },
      { op: "sub", id: 2, key: "swarm/gcs-01/rx/**", max_hz: 0 },
    ]);
    ws.onmessage!({ data: encodeFrame("truth/state", "e", new Uint8Array([9])).buffer });
    ws.onmessage!({ data: encodeFrame("swarm/gcs-01/rx/c2/TaskStatus", "env", new Uint8Array()).buffer });
    ws.onmessage!({ data: encodeFrame("other/key", "e", new Uint8Array()).buffer });
    ws.onmessage!({ data: new Uint8Array([1]).buffer });
    expect(got).toEqual(["A:truth/state:9", "B:swarm/gcs-01/rx/c2/TaskStatus:env"]);
    expect(t.received).toBe(3);
    expect(t.malformed).toBe(1);

    t.put("sim/ctrl/cmd", new Uint8Array([1, 2]), "enc");
    const bin = ws.sent.find((s) => typeof s !== "string") as Uint8Array;
    expect(decodeFrame(bin).key).toBe("sim/ctrl/cmd");
    expect(states).toEqual(["connecting", "open"]);
  });

  it("같은 키 표현식은 서버 구독을 함께 쓰고, 마지막 해제 때 unsub한다", async () => {
    const { t } = make();
    const p = t.open();
    last().accept();
    last().welcome();
    await p;
    const ws = last();
    const a = t.subscribe("truth/state", () => {}, { maxHz: 10 });
    const b = t.subscribe("truth/state", () => {}, { maxHz: 5 });
    expect(ws.json().filter((m) => m.op === "sub")).toEqual([{ op: "sub", id: 1, key: "truth/state", max_hz: 10 }]);
    // 더 높은 주기(0 = 제한 없음)를 원하면 서버 구독을 바꾼다
    const c = t.subscribe("truth/state", () => {});
    expect(ws.json().slice(-2)).toEqual([
      { op: "unsub", id: 1 },
      { op: "sub", id: 2, key: "truth/state", max_hz: 0 },
    ]);
    a();
    b();
    expect(ws.json().filter((m) => m.op === "unsub")).toHaveLength(1);
    c();
    expect(ws.json().at(-1)).toEqual({ op: "unsub", id: 2 });
  });

  it("끊기면 다시 붙어 hello와 구독을 다시 보낸다", async () => {
    const { t, states } = make({ reconnectMs: 1000 });
    t.subscribe("truth/state", () => {});
    const p = t.open();
    last().accept();
    last().welcome();
    await p;
    last().drop(1006, "");
    expect(t.isOpen).toBe(false);
    expect(states.at(-1)).toBe("connecting");
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.all).toHaveLength(2);
    last().accept();
    last().welcome();
    expect(last().json()).toEqual([
      { op: "hello", client: "ui-test", role: "control", gcs: "gcs-01" },
      { op: "sub", id: 1, key: "truth/state", max_hz: 0 },
    ]);
    expect(states.at(-1)).toBe("open");
    t.close();
    expect(last().closed?.code).toBe(1000);
    vi.advanceTimersByTime(5000);
    expect(FakeSocket.all).toHaveLength(2);
  });

  it("첫 접속 실패·hello 거부·프로토콜 불일치·welcome 시간 초과", async () => {
    const a = make({ reconnectMs: 0 });
    const pa = a.t.open();
    last().drop(1006, "refused");
    await expect(pa).rejects.toThrow(/refused/);
    expect(a.states.at(-1)).toBe("closed");

    const b = make({ reconnectMs: 0 });
    const pb = b.t.open();
    last().accept();
    last().onmessage!({ data: JSON.stringify({ op: "error", code: "bad_request", msg: "bad gcs" }) });
    await expect(pb).rejects.toThrow(/bad gcs/);
    expect(b.errors).toEqual(["bad_request"]);

    const c = make({ reconnectMs: 1000 });
    const pc = c.t.open();
    last().accept();
    last().welcome(2);
    await expect(pc).rejects.toThrow(/protocol 2/);
    expect(last().closed?.code).toBe(1002);
    last().drop(1002, "protocol mismatch");
    vi.advanceTimersByTime(5000);
    expect(FakeSocket.all).toHaveLength(3); // 다시 붙지 않는다

    const d = make({ reconnectMs: 0, helloTimeoutMs: 500 });
    const pd = d.t.open();
    last().accept();
    vi.advanceTimersByTime(500);
    expect(last().closed?.code).toBe(4000);
    last().drop(4000, "welcome timeout");
    await expect(pd).rejects.toThrow(/welcome timeout/);
  });

  it("observer는 gcs 없이 hello를 보낸다", () => {
    const t = new BridgeTransport({ url: "ws://x/bus", client: "mon-01", role: "observer", socketFactory: (u) => new FakeSocket(u) });
    void t.open().catch(() => {});
    last().accept();
    expect(last().json()[0]).toEqual({ op: "hello", client: "mon-01", role: "observer" });
    t.close();
  });
});

describe("sourceConfig", () => {
  it("쿼리 > 환경변수 > 기본값, 잘못된 GCS는 관찰 전용", () => {
    expect(parseSourceConfig("", {}, "localhost")).toEqual({ kind: "mock", bridgeUrl: "ws://localhost:8765/bus", gcs: "gcs-01" });
    expect(parseSourceConfig("?source=bus&bridge=ws://a:1/bus&gcs=gcs-02", { VITE_BRIDGE_URL: "ws://env/bus" })).toEqual({
      kind: "bus",
      bridgeUrl: "ws://a:1/bus",
      gcs: "gcs-02",
    });
    expect(parseSourceConfig("?source=bus", { VITE_BRIDGE_URL: "ws://env/bus", VITE_GCS: "gcs-09" })).toMatchObject({ bridgeUrl: "ws://env/bus", gcs: "gcs-09" });
    expect(parseSourceConfig("?gcs=").gcs).toBeNull();
    expect(parseSourceConfig("?gcs=GCS").gcs).toBeNull();
    expect(withSource("?gcs=gcs-02&source=mock", "bus")).toBe("?gcs=gcs-02&source=bus");
  });
});
