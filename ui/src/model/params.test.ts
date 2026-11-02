// TC-UI-029~030: 기체별 매개변수 — 항목 구성, 입력 검사, set_params 메시지, 거부 표시, 목 소스·버스 연결 (IMP-UI-045~047, DEC-035)
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { MockParams } from "../data/mockParams";
import { MockSource } from "../data/mockSource";
import { BusSource, SIM_CMD_ENCODING } from "../data/busSource";
import type { BusTransport, TransportCallback } from "../data/busSource";
import { ParamLayer } from "../gen/swarm/v1/entity_pb";
import { EntityParamsSchema, ParamOwner, SimCommandSchema } from "../gen/swarm/v1/sim_pb";
import { ParamStore, applied, composeGroups, parseInput, rejectLabel, resetValue, setParamsCommands } from "./params";

function storeWith(ids: string[], mp = new MockParams()): ParamStore {
  const s = new ParamStore();
  for (const id of ids) for (const o of [ParamOwner.DYNAMICS, ParamOwner.FA, ParamOwner.MA]) s.onParams(mp.snapshot(id, o, 1_000_000n));
  return s;
}

const row = (s: ParamStore, ids: string[], key: string) => {
  const r = composeGroups(s, ids).flatMap((g) => g.rows).find((x) => x.key === key);
  if (!r) throw new Error(`행 없음: ${key}`);
  return r;
};

