// TC-UI-076~082: 운용 시나리오 보완 모델 (IMP-UI-085~091, docs/51 §4)
import type { DescMessage, MessageInitShape } from "@bufbuild/protobuf";
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import {
  ApprovalRequestSchema,
  ApprovalResponseSchema,
  FormationCommandSchema,
  FormationShape,
  LostLinkPolicy,
  TaskCommandSchema,
  TaskStatusSchema,
} from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { EngagementCriteriaSchema } from "../gen/swarm/v1/mp_pb";
import { StoreLoadoutSchema } from "../gen/swarm/v1/ms_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { LeaderUpdateSchema, PeerStatusSchema, TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import { FaultKind } from "../gen/swarm/v1/sim_pb";
import { ActivityStore } from "./activity";
import { ApprovalStore, approvalRemainingS } from "./approvals";
import { AREA_MAX_VERTICES, C2Commander, missionTask } from "./commands";
import { FaultLog, faultCommand } from "./faults";
import { GcsPicture } from "./gcsPicture";
import { missionOverlay } from "./missionOverlay";
import { TaskLog, cancellable } from "./taskLog";

const GCS = "gcs-01";
const UI = "ui-me";
const clock = () => ({ simTimeUs: 5_000_000n, frame: 250n });
const geo = (latDeg: number, lonDeg: number, altM = 900) => ({ latDeg, lonDeg, altM });

/** 기체가 보낸 rx 봉투 */
function rx<D extends DescMessage>(schema: D, init: MessageInitShape<D>, source: string, simTimeUs = 5_000_000n, publisher = ""): LinkEnvelope {
  const msg = create(schema, init);
  return create(LinkEnvelopeSchema, {
    header: { source, simTimeUs, seq: 1 },
    publisher,
    msgType: schema.typeName,
    payload: toBinary(schema, msg),
  });
}

const status = (taskId: string, state: CommandState, source: string, reason = "") =>
  rx(TaskStatusSchema, { header: { source }, taskId, state, reason }, source);

describe("TC-UI-076 재밍·추적 작업 (IMP-UI-085)", () => {
  it("재밍은 JamTask(원 영역, duration_s), 0초는 해제까지(0). 추적은 TrackTask(target_id)", () => {
    const c = new C2Commander(GCS, UI, clock);
    const jam = fromBinary(TaskCommandSchema, c.mission({ kind: "jam", center: geo(37, 127), radiusM: 2000, durationS: 120 }, ["uav-001"]).envelope.payload);
    expect(jam.task.case).toBe("jam");
    if (jam.task.case === "jam") {
      expect(jam.task.value.durationS).toBe(120);
      expect(jam.task.value.area?.shape.case).toBe("circle");
      if (jam.task.value.area?.shape.case === "circle") expect(jam.task.value.area.shape.value.radiusM).toBe(2000);
    }
    const forever = missionTask({ kind: "jam", center: geo(37, 127), radiusM: 500 });
    expect(forever.summary).toContain("해제까지");
    const fv = create(TaskCommandSchema, { task: forever.task }).task;
    expect(fv.case === "jam" && fv.value.durationS).toBe(0);
    const trk = fromBinary(TaskCommandSchema, c.mission({ kind: "track", targetId: "tgt-101" }, ["uav-002"]).envelope.payload);
    expect(trk.task.case === "track" && trk.task.value.targetId).toBe("tgt-101");
    expect(() => missionTask({ kind: "track", targetId: "" })).toThrow();
    expect(() => missionTask({ kind: "jam", center: geo(37, 127), radiusM: 0 })).toThrow();
  });

  it("행동 표시: 수행이 확인된 재밍은 영역 윤곽과 중심, 추적은 GCS가 받은 TrackShare 위치", () => {
    const c = new C2Commander(GCS, UI, clock);
    const a = new ActivityStore();
    const jam = c.mission({ kind: "jam", center: geo(37, 127), radiusM: 1000, polygon: [geo(37, 127), geo(37.02, 127), geo(37.01, 127.02)] }, ["uav-001"]);
    const trk = c.mission({ kind: "track", targetId: "tgt-101" }, ["uav-002"]);
    a.onTx(jam.key, jam.envelope);
    a.onTx(trk.key, trk.envelope);
    a.onRx("k", status(jam.taskId!, CommandState.EXECUTING, "uav-001"));
    a.onRx("k", status(trk.taskId!, CommandState.EXECUTING, "uav-002"));
    const s = a.shapeOf("uav-001")!;
    expect(s.kind).toBe("jam");
    expect(s.label).toBe("재밍");
    expect(s.paths[0]).toHaveLength(4); // 닫힌 삼각형
    expect(a.shapeOf("uav-002")).toBeNull(); // 표적 위치를 모른다
    a.onRx("k", rx(TrackShareSchema, { header: { source: "uav-003" }, targetId: "tgt-101", position: geo(37.1, 127.1), observedTimeUs: 1n }, "uav-003"));
    expect(a.shapeOf("uav-002")).toMatchObject({ kind: "track", lead: { latDeg: 37.1 } });
  });
});

