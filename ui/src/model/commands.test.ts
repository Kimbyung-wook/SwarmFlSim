// TC-UI-018: C2 명령 생성(TaskCommand·FormationCommand·GroupAssignment → LinkEnvelope), 그룹, 명령 기록, 목 소스 응답
// (IMP-UI-025~027, IMP-UI-029)
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { FormationCommandSchema, FormationShape, GroupAssignmentSchema, TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { MockSource } from "../data/mockSource";
import { C2Commander, c2TxKey } from "./commands";
import { GroupStore, groupId, slotFromKey } from "./groups";
import { TaskLog } from "./taskLog";

const clock = () => ({ simTimeUs: 12_000_000n, frame: 600n });

describe("C2Commander", () => {
  it("MoveTo TaskCommand를 swarm/<gcs>/tx/c2/TaskCommand LinkEnvelope로 싼다", () => {
    const c = new C2Commander("gcs-01", "ui-ab", clock);
    const out = c.task("moveTo", ["uav-001", "uav-002"], { latDeg: 36.5, lonDeg: 127.4, altM: 800, speedMps: 30 });
    expect(out.key).toBe("swarm/gcs-01/tx/c2/TaskCommand");
    expect(out.key).toBe(c2TxKey("gcs-01", "TaskCommand"));
    expect(out.taskId).toBe("ui-ab-t1");
    const env = out.envelope;
    expect(env.dst).toEqual(["uav-001", "uav-002"]);
    expect(env.iface).toBe(L1Interface.C2);
    expect(env.msgType).toBe("swarm.v1.TaskCommand");
    expect(env.header).toMatchObject({ source: "gcs-01", seq: 1, simTimeUs: 12_000_000n, frame: 600n, correlationId: "ui-ab-t1" });
    const tc = fromBinary(TaskCommandSchema, env.payload);
    expect(tc.taskId).toBe("ui-ab-t1");
    expect(tc.assignees).toEqual(["uav-001", "uav-002"]);
    expect(tc.header?.seq).toBe(1);
    expect(tc.task.case).toBe("moveTo");
    if (tc.task.case === "moveTo") {
      expect(tc.task.value.destination).toMatchObject({ latDeg: 36.5, lonDeg: 127.4, altM: 800 });
      expect(tc.task.value.speedMps).toBe(30);
    }
    // 봉투 직렬화 왕복
    expect(fromBinary(LinkEnvelopeSchema, toBinary(LinkEnvelopeSchema, env)).payload).toEqual(env.payload);
  });

  it("Hold·RTB·취소, 키별 seq와 task_id 증가, 빈 대상 거부", () => {
    const c = new C2Commander("gcs-01", "ui-ab", clock);
    const h = c.task("hold", ["uav-001"]);
    const r = c.task("returnToBase", ["uav-001"]);
    expect(fromBinary(TaskCommandSchema, h.envelope.payload).task.case).toBe("hold");
    expect(fromBinary(TaskCommandSchema, r.envelope.payload).task.case).toBe("returnToBase");
    expect([h.envelope.header?.seq, r.envelope.header?.seq]).toEqual([1, 2]);
    expect([h.taskId, r.taskId]).toEqual(["ui-ab-t1", "ui-ab-t2"]);
    const x = c.cancel("ui-ab-t1", ["uav-001"]);
    expect(fromBinary(TaskCommandSchema, x.envelope.payload)).toMatchObject({ taskId: "ui-ab-t1", cancel: true });
    expect(() => c.task("hold", [])).toThrow();
    expect(() => c.task("moveTo", ["uav-001"])).toThrow();
  });

  it("FormationCommand와 GroupAssignment(이전 구성원에게도 전달)", () => {
    const c = new C2Commander("gcs-01", "ui-ab", clock);
    const f = c.formation("grp-1", ["uav-003", "uav-001", "uav-002"], FormationShape.WEDGE, 120);
    expect(f.key).toBe("swarm/gcs-01/tx/c2/FormationCommand");
    const fc = fromBinary(FormationCommandSchema, f.envelope.payload);
    expect(fc).toMatchObject({ groupId: "grp-1", leader: "uav-003", shape: FormationShape.WEDGE, spacingM: 120 });
    expect(fc.members).toEqual(["uav-003", "uav-001", "uav-002"]);
    expect(f.envelope.header?.seq).toBe(1);

    const g = c.group("grp-2", ["uav-004"], ["uav-004", "uav-005"]);
    expect(g.key).toBe("swarm/gcs-01/tx/c2/GroupAssignment");
    expect(g.envelope.dst).toEqual(["uav-004", "uav-005"]);
    const ga = fromBinary(GroupAssignmentSchema, g.envelope.payload);
    expect(ga).toMatchObject({ groupId: "grp-2", members: ["uav-004"] });
  });
});

describe("GroupStore", () => {
  it("지정·호출, 한 기체는 한 그룹에만, 빈 지정은 해제", () => {
    const g = new GroupStore();
    expect(slotFromKey("3")).toBe("3");
    expect(slotFromKey("a")).toBeNull();
    expect(groupId("0")).toBe("grp-0");
    g.assign("1", ["uav-001", "uav-002"]);
    const ch = g.assign("2", ["uav-002", "uav-003"]);
    expect(ch).toEqual([
      { slot: "1", members: ["uav-001"], previous: ["uav-001", "uav-002"] },
      { slot: "2", members: ["uav-002", "uav-003"], previous: [] },
    ]);
    expect(g.slotOf("uav-002")).toBe("2");
    expect(g.recall("2", new Set(["uav-003"]))).toEqual(["uav-003"]);
    g.assign("1", []);
    expect(g.entries().map(([s]) => s)).toEqual(["2"]);
  });
});

describe("TaskLog", () => {
  it("rx TaskStatus를 task_id로 명령에 붙이고 최근 수신을 남긴다", () => {
    const log = new TaskLog(2, 3);
    const c = new C2Commander("gcs-01", "ui-ab", clock);
    const t1 = c.task("hold", ["uav-001", "uav-002"]);
    log.sent(t1);
    const st = create(TaskStatusSchema, {
      header: { source: "uav-002", simTimeUs: 5n },
      taskId: t1.taskId,
      state: CommandState.EXECUTING,
      progress: 0.5,
    });
    const env = create(LinkEnvelopeSchema, {
      header: { source: "uav-002" },
      msgType: "swarm.v1.TaskStatus",
      payload: toBinary(TaskStatusSchema, st),
    });
    log.received("swarm/gcs-01/rx/c2/TaskStatus", env);
    expect(log.get(t1.taskId!)!.reports.get("uav-002")).toMatchObject({ state: CommandState.EXECUTING, progress: 0.5, simTimeUs: 5n });
    log.received("swarm/gcs-01/rx/p2p/PeerStatus", create(LinkEnvelopeSchema, { header: { source: "uav-009" }, msgType: "swarm.v1.PeerStatus" }));
    expect(log.recentRx.map((r) => r.source)).toEqual(["uav-009", "uav-002"]);

    log.sent(c.task("hold", ["uav-001"]), "브리지에 연결되어 있지 않다");
    log.sent(c.task("hold", ["uav-001"]));
    expect(log.list().map((t) => t.id)).toEqual(["ui-ab-t3", "ui-ab-t2"]);
    // 편대·그룹은 같은 group_id여도 따로 남는다
    const log2 = new TaskLog();
    log2.sent(c.group("grp-1", ["uav-001"]));
    log2.sent(c.formation("grp-1", ["uav-001", "uav-002"], FormationShape.LINE, 100));
    expect(log2.list().map((t) => t.id)).toEqual(["FormationCommand#1", "GroupAssignment#1"]);
    expect(log.list()[1].error).not.toBe("");
  });
});

describe("MockSource C2", () => {
  it("TaskCommand에 대상마다 ACCEPTED TaskStatus를 rx로 돌려준다", () => {
    const src = new MockSource({ autoStart: false });
    const log = new TaskLog();
    src.subscribe({ rx: (k, env) => log.received(k, env) });
    const out = new C2Commander(src.gcs, "ui-ab", clock).task("hold", ["uav-001", "uav-002"]);
    log.sent(out);
    src.sendC2(out);
    const e = log.get(out.taskId!)!;
    expect([...e.reports.keys()]).toEqual(["uav-001", "uav-002"]);
    expect(e.reports.get("uav-001")!.state).toBe(CommandState.ACCEPTED);
  });
});