describe("TC-UI-029 매개변수 항목 구성·검사·메시지", () => {
  it("계층 순서(기체→제어→유도→행위→결정)로 묶고 기본값과 현재값을 함께 담는다", () => {
    const g = composeGroups(storeWith(["uav-001"]), ["uav-001"]);
    expect(g.map((x) => x.layer)).toEqual([ParamLayer.AIRFRAME, ParamLayer.CONTROL, ParamLayer.GUIDANCE, ParamLayer.BEHAVIOR, ParamLayer.DECISION]);
    const v = g[0].rows.find((r) => r.spec.name === "v_max_mps")!;
    expect(v).toMatchObject({ type: "number", defaultValue: 45, common: 45, mixed: false, owner: ParamOwner.DYNAMICS });
    expect(row(storeWith(["uav-001"]), ["uav-001"], `${ParamOwner.FA}:terrain_follow`).type).toBe("boolean");
    expect(row(storeWith(["uav-001"]), ["uav-001"], `${ParamOwner.MA}:formation`).type).toBe("string");
    expect(composeGroups(storeWith([]), ["uav-001"])).toEqual([]);
    expect(composeGroups(storeWith(["uav-001"]), [])).toEqual([]);
  });

  it("여러 기체: 이름이 같은 항목을 합치고, 값이 다르면 혼합으로 본다. 선언을 못 받은 기체가 있으면 그 소유자는 뺀다", () => {
    const mp = new MockParams();
    mp.apply("uav-002", ParamOwner.DYNAMICS, { v_max_mps: 60 });
    const s = storeWith(["uav-001", "uav-002"], mp);
    const r = row(s, ["uav-001", "uav-002"], `${ParamOwner.DYNAMICS}:v_max_mps`);
    expect(r.mixed).toBe(true);
    expect(r.common).toBeUndefined();
    expect(r.targets.map((t) => [t.entityId, t.value])).toEqual([["uav-001", 45], ["uav-002", 60]]);
    expect(row(s, ["uav-001", "uav-002"], `${ParamOwner.DYNAMICS}:kp_roll`).mixed).toBe(false);
    const half = new ParamStore();
    half.onParams(mp.snapshot("uav-001", ParamOwner.FA, 0n));
    expect(composeGroups(half, ["uav-001", "uav-002"])).toEqual([]);
  });

  it("입력 검사: 숫자 형식·min/max, 문자열, 참/거짓", () => {
    const s = storeWith(["uav-001"]);
    const bank = row(s, ["uav-001"], `${ParamOwner.DYNAMICS}:bank_max_deg`).spec; // 5~75
    expect(parseInput(bank, " 30.5 ")).toEqual({ ok: true, value: 30.5 });
    expect(parseInput(bank, "4.9")).toMatchObject({ ok: false });
    expect(parseInput(bank, "75.1")).toMatchObject({ ok: false });
    expect(parseInput(bank, "")).toMatchObject({ ok: false });
    expect(parseInput(bank, "abc")).toMatchObject({ ok: false });
    expect(parseInput(bank, "Infinity")).toMatchObject({ ok: false });
    expect(parseInput(row(s, ["uav-001"], `${ParamOwner.MA}:formation`).spec, "wedge")).toEqual({ ok: true, value: "wedge" });
    const tf = row(s, ["uav-001"], `${ParamOwner.FA}:terrain_follow`).spec;
    expect(parseInput(tf, true)).toEqual({ ok: true, value: true });
    expect(parseInput(tf, "maybe")).toMatchObject({ ok: false });
  });

  it("입력 검사: choices가 있으면 허용 목록 밖 문자열은 거절한다", () => {
    const sp = row(storeWith(["uav-001"]), ["uav-001"], `${ParamOwner.FA}:racetrack_guidance`).spec;
    expect(sp.choices).toEqual(["dubins", "vector_field"]);
    expect(parseInput(sp, "vector_field")).toEqual({ ok: true, value: "vector_field" });
    expect(parseInput(sp, "spiral")).toMatchObject({ ok: false });
    expect(parseInput(sp, "")).toMatchObject({ ok: false });
    expect(rejectLabel("choice")).toBe("허용 목록에 없는 값");
  });

  it("set_params 메시지: 기체마다 하나, 소유자와 바꿀 이름만 담고 직렬화 왕복이 같다", () => {
    const cmds = setParamsCommands("ui-x", ["uav-001", "uav-002"], ParamOwner.FA, { lookahead_s: 12, terrain_follow: true });
    expect(cmds).toHaveLength(2);
    const back = fromBinary(SimCommandSchema, toBinary(SimCommandSchema, cmds[1]));
    expect(back.issuer).toBe("ui-x");
    expect(back.cmd.case).toBe("setParams");
    if (back.cmd.case !== "setParams") return;
    expect(back.cmd.value.entityId).toBe("uav-002");
    expect(back.cmd.value.owner).toBe(ParamOwner.FA);
    expect(back.cmd.value.values).toEqual({ lookahead_s: 12, terrain_follow: true });
    expect(() => setParamsCommands("ui-x", ["uav-001"], ParamOwner.FA, {})).toThrow();
    expect(() => setParamsCommands("ui-x", [], ParamOwner.FA, { a: 1 })).toThrow();
  });

  it("기본값으로 되돌리기: 이미 기본값이면 null, 아니면 기본값", () => {
    const mp = new MockParams();
    const k = `${ParamOwner.DYNAMICS}:v_max_mps`;
    expect(resetValue(row(storeWith(["uav-001"], mp), ["uav-001"], k))).toBeNull();
    mp.apply("uav-001", ParamOwner.DYNAMICS, { v_max_mps: 70 });
    expect(resetValue(row(storeWith(["uav-001"], mp), ["uav-001"], k))).toBe(45);
  });
});

