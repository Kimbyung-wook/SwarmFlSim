// TC-UI-008: 버스 소스 자리의 키·인코딩 (IMP-UI-011), 아이콘 생성 (IMP-UI-012)
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { SimCommandSchema } from "../gen/swarm/v1/sim_pb";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { iconSvg, iconUrl, isDirectional, sideColor } from "../model/symbology";
import type { BusTransport } from "./busSource";
import { BusSource, KEY_SIM_CMD, KEY_TRUTH_STATE, UnimplementedTransport } from "./busSource";

class FakeTransport implements BusTransport {
  subs = new Map<string, (p: Uint8Array) => void>();
  puts: { key: string; payload: Uint8Array; encoding: string }[] = [];
  async open() {}
  subscribe(key: string, cb: (p: Uint8Array) => void) {
    this.subs.set(key, cb);
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
    t.subs.get(KEY_TRUTH_STATE)!(toBinary(TruthFrameSchema, f));
    expect(got).toEqual(["uav-001"]);

    src.send(create(SimCommandSchema, { issuer: "ui-a1", cmd: { case: "pause", value: {} } }));
    expect(t.puts[0].key).toBe(KEY_SIM_CMD);
    expect(t.puts[0].encoding).toBe("application/protobuf;swarm.v1.SimCommand");
    expect(fromBinary(SimCommandSchema, t.puts[0].payload).cmd.case).toBe("pause");

    src.close();
    expect(t.subs.size).toBe(0);
  });

  it("전송 계층이 없으면 연결에 실패한다", async () => {
    await expect(new BusSource(new UnimplementedTransport()).connect()).rejects.toThrow();
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
