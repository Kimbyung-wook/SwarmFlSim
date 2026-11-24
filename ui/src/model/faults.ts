// IMP-UI-087: 시험 진행자용 고장 주입 (REQ-UI-001, DEC-014). C2가 아니라 시뮬레이션 통제 sim/ctrl/cmd InjectFault다.
// 링크 단절은 Datalink가, 그 밖(ENGINE·SENSOR·NAV·KILL)은 Sim Core가 처리한다. KILL은 되돌릴 수 없다.
// 결정(WP5): GCS를 지정하지 않은 관찰 전용 UI에서도 쓸 수 있다. Start·Pause·Reset과 같은 시뮬레이션 통제이고
//   운용자(GCS)의 지식·권한과 무관하기 때문이다. 브리지 role=control이 아니면 브리지가 거부한다.
// 결과는 버스가 따로 알려 주지 않으므로(KILL은 truth/event/kill) UI가 보낸 주입을 기억해 남은 시간을 보인다.
import type { MessageInitShape } from "@bufbuild/protobuf";
import { FaultKind } from "../gen/swarm/v1/sim_pb";
import type { SimCommandSchema } from "../gen/swarm/v1/sim_pb";

export const FAULT_KINDS: { kind: FaultKind; label: string; hint: string }[] = [
  { kind: FaultKind.GCS_LINK_CUT, label: "GCS 링크 단절", hint: "그 기체와 GCS 사이 링크만 끊는다 (Datalink)" },
  { kind: FaultKind.LINK_CUT, label: "링크 전체 단절", hint: "그 기체의 모든 링크(GCS·P2P)를 끊는다 (Datalink)" },
  { kind: FaultKind.ENGINE, label: "엔진 고장", hint: "동역학 모델이 엔진 정지를 지원하는 기체만 (Sim Core)" },
  { kind: FaultKind.SENSOR, label: "센서 고장", hint: "탐재 센서 탐지를 막는다 (Sim Core → Payload)" },
  { kind: FaultKind.NAV, label: "항법 고장", hint: "항법 고장 상태 (Sim Core)" },
  { kind: FaultKind.KILL, label: "제거(KILL)", hint: "엔티티를 파괴한다. 해제할 수 없다 (Sim Core)" },
];

export const faultLabel = (k: FaultKind) => FAULT_KINDS.find((f) => f.kind === k)?.label ?? `FAULT ${k}`;

type Cmd = MessageInitShape<typeof SimCommandSchema>["cmd"];

/** InjectFault 명령. durationS 0 = 해제 명령까지 */
export function faultCommand(entityId: string, fault: FaultKind, durationS: number, clear = false): Cmd {
  if (!entityId) throw new Error("대상 엔티티가 없다");
  if (fault === FaultKind.UNSPECIFIED) throw new Error("고장 종류가 없다");
  if (clear && fault === FaultKind.KILL) throw new Error("KILL은 해제할 수 없다");
  const d = Number.isFinite(durationS) && durationS > 0 ? durationS : 0;
  return { case: "fault", value: { entityId, fault, durationS: clear ? 0 : d, clear } };
}

export interface FaultEntry {
  entityId: string;
  fault: FaultKind;
  /** 주입 시각(모의 us) */
  atUs: bigint;
  /** 0 = 해제까지 */
  durationS: number;
}

/** 이 UI가 주입한 고장. 같은 (엔티티, 종류)는 마지막 것만 둔다 (Sim Core·Datalink와 같은 규칙) */
export class FaultLog {
  private readonly items = new Map<string, FaultEntry>();
  version = 0;

  private static key(id: string, k: FaultKind) {
    return `${id}|${k}`;
  }

  injected(entityId: string, fault: FaultKind, durationS: number, atUs: bigint): void {
    const k = FaultLog.key(entityId, fault);
    this.items.delete(k);
    this.items.set(k, { entityId, fault, durationS: durationS > 0 ? durationS : 0, atUs });
    this.version++;
  }

  cleared(entityId: string, fault: FaultKind): void {
    if (this.items.delete(FaultLog.key(entityId, fault))) this.version++;
  }

  /** 아직 걸려 있다고 보이는 것(시간이 지난 것은 뺀다). 최근 것이 먼저. KILL은 남긴다 */
  active(nowUs: bigint | null): (FaultEntry & { remainingS: number | null })[] {
    const out: (FaultEntry & { remainingS: number | null })[] = [];
    for (const e of [...this.items.values()].reverse()) {
      if (e.durationS === 0 || nowUs === null) {
        out.push({ ...e, remainingS: null });
        continue;
      }
      const left = e.durationS - Number(nowUs - e.atUs) / 1e6;
      if (left > 0) out.push({ ...e, remainingS: left });
    }
    return out;
  }

  /** Reset·시나리오 적재 때 (Sim Core·Datalink가 고장을 모두 지운다) */
  clear(): void {
    if (this.items.size) this.version++;
    this.items.clear();
  }
}