describe("TC-UI-077 승인 대기 목록 (IMP-UI-086)", () => {
  const req = (rid: string, source = "uav-001", t = 10_000_000n) =>
    rx(ApprovalRequestSchema, { header: { source, simTimeUs: t }, requestId: rid, taskId: "t-9", targetId: "tgt-001", description: "strike t-9" }, source, t);
  const resp = (rid: string, approved: boolean, publisher: string, seq = 1) =>
    create(LinkEnvelopeSchema, {
      header: { source: GCS, seq },
      publisher,
      msgType: ApprovalResponseSchema.typeName,
      payload: toBinary(ApprovalResponseSchema, create(ApprovalResponseSchema, { requestId: rid, approved })),
    });

  it("ApprovalResponse는 tx/c2, 요청 기체에게만, publisher는 UI ID (DEC-075·077)", () => {
    const out = new C2Commander(GCS, UI, clock).approval("uav-001-approval-1", true, "uav-001");
    expect(out.key).toBe("swarm/gcs-01/tx/c2/ApprovalResponse");
    expect(out.envelope.dst).toEqual(["uav-001"]);
    expect(out.envelope.publisher).toBe(UI);
    expect(out.envelope.iface).toBe(L1Interface.C2);
    expect(fromBinary(ApprovalResponseSchema, out.envelope.payload)).toMatchObject({ requestId: "uav-001-approval-1", approved: true });
  });

  it("요청이 대기 목록에 들고, 처음 본 응답이 처리된 것, 뒤 응답은 늦음. 같은 봉투 되돌림은 한 번만 센다", () => {
    const s = new ApprovalStore(UI);
    s.onRx("swarm/gcs-01/rx/c2/ApprovalRequest", req("r1"));
    expect(s.pending().map((v) => [v.requester, v.taskId, v.targetId])).toEqual([["uav-001", "t-9", "tgt-001"]]);
    // Gateway(외부 승인)가 먼저 응답 → 처리됨. 이 UI의 응답은 늦음
    s.onTx("k", resp("r1", false, "gateway-gw1"));
    s.onTx("k", resp("r1", true, UI));
    s.onTx("k", resp("r1", true, UI)); // tx 되돌림
    const v = s.get("r1")!;
    expect(s.pending()).toHaveLength(0);
    expect(v.decision).toEqual({ approved: false, by: "gateway-gw1", mine: false });
    expect(v.late).toEqual([{ approved: true, by: UI, mine: true }]);
    s.onRx("k", status("t-9", CommandState.REJECTED, "uav-001", "approval denied"));
    expect(v.outcome).toBe("거부 (approval denied)");
  });

  it("응답 없이 시간 초과(REJECTED)하거나 다른 기체의 보고면 닫히지 않는다. 남은 시간은 approval_timeout_s 기준", () => {
    const s = new ApprovalStore(UI);
    s.onRx("k", req("r2", "uav-002", 10_000_000n));
    s.onRx("k", status("t-9", CommandState.REJECTED, "uav-003", "x"));
    expect(s.pending()).toHaveLength(1);
    const v = s.pending()[0];
    expect(approvalRemainingS(v, 60, 25_000_000n)).toBe(45);
    expect(approvalRemainingS(v, 60, 90_000_000n)).toBe(0);
    expect(approvalRemainingS(v, 0, 25_000_000n)).toBeNull();
    expect(approvalRemainingS(v, undefined, 25_000_000n)).toBeNull();
    s.onRx("k", status("t-9", CommandState.REJECTED, "uav-002", "approval timeout"));
    expect(s.pending()).toHaveLength(0);
    expect(v.decision).toBeNull();
    expect(v.outcome).toContain("approval timeout");
    // 끝난 요청에 온 응답은 늦음
    s.onTx("k", resp("r2", true, UI, 7));
    expect(v.decision).toBeNull();
    expect(v.late).toHaveLength(1);
    s.clear();
    expect(s.list()).toHaveLength(0);
  });
});

