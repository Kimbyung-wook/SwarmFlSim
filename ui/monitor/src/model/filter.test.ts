// TC-MON-005: 필터 (엔티티·인터페이스·메시지 타입·결과) (IMP-MON-007)
import { create } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { DropReason, LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import type { Filter } from "./filter";
import { EMPTY_FILTER, isEmptyFilter, matchEnvelope, matchOutcome, toggle } from "./filter";
import { outcome } from "./testutil";

const f = (p: Partial<Filter>): Filter => ({ ...EMPTY_FILTER, ...p });

describe("matchOutcome", () => {
  const o = outcome({ src: "uav-001", dst: "gcs-01", iface: L1Interface.C2, msgType: "swarm.v1.TaskStatus", reason: DropReason.JAMMED });

  it("빈 필터는 전부 통과", () => {
    expect(isEmptyFilter(EMPTY_FILTER)).toBe(true);
    expect(matchOutcome(EMPTY_FILTER, o)).toBe(true);
  });

  it("엔티티: any/src/dst", () => {
    expect(matchOutcome(f({ entities: new Set(["gcs-01"]) }), o)).toBe(true);
    expect(matchOutcome(f({ entities: new Set(["gcs-01"]), entityMode: "src" }), o)).toBe(false);
    expect(matchOutcome(f({ entities: new Set(["gcs-01"]), entityMode: "dst" }), o)).toBe(true);
    expect(matchOutcome(f({ entities: new Set(["uav-009"]) }), o)).toBe(false);
  });

  it("인터페이스·타입·결과", () => {
    expect(matchOutcome(f({ ifaces: new Set([L1Interface.C2]) }), o)).toBe(true);
    expect(matchOutcome(f({ ifaces: new Set([L1Interface.P2P]) }), o)).toBe(false);
    expect(matchOutcome(f({ msgTypes: new Set(["swarm.v1.PeerStatus"]) }), o)).toBe(false);
    expect(matchOutcome(f({ outcomes: new Set([DropReason.JAMMED]) }), o)).toBe(true);
    expect(matchOutcome(f({ outcomes: new Set(["delivered" as const]) }), o)).toBe(false);
    expect(matchOutcome(f({ outcomes: new Set(["delivered" as const]) }), outcome({}))).toBe(true);
  });

  it("조건은 AND로 결합한다", () => {
    expect(matchOutcome(f({ entities: new Set(["uav-001"]), ifaces: new Set([L1Interface.P2P]) }), o)).toBe(false);
  });
});

describe("matchEnvelope", () => {
  const bcast = create(LinkEnvelopeSchema, { header: { source: "uav-001" }, iface: L1Interface.P2P, msgType: "swarm.v1.PeerStatus" });
  const uni = create(LinkEnvelopeSchema, {
    header: { source: "gcs-01" },
    dst: ["uav-003"],
    iface: L1Interface.C2,
    msgType: "swarm.v1.TaskCommand",
  });

  it("tx 브로드캐스트: any는 송신자로만, dst 모드는 통과", () => {
    expect(matchEnvelope(f({ entities: new Set(["uav-005"]) }), "tx", "uav-001", bcast)).toBe(false);
    expect(matchEnvelope(f({ entities: new Set(["uav-001"]) }), "tx", "uav-001", bcast)).toBe(true);
    expect(matchEnvelope(f({ entities: new Set(["uav-005"]), entityMode: "dst" }), "tx", "uav-001", bcast)).toBe(true);
    expect(matchEnvelope(f({ entities: new Set(["uav-005"]), entityMode: "src" }), "tx", "uav-001", bcast)).toBe(false);
  });

  it("tx 유니캐스트는 dst 목록, rx는 수신 엔티티로 판정한다", () => {
    expect(matchEnvelope(f({ entities: new Set(["uav-003"]), entityMode: "dst" }), "tx", "gcs-01", uni)).toBe(true);
    expect(matchEnvelope(f({ entities: new Set(["uav-004"]) }), "tx", "gcs-01", uni)).toBe(false);
    expect(matchEnvelope(f({ entities: new Set(["uav-003"]), entityMode: "dst" }), "rx", "uav-003", uni)).toBe(true);
  });

  it("결과 필터: 손실 사유만 고르면 rx는 빠진다", () => {
    const only = f({ outcomes: new Set([DropReason.JAMMED]) });
    expect(matchEnvelope(only, "rx", "uav-003", uni)).toBe(false);
    expect(matchEnvelope(only, "tx", "gcs-01", uni)).toBe(true);
    const typed = f({ ifaces: new Set([L1Interface.C2]), msgTypes: new Set(["swarm.v1.TaskCommand"]) });
    expect(matchEnvelope(typed, "tx", "gcs-01", uni)).toBe(true);
    expect(matchEnvelope(typed, "tx", "uav-001", bcast)).toBe(false);
  });

  it("toggle은 새 집합을 만든다", () => {
    const a = new Set([1]);
    const b = toggle(a, 2);
    expect([...a]).toEqual([1]);
    expect([...toggle(b, 1)]).toEqual([2]);
  });
});
