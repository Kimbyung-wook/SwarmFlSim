// IMP-MON-004: 버스 프레임 해석 (키 → 메시지 종류, protobuf-es) (REQ-UI-005, docs/10_contracts.md §3.2·§3.3)
import type { DescMessage, Registry } from "@bufbuild/protobuf";
import { createRegistry, fromBinary, toJson } from "@bufbuild/protobuf";
import type { BusFrame } from "../bridge/frame";
import { protobufTypeName } from "../bridge/frame";
import { file_swarm_v1_c2 } from "../gen/swarm/v1/c2_pb";
import { file_swarm_v1_common } from "../gen/swarm/v1/common_pb";
import { file_swarm_v1_entity } from "../gen/swarm/v1/entity_pb";
import { file_swarm_v1_fa } from "../gen/swarm/v1/fa_pb";
import type { LinkEnvelope, LinkOutcome, LinkState } from "../gen/swarm/v1/link_pb";
import { file_swarm_v1_link, LinkEnvelopeSchema, LinkOutcomeSchema, LinkStateSchema } from "../gen/swarm/v1/link_pb";
import { file_swarm_v1_mp } from "../gen/swarm/v1/mp_pb";
import { file_swarm_v1_ms } from "../gen/swarm/v1/ms_pb";
import { file_swarm_v1_p2p } from "../gen/swarm/v1/p2p_pb";
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import { file_swarm_v1_sim, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import type { TruthEvent, TruthFrame } from "../gen/swarm/v1/truth_pb";
import { file_swarm_v1_truth, TruthEventSchema, TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { file_swarm_v1_vi } from "../gen/swarm/v1/vi_pb";

/** swarm.v1 전체. 메시지 echo가 msg_type 이름으로 스키마를 찾는다 */
export const registry: Registry = createRegistry(
  file_swarm_v1_common,
  file_swarm_v1_entity,
  file_swarm_v1_c2,
  file_swarm_v1_vi,
  file_swarm_v1_ms,
  file_swarm_v1_mp,
  file_swarm_v1_p2p,
  file_swarm_v1_fa,
  file_swarm_v1_link,
  file_swarm_v1_sim,
  file_swarm_v1_truth,
);

export type Direction = "tx" | "rx";

export type BusEvent =
  | { kind: "outcome"; key: string; outcome: LinkOutcome }
  | { kind: "linkState"; key: string; state: LinkState }
  | { kind: "envelope"; key: string; dir: Direction; entity: string; iface: string; msg: string; env: LinkEnvelope }
  | { kind: "truth"; key: string; frame: TruthFrame }
  | { kind: "truthEvent"; key: string; event: TruthEvent }
  | { kind: "status"; key: string; status: SimStatus }
  | { kind: "ignored"; key: string; reason: string };

export interface SwarmKey {
  entity: string;
  dir: Direction;
  iface: string;
  msg: string;
}

/** `swarm/<id>/tx|rx/<iface>/<msg>` */
export function parseSwarmKey(key: string): SwarmKey | undefined {
  const p = key.split("/");
  if (p.length !== 5 || p[0] !== "swarm" || (p[2] !== "tx" && p[2] !== "rx")) return undefined;
  return { entity: p[1], dir: p[2], iface: p[3], msg: p[4] };
}

function typeMismatch(f: BusFrame, schema: DescMessage): string | undefined {
  const t = protobufTypeName(f.encoding);
  // 인코딩이 비어 있으면 키로 판단한다. 다른 형식이면 버린다
  if (f.encoding === "" || t === schema.typeName) return undefined;
  return `인코딩 ${f.encoding} ≠ ${schema.typeName}`;
}

export function decodeBusFrame(f: BusFrame): BusEvent {
  const k = f.key;
  const decode = <T extends DescMessage>(schema: T) => {
    const bad = typeMismatch(f, schema);
    if (bad) throw new DecodeMismatch(bad);
    return fromBinary(schema, f.payload);
  };
  try {
    if (k.startsWith("link/outcome/")) return { kind: "outcome", key: k, outcome: decode(LinkOutcomeSchema) };
    if (k.startsWith("link/state/")) return { kind: "linkState", key: k, state: decode(LinkStateSchema) };
    if (k.startsWith("swarm/")) {
      const sk = parseSwarmKey(k);
      if (!sk) return { kind: "ignored", key: k, reason: "swarm 키 형식이 아니다" };
      return { kind: "envelope", key: k, ...sk, env: decode(LinkEnvelopeSchema) };
    }
    if (k === "truth/state") return { kind: "truth", key: k, frame: decode(TruthFrameSchema) };
    if (k.startsWith("truth/event/")) return { kind: "truthEvent", key: k, event: decode(TruthEventSchema) };
    if (k === "sim/ctrl/status") return { kind: "status", key: k, status: decode(SimStatusSchema) };
  } catch (e) {
    return { kind: "ignored", key: k, reason: e instanceof DecodeMismatch ? e.message : `해석 실패: ${String(e)}` };
  }
  return { kind: "ignored", key: k, reason: "구독하지 않는 키" };
}

class DecodeMismatch extends Error {}

export interface EchoDecoded {
  typeName: string;
  json?: unknown;
  error?: string;
}

/** LinkEnvelope.payload를 msg_type 스키마로 해석한다 (메시지 echo) */
export function decodePayload(msgType: string, payload: Uint8Array): EchoDecoded {
  const schema = registry.getMessage(msgType);
  if (!schema) return { typeName: msgType, error: "등록되지 않은 메시지 타입" };
  try {
    const m = fromBinary(schema, payload);
    return { typeName: msgType, json: toJson(schema, m, { registry, alwaysEmitImplicit: false }) };
  } catch (e) {
    return { typeName: msgType, error: `해석 실패: ${String(e)}` };
  }
}

/** 메시지 echo용 JSON. LinkEnvelope 자체 필드 + 해석한 payload */
export function envelopeJson(env: LinkEnvelope): unknown {
  return toJson(LinkEnvelopeSchema, env, { registry });
}