describe("TC-UI-078 고장 주입 (IMP-UI-087)", () => {
  it("InjectFault 명령: 지속 시간, 해제(clear), KILL 해제 불가", () => {
    expect(faultCommand("uav-001", FaultKind.GCS_LINK_CUT, 30)).toEqual({
      case: "fault",
      value: { entityId: "uav-001", fault: FaultKind.GCS_LINK_CUT, durationS: 30, clear: false },
    });
    expect(faultCommand("uav-001", FaultKind.ENGINE, -5)!.value).toMatchObject({ durationS: 0 });
    expect(faultCommand("uav-001", FaultKind.SENSOR, 30, true)!.value).toMatchObject({ durationS: 0, clear: true });
    expect(() => faultCommand("uav-001", FaultKind.KILL, 0, true)).toThrow();
    expect(() => faultCommand("", FaultKind.NAV, 0)).toThrow();
  });

  it("주입 기록: 같은 (엔티티, 종류)는 하나, 지속 시간이 지나면 빠지고, 해제·Reset이면 지운다", () => {
    const l = new FaultLog();
    l.injected("uav-001", FaultKind.GCS_LINK_CUT, 30, 0n);
    l.injected("uav-001", FaultKind.GCS_LINK_CUT, 60, 10_000_000n);
    l.injected("uav-002", FaultKind.NAV, 0, 0n);
    l.injected("tgt-001", FaultKind.KILL, 0, 0n);
    const a = l.active(40_000_000n);
    expect(a.map((e) => [e.entityId, e.remainingS])).toEqual([["tgt-001", null], ["uav-002", null], ["uav-001", 30]]);
    expect(l.active(80_000_000n).map((e) => e.entityId)).toEqual(["tgt-001", "uav-002"]);
    l.cleared("uav-002", FaultKind.NAV);
    expect(l.active(0n).map((e) => e.entityId)).toEqual(["tgt-001", "uav-001"]);
    l.clear();
    expect(l.active(0n)).toHaveLength(0);
  });
});