describe("TC-UI-030 적용·거부 표시와 소스 연결", () => {
  it("거부는 사유 코드 4종 모두 항목에 붙고, 값은 바뀌지 않는다 (낙관적 적용 없음)", () => {
    const mp = new MockParams();
    mp.apply("uav-001", ParamOwner.DYNAMICS, { nope: 1, v_max_mps: "fast", bank_max_deg: 200, mass_kg: 20 });
    const s = storeWith(["uav-001"], mp);
    const rej = (name: string) => s.get("uav-001", ParamOwner.DYNAMICS)!.rejected.find((r) => r.name === name)?.reason;
    expect([rej("nope"), rej("v_max_mps"), rej("bank_max_deg"), rej("mass_kg")]).toEqual(["unknown", "type", "range", "not_runtime"]);
    const m = row(s, ["uav-001"], `${ParamOwner.DYNAMICS}:mass_kg`);
    expect(m.rejected).toEqual({ entityId: "uav-001", reason: "not_runtime" });
    expect(m.spec.runtime).toBe(false);
    expect(m.common).toBe(11); // 거부됐으므로 그대로
    expect(rejectLabel("range")).toBe("허용 범위를 벗어남");
    expect(rejectLabel("other")).toBe("other");
  });

  it("applied: 모든 대상의 values가 보낸 값과 같을 때만 적용으로 본다", () => {
    const mp = new MockParams();
    const k = `${ParamOwner.DYNAMICS}:v_max_mps`;
    expect(applied(row(storeWith(["uav-001", "uav-002"], mp), ["uav-001", "uav-002"], k), 60)).toBe(false);
    mp.apply("uav-001", ParamOwner.DYNAMICS, { v_max_mps: 60 });
    expect(applied(row(storeWith(["uav-001", "uav-002"], mp), ["uav-001", "uav-002"], k), 60)).toBe(false);
    mp.apply("uav-002", ParamOwner.DYNAMICS, { v_max_mps: 60 });
    expect(applied(row(storeWith(["uav-001", "uav-002"], mp), ["uav-001", "uav-002"], k), 60)).toBe(true);
  });

  it("목 소스: 적재 후 UAV마다 3개 소유자의 EntityParams를 내고, set_params는 EntityParams로만 확인된다", async () => {
    const src = new MockSource({ autoStart: false });
    const store = new ParamStore();
    src.subscribe({ params: (p) => store.onParams(p) });
    await src.connect();
    expect(store.get("uav-001", ParamOwner.DYNAMICS)?.specs.length).toBeGreaterThan(0);
    expect(store.has("gcs-01")).toBe(false);
    const before = store.version;
    for (const c of setParamsCommands("ui-t", ["uav-001"], ParamOwner.DYNAMICS, { v_max_mps: 60, mass_kg: 30 })) src.send(c);
    expect(store.version).toBeGreaterThan(before);
    const p = store.get("uav-001", ParamOwner.DYNAMICS)!;
    expect(p.values?.v_max_mps).toBe(60);
    expect(p.values?.mass_kg).toBe(11);
    expect(p.rejected).toEqual([expect.objectContaining({ name: "mass_kg", reason: "not_runtime" })]);
    // 다른 기체는 그대로
    expect(store.get("uav-002", ParamOwner.DYNAMICS)?.values?.v_max_mps).toBe(45);
    // 리셋하면 기본값으로 돌아간다
    src.send(create(SimCommandSchema, { issuer: "ui-t", cmd: { case: "reset", value: {} } }));
    expect(store.get("uav-001", ParamOwner.DYNAMICS)?.values?.v_max_mps).toBe(45);
  });

  it("버스 소스: sim/param/**을 구독해 EntityParams를 풀고, set_params를 sim/ctrl/cmd로 보낸다", async () => {
    const subs = new Map<string, TransportCallback>();
    const puts: { key: string; payload: Uint8Array; encoding: string }[] = [];
    const t: BusTransport = {
      open: async () => {},
      subscribe: (key, cb) => (subs.set(key, cb), () => subs.delete(key)),
      put: (key, payload, encoding) => void puts.push({ key, payload, encoding }),
      close: () => {},
    };
    const src = new BusSource(t, { gcs: "gcs-01" });
    const got: string[] = [];
    src.subscribe({ params: (p) => got.push(`${p.entityId}/${p.owner}`) });
    await src.connect();
    expect([...subs.keys()]).toContain("sim/param/**");
    const ep = create(EntityParamsSchema, { entityId: "uav-007", owner: ParamOwner.MA, values: { aggressiveness: 0.7 } });
    subs.get("sim/param/**")!(toBinary(EntityParamsSchema, ep), "sim/param/uav-007/ma", "");
    expect(got).toEqual([`uav-007/${ParamOwner.MA}`]);
    src.send(setParamsCommands("ui-t", ["uav-007"], ParamOwner.MA, { aggressiveness: 0.2 })[0]);
    expect(puts).toHaveLength(1);
    expect(puts[0].key).toBe("sim/ctrl/cmd");
    expect(puts[0].encoding).toBe(SIM_CMD_ENCODING);
    expect(fromBinary(SimCommandSchema, puts[0].payload).cmd.case).toBe("setParams");
  });
});
