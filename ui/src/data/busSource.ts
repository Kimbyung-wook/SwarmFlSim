// IMP-UI-011: 버스 데이터 소스 자리 (DEC-002). 연결 방식은 ui/README.md §버스 연결의 제안을 확정한 뒤 구현한다.
// 키: truth/state(TruthFrame), sim/ctrl/status(SimStatus) 구독, sim/ctrl/cmd(SimCommand) 발행 (docs/10_contracts.md §3.2)
import { fromBinary, toBinary } from "@bufbuild/protobuf";
import type { SimCommand } from "../gen/swarm/v1/sim_pb";
import { SimCommandSchema, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import type { DataHandlers, DataSource } from "./source";
import { HandlerSet } from "./source";

export const KEY_TRUTH_STATE = "truth/state";
export const KEY_SIM_STATUS = "sim/ctrl/status";
export const KEY_SIM_CMD = "sim/ctrl/cmd";

/** 전송 계층이 제공해야 하는 최소 기능. zenoh-ts 세션 또는 WebSocket 브리지가 이 형태로 감싼다 */
export interface BusTransport {
  open(): Promise<void>;
  subscribe(key: string, cb: (payload: Uint8Array) => void): () => void;
  put(key: string, payload: Uint8Array, encoding: string): void;
  close(): void;
}

export class BusSource implements DataSource {
  readonly name = "bus";
  private readonly handlers = new HandlerSet();
  private unsubs: (() => void)[] = [];

  constructor(private readonly transport: BusTransport) {}

  subscribe(h: DataHandlers): () => void {
    return this.handlers.add(h);
  }

  async connect(): Promise<void> {
    await this.transport.open();
    this.unsubs = [
      this.transport.subscribe(KEY_TRUTH_STATE, (p) => this.handlers.truth(fromBinary(TruthFrameSchema, p))),
      this.transport.subscribe(KEY_SIM_STATUS, (p) => this.handlers.status(fromBinary(SimStatusSchema, p))),
    ];
  }

  send(cmd: SimCommand): void {
    this.transport.put(KEY_SIM_CMD, toBinary(SimCommandSchema, cmd), `application/protobuf;${SimCommandSchema.typeName}`);
  }

  close(): void {
    for (const u of this.unsubs) u();
    this.unsubs = [];
    this.transport.close();
  }
}

/** 전송 계층이 아직 없을 때 쓰는 자리 표시. connect에서 실패한다 */
export class UnimplementedTransport implements BusTransport {
  async open(): Promise<void> {
    throw new Error("버스 전송 계층이 아직 없다 (ui/README.md §버스 연결)");
  }
  subscribe(): () => void {
    return () => {};
  }
  put(): void {}
  close(): void {}
}