describe("TC-UI-079 작업 취소·링크 상실 정책 (IMP-UI-088)", () => {
  it("lost_link_policy를 작업에 싣는다. 기본은 UNSPECIFIED(MA 변수)", () => {
    const c = new C2Commander(GCS, UI, clock);
    const dflt = fromBinary(TaskCommandSchema, c.mission({ kind: "returnToBase" }, ["uav-001"]).envelope.payload);
    expect(dflt.lostLinkPolicy).toBe(LostLinkPolicy.UNSPECIFIED);
    const out = c.mission({ kind: "moveTo", destination: geo(37, 127) }, ["uav-001"], undefined, LostLinkPolicy.CONTINUE);
    expect(fromBinary(TaskCommandSchema, out.envelope.payload).lostLinkPolicy).toBe(LostLinkPolicy.CONTINUE);
    expect(out.summary).toContain("상실 시 계속 수행");
  });

  it("취소는 같은 task_id·대상의 cancel 명령이고, 기록은 새로 만들지 않고 원래 작업에 표시한다. 모두 끝나면 취소 단추가 없다", () => {
    const c = new C2Commander(GCS, UI, clock);
    const log = new TaskLog();
    const out = c.mission({ kind: "hold", direction: 0 }, ["uav-001", "uav-002"]);
    const e = log.sent(out);
    expect(cancellable(e)).toBe(true);
    const cx = c.cancel(out.taskId!, e.assignees);
    const tc = fromBinary(TaskCommandSchema, cx.envelope.payload);
    expect([tc.cancel, tc.taskId, tc.assignees]).toEqual([true, out.taskId, ["uav-001", "uav-002"]]);
    log.cancelSent(out.taskId!);
    expect(log.list()).toHaveLength(1);
    expect(log.get(out.taskId!)?.cancelRequested).toBe(true);
    log.received("k", status(out.taskId!, CommandState.CANCELLED, "uav-001"));
    expect(cancellable(e)).toBe(true);
    log.received("k", status(out.taskId!, CommandState.CANCELLED, "uav-002"));
    expect(cancellable(e)).toBe(false);
    // 편대·그룹 명령(지도 임무가 아님)은 취소할 수 없다
    expect(cancellable(log.sent(c.formation("g1", ["uav-001", "uav-002"], FormationShape.WEDGE, 100)))).toBe(false);
  });
});

describe("TC-UI-080 다각형 영역 (IMP-UI-089)", () => {
  const tri = [geo(37, 127), geo(37.02, 127), geo(37.01, 127.02)];
  it("정찰·재밍 다각형은 Polygon 꼭짓점으로, 3점 미만·상한 초과는 거부", () => {
    const s = missionTask({ kind: "search", center: geo(37, 127), radiusM: 1500, polygon: tri });
    expect(s.summary).toBe("정찰 다각형 3점");
    const st = create(TaskCommandSchema, { task: s.task }).task;
    if (st.case === "searchArea" && st.value.area?.shape.case === "polygon") {
      expect(st.value.area.shape.value.vertices.map((v) => v.latDeg)).toEqual([37, 37.02, 37.01]);
    } else throw new Error("polygon expected");
    expect(() => missionTask({ kind: "search", center: geo(37, 127), radiusM: 1, polygon: tri.slice(0, 2) })).toThrow();
    const many = Array.from({ length: AREA_MAX_VERTICES + 1 }, (_, i) => geo(37 + i * 1e-3, 127));
    expect(() => missionTask({ kind: "jam", center: geo(37, 127), radiusM: 1, polygon: many })).toThrow();
    // 빈 다각형이면 원
    expect(missionTask({ kind: "search", center: geo(37, 127), radiusM: 1500, polygon: [] }).summary).toContain("r1500");
  });

  it("미리보기: 그리는 중인 꼭짓점 번호와 3점부터 닫은 윤곽", () => {
    const two = missionOverlay({ kind: "jam", center: geo(37, 127), radiusM: 1, polygon: tri.slice(0, 2) }, "pending");
    expect(two.points.map((p) => p.label)).toEqual(["재밍 1", "2"]);
    expect(two.lines[0].positions).toHaveLength(2);
    expect(two.circles).toHaveLength(0);
    const three = missionOverlay({ kind: "search", center: geo(37, 127), radiusM: 1, polygon: tri }, "pending");
    expect(three.lines[0].positions).toHaveLength(4);
    expect(missionOverlay({ kind: "search", center: geo(37, 127), radiusM: 800 }, "pending").circles).toEqual([{ center: geo(37, 127), radiusM: 800, style: "pending" }]);
  });
});

