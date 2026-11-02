// TC-UI-024: 목 소스 임무 비행 — 이동 도착, 선회 유지, 항로 순서 비행, 정찰 원, 타격 접근, 진행 보고 (IMP-UI-041)
import { create, fromBinary, toBinary } from "@bufbuild/protobuf";
import type { MessageInitShape } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import type { TaskCommand } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { EntityKind } from "../gen/swarm/v1/entity_pb";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";
import { toEntityView } from "../model/entityView";
import { MOCK_ORIGIN, MockScenario, geodeticToNed } from "./mockScenario";

const geo = (n: number, e: number, altM = 1500) => ({
  latDeg: MOCK_ORIGIN.lat + n / 6378137 / (Math.PI / 180),
  lonDeg: MOCK_ORIGIN.lon + e / (6378137 * Math.cos((MOCK_ORIGIN.lat * Math.PI) / 180)) / (Math.PI / 180),
  altM,
});

function cmd(init: MessageInitShape<typeof TaskCommandSchema>, assignees = ["uav-001"]): TaskCommand {
  return create(TaskCommandSchema, { taskId: "t1", assignees, ...init });
}

function run(sc: MockScenario, from: number, to: number, hz = 10) {
  const reports = [];
  for (let t = from; t <= to + 1e-9; t += 1 / hz) {
    sc.frameAt(BigInt(Math.round(t * 50)), 50);
    reports.push(...sc.takeReports());
  }
  return reports;
}

const posOf = (sc: MockScenario, id: string, t: number) => {
  const a = sc.actors.find((x) => x.id === id)!;
  const v = toEntityView(sc.entityAt(a, t));
  return { ...geodeticToNed({ latDeg: v.lat, lonDeg: v.lon }), alt: v.alt, v };
};
const dist = (a: { n: number; e: number }, b: { n: number; e: number }) => Math.hypot(a.n - b.n, a.e - b.e);

describe("TC-UI-024 목 소스 임무 비행", () => {
  it("이동: 목적지 근처에 도착한 뒤 그 주변에서 선회하고, COMPLETED를 한 번 보고한다", () => {
    const sc = new MockScenario();
    sc.frameAt(0n, 50);
    const dest = { n: 8000, e: -4000 };
    sc.command(cmd({ task: { case: "moveTo", value: { destination: geo(dest.n, dest.e, 2000) } } }), 0);
    expect(sc.isGuided("uav-001")).toBe(true);
    const reports = run(sc, 0, 300);
    expect(reports.filter((r) => r.state === CommandState.COMPLETED)).toHaveLength(1);
    const p = posOf(sc, "uav-001", 300);
    expect(dist(p, dest)).toBeLessThan(1500);
    expect(Math.abs(p.alt - 2000)).toBeLessThan(60);
  });

  it("명령 받지 않은 기체는 해석 궤도 그대로", () => {
    const a = new MockScenario();
    const b = new MockScenario();
    a.command(cmd({ task: { case: "moveTo", value: { destination: geo(0, 0) } } }), 0);
    run(a, 0, 20);
    const before = posOf(b, "uav-002", 20);
    const after = posOf(a, "uav-002", 20);
    expect(after.n).toBeCloseTo(before.n, 6);
  });

  it("선회 대기: 중심 둘레 반경 근처를 유지한다", () => {
    const sc = new MockScenario();
    sc.frameAt(0n, 50);
    const c = { n: 9000, e: -5000 };
    sc.command(cmd({ task: { case: "hold", value: { center: geo(c.n, c.e), radiusM: 700, direction: TurnDirection.CW } } }), 0);
    run(sc, 0, 400);
    for (const t of [400, 410, 420, 430]) {
      sc.frameAt(BigInt(t * 50), 50);
      const d = dist(posOf(sc, "uav-001", t), c);
      expect(d).toBeGreaterThan(400);
      expect(d).toBeLessThan(1100);
    }
  });

  it("항로: 항로점을 순서대로 지나고 끝나면 COMPLETED, 진행 보고가 단조 증가한다", () => {
    const sc = new MockScenario();
    sc.frameAt(0n, 50);
    const wps = [geo(9000, -4000), geo(9000, -1000), geo(7000, -1000)];
    sc.command(
      cmd({ task: { case: "route", value: { waypoints: wps.map((position) => ({ position, action: { case: undefined } })), loop: false } } }),
      0,
    );
    const seen: number[] = [];
    const reports = run(sc, 0, 600);
    for (const r of reports) if (r.state === CommandState.EXECUTING) seen.push(r.progress);
    expect(seen.length).toBeGreaterThanOrEqual(2);
    expect([...seen].sort((a, b) => a - b)).toEqual(seen);
    expect(reports.at(-1)?.state).toBe(CommandState.COMPLETED);
  });

  it("정찰: 지정한 원 둘레를 돈다", () => {
    const sc = new MockScenario();
    sc.frameAt(0n, 50);
    const c = { n: 8000, e: -3000 };
    sc.command(
      cmd({ task: { case: "searchArea", value: { area: { shape: { case: "circle", value: { center: geo(c.n, c.e), radiusM: 1000 } } } } } }),
      0,
    );
    run(sc, 0, 400);
    const d = dist(posOf(sc, "uav-001", 400), c);
    expect(d).toBeGreaterThan(600);
    expect(d).toBeLessThan(1400);
  });

  it("타격: 적 엔티티 위치로 접근한다", () => {
    const sc = new MockScenario();
    sc.frameAt(0n, 50);
    const tgt = posOf(sc, "tgt-001", 0);
    sc.command(cmd({ task: { case: "strike", value: { targetId: "tgt-001", weaponType: "fpv" } } }), 0);
    run(sc, 0, 400);
    expect(dist(posOf(sc, "uav-001", 400), tgt)).toBeLessThan(1000);
  });

  it("다룰 수 없는 대상은 거부, 취소는 그 임무일 때만 선회로 바꾼다", () => {
    const sc = new MockScenario();
    const rej = sc.command(cmd({ task: { case: "returnToBase", value: {} } }, ["tgt-001", "uav-001"]), 0);
    expect(rej).toEqual(["tgt-001"]);
    sc.command(cmd({ taskId: "other", cancel: true, task: { case: undefined } }), 0);
    expect(sc.isGuided("uav-001")).toBe(true);
  });

  it("시각을 되돌리면 유도가 풀린다", () => {
    const sc = new MockScenario();
    sc.command(cmd({ task: { case: "returnToBase", value: {} } }), 10);
    sc.frameAt(1000n, 50);
    sc.frameAt(0n, 50);
    expect(sc.isGuided("uav-001")).toBe(false);
    expect(sc.actors.find((a) => a.id === "uav-001")!.kind).toBe(EntityKind.UAV);
  });

  it("TaskStatus 직렬화 왕복", () => {
    const st = create(TaskStatusSchema, { taskId: "t1", state: CommandState.EXECUTING, progress: 0.5 });
    expect(fromBinary(TaskStatusSchema, toBinary(TaskStatusSchema, st)).progress).toBe(0.5);
  });
});
