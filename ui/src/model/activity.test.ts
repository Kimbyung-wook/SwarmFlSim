// TC-UI-069: 기체별 현재 행동 — GCS가 아는 출처만으로 작업·목표점·선회원·표적·귀환점을 정한다 (IMP-UI-080)
// TC-UI-071: 표시 범위(전체·선택·끔)와 외삽 배속, 보고 위치 외삽 (IMP-UI-080, IMP-UI-083)
import { create, toBinary } from "@bufbuild/protobuf";
import type { DescMessage, MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { MissionPlanSchema, RoutePlanSchema } from "../gen/swarm/v1/mp_pb";
import { TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import { ScenarioSchema, SimRunState, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { NavigationReportSchema } from "../gen/swarm/v1/vi_pb";
import { ActivityStore, MA_DEFAULT_HOLD_RADIUS_M, MAX_EXTRAPOLATE_S } from "./activity";
import { activityFilter, simRate } from "./activityMode";
import { distanceBearing } from "./racetrack";

const GCS = "gcs-01";

function env<D extends DescMessage>(schema: D, init: MessageInitShape<D>, source: string, simUs = 0n) {
  const msg = create(schema, init);
  return create(LinkEnvelopeSchema, {
    header: { source, simTimeUs: simUs },
    dst: [GCS],
    msgType: schema.typeName,
    payload: toBinary(schema, msg),
    rxTimeUs: simUs,
  });
}

const geo = (latDeg: number, lonDeg = 127, altM = 1000) => ({ latDeg, lonDeg, altM });
type TaskInit = MessageInitShape<typeof TaskCommandSchema>;

function tx(s: ActivityStore, t: TaskInit) {
  s.onTx(`swarm/${GCS}/tx/c2/TaskCommand`, env(TaskCommandSchema, t, GCS));
}
function status(s: ActivityStore, id: string, taskId: string, state: CommandState, progress = 0) {
  s.onRx(`swarm/${GCS}/rx/c2/TaskStatus`, env(TaskStatusSchema, { header: { source: id }, taskId, state, progress }, id));
}
function nav(s: ActivityStore, id: string, lat: number, simUs = 0n, vn = 0, wallMs = 0) {
  s.onRx(
    `swarm/${GCS}/rx/vi/NavigationReport`,
    env(NavigationReportSchema, { header: { source: id, simTimeUs: simUs }, kinematics: { position: geo(lat), velocityNedMps: { x: vn, y: 0, z: 0 } } }, id, simUs),
    wallMs,
  );
}

describe("ActivityStore 작업 판단 (TC-UI-069)", () => {
  it("move_to: 수행 보고 뒤에만 목적지 o와 대시선 끝을 낸다. 끝 상태면 지운다", () => {
    const s = new ActivityStore();
    tx(s, { taskId: "t1", assignees: ["uav-001"], task: { case: "moveTo", value: { destination: geo(37.6) } } });
    expect(s.shapeOf("uav-001")).toBeNull(); // 보냈지만 기체가 아직 받았다고 하지 않았다
    status(s, "uav-001", "t1", CommandState.ACCEPTED);
    const a = s.shapeOf("uav-001")!;
    expect(a.kind).toBe("moveTo");
    expect(a.lead).toEqual(geo(37.6));
    expect(a.marks).toEqual([{ pos: geo(37.6), glyph: "o" }]);
    status(s, "uav-001", "t1", CommandState.EXECUTING, 0.3);
    expect(s.shapeOf("uav-001")!.kind).toBe("moveTo");
    for (const st of [CommandState.COMPLETED, CommandState.CANCELLED, CommandState.FAILED, CommandState.REJECTED]) {
      status(s, "uav-001", "t1", CommandState.EXECUTING);
      status(s, "uav-001", "t1", st);
      expect(s.shapeOf("uav-001")).toBeNull();
    }
  });

  it("다른 작업의 거부는 수행 중 작업을 지우지 않는다. 새 작업이 수락되면 그것을 그린다", () => {
    const s = new ActivityStore();
    tx(s, { taskId: "a", assignees: ["uav-001"], task: { case: "moveTo", value: { destination: geo(37.6) } } });
    tx(s, { taskId: "b", assignees: ["uav-001"], task: { case: "moveTo", value: { destination: geo(37.7) } } });
    status(s, "uav-001", "a", CommandState.EXECUTING);
    status(s, "uav-001", "b", CommandState.REJECTED);
    expect(s.shapeOf("uav-001")!.taskId).toBe("a");
    status(s, "uav-001", "b", CommandState.ACCEPTED);
    expect(s.shapeOf("uav-001")!.taskId).toBe("b");
    status(s, "uav-001", "a", CommandState.EXECUTING, 0.5); // 같은 작업의 진행 보고는 순서를 바꾸지 않는다
    expect(s.shapeOf("uav-001")!.taskId).toBe("b");
  });

  it("작업 내용을 모르면(편대 등) 그리지 않는다. 취소 명령은 내용을 덮지 않는다", () => {
    const s = new ActivityStore();
    status(s, "uav-001", "unknown", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")).toBeNull();
    tx(s, { taskId: "t1", assignees: ["uav-001"], task: { case: "moveTo", value: { destination: geo(37.6) } } });
    tx(s, { taskId: "t1", assignees: ["uav-001"], cancel: true });
    status(s, "uav-001", "t1", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")!.lead).toEqual(geo(37.6));
  });

  it("hold: 중심이 없으면 작업 시작 때 보고 위치, 반경이 없으면 MA 변수 → MA 기본값. 옅은 원과 중심 o", () => {
    const radius: Record<string, number> = { "uav-002": 450 };
    const s = new ActivityStore((id) => radius[id]);
    tx(s, { taskId: "h", assignees: ["uav-001", "uav-002"], task: { case: "hold", value: {} } });
    nav(s, "uav-001", 37.5);
    nav(s, "uav-002", 37.4);
    status(s, "uav-001", "h", CommandState.EXECUTING);
    status(s, "uav-002", "h", CommandState.EXECUTING);
    nav(s, "uav-001", 37.55); // 작업 시작 뒤 움직여도 중심은 그대로
    const a = s.shapeOf("uav-001")!;
    expect(a.kind).toBe("hold");
    expect(a.circles).toEqual([{ center: geo(37.5), radiusM: MA_DEFAULT_HOLD_RADIUS_M }]);
    expect(a.marks).toEqual([{ pos: geo(37.5), glyph: "o" }]);
    expect(s.shapeOf("uav-002")!.circles[0].radiusM).toBe(450);

    tx(s, { taskId: "h2", assignees: ["uav-001"], task: { case: "hold", value: { center: geo(37.3, 127.1, 0), radiusM: 800 } } });
    status(s, "uav-001", "h2", CommandState.ACCEPTED);
    const b = s.shapeOf("uav-001")!;
    // 고도 0은 현재 고도 유지(마지막 보고 고도)
    expect(b.circles).toEqual([{ center: geo(37.3, 127.1, 1000), radiusM: 800 }]);
  });

  it("hold 레이스트랙은 원 대신 폐곡선", () => {
    const s = new ActivityStore();
    tx(s, { taskId: "r", assignees: ["uav-001"], task: { case: "hold", value: { center: geo(37.3), radiusM: 500, racetrack: { legLengthM: 2000, axisHeadingDeg: 90 } } } });
    status(s, "uav-001", "r", CommandState.EXECUTING);
    const a = s.shapeOf("uav-001")!;
    expect(a.circles).toEqual([]);
    expect(a.paths).toHaveLength(1);
    expect(a.paths[0][0]).toEqual(a.paths[0][a.paths[0].length - 1]);
  });

  it("return_to_base: 귀환점은 그 기체가 처음 보고한 위치", () => {
    const s = new ActivityStore();
    nav(s, "uav-001", 37.1);
    nav(s, "uav-001", 37.2);
    tx(s, { taskId: "rtb", assignees: ["uav-001"], task: { case: "returnToBase", value: {} } });
    status(s, "uav-001", "rtb", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")!.lead).toEqual(geo(37.1));
    // 보고가 없으면 귀환점을 모른다
    tx(s, { taskId: "rtb2", assignees: ["uav-009"], task: { case: "returnToBase", value: {} } });
    status(s, "uav-009", "rtb2", CommandState.EXECUTING);
    expect(s.shapeOf("uav-009")).toBeNull();
  });

  it("strike: aim_point가 있으면 거기, 없으면 GCS가 받은 TrackShare의 최근 위치에 x", () => {
    const s = new ActivityStore();
    tx(s, { taskId: "s1", assignees: ["uav-001"], task: { case: "strike", value: { targetId: "tgt-001", weaponType: "fpv" } } });
    status(s, "uav-001", "s1", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")).toBeNull(); // 표적 위치를 모른다 (truth는 쓰지 않는다)
    const track = (lat: number, t: bigint) =>
      s.onRx(`swarm/${GCS}/rx/p2p/TrackShare`, env(TrackShareSchema, { targetId: "tgt-001", position: geo(lat, 127, 50), observedTimeUs: t }, "uav-003"));
    track(37.8, 2n);
    track(37.7, 1n); // 더 오래된 관측은 무시
    const a = s.shapeOf("uav-001")!;
    expect(a.kind).toBe("strike");
    expect(a.marks).toEqual([{ pos: geo(37.8, 127, 50), glyph: "x" }]);
    expect(a.lead).toEqual(geo(37.8, 127, 50));

    tx(s, { taskId: "s2", assignees: ["uav-002"], task: { case: "strike", value: { targetId: "x", aimPoint: geo(37.9, 127, 0), weaponType: "agm_short" } } });
    status(s, "uav-002", "s2", CommandState.ACCEPTED);
    expect(s.shapeOf("uav-002")!.marks[0]).toEqual({ pos: geo(37.9, 127, 0), glyph: "x" });
  });

  it("route: progress로 다음 항로점을 추정하고 남은 점 o, 행위 원, loop면 닫는다", () => {
    const s = new ActivityStore();
    const wps = [37.1, 37.2, 37.3, 37.4].map((lat, i) => ({
      position: geo(lat),
      action: i === 2 ? { case: "loiter" as const, value: { durationS: 30 } } : { case: undefined },
    }));
    tx(s, { taskId: "r", assignees: ["uav-001"], task: { case: "route", value: { waypoints: wps, loop: false } } });
    status(s, "uav-001", "r", CommandState.EXECUTING, 0.5); // 4점 중 2점을 마쳤다
    const a = s.shapeOf("uav-001")!;
    expect(a.estimated).toBe(true);
    expect(a.lead).toEqual(geo(37.3));
    expect(a.marks.map((m) => m.pos.latDeg)).toEqual([37.3, 37.4]);
    expect(a.circles).toEqual([{ center: geo(37.3), radiusM: MA_DEFAULT_HOLD_RADIUS_M }]);
    expect(a.label).toBe("항로 3/4");

    tx(s, { taskId: "L", assignees: ["uav-002"], task: { case: "route", value: { waypoints: wps, loop: true } } });
    status(s, "uav-002", "L", CommandState.EXECUTING, 0.75);
    const b = s.shapeOf("uav-002")!;
    expect(b.marks.map((m) => m.pos.latDeg)).toEqual([37.4, 37.1, 37.2, 37.3]);
    expect(b.paths[0].map((p) => p.latDeg)).toEqual([37.4, 37.1, 37.2, 37.3, 37.4]);
  });

  it("search_area: 영역 윤곽과 중심 o", () => {
    const s = new ActivityStore();
    tx(s, { taskId: "sa", assignees: ["uav-001"], task: { case: "searchArea", value: { area: { shape: { case: "circle", value: { center: geo(37.5), radiusM: 1000 } } } } } });
    status(s, "uav-001", "sa", CommandState.EXECUTING);
    const a = s.shapeOf("uav-001")!;
    expect(a.kind).toBe("search");
    const ring = a.paths[0];
    expect(ring.length).toBe(49);
    expect(distanceBearing(geo(37.5), ring[10]).distM).toBeCloseTo(1000, -1);
  });

  it("MissionPlan(tx/mp)과 시나리오 mission_plan의 작업도 내용으로 쓴다. 다른 시나리오면 지난 실행을 지운다", () => {
    const s = new ActivityStore();
    s.onTx(`swarm/${GCS}/tx/mp/MissionPlan`, env(MissionPlanSchema, { planId: "p", tasks: [{ taskId: "gw", assignees: ["uav-001"], task: { case: "moveTo", value: { destination: geo(37.2) } } }] }, GCS));
    status(s, "uav-001", "gw", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")!.lead).toEqual(geo(37.2));

    s.onScenario(create(ScenarioSchema, { name: "a", missionPlan: { planId: "p0", tasks: [{ taskId: "sc", assignees: ["uav-002"], task: { case: "moveTo", value: { destination: geo(37.3) } } }] } }));
    s.onScenario(create(ScenarioSchema, { name: "a", missionPlan: { planId: "p0" } })); // 같은 시나리오 재발행
    status(s, "uav-002", "sc", CommandState.ACCEPTED);
    expect(s.shapeOf("uav-002")!.lead).toEqual(geo(37.3));
    s.onScenario(create(ScenarioSchema, { name: "b" }));
    expect(s.entityIds()).toEqual([]);
  });

  it("단독 RoutePlan은 상태 보고가 없어 받는 즉시 그리고, 도달 반경으로 다음 점을 추정한다. 같은 ID의 작업이 있으면 따로 보지 않는다", () => {
    const s = new ActivityStore();
    const rp = (routeId: string) =>
      env(RoutePlanSchema, { routeId, entityId: "uav-001", waypoints: [{ position: geo(37.1) }, { position: geo(37.2) }] }, GCS);
    nav(s, "uav-001", 37.0);
    s.onTx(`swarm/${GCS}/tx/mp/RoutePlan`, rp("q"));
    expect(s.shapeOf("uav-001")!.marks.map((m) => m.pos.latDeg)).toEqual([37.1, 37.2]);
    nav(s, "uav-001", 37.1005); // 첫 점 도달 반경 안
    expect(s.shapeOf("uav-001")!.lead).toEqual(geo(37.2));
    nav(s, "uav-001", 37.2);
    expect(s.shapeOf("uav-001")).toBeNull();

    tx(s, { taskId: "same", assignees: ["uav-001"], task: { case: "moveTo", value: { destination: geo(37.9) } } });
    s.onTx(`swarm/${GCS}/tx/mp/RoutePlan`, rp("same"));
    expect(s.shapeOf("uav-001")).toBeNull();
  });

  it("Reset(모의 시각 되감기)이면 보고·귀환점을 지운다", () => {
    const s = new ActivityStore();
    s.onSimStatus(60_000_000n, 1);
    nav(s, "uav-001", 37.1);
    tx(s, { taskId: "rtb", assignees: ["uav-001"], task: { case: "returnToBase", value: {} } });
    status(s, "uav-001", "rtb", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")).not.toBeNull();
    s.onSimStatus(0n, 0);
    expect(s.shapeOf("uav-001")).toBeNull();
    nav(s, "uav-001", 37.4);
    status(s, "uav-001", "rtb", CommandState.EXECUTING);
    expect(s.shapeOf("uav-001")!.lead).toEqual(geo(37.4)); // 작업 내용은 남고 귀환점은 새로 정한다
  });
});

describe("표시 위치 외삽·표시 범위 (TC-UI-071)", () => {
  it("보고 시각부터 지금 모의 시각까지 속도로 외삽하고, 멈춤이면 더 나가지 않으며, 최대 외삽 시간을 넘지 않는다", () => {
    const s = new ActivityStore();
    s.onSimStatus(10_000_000n, 1, 1000);
    nav(s, "uav-001", 37.0, 10_000_000n, 50);
    const north = (wall: number) => distanceBearing(geo(37.0), s.positionAt("uav-001", wall)!).distM;
    expect(north(1000)).toBeCloseTo(0, 3);
    expect(north(2000)).toBeCloseTo(50, 0); // 1 s × 50 m/s
    s.onSimStatus(11_000_000n, 0, 2000); // 일시정지
    expect(north(9000)).toBeCloseTo(50, 0);
    s.onSimStatus(11_000_000n, 2, 9000); // 2배속
    expect(north(30_000)).toBeCloseTo(50 * MAX_EXTRAPOLATE_S, 0);
    expect(s.positionAt("uav-404", 0)).toBeNull();
  });

  it("모의 시각을 모르면 받은 뒤 흐른 벽시계로 외삽한다", () => {
    const s = new ActivityStore();
    nav(s, "uav-001", 37.0, 0n, 20, 5000);
    expect(distanceBearing(geo(37.0), s.positionAt("uav-001", 6000)!).distM).toBeCloseTo(20, 0);
  });

  it("표시 범위: 전체(null)·선택 기체만·끔, 배속은 실행 중에만", () => {
    expect(activityFilter("all", ["uav-001"])).toBeNull();
    expect([...(activityFilter("selected", ["uav-001"]) as Set<string>)]).toEqual(["uav-001"]);
    expect(activityFilter("off", [])).toBe("off");
    const st = (state: SimRunState, rateActual: number, rateTarget = 1) => create(SimStatusSchema, { state, rateActual, rateTarget });
    expect(simRate(null)).toBe(0);
    expect(simRate(st(SimRunState.PAUSED, 2))).toBe(0);
    expect(simRate(st(SimRunState.RUNNING, 2))).toBe(2);
    expect(simRate(st(SimRunState.RUNNING, 0, 5))).toBe(5);

    const s = new ActivityStore();
    for (const id of ["uav-001", "uav-002"]) {
      tx(s, { taskId: `m-${id}`, assignees: [id], task: { case: "moveTo", value: { destination: geo(37.6) } } });
      status(s, id, `m-${id}`, CommandState.EXECUTING);
    }
    expect(s.shapes().map((x) => x.entityId)).toEqual(["uav-001", "uav-002"]);
    expect(s.shapes(new Set(["uav-002"])).map((x) => x.entityId)).toEqual(["uav-002"]);
  });
});
