// IMP-MON-003: 프레임 소스 추상화와 브리지 WebSocket 클라이언트 (REQ-UI-005, DEC-027)
// 모니터는 관전자(observer)로 접속하고 발행하지 않는다.
import type { BusFrame, ClientMsg, ServerMsg } from "./frame";
import { BRIDGE_PROTOCOL, decodeFrame, FrameError, parseServerMsg } from "./frame";

export type ConnState = "idle" | "connecting" | "open" | "closed" | "error";

export interface SourceStatus {
  state: ConnState;
  detail?: string;
  contract?: string;
}

export interface FrameSource {
  readonly name: string;
  /** 프레임은 받는 즉시 동기 호출한다 */
  onFrame(cb: (f: BusFrame) => void): void;
  onStatus(cb: (s: SourceStatus) => void): void;
  connect(): void;
  close(): void;
}

export interface Subscription {
  key: string;
  max_hz: number;
}

/** 모니터 구독 목록 (docs/10_contracts.md §3.2). 통계용 키는 다운샘플하지 않는다 */
export const MONITOR_SUBSCRIPTIONS: readonly Subscription[] = [
  { key: "link/outcome/**", max_hz: 0 },
  { key: "link/state/**", max_hz: 2 },
  { key: "swarm/*/tx/**", max_hz: 0 },
  { key: "swarm/*/rx/**", max_hz: 0 },
  { key: "truth/state", max_hz: 1 },
  { key: "truth/event/**", max_hz: 0 },
  { key: "sim/ctrl/status", max_hz: 2 },
];

/** 시험에서 바꿔 끼울 수 있도록 필요한 부분만 둔다 */
export interface WebSocketLike {
  binaryType: string;
  readonly readyState: number;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code?: number; reason?: string }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface BridgeOptions {
  url: string;
  client: string;
  subscriptions?: readonly Subscription[];
  /** 끊기면 다시 붙는 간격(ms). 0이면 다시 붙지 않는다 */
  reconnectMs?: number;
  createSocket?: (url: string) => WebSocketLike;
}

export class BridgeSource implements FrameSource {
  readonly name = "bridge";
  private frameCb: (f: BusFrame) => void = () => {};
  private statusCb: (s: SourceStatus) => void = () => {};
  private ws: WebSocketLike | null = null;
  private closed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  /** 해석하지 못한 바이너리 프레임 수 */
  badFrames = 0;

  constructor(private readonly opts: BridgeOptions) {}

  onFrame(cb: (f: BusFrame) => void): void {
    this.frameCb = cb;
  }

  onStatus(cb: (s: SourceStatus) => void): void {
    this.statusCb = cb;
  }

  connect(): void {
    this.closed = false;
    this.open();
  }

  close(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.ws?.close();
    this.ws = null;
    this.statusCb({ state: "closed" });
  }

  private open(): void {
    this.statusCb({ state: "connecting", detail: this.opts.url });
    const create = this.opts.createSocket ?? ((u: string) => new WebSocket(u) as unknown as WebSocketLike);
    let ws: WebSocketLike;
    try {
      ws = create(this.opts.url);
    } catch (e) {
      this.statusCb({ state: "error", detail: String(e) });
      this.retry();
      return;
    }
    this.ws = ws;
    ws.binaryType = "arraybuffer";
    const send = (m: ClientMsg) => ws.send(JSON.stringify(m));
    ws.onopen = () => send({ op: "hello", client: this.opts.client, role: "observer" });
    ws.onmessage = (ev) => {
      const d = ev.data;
      if (typeof d === "string") {
        this.control(d, send);
        return;
      }
      const buf = d instanceof ArrayBuffer ? new Uint8Array(d) : d instanceof Uint8Array ? d : null;
      if (!buf) return;
      try {
        this.frameCb(decodeFrame(buf));
      } catch (e) {
        if (!(e instanceof FrameError)) throw e;
        this.badFrames++;
      }
    };
    ws.onerror = () => this.statusCb({ state: "error", detail: "WebSocket 오류" });
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (this.closed) return;
      this.statusCb({ state: "closed", detail: ev.reason || `code ${ev.code ?? "?"}` });
      this.retry();
    };
  }

  private control(text: string, send: (m: ClientMsg) => void): void {
    let m: ServerMsg;
    try {
      m = parseServerMsg(text);
    } catch {
      return;
    }
    if (m.op === "welcome") {
      if (m.protocol !== BRIDGE_PROTOCOL) {
        this.statusCb({ state: "error", detail: `브리지 프로토콜 ${m.protocol} (기대 ${BRIDGE_PROTOCOL})` });
        this.ws?.close();
        return;
      }
      (this.opts.subscriptions ?? MONITOR_SUBSCRIPTIONS).forEach((s, i) =>
        send({ op: "sub", id: i + 1, key: s.key, max_hz: s.max_hz }),
      );
      this.statusCb({ state: "open", contract: m.contract, detail: this.opts.url });
    } else {
      this.statusCb({ state: "error", detail: `${m.code}: ${m.msg}` });
    }
  }

  private retry(): void {
    const ms = this.opts.reconnectMs ?? 2000;
    if (this.closed || ms <= 0) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!this.closed) this.open();
    }, ms);
  }
}
