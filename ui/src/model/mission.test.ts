// TC-UI-020~023: 지도 임무 명령 생성, 항로 편집 모델, 우클릭 입력 판정, 도형·진행 표시 (IMP-UI-035~038)
import { fromBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { TaskCommandSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";
import { C2Commander } from "./commands";
import type { WaypointSpec } from "./commands";
import { classifyRightClick, pickHandle } from "./mapInput";
import { draftOverlay, missionOverlay } from "./missionOverlay";
import * as R from "./routeDraft";
import { TaskLog } from "./taskLog";

const c = () => new C2Commander("gcs-01", "ui-ab", () => ({ simTimeUs: 1_000_000n, frame: 50n }));
const decode = (out: { envelope: { payload: Uint8Array } }) => fromBinary(TaskCommandSchema, out.envelope.payload);
const P = { latDeg: 36.5, lonDeg: 127.4, altM: 900 };

describe("TC-UI-020 임무 명령 생성", () => {
  it("선회 대기: 중심·반경·시간·방향, 0은 필드 없음", () => {
    const tc = decode(c().mission({ kind: "hold", center: P, radiusM: 800, durationS: 120, direction: TurnDirection.CCW }, ["uav-001", "uav-002"]));
    expect(tc.assignees).toEqual(["uav-001", "uav-002"]);
    expect(tc.task.case).toBe("hold");
    if (tc.task.case !== "hold") return;
    expect(tc.task.value.center).toMatchObject(P);
    expect(tc.task.value.radiusM).toBe(800);
    expect(tc.task.value.durationS).toBe(120);
    expect(tc.task.value.direction).toBe(TurnDirection.CCW);
    const open = decode(c().mission({ kind: "hold", center: P, radiusM: 800, durationS: 0, direction: TurnDirection.CW }, ["uav-001"]));
    if (open.task.case === "hold") expect(open.task.value.durationS).toBeUndefined();
  });

  it("타격: 적 엔티티면 target_id만, 지점이면 aim_point", () => {
    const byId = decode(c().mission({ kind: "strike", weapon: "fpv", targetId: "tgt-001", aimPoint: P }, ["uav-001"]));
    if (byId.task.case !== "strike") throw new Error("strike");
    expect(byId.task.value).toMatchObject({ targetId: "tgt-001", weaponType: "fpv" });
    expect(byId.task.value.aimPoint).toBeUndefined();
    const byPoint = decode(c().mission({ kind: "strike", weapon: "agm_short", aimPoint: P }, ["uav-001"]));
    if (byPoint.task.case !== "strike") throw new Error("strike");
    expect(byPoint.task.value.targetId).toBe("");
    expect(byPoint.task.value.aimPoint).toMatchObject(P);
    expect(() => c().mission({ kind: "strike", weapon: "fpv" }, ["uav-001"])).toThrow();
  });

  it("정찰: 원형 Area", () => {
    const tc = decode(c().mission({ kind: "search", center: P, radiusM: 1500 }, ["uav-001"]));
    if (tc.task.case !== "searchArea") throw new Error("searchArea");
    const sh = tc.task.value.area?.shape;
    expect(sh?.case).toBe("circle");
    if (sh?.case === "circle") expect(sh.value).toMatchObject({ radiusM: 1500, center: { latDeg: 36.5 } });
    expect(() => c().mission({ kind: "search", center: P, radiusM: 0 }, ["uav-001"])).toThrow();
  });

  it("항로: 항로점 속성·행위와 loop, 같은 task_id로 다시 보내면 ID가 유지된다", () => {
    const cm = c();
    const wps: WaypointSpec[] = [
      { position: P, speedMps: 30, action: { kind: "none" } },
      { position: { ...P, altM: 1200 }, action: { kind: "loiter", durationS: 90, radiusM: 500, direction: TurnDirection.CW } },
      { position: P, action: { kind: "recon", radiusM: 1000 } },
    ];
    const first = cm.mission({ kind: "route", waypoints: wps, loop: true }, ["uav-001"]);
    const tc = decode(first);
    if (tc.task.case !== "route") throw new Error("route");
    expect(tc.task.value.loop).toBe(true);
    const w = tc.task.value.waypoints;
    expect(w).toHaveLength(3);
    expect(w[0].speedMps).toBe(30);
    expect(w[0].action.case).toBeUndefined();
    expect(w[1].position?.altM).toBe(1200);
    expect(w[1].speedMps).toBeUndefined();
    expect(w[1].action).toMatchObject({ case: "loiter", value: { durationS: 90, radiusM: 500, direction: TurnDirection.CW } });
    expect(w[2].action).toMatchObject({ case: "recon", value: { radiusM: 1000 } });
    const again = cm.mission({ kind: "route", waypoints: wps.slice(0, 2), loop: false }, ["uav-001"], first.taskId);
    expect(again.taskId).toBe(first.taskId);
    expect(decode(again).taskId).toBe(first.taskId);
    expect(() => cm.mission({ kind: "route", waypoints: [], loop: false }, ["uav-001"])).toThrow();
  });
});

describe("TC-UI-021 항로점 편집 모델", () => {
  const at = (n: number) => ({ latDeg: 36 + n / 100, lonDeg: 127 + n / 100 });
  const base = () => [1, 2, 3].reduce((d, n) => R.addWaypoint(d, at(n), { altM: 1000, speedMps: 25 }), R.emptyRoute());

  it("추가: 순서대로 쌓이고 고도·속력은 직전 항로점을 따른다", () => {
    let d = R.addWaypoint(R.emptyRoute(), at(1), { altM: 1000, speedMps: 25 });
    d = R.setAltitude(d, 0, 1500);
    d = R.addWaypoint(d, at(2), { altM: 1000 });
    expect(d.waypoints.map((w) => w.position.latDeg)).toEqual([36.01, 36.02]);
    expect(d.waypoints[1].position.altM).toBe(1500);
    expect(d.waypoints[1].speedMps).toBe(25);
  });

  it("이동은 고도를 유지하고, 속성·행위를 바꾼다", () => {
    let d = R.setAltitude(base(), 1, 1800);
    d = R.moveWaypoint(d, 1, { latDeg: 37, lonDeg: 128 });
    expect(d.waypoints[1].position).toEqual({ latDeg: 37, lonDeg: 128, altM: 1800 });
    d = R.setSpeed(d, 1, 0);
    expect(d.waypoints[1].speedMps).toBeUndefined();
    d = R.setAction(d, 2, { kind: "recon", radiusM: 700 });
    expect(R.routeSpec(d).waypoints[2].action).toEqual({ kind: "recon", radiusM: 700 });
  });

  it("삭제와 순서 바꾸기, 범위 밖은 오류, 원본은 바뀌지 않는다", () => {
    const d = base();
    const del = R.removeWaypoint(d, 0);
    expect(del.waypoints.map((w) => w.position.latDeg)).toEqual([36.02, 36.03]);
    expect(d.waypoints).toHaveLength(3);
    expect(R.reorderWaypoint(d, 2, 0).waypoints.map((w) => w.position.latDeg)).toEqual([36.03, 36.01, 36.02]);
    expect(R.reorderWaypoint(d, 0, 5)).toBe(d);
    expect(() => R.removeWaypoint(d, 9)).toThrow(RangeError);
  });

  it("보낸 항로를 다시 편집한다", () => {
    const d = R.draftFromSpec(R.routeSpec({ ...base(), loop: true }), "ui-ab-t3", ["uav-001"]);
    expect(d).toMatchObject({ taskId: "ui-ab-t3", loop: true, assignees: ["uav-001"] });
    expect(d.waypoints).toHaveLength(3);
  });
});

describe("TC-UI-022 우클릭 입력 판정", () => {
  const rect = { x0: 10, y0: 10, x1: 11, y1: 11 };
  const drag = { x0: 10, y0: 10, x1: 80, y1: 80 };
  const pt = { latDeg: 36, lonDeg: 127, heightM: 100 };
  const ctx = { hasTargets: true, entityId: "tgt-001" };

  it("선택 기체가 있으면 임무 메뉴, 커서 아래 엔티티를 함께 넘긴다", () => {
    expect(classifyRightClick(rect, { ctrlKey: false }, pt, ctx)).toEqual({ kind: "menu", point: pt, entityId: "tgt-001" });
  });
  it("선택 기체가 없으면 아무 일도 없다", () => {
    expect(classifyRightClick(rect, { ctrlKey: false }, pt, { hasTargets: false, entityId: null }).kind).toBe("none");
  });
  it("Ctrl(Cmd)+우클릭은 항로점 추가, 선택이 없어도 된다", () => {
    expect(classifyRightClick(rect, { ctrlKey: true }, pt, { hasTargets: false, entityId: null })).toEqual({ kind: "waypoint", point: pt });
    expect(classifyRightClick(rect, { ctrlKey: false, metaKey: true }, pt, ctx).kind).toBe("waypoint");
  });
  it("끌었거나 지면을 못 찾으면 무시한다", () => {
    expect(classifyRightClick(drag, { ctrlKey: true }, pt, ctx).kind).toBe("none");
    expect(classifyRightClick(rect, { ctrlKey: false }, null, ctx).kind).toBe("none");
  });
  it("손잡이 집기: 반경 안 가장 가까운 것", () => {
    const hs = [{ x: 100, y: 100 }, null, { x: 106, y: 100 }];
    expect(pickHandle(hs, 105, 100)).toBe(2);
    expect(pickHandle(hs, 300, 300)).toBeNull();
  });
});

describe("TC-UI-023 지도 도형·진행 표시", () => {
  it("편집 중 항로: 번호 손잡이, 선, 행위 원", () => {
    let d = [1, 2, 3].reduce((x, n) => R.addWaypoint(x, { latDeg: 36 + n / 100, lonDeg: 127 }, { altM: 1000 }), R.emptyRoute());
    d = R.setAction(d, 1, { kind: "loiter", durationS: 60, radiusM: 700, direction: TurnDirection.CW });
    const o = draftOverlay(d);
    expect(o.points.map((p) => p.label)).toEqual(["1", "2", "3"]);
    expect(o.points.map((p) => p.handle)).toEqual([0, 1, 2]);
    expect(o.lines[0].positions).toHaveLength(3);
    expect(o.circles).toMatchObject([{ radiusM: 700 }]);
    expect(draftOverlay({ ...d, loop: true }).lines[0].positions).toHaveLength(4);
  });

  it("임무 도형: 정찰 원, 조준점 없는 타격은 그리지 않는다", () => {
    expect(missionOverlay({ kind: "search", center: P, radiusM: 1200 }, "sent").circles).toMatchObject([{ radiusM: 1200 }]);
    expect(missionOverlay({ kind: "strike", weapon: "fpv", targetId: "t" }, "sent").points).toHaveLength(0);
  });

  it("activeMissions: 기체별 최근 임무, 끝난 임무·전송 실패는 뺀다", () => {
    const cm = c();
    const log = new TaskLog();
    const hold = cm.mission({ kind: "hold", center: P, direction: TurnDirection.CW }, ["uav-001"]);
    const search = cm.mission({ kind: "search", center: P, radiusM: 900 }, ["uav-001", "uav-002"]);
    log.sent(hold);
    log.sent(search);
    expect(log.activeMissions().map((e) => e.id)).toEqual([search.taskId]);
    const e = log.get(search.taskId!)!;
    e.reports.set("uav-001", { state: CommandState.COMPLETED, progress: 1, reason: "", simTimeUs: 0n });
    expect(log.activeMissions()).toHaveLength(1);
    e.reports.set("uav-002", { state: CommandState.COMPLETED, progress: 1, reason: "", simTimeUs: 0n });
    expect(log.activeMissions().map((x) => x.id)).toEqual([hold.taskId].filter(() => false));
    e.error = "x";
    expect(log.activeMissions().map((x) => x.id)).toEqual([hold.taskId]);
  });
});
