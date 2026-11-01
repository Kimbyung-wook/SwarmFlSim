// IMP-UI-008: 데이터 소스 추상화 (REQ-UI-001, DEC-002)
// UI는 이 인터페이스로만 truth/state, sim/ctrl/status를 받고 sim/ctrl/cmd를 보낸다.
// 구현: MockSource(내장 시나리오), BusSource(Zenoh 연결 자리, ui/README.md §버스 연결 참고)
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import type { SimCommand, SimStatus } from "../gen/swarm/v1/sim_pb";

export interface DataHandlers {
  /** truth/state */
  truth?: (f: TruthFrame) => void;
  /** sim/ctrl/status */
  status?: (s: SimStatus) => void;
}

export interface DataSource {
  readonly name: string;
  subscribe(h: DataHandlers): () => void;
  /** sim/ctrl/cmd */
  send(cmd: SimCommand): void;
  connect(): Promise<void>;
  close(): void;
}

/** 구독자 목록 관리 공통부 */
export class HandlerSet {
  private readonly set = new Set<DataHandlers>();

  add(h: DataHandlers): () => void {
    this.set.add(h);
    return () => void this.set.delete(h);
  }

  truth(f: TruthFrame): void {
    for (const h of this.set) h.truth?.(f);
  }

  status(s: SimStatus): void {
    for (const h of this.set) h.status?.(s);
  }
}
