// IMP-UI-024: BusTransport의 WebSocket 브리지 구현 (DEC-027, 브리지 프로토콜 v1)
// - 접속하면 hello를 보내고 welcome을 기다린다. 끊기면 reconnectMs 뒤 다시 붙고 구독을 다시 보낸다.
// - 바이너리 프레임에는 구독 ID가 없으므로 받은 키를 로컬 구독의 키 표현식과 맞춰 나눈다.
//   같은 키 표현식은 서버 구독 하나를 같이 쓴다. 서로 겹치는 다른 표현식은 중복 수신되므로 BusSource는 겹치게 구독하지 않는다.
import type { BusTransport, SubscribeOptions, TransportCallback } from "./busSource";
import type { BridgeErrorCode, BridgeRole, ClientMessage } from "./bridgeFrame";
import { BRIDGE_PROTOCOL, decodeFrame, encodeFrame, keyexprMatches, parseServerMessage } from "./bridgeFrame";

/** 시험에서 바꿔 끼울 수 있게 쓰는 WebSocket의 최소 부분 */
export interface WebSocketLike {
  binaryType: string;
  readonly readyState: number;
  send(data: string | Uint8Array): void;
  close(code?: number, reason?: string): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number; reason: string }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

export type BridgeState = "connecting" | "open" | "closed";

export interface BridgeTransportOptions {
  url: string;
  client: string;
  role: BridgeRole;
  gcs?: string;
  /** 끊긴 뒤 다시 붙는 간격(ms). 0이면 다시 붙지 않는다 */
  reconnectMs: number;
  helloTimeoutMs: number;
  socketFactory: (url: string) => WebSocketLike;
  onState?: (s: BridgeState, detail?: string) => void;
  onError?: (code: BridgeErrorCode | "protocol", msg: string) => void;
}

const DEFAULTS = {
  role: "control" as BridgeRole,
  reconnectMs: 2000,
  helloTimeoutMs: 5000,
  socketFactory: (url: string) => new WebSocket(url) as unknown as WebSocketLike,
};

interface ServerSub {
  id: number;
  key: string;
  maxHz: number;
  cbs: Set<TransportCallback>;
}

export class BridgeTransport implements BusTransport {
  private readonly opts: BridgeTransportOptions;
  private ws: WebSocketLike | null = null;
  private ready = false;
  private stopped = false;
  private nextId = 1;
  private readonly subs = new Map<string, ServerSub>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private helloTimer: ReturnType<typeof setTimeout> | null = null;
  private firstOpen: { resolve: () => void; reject: (e: Error) => void } | null = null;
  /** 받은 바이너리 프레임 수, 해석 실패 수 */
  received = 0;
  malformed = 0;

  constructor(opts: Partial<BridgeTransportOptions> & Pick<BridgeTransportOptions, "url" | "client">) {
    this.opts = { ...DEFAULTS, ...opts };
  }

  get isOpen(): boolean {
    return this.ready;
  }

  /** 첫 welcome에서 끝난다. 첫 접속이 실패하면 거부하되 reconnectMs > 0이면 계속 다시 붙는다 */
  open(): Promise<void> {
    this.stopped = false;
    return new Promise((resolve, reject) => {
      this.firstOpen = { resolve, reject };
      this.dial();
    });
  }

  subscribe(key: string, cb: TransportCallback, opts?: SubscribeOptions): () => void {
    const maxHz = opts?.maxHz ?? 0;
    let s = this.subs.get(key);
    if (!s) {
      s = { id: this.nextId++, key, maxHz, cbs: new Set() };
      this.subs.set(key, s);
      if (this.ready) this.sendJson({ op: "sub", id: s.id, key, max_hz: maxHz });
    } else if (maxHz === 0 ? s.maxHz !== 0 : s.maxHz !== 0 && maxHz > s.maxHz) {
      // 같은 키를 더 높은 주기로 원하면 서버 구독을 바꾼다
      s.maxHz = maxHz;
      if (this.ready) {
        this.sendJson({ op: "unsub", id: s.id });
        s.id = this.nextId++;
        this.sendJson({ op: "sub", id: s.id, key, max_hz: maxHz });
      }
    }
    s.cbs.add(cb);
    const sub = s;
    return () => {
      sub.cbs.delete(cb);
      if (sub.cbs.size === 0 && this.subs.get(key) === sub) {
        this.subs.delete(key);
        if (this.ready) this.sendJson({ op: "unsub", id: sub.id });
      }
    };
  }

