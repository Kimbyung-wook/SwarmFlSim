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

  it("시계 시각이 5 s 넘게 거꾸로 가면(재생 되감기) 집계를 지운다", () => {
    const s = new MonitorStore();
    const status = (t: number) => frameOf("sim/ctrl/status", SimStatusSchema, { simTimeUs: BigInt(t) });
    s.handleFrame(status(60_000_000));
    s.handleFrame(outcomeFrame(outcome({ t: 60_000_000 })));
    s.handleFrame(status(58_000_000)); // 지터 수준은 유지
    s.handleFrame(outcomeFrame(outcome({ t: 58_000_000 })));
    expect(s.agg.all.total).toBe(2);
    s.handleFrame(status(1_000_000));
    s.handleFrame(outcomeFrame(outcome({ t: 1_000_000 })));
    expect(s.rewinds).toBe(1);
    expect(s.agg.all.total).toBe(1);
    expect(s.timeline.size).toBe(1);
    expect(s.entities.size).toBe(2);
  });

  it("데이터링크가 밀려 늦게 온 outcome은 되감기가 아니다. 지연을 잰다", () => {
    const s = new MonitorStore();
    s.handleFrame(frameOf("sim/ctrl/status", SimStatusSchema, { simTimeUs: 80_000_000n }));
    s.handleFrame(outcomeFrame(outcome({ t: 7_400_000 })));
    s.handleFrame(outcomeFrame(outcome({ t: 7_420_000 })));
    expect(s.rewinds).toBe(0);
    expect(s.agg.all.total).toBe(2);
    expect(s.linkLagUs).toBe(72_580_000);
  });

  // TC-MON-014: 링크 지연은 outcome을 받은 순간의 sim 시계 − tx 시각. 트래픽 공백은 지연이 아니다 (IMP-MON-026)
  it("트래픽이 없는 구간은 링크 지연이 아니다(재생 배속과도 무관)", () => {
    const s = new MonitorStore();
    const status = (t: number) => frameOf("sim/ctrl/status", SimStatusSchema, { simTimeUs: BigInt(t) });
    s.handleFrame(status(295_600_000));
    s.handleFrame(outcomeFrame(outcome({ t: 295_500_000 })));
    expect(s.linkLagUs).toBe(100_000);
    // outcome 없이 시계만 150 s 흐른다: 이전 구현은 150 s로 표시했다
    for (let t = 296_600_000; t <= 445_600_000; t += 1_000_000) s.handleFrame(status(t));
    expect(s.linkLagUs).toBe(0);
    // 다시 outcome이 오면 그 순간의 지연만 본다
    s.handleFrame(outcomeFrame(outcome({ t: 445_000_000 })));
    expect(s.linkLagUs).toBe(600_000);
    // 데이터링크가 밀려 늦게 온 outcome은 그 지연이 보이고, 5 s 지나면 사라진다
    s.handleFrame(outcomeFrame(outcome({ t: 405_600_000 })));
    expect(s.linkLagUs).toBe(40_000_000);
    s.handleFrame(status(452_000_000));
    expect(s.linkLagUs).toBe(0);
  });
});
