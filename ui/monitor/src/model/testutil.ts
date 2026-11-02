// 시험 공용: LinkOutcome·프레임 생성
import type { DescMessage, MessageInitShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { BusFrame } from "../bridge/frame";
import { PROTOBUF_ENCODING_PREFIX } from "../bridge/frame";
import type { LinkOutcome } from "../gen/swarm/v1/link_pb";
import { DropReason, LinkOutcomeKind, LinkOutcomeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";

export function outcome(p: {
  src?: string;
  dst?: string;
  seq?: number;
  t?: number;
  lat?: number;
  reason?: DropReason;
  size?: number;
  iface?: L1Interface;
  msgType?: string;
}): LinkOutcome {
  const dropped = p.reason !== undefined && p.reason !== DropReason.NONE;
  const t = p.t ?? 1_000_000;
  return create(LinkOutcomeSchema, {
    src: p.src ?? "uav-001",
    dst: p.dst ?? "gcs-01",
    seq: p.seq ?? 1,
    iface: p.iface ?? L1Interface.P2P,
    msgType: p.msgType ?? "swarm.v1.PeerStatus",
    sizeBytes: p.size ?? 100,
    outcome: dropped ? LinkOutcomeKind.DROPPED : LinkOutcomeKind.DELIVERED,
    reason: dropped ? p.reason : DropReason.NONE,
    txTimeUs: BigInt(t),
    rxTimeUs: dropped ? 0n : BigInt(t + (p.lat ?? 5000)),
  });
}

export function frameOf<S extends DescMessage>(key: string, schema: S, init: MessageInitShape<S>): BusFrame {
  return { key, encoding: `${PROTOBUF_ENCODING_PREFIX}${schema.typeName}`, payload: toBinary(schema, create(schema, init)) };
}
