// TC-UI-008: 버스 소스의 키·인코딩·구독 주기, rx 해석, C2 송신 키 검사 (IMP-UI-011, IMP-UI-028), 아이콘 생성 (IMP-UI-012)
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { SimCommandSchema } from "../gen/swarm/v1/sim_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { C2Commander, ENVELOPE_ENCODING } from "../model/commands";
import { iconSvg, iconUrl, isDirectional, sideColor } from "../model/symbology";
import type { BusTransport, SubscribeOptions, TransportCallback } from "./busSource";
import { BusSource, KEY_SIM_CMD, KEY_SIM_PARAMS, KEY_SIM_STATUS, KEY_TRUTH_STATE } from "./busSource";

class FakeTransport implements BusTransport {
  subs = new Map<string, { cb: TransportCallback; opts?: SubscribeOptions }>();
  puts: { key: string; payload: Uint8Array; encoding: string }[] = [];
  opened = false;
  async open() {
    this.opened = true;
  }
  subscribe(key: string, cb: TransportCallback, opts?: SubscribeOptions) {
    this.subs.set(key, { cb, opts });
    return () => void this.subs.delete(key);
  }
  put(key: string, payload: Uint8Array, encoding: string) {
    this.puts.push({ key, payload, encoding });
  }
  close() {}
}

describe("BusSource", () => {
  it("truth/state를 디코드해 전달하고 sim/ctrl/cmd로 인코드해 보낸다", async () => {
    const t = new FakeTransport();
    const src = new BusSource(t);
    const got: string[] = [];
    src.subscribe({ truth: (f) => got.push(f.entities[0].id) });
    await src.connect();
    const f = create(TruthFrameSchema, { entities: [{ id: "uav-001" }] });
    t.subs.get(KEY_TRUTH_STATE)!.cb(toBinary(TruthFrameSchema, f), KEY_TRUTH_STATE, "");
    expect(got).toEqual(["uav-001"]);

    src.send(create(SimCommandSchema, { issuer: "ui-a1", cmd: { case: "pause", value: {} } }));
    expect(t.puts[0].key).toBe(KEY_SIM_CMD);
    expect(t.puts[0].encoding).toBe("application/protobuf;swarm.v1.SimCommand");
    expect(fromBinary(SimCommandSchema, t.puts[0].payload).cmd.case).toBe("pause");

    src.close();
    expect(t.subs.size).toBe(0);
  });

  it("구독 키와 truth 다운샘플 주기, GCS가 없으면 rx를 구독하지 않는다", async () => {
    const a = new FakeTransport();
    await new BusSource(a, { gcs: "gcs-01", truthMaxHz: 20 }).connect();
    expect([...a.subs.keys()].sort()).toEqual([KEY_SIM_STATUS, KEY_SIM_PARAMS, "swarm/gcs-01/rx/**", KEY_TRUTH_STATE].sort());
    // 브리지 다운샘플은 걸지 않는다 (프레임 번호 공백 계산, DEC-042)
    expect(a.subs.get(KEY_TRUTH_STATE)!.opts?.maxHz).toBeUndefined();
    expect(a.opened).toBe(true);

    const b = new FakeTransport();
    const src = new BusSource(b);
    await src.connect();
    expect([...b.subs.keys()].sort()).toEqual([KEY_SIM_STATUS, KEY_SIM_PARAMS, KEY_TRUTH_STATE].sort());
    const out = new C2Commander("gcs-01", "ui-x").task("hold", ["uav-001"]);
    expect(() => src.sendC2(out)).toThrow(/GCS/);
  });

  it("TC-UI-043 truth는 모든 프레임 번호를 알리고, 엔티티 해석은 truthMaxHz로 줄인다 (IMP-UI-059, DEC-042)", async () => {
    const t = new FakeTransport();
    let ms = 0;
    const src = new BusSource(t, { truthMaxHz: 10, clock: () => ms });
    const seq: bigint[] = [];
    let truths = 0;
    src.subscribe({ frameSeq: (n) => seq.push(n), truth: () => truths++ });
    await src.connect();
    const cb = t.subs.get(KEY_TRUTH_STATE)!.cb;
    for (let n = 1n; n <= 25n; n++) {
      cb(toBinary(TruthFrameSchema, create(TruthFrameSchema, { header: { frame: n } })), KEY_TRUTH_STATE, "");
      ms += 20; // 50 Hz
    }
    expect(seq).toHaveLength(25);
    expect(seq[24]).toBe(25n);
    expect(truths).toBe(5); // 100 ms마다 한 번
  });

  it("rx LinkEnvelope를 해석하고 C2를 자기 GCS tx 키로만 보낸다", async () => {
    const t = new FakeTransport();
    const errs: string[] = [];
    const src = new BusSource(t, { gcs: "gcs-01", onDecodeError: (k) => errs.push(k) });
    const rx: string[] = [];
    src.subscribe({ rx: (k, env) => rx.push(`${k}|${env.header?.source}`) });
    await src.connect();
    const cb = t.subs.get("swarm/gcs-01/rx/**")!.cb;
    const env = create(LinkEnvelopeSchema, { header: { source: "uav-003" }, msgType: "swarm.v1.TaskStatus" });
    cb(toBinary(LinkEnvelopeSchema, env), "swarm/gcs-01/rx/c2/TaskStatus", ENVELOPE_ENCODING);
    cb(new Uint8Array([0xff, 0xff, 0xff]), "swarm/gcs-01/rx/c2/Bad", ENVELOPE_ENCODING);
    expect(rx).toEqual(["swarm/gcs-01/rx/c2/TaskStatus|uav-003"]);
    expect(errs).toEqual(["swarm/gcs-01/rx/c2/Bad"]);

    const out = new C2Commander("gcs-01", "ui-x").task("returnToBase", ["uav-001", "uav-002"]);
    src.sendC2(out);
    expect(t.puts[0].key).toBe("swarm/gcs-01/tx/c2/TaskCommand");
    expect(t.puts[0].encoding).toBe(ENVELOPE_ENCODING);
    expect(fromBinary(LinkEnvelopeSchema, t.puts[0].payload).dst).toEqual(["uav-001", "uav-002"]);
    expect(() => src.sendC2(new C2Commander("gcs-02", "ui-x").task("hold", ["uav-001"]))).toThrow(/다른 GCS/);
  });
});

describe("symbology", () => {
  it("진영별 색과 선택 링", () => {
    expect(sideColor(Side.BLUE)).not.toBe(sideColor(Side.RED));
    expect(iconSvg(EntityKind.UAV, Side.BLUE, true)).toContain("stroke-dasharray");
    expect(iconSvg(EntityKind.UAV, Side.BLUE, false)).not.toContain("stroke-dasharray");
    expect(iconSvg(EntityKind.UAV, Side.RED, false, false)).toContain("#6b7280");
  });

  it("데이터 URL은 캐시되고 공중 종류만 회전한다", () => {
    const a = iconUrl(EntityKind.GCS, Side.BLUE);
    expect(a.startsWith("data:image/svg+xml")).toBe(true);
    expect(iconUrl(EntityKind.GCS, Side.BLUE)).toBe(a);
    expect(isDirectional(EntityKind.UAV)).toBe(true);
    expect(isDirectional(EntityKind.GROUND_TARGET)).toBe(false);
  });
});
