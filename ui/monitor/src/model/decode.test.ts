// TC-MON-003: 버스 프레임 해석, 메시지 echo 해석 (IMP-MON-004)
import { create, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind } from "../gen/swarm/v1/entity_pb";
import { LinkEnvelopeSchema, LinkOutcomeSchema, LinkStateSchema } from "../gen/swarm/v1/link_pb";
import { PeerStatusSchema } from "../gen/swarm/v1/p2p_pb";
import { SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { TruthEventSchema, TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { decodeBusFrame, decodePayload, parseSwarmKey } from "./decode";
import { frameOf } from "./testutil";

describe("decodeBusFrame", () => {
  it("키별로 메시지 종류를 고른다", () => {
    const peer = toBinary(PeerStatusSchema, create(PeerStatusSchema, { groupId: "g1" }));
    const cases = [
      [frameOf("link/outcome/uav-001/gcs-01", LinkOutcomeSchema, { src: "uav-001", seq: 3 }), "outcome"],
      [frameOf("link/state/gcs-01/uav-001", LinkStateSchema, { a: "gcs-01", b: "uav-001" }), "linkState"],
      [frameOf("swarm/uav-001/tx/p2p/PeerStatus", LinkEnvelopeSchema, { msgType: "swarm.v1.PeerStatus", payload: peer }), "envelope"],
      [frameOf("truth/state", TruthFrameSchema, { entities: [{ id: "uav-001", kind: EntityKind.UAV }] }), "truth"],
      [frameOf("truth/event/kill", TruthEventSchema, { event: { case: "kill", value: { entityId: "uav-001" } } }), "truthEvent"],
      [frameOf("sim/ctrl/status", SimStatusSchema, { frameHz: 50 }), "status"],
    ] as const;
    for (const [f, kind] of cases) expect(decodeBusFrame(f).kind).toBe(kind);
    const env = decodeBusFrame(cases[2][0]);
    expect(env.kind === "envelope" && [env.dir, env.entity, env.iface, env.msg]).toEqual(["tx", "uav-001", "p2p", "PeerStatus"]);
  });

  it("인코딩이 키와 맞지 않거나 해석할 수 없으면 무시한다", () => {
    expect(decodeBusFrame(frameOf("link/outcome/a-1/b-1", LinkStateSchema, { a: "x" })).kind).toBe("ignored");
    expect(decodeBusFrame({ key: "truth/state", encoding: "", payload: new Uint8Array([0xff, 0xff]) }).kind).toBe("ignored");
    expect(decodeBusFrame({ key: "swarm/uav-001/foo", encoding: "", payload: new Uint8Array() }).kind).toBe("ignored");
    expect(decodeBusFrame({ key: "onboard/uav-001/X", encoding: "", payload: new Uint8Array() }).kind).toBe("ignored");
  });

  it("인코딩이 비면 키로 판단한다", () => {
    const f = frameOf("link/outcome/a-1/b-1", LinkOutcomeSchema, { src: "a-1" });
    expect(decodeBusFrame({ ...f, encoding: "" }).kind).toBe("outcome");
  });

  it("swarm 키 형식", () => {
    expect(parseSwarmKey("swarm/gcs-01/rx/c2/TaskStatus")).toEqual({ entity: "gcs-01", dir: "rx", iface: "c2", msg: "TaskStatus" });
    expect(parseSwarmKey("swarm/gcs-01/zz/c2/TaskStatus")).toBeUndefined();
    expect(parseSwarmKey("swarm/gcs-01/tx/c2")).toBeUndefined();
  });
});

describe("decodePayload (echo)", () => {
  it("msg_type 이름으로 해석해 JSON을 만든다", () => {
    const b = toBinary(PeerStatusSchema, create(PeerStatusSchema, { groupId: "g1", energyFrac: 0.5, header: { source: "uav-001", seq: 7 } }));
    const d = decodePayload("swarm.v1.PeerStatus", b);
    expect(d.error).toBeUndefined();
    expect(d.json).toMatchObject({ groupId: "g1", energyFrac: 0.5, header: { source: "uav-001", seq: 7 } });
  });

  it("모르는 타입·깨진 바이트는 오류로 표시한다", () => {
    expect(decodePayload("swarm.v1.Nope", new Uint8Array()).error).toBeDefined();
    expect(decodePayload("swarm.v1.PeerStatus", new Uint8Array([0x0a, 0xff])).error).toBeDefined();
  });
});