describe("TC-UI-081 GCS 수신 정보 (IMP-UI-090)", () => {
  it("TrackShare는 출처 기체·트랙별 최근 것, 오래된 것은 뺀다", () => {
    const p = new GcsPicture();
    const ts = (src: string, obs: bigint, lat: number) =>
      rx(TrackShareSchema, { header: { source: src }, trackId: `${src}-t`, targetId: "tgt-1", position: geo(lat, 127), kind: EntityKind.GROUND_TARGET, observedTimeUs: obs }, src);
    p.onRx("k", ts("uav-001", 10_000_000n, 37.1));
    p.onRx("k", ts("uav-001", 5_000_000n, 37.0)); // 더 오래된 관측은 버린다
    p.onRx("k", ts("uav-002", 12_000_000n, 37.2));
    const t = p.sharedTracks(20_000_000n);
    expect(t.map((x) => [x.source, x.pos.latDeg])).toEqual([["uav-001", 37.1], ["uav-002", 37.2]]);
    expect(p.sharedTracks(41_000_000n).map((x) => x.source)).toEqual(["uav-002"]);
  });

  it("StoreLoadout 잔량, LeaderUpdate 리더(term 큰 것), PeerStatus 편대, 보고가 없으면 지정 편대", () => {
    const p = new GcsPicture();
    p.onRx("k", rx(StoreLoadoutSchema, { header: { source: "uav-001" }, stores: [{ id: "sta1", type: "agm_short", count: 1 }] }, "uav-001"));
    expect(p.loadout("uav-001")?.map((s) => [s.type, s.count])).toEqual([["agm_short", 1]]);
    expect(p.loadout("uav-002")).toBeUndefined();
    const fc = new C2Commander(GCS, UI, clock).formation("fmn-a", ["uav-002", "uav-001"], FormationShape.WEDGE, 100, "");
    p.onTx(fc.key, fc.envelope);
    expect(p.group("uav-002")).toEqual({ groupId: "fmn-a", leader: "uav-001", from: "command" }); // 리더 비면 사전순 첫 기체
    p.onRx("k", rx(LeaderUpdateSchema, { header: { source: "uav-002" }, groupId: "fmn-a", leader: "uav-002", term: 2n }, "uav-002"));
    p.onRx("k", rx(LeaderUpdateSchema, { header: { source: "uav-001" }, groupId: "fmn-a", leader: "uav-001", term: 1n }, "uav-001"));
    expect(p.group("uav-001")).toEqual({ groupId: "fmn-a", leader: "uav-002", from: "report" });
    p.onRx("k", rx(PeerStatusSchema, { header: { source: "uav-009" }, groupId: "fmn-b" }, "uav-009"));
    expect(p.group("uav-009")).toEqual({ groupId: "fmn-b", leader: "", from: "report" });
    expect(fromBinary(FormationCommandSchema, fc.envelope.payload).leader).toBe("");
  });
});

describe("TC-UI-082 교전 기준 배포 (IMP-UI-091)", () => {
  it("EngagementCriteria를 swarm/<gcs>/tx/mp로, L1 MP, 받을 기체를 dst로", () => {
    const c = new C2Commander(GCS, UI, clock);
    const out = c.engagementCriteria(
      { hostileSides: [Side.RED], requireApproval: true, weaponsFree: [{ center: geo(37, 127), radiusM: 5000 }], noStrike: [{ center: geo(37.1, 127.1), radiusM: 800 }] },
      ["uav-001", "uav-002"],
    );
    expect(out.key).toBe("swarm/gcs-01/tx/mp/EngagementCriteria");
    expect(out.envelope.iface).toBe(L1Interface.MP);
    expect(out.envelope.dst).toEqual(["uav-001", "uav-002"]);
    expect(out.envelope.publisher).toBe(UI);
    const m = fromBinary(EngagementCriteriaSchema, out.envelope.payload);
    expect(m.hostileSides).toEqual([Side.RED]);
    expect(m.requireApproval).toBe(true);
    expect(m.weaponsFree[0].shape.case).toBe("circle");
    expect(m.noStrike).toHaveLength(1);
    expect(out.summary).toContain("승인 필요");
    expect(() => c.engagementCriteria({ hostileSides: [], requireApproval: false, weaponsFree: [], noStrike: [] }, [])).toThrow();
  });
});
