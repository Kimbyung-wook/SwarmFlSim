// IMP-UI-008: 데이터 소스 추상화 (REQ-UI-001, DEC-002)
// UI는 이 인터페이스로만 truth/state, sim/ctrl/status를 받고 sim/ctrl/cmd를 보낸다.
// 구현: MockSource(내장 시나리오), BusSource(BusTransport, 브리지 WebSocket은 BridgeTransport)
// IMP-UI-028: C2 명령 송신(swarm/<gcs>/tx/c2/**)과 swarm/<gcs>/rx/** 수신을 더한다 (REQ-UI-003, REQ-UI-004)
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import type { EntityParams, SimCommand, SimStatus } from "../gen/swarm/v1/sim_pb";
import type { OutgoingC2 } from "../model/commands";

export interface DataHandlers {
  /** truth/state */
  truth?: (f: TruthFrame) => void;
  /** sim/ctrl/status */
  status?: (s: SimStatus) => void;
  /** swarm/<gcs>/rx/** (데이터링크가 전달한 LinkEnvelope) */
  rx?: (key: string, env: LinkEnvelope) => void;
  /** sim/param/<entity>/<owner> (DEC-035) */
  params?: (p: EntityParams) => void;
}

export interface DataSource {
  readonly name: string;
  /** 이 UI가 맡은 GCS 엔티티. 없으면 C2 명령을 보낼 수 없다 */
  readonly gcs: string | null;
  subscribe(h: DataHandlers): () => void;
  /** sim/ctrl/cmd. 보낼 수 없으면 예외 */
  send(cmd: SimCommand): void;
  /** swarm/<gcs>/tx/c2/<msg>. 보낼 수 없으면 예외 */
  sendC2(out: OutgoingC2): void;
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

  rx(key: string, env: LinkEnvelope): void {
    for (const h of this.set) h.rx?.(key, env);
  }

  params(p: EntityParams): void {
    for (const h of this.set) h.params?.(p);
  }
}
