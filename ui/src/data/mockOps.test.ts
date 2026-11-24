// TC-UI-083: 목 소스의 운용 시나리오 흉내 — 승인·고장 주입·수신 정보 (IMP-UI-093)
import { create, fromBinary } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { ApprovalRequestSchema, FormationShape, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { Side } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LeaderUpdateSchema, TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import { StoreLoadoutSchema } from "../gen/swarm/v1/ms_pb";
import { FaultKind, ParamOwner, SimCommandSchema } from "../gen/swarm/v1/sim_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import { ApprovalStore } from "../model/approvals";
import { C2Commander } from "../model/commands";
import { faultCommand } from "../model/faults";
import { GcsPicture } from "../model/gcsPicture";
import type { MockClock } from "./mockSource";
import { MockSource } from "./mockSource";

class FakeClock implements MockClock {
  t = 0;
  private fn: (() => void) | null = null;
  now = () => this.t;
  setInterval(fn: () => void) {
    this.fn = fn;
    return 1;
  }
  clearInterval() {
    this.fn = null;
  }
  advance(ms: number, stepMs = 20) {
    for (let e = 0; e < ms; e += stepMs) {
      this.t += stepMs;
      this.fn?.();
    }
  }
}

const sim = (c: MessageInitShape<typeof SimCommandSchema>["cmd"]) => create(SimCommandSchema, { issuer: "ui-test", cmd: c });

async function setup() {
  const clock = new FakeClock();
  const src = new MockSource({ frameHz: 50, events: false }, clock);
  const rx: [string, LinkEnvelope][] = [];
  const frames: TruthFrame[] = [];
  src.subscribe({ rx: (k, e) => rx.push([k, e]), truth: (f) => frames.push(f) });
  await src.connect();
  const c = new C2Commander(src.gcs, "ui-me");
  const of = (name: string) => rx.filter(([k]) => k.endsWith(`/${name}`)).map(([, e]) => e);
  const statuses = (taskId: string) =>
    of("TaskStatus").map((e) => fromBinary(TaskStatusSchema, e.payload)).filter((s) => s.taskId === taskId).map((s) => [s.header?.source, s.state, s.reason]);
  return { clock, src, rx, frames, c, of, statuses };
}

describe("TC-UI-083 목 소스 운용 흉내", () => {
  it("교전 기준 require_approval이면 타격은 승인 요청 → 승인하면 수락, 늦은 응답은 무시", async () => {
    const { src, c, of, statuses } = await setup();
    src.sendC2(c.engagementCriteria({ hostileSides: [Side.RED], requireApproval: true, weaponsFree: [], noStrike: [] }, ["uav-001"]));
    const s = c.mission({ kind: "strike", weapon: "agm_short", targetId: "tgt-001" }, ["uav-001"]);
    src.sendC2(s);
    const reqs = of("ApprovalRequest").map((e) => fromBinary(ApprovalRequestSchema, e.payload));
    expect(reqs.map((r) => [r.header?.source, r.taskId, r.targetId])).toEqual([["uav-001", s.taskId, "tgt-001"]]);
    expect(statuses(s.taskId!)).toEqual([]);
    src.sendC2(c.approval(reqs[0].requestId, true, "uav-001"));
    src.sendC2(c.approval(reqs[0].requestId, false, "uav-001")); // 늦음
    expect(statuses(s.taskId!)).toEqual([["uav-001", CommandState.ACCEPTED, "목 소스: 수락"]]);
    // 승인 기준이 없으면 바로 수락
    src.sendC2(c.engagementCriteria({ hostileSides: [], requireApproval: false, weaponsFree: [], noStrike: [] }, ["uav-001"]));
    const s2 = c.mission({ kind: "strike", weapon: "agm_short", targetId: "tgt-002" }, ["uav-001"]);
    src.sendC2(s2);
    expect(statuses(s2.taskId!)[0][1]).toBe(CommandState.ACCEPTED);
  });

  it("approval_tasks의 작업은 승인을 기다리고, 거부면 REJECTED, approval_timeout_s가 지나면 approval timeout", async () => {
    const { clock, src, c, of, statuses } = await setup();
    src.send(sim({ case: "setParams", value: { entityId: "uav-002", owner: ParamOwner.MA, values: { approval_tasks: "jam,track", approval_timeout_s: 5 } } }));
    const j = c.mission({ kind: "jam", center: { latDeg: 37, lonDeg: 127, altM: 900 }, radiusM: 1000 }, ["uav-002"]);
    src.sendC2(j);
    const rid = fromBinary(ApprovalRequestSchema, of("ApprovalRequest")[0].payload).requestId;
    src.sendC2(c.approval(rid, false, "uav-002"));
    expect(statuses(j.taskId!)).toEqual([["uav-002", CommandState.REJECTED, "approval denied"]]);
    const t = c.mission({ kind: "track", targetId: "tgt-101" }, ["uav-002"]);
    src.sendC2(t);
    clock.advance(6000);
    expect(statuses(t.taskId!)).toEqual([["uav-002", CommandState.REJECTED, "approval timeout"]]);
    // 대기 중 같은 작업 취소는 CANCELLED
    const t2 = c.mission({ kind: "track", targetId: "tgt-101" }, ["uav-002"]);
    src.sendC2(t2);
    src.sendC2(c.cancel(t2.taskId!, ["uav-002"]));
    expect(statuses(t2.taskId!)).toEqual([["uav-002", CommandState.CANCELLED, ""]]);
  });

  it("GCS 링크 단절 동안 그 기체는 명령을 받지 못하고 보고도 오지 않는다. 시간이 지나면 복구", async () => {
    const { clock, src, c, rx, statuses } = await setup();
    src.send(sim(faultCommand("uav-001", FaultKind.GCS_LINK_CUT, 3)));
    const n0 = rx.length;
    const h = c.mission({ kind: "returnToBase" }, ["uav-001"]);
    src.sendC2(h);
    clock.advance(2000);
    expect(statuses(h.taskId!)).toEqual([]);
    expect(rx.slice(n0).some(([, e]) => e.header?.source === "uav-001")).toBe(false);
    clock.advance(2000);
    expect(rx.slice(n0).some(([k, e]) => k.endsWith("NavigationReport") && e.header?.source === "uav-001")).toBe(true);
    src.send(sim(faultCommand("uav-002", FaultKind.LINK_CUT, 0)));
    src.send(sim(faultCommand("uav-002", FaultKind.LINK_CUT, 0, true)));
    const m = c.mission({ kind: "returnToBase" }, ["uav-002"]);
    src.sendC2(m);
    expect(statuses(m.taskId!)[0][1]).toBe(CommandState.ACCEPTED);
  });

  it("KILL은 엔티티를 파괴(alive=false, 자리 고정)하고 Reset하면 되살린다", async () => {
    const { clock, src, frames } = await setup();
    src.send(sim(faultCommand("uav-003", FaultKind.KILL, 0)));
    clock.advance(100);
    const p1 = frames[frames.length - 1].entities.find((e) => e.id === "uav-003")!;
    clock.advance(2000);
    const p2 = frames[frames.length - 1].entities.find((e) => e.id === "uav-003")!;
    expect(p1.alive).toBe(false);
    expect(p2.kinematics?.position).toEqual(p1.kinematics?.position);
    src.send(sim({ case: "reset", value: {} }));
    expect(frames[frames.length - 1].entities.find((e) => e.id === "uav-003")!.alive).toBe(true);
  });

  it("StoreLoadout(적재 때)·LeaderUpdate(편대 지정)·TrackShare(추적 중 1 Hz)를 rx로 내고 GcsPicture가 읽는다", async () => {
    const { clock, src, c, rx, of } = await setup();
    const p = new GcsPicture();
    const ap = new ApprovalStore("ui-me");
    for (const [k, e] of rx) p.onRx(k, e);
    expect(fromBinary(StoreLoadoutSchema, of("StoreLoadout")[0].payload).stores.map((s) => s.type)).toEqual(["camera", "jammer", "agm_short"]);
    expect(p.loadout("uav-001")?.find((s) => s.type === "agm_short")?.count).toBe(2);
    src.sendC2(c.formation("fmn-1", ["uav-002", "uav-001"], FormationShape.WEDGE, 100, "uav-002"));
    const lu = fromBinary(LeaderUpdateSchema, of("LeaderUpdate")[0].payload);
    expect([lu.groupId, lu.leader, lu.term]).toEqual(["fmn-1", "uav-002", 1n]);
    src.sendC2(c.mission({ kind: "track", targetId: "tgt-101" }, ["uav-001"]));
    const n0 = rx.length;
    clock.advance(2100);
    const shares = rx.slice(n0).filter(([k]) => k.endsWith("/TrackShare"));
    expect(shares.length).toBeGreaterThanOrEqual(2);
    expect(shares[0][0]).toBe("swarm/gcs-01/rx/p2p/TrackShare");
    expect(fromBinary(TrackShareSchema, shares[0][1].payload)).toMatchObject({ targetId: "tgt-101", header: { source: "uav-001" } });
    for (const [k, e] of rx) {
      p.onRx(k, e);
      ap.onRx(k, e);
    }
    // LeaderUpdate는 리더 자신의 편대만 알려 준다. 구성원은 보낸 FormationCommand로 안다
    expect(p.group("uav-002")).toEqual({ groupId: "fmn-1", leader: "uav-002", from: "report" });
    expect(p.group("uav-001")).toBeNull();
    const f = c.formation("fmn-1", ["uav-002", "uav-001"], FormationShape.WEDGE, 100, "uav-002");
    p.onTx(f.key, f.envelope);
    expect(p.group("uav-001")).toMatchObject({ groupId: "fmn-1", leader: "uav-002" });
    expect(p.sharedTracks(src.status().simTimeUs).map((t) => t.source)).toEqual(["uav-001"]);
  });
});
