// IMP-UI-011: 버스 데이터 소스 (DEC-002, DEC-027). 전송 계층은 BusTransport, 브라우저에서는 BridgeTransport(WebSocket 브리지)
// 키: truth/state(TruthFrame), sim/ctrl/status(SimStatus), swarm/<gcs>/rx/**(LinkEnvelope) 구독,
//     sim/ctrl/cmd(SimCommand), swarm/<gcs>/tx/c2/<msg>(LinkEnvelope) 발행 (docs/10_contracts.md §3.2)
import { fromBinary, toBinary } from "@bufbuild/protobuf";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import type { SimCommand } from "../gen/swarm/v1/sim_pb";
import { SimCommandSchema, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import type { OutgoingC2 } from "../model/commands";
import { ENVELOPE_ENCODING } from "../model/commands";
import type { DataHandlers, DataSource } from "./source";
import { HandlerSet } from "./source";

export const KEY_TRUTH_STATE = "truth/state";
export const KEY_SIM_STATUS = "sim/ctrl/status";
export const KEY_SIM_CMD = "sim/ctrl/cmd";
export const SIM_CMD_ENCODING = `application/protobuf;${SimCommandSchema.typeName}`;

export function rxAllKey(gcs: string): string {
  return `swarm/${gcs}/rx/**`;
}

export interface SubscribeOptions {
  /** 브리지 다운샘플 최대 주기. 0이면 제한 없음 */
  maxHz?: number;
}

export type TransportCallback = (payload: Uint8Array, key: string, encoding: string) => void;

/** 전송 계층이 제공해야 하는 최소 기능 */
export interface BusTransport {
  open(): Promise<void>;
  subscribe(key: string, cb: TransportCallback, opts?: SubscribeOptions): () => void;
  /** 보낼 수 없으면 예외 */
  put(key: string, payload: Uint8Array, encoding: string): void;
  close(): void;
}

export interface BusSourceOptions {
  /** 이 UI가 맡은 GCS. 없으면 C2 송수신을 하지 않는다 */
  gcs: string | null;
  /** truth/state 최대 수신 주기 (지도 렌더 주기보다 높을 필요가 없다) */
  truthMaxHz: number;
  /** 해석 실패 보고 */
  onDecodeError?: (key: string, e: unknown) => void;
}

const DEFAULTS: BusSourceOptions = { gcs: null, truthMaxHz: 30 };

export class BusSource implements DataSource {
  readonly name = "bus";
  readonly gcs: string | null;
  private readonly handlers = new HandlerSet();
  private readonly opts: BusSourceOptions;
  private unsubs: (() => void)[] = [];

  constructor(
    private readonly transport: BusTransport,
    opts: Partial<BusSourceOptions> = {},
  ) {
    this.opts = { ...DEFAULTS, ...opts };
    this.gcs = this.opts.gcs;
  }

  subscribe(h: DataHandlers): () => void {
    return this.handlers.add(h);
  }

  /** 구독을 먼저 걸어 두고 연다. 전송 계층이 다시 붙으면 구독을 다시 보낸다 */
  async connect(): Promise<void> {
    const t = this.transport;
    this.unsubs = [
      t.subscribe(KEY_TRUTH_STATE, (p, k) => this.decode(k, () => this.handlers.truth(fromBinary(TruthFrameSchema, p))), {
        maxHz: this.opts.truthMaxHz,
      }),
      t.subscribe(KEY_SIM_STATUS, (p, k) => this.decode(k, () => this.handlers.status(fromBinary(SimStatusSchema, p)))),
    ];
    if (this.gcs) {
      this.unsubs.push(
        t.subscribe(rxAllKey(this.gcs), (p, k) => this.decode(k, () => this.handlers.rx(k, fromBinary(LinkEnvelopeSchema, p)))),
      );
    }
    await t.open();
  }

  send(cmd: SimCommand): void {
    this.transport.put(KEY_SIM_CMD, toBinary(SimCommandSchema, cmd), SIM_CMD_ENCODING);
  }

  sendC2(out: OutgoingC2): void {
    if (!this.gcs) throw new Error("GCS가 지정되지 않아 C2 명령을 보낼 수 없다 (?gcs=)");
    if (!out.key.startsWith(`swarm/${this.gcs}/tx/`)) throw new Error(`다른 GCS의 키: ${out.key}`);
    this.transport.put(out.key, toBinary(LinkEnvelopeSchema, out.envelope), ENVELOPE_ENCODING);
  }

  close(): void {
    for (const u of this.unsubs) u();
    this.unsubs = [];
    this.transport.close();
  }

  private decode(key: string, fn: () => void): void {
    try {
      fn();
    } catch (e) {
      this.opts.onDecodeError?.(key, e);
    }
  }
}