  put(key: string, payload: Uint8Array, encoding: string): void {
    if (!this.ready || !this.ws) throw new Error("브리지에 연결되어 있지 않다");
    this.ws.send(encodeFrame(key, encoding, payload));
  }

  close(): void {
    this.stopped = true;
    this.clearTimers();
    const ws = this.ws;
    this.ws = null;
    this.ready = false;
    if (ws) {
      ws.onclose = ws.onmessage = ws.onerror = ws.onopen = null;
      ws.close(1000, "client close");
    }
    this.subs.clear();
    this.failFirst("closed");
    this.opts.onState?.("closed", "닫음");
  }

  private dial(): void {
    this.clearTimers();
    this.opts.onState?.("connecting", this.opts.url);
    let ws: WebSocketLike;
    try {
      ws = this.opts.socketFactory(this.opts.url);
    } catch (e) {
      this.lost(String(e instanceof Error ? e.message : e));
      return;
    }
    this.ws = ws;
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      const hello: ClientMessage = { op: "hello", client: this.opts.client, role: this.opts.role };
      if (this.opts.gcs) hello.gcs = this.opts.gcs;
      this.sendJson(hello);
      this.helloTimer = setTimeout(() => {
        this.opts.onError?.("protocol", "welcome 시간 초과");
        ws.close(4000, "welcome timeout");
      }, this.opts.helloTimeoutMs);
    };
    ws.onmessage = (ev) => this.onMessage(ev.data);
    ws.onerror = () => {
      /* onclose가 뒤따른다 */
    };
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.lost(ev.reason || `연결 끊김 (${ev.code})`);
    };
  }

  private onMessage(data: unknown): void {
    if (typeof data === "string") {
      const m = parseServerMessage(data);
      if (!m) {
        this.opts.onError?.("protocol", `알 수 없는 제어 프레임: ${data.slice(0, 80)}`);
      } else if (m.op === "welcome") {
        this.onWelcome(m.protocol, m.contract);
      } else {
        this.opts.onError?.(m.code, m.msg);
        if (!this.ready) this.failFirst(`${m.code}: ${m.msg}`);
      }
      return;
    }
    if (!(data instanceof ArrayBuffer || data instanceof Uint8Array)) return;
    let f;
    try {
      f = decodeFrame(data);
    } catch {
      this.malformed++;
      return;
    }
    this.received++;
    for (const s of this.subs.values()) {
      if (!keyexprMatches(s.key, f.key)) continue;
      for (const cb of s.cbs) cb(f.payload, f.key, f.encoding);
    }
  }

  private onWelcome(protocol: number, contract: string): void {
    if (this.helloTimer) clearTimeout(this.helloTimer);
    this.helloTimer = null;
    if (protocol !== BRIDGE_PROTOCOL) {
      this.opts.onError?.("protocol", `브리지 프로토콜 ${protocol}은 지원하지 않는다 (필요: ${BRIDGE_PROTOCOL})`);
      this.failFirst(`protocol ${protocol}`);
      this.stopped = true;
      this.ws?.close(1002, "protocol mismatch");
      return;
    }
    this.ready = true;
    for (const s of this.subs.values()) this.sendJson({ op: "sub", id: s.id, key: s.key, max_hz: s.maxHz });
    this.opts.onState?.("open", `계약 ${contract}`);
    const first = this.firstOpen;
    this.firstOpen = null;
    first?.resolve();
  }

  private lost(reason: string): void {
    this.ready = false;
    if (this.helloTimer) clearTimeout(this.helloTimer);
    this.helloTimer = null;
    this.failFirst(reason);
    if (this.stopped) return;
    this.opts.onState?.(this.opts.reconnectMs > 0 ? "connecting" : "closed", reason);
    if (this.opts.reconnectMs > 0) this.reconnectTimer = setTimeout(() => this.dial(), this.opts.reconnectMs);
  }

  private failFirst(reason: string): void {
    const first = this.firstOpen;
    this.firstOpen = null;
    first?.reject(new Error(`브리지 ${this.opts.url}: ${reason}`));
  }

  private sendJson(m: ClientMessage): void {
    this.ws?.send(JSON.stringify(m));
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.helloTimer) clearTimeout(this.helloTimer);
    this.reconnectTimer = this.helloTimer = null;
  }
}
