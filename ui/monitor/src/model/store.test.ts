// TC-MON-006: 원형 버퍼, 상태 보관소(echo 색인, 엔티티 목록, 되감기), 엔티티 트리 (IMP-MON-008~010)
import { create, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { LinkEnvelopeSchema, LinkOutcomeSchema, LinkStateSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { PeerStatusSchema } from "../gen/swarm/v1/p2p_pb";
import { SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { TruthEventSchema, TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { Ring } from "./ring";
import { MonitorStore, txKeyOf } from "./store";
import { frameOf, outcome } from "./testutil";
import { buildTree } from "./tree";

function txFrame(src: string, seq: number, tUs: number) {
  const payload = toBinary(PeerStatusSchema, create(PeerStatusSchema, { groupId: "g" }));
  return frameOf(`swarm/${src}/tx/p2p/PeerStatus`, LinkEnvelopeSchema, {
    header: { source: src, seq, simTimeUs: BigInt(tUs) },
    iface: L1Interface.P2P,
    msgType: "swarm.v1.PeerStatus",
    payload,
  });
}

function outcomeFrame(o: ReturnType<typeof outcome>) {
  return { key: `link/outcome/${o.src}/${o.dst}`, encoding: "", payload: toBinary(LinkOutcomeSchema, o) };
}

describe("Ring", () => {
  it("용량을 넘으면 오래된 것을 밀어내고 최신부터 돌려준다", () => {
    const r = new Ring<number>(3);
    expect([1, 2, 3].map((v) => r.push(v))).toEqual([undefined, undefined, undefined]);
    expect(r.push(4)).toBe(1);
    expect(r.newest(10)).toEqual([4, 3, 2]);
    expect(r.newest(10, (v) => v % 2 === 0)).toEqual([4, 2]);
    expect(r.newest(1)).toEqual([4]);
    expect([r.size, r.pushed]).toEqual([3, 4]);
    r.clear();
    expect(r.newest(10)).toEqual([]);
  });
});

describe("MonitorStore", () => {
  it("outcome에서 송신 엔벨로프를 찾는다(echo)", () => {
    const s = new MonitorStore({ echoCapacity: 1, txCapacity: 2 });
    s.handleFrame(txFrame("uav-001", 1, 1_000_000));
    const o = outcome({ src: "uav-001", dst: "uav-002", seq: 1 });
    expect(txKeyOf(o)).toBe("swarm/uav-001/tx/p2p/PeerStatus");
    s.handleFrame(outcomeFrame(o));
    expect(s.envelopeFor(o)?.env.header?.seq).toBe(1);
    expect(s.timeline.size).toBe(1);
    // tx 보관분에서 밀려나면 색인도 지운다
    s.handleFrame(txFrame("uav-001", 2, 1_020_000));
    s.handleFrame(txFrame("uav-001", 3, 1_040_000));
    expect(s.envelopeFor(o)).toBeUndefined();
    expect(s.envelopeFor(outcome({ src: "uav-001", seq: 3 }))).toBeDefined();
    expect(s.agg.entity("uav-001").envTx).toBe(3);
  });

  it("엔티티 종류·진영은 truth/state, 파괴는 truth/event/kill로 갱신한다", () => {
    const s = new MonitorStore();
    s.handleFrame(outcomeFrame(outcome({ src: "uav-001", dst: "gcs-01" })));
    expect(s.entities.get("gcs-01")).toMatchObject({ kind: EntityKind.UNSPECIFIED, fromTruth: false });
    s.handleFrame(
      frameOf("truth/state", TruthFrameSchema, {
        header: { simTimeUs: 1_000_000n },
        entities: [
          { id: "gcs-01", kind: EntityKind.GCS, side: Side.BLUE, alive: true },
          { id: "uav-001", kind: EntityKind.UAV, side: Side.BLUE, alive: true },
          { id: "tgt-001", kind: EntityKind.GROUND_TARGET, side: Side.RED, alive: true },
        ],
      }),
    );
    expect(s.entities.get("gcs-01")).toMatchObject({ kind: EntityKind.GCS, fromTruth: true });
    s.handleFrame(frameOf("truth/event/kill", TruthEventSchema, { event: { case: "kill", value: { entityId: "uav-001" } } }));
    expect(s.entities.get("uav-001")!.alive).toBe(false);

    const tree = buildTree(s.entities.values());
    expect(tree.map((g) => g.cls)).toEqual(["air", "ground"]);
    expect(tree[1].sides.map((x) => [x.side, x.entities.map((e) => e.id)])).toEqual([
      [Side.BLUE, ["gcs-01"]],
      [Side.RED, ["tgt-001"]],
    ]);
  });

  it("링크 상태·SimStatus·무시한 프레임", () => {
    const s = new MonitorStore();
    s.handleFrame(frameOf("link/state/gcs-01/uav-001", LinkStateSchema, { a: "gcs-01", b: "uav-001", lossRate: 0.3 }));
    s.handleFrame(frameOf("sim/ctrl/status", SimStatusSchema, { simTimeUs: 7_000_000n, frameHz: 50 }));
    s.handleFrame({ key: "foo/bar", encoding: "", payload: new Uint8Array() });
    expect(s.linkStates.get("gcs-01|uav-001")!.lossRate).toBeCloseTo(0.3);
    expect(s.status!.frameHz).toBe(50);
    expect(s.agg.nowUs).toBe(7_000_000);
    expect([s.frames, s.ignored]).toEqual([3, 1]);
  });

  it("시각이 5 s 넘게 거꾸로 가면(재생 되감기) 집계를 지운다", () => {
    const s = new MonitorStore();
    s.handleFrame(outcomeFrame(outcome({ t: 60_000_000 })));
    s.handleFrame(outcomeFrame(outcome({ t: 58_000_000 }))); // 지터 수준은 유지
    expect(s.agg.all.total).toBe(2);
    s.handleFrame(outcomeFrame(outcome({ t: 1_000_000 })));
    expect(s.rewinds).toBe(1);
    expect(s.agg.all.total).toBe(1);
    expect(s.timeline.size).toBe(1);
    expect(s.entities.size).toBe(2);
  });
});
