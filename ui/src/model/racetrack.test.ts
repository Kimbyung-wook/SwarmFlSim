// TC-UI-026~027: 레이스트랙 도형(원 중심·접점·폐곡선)과 메시지 생성, 목 소스 레이스트랙 비행 (IMP-UI-042~044, DEC-034)
import { create, fromBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { TaskCommandSchema } from "../gen/swarm/v1/c2_pb";
import { EntityKind } from "../gen/swarm/v1/entity_pb";
import { TurnDirection } from "../gen/swarm/v1/vi_pb";
import { MockScenario, geodeticToNed } from "../data/mockScenario";
import { toEntityView } from "./entityView";
import { C2Commander } from "./commands";
import { draftOverlay, missionOverlay } from "./missionOverlay";
import { distanceBearing, normalizeHeadingDeg, racetrackGeometry, toLocal } from "./racetrack";
import * as R from "./routeDraft";

const C = { latDeg: 36.5, lonDeg: 127.4 };
const P = { ...C, altM: 1500 };
const cm = () => new C2Commander("gcs-01", "ui-ab", () => ({ simTimeUs: 0n, frame: 0n }));
const decode = (o: { envelope: { payload: Uint8Array } }) => fromBinary(TaskCommandSchema, o.envelope.payload);

describe("TC-UI-026 레이스트랙 도형", () => {
  it("원 중심은 중점 ± (길이/2)·축 방향", () => {
    const g = racetrackGeometry(C, 800, { legLengthM: 4000, axisHeadingDeg: 90 }, TurnDirection.CW);
    const c2 = toLocal(C, g.c2), c1 = toLocal(C, g.c1);
    expect(c2.n).toBeCloseTo(0, 3);
    expect(c2.e).toBeCloseTo(2000, 3);
    expect(c1.e).toBeCloseTo(-2000, 3);
    const d = distanceBearing(g.c1, g.c2);
    expect(d.distM).toBeCloseTo(4000, 3);
    expect(d.bearingDeg).toBeCloseTo(90, 5);
    expect(distanceBearing(C, racetrackGeometry(C, 500, { legLengthM: 2000, axisHeadingDeg: 0 }, TurnDirection.CW).c2).bearingDeg).toBeCloseTo(0, 5);
  });

  it("접점은 축과 평행한 직선의 끝이고 중심에서 반경만큼 떨어진다", () => {
    const g = racetrackGeometry(C, 800, { legLengthM: 4000, axisHeadingDeg: 90 }, TurnDirection.CW);
    const [aS, aE, bS, bE] = g.tangents.map((p) => toLocal(C, p));
    // 축이 동쪽이면 시계 방향 A는 축의 왼쪽(북쪽)에서 동쪽으로 간다
    expect(aS).toMatchObject({ n: expect.closeTo(800, 3), e: expect.closeTo(-2000, 3) });
    expect(aE).toMatchObject({ n: expect.closeTo(800, 3), e: expect.closeTo(2000, 3) });
    expect(bS.n).toBeCloseTo(-800, 3);
    expect(bS.e).toBeCloseTo(2000, 3);
    expect(bE.e).toBeCloseTo(-2000, 3);
    // 반시계는 좌우가 바뀐다
    const ccw = racetrackGeometry(C, 800, { legLengthM: 4000, axisHeadingDeg: 90 }, TurnDirection.CCW);
    expect(toLocal(C, ccw.tangents[0]).n).toBeCloseTo(-800, 3);
  });

  it("폐곡선: 처음과 끝이 같고 모든 점이 두 원 중심을 잇는 선분에서 반경 이내", () => {
    const g = racetrackGeometry(C, 800, { legLengthM: 4000, axisHeadingDeg: 30 }, TurnDirection.CW);
    expect(g.outline[0]).toEqual(g.outline.at(-1));
    for (const p of g.outline) {
      const q = toLocal(C, p);
      // 축 좌표
      const a = (30 * Math.PI) / 180;
      const s = q.n * Math.cos(a) + q.e * Math.sin(a);
      const l = -q.n * Math.sin(a) + q.e * Math.cos(a);
      const dEnd = Math.abs(s) <= 2000 ? Math.abs(l) : Math.hypot(Math.abs(s) - 2000, l);
      expect(dEnd).toBeCloseTo(800, 0);
    }
  });

  it("방위 정규화", () => {
    expect(normalizeHeadingDeg(-90)).toBe(270);
    expect(normalizeHeadingDeg(360)).toBe(0);
    expect(normalizeHeadingDeg(450)).toBe(90);
  });

  it("도형: 레이스트랙이면 선, 원형이면 원. 직선 길이 0은 원", () => {
    const race = missionOverlay({ kind: "hold", center: P, radiusM: 700, direction: TurnDirection.CW, racetrack: { legLengthM: 3000, axisHeadingDeg: 45 } }, "sent");
    expect(race.circles).toHaveLength(0);
    expect(race.lines).toHaveLength(1);
    const circ = missionOverlay({ kind: "hold", center: P, radiusM: 700, direction: TurnDirection.CW, racetrack: { legLengthM: 0, axisHeadingDeg: 45 } }, "sent");
    expect(circ.circles).toHaveLength(1);
    let d = R.addWaypoint(R.emptyRoute(), C, { altM: 1000 });
    d = R.setAction(d, 0, { kind: "loiter", durationS: 60, radiusM: 500, direction: TurnDirection.CCW, racetrack: { legLengthM: 2000, axisHeadingDeg: 0 } });
    expect(draftOverlay(d).lines).toHaveLength(1);
  });
});

describe("TC-UI-026 메시지 생성", () => {
  it("HoldTask.racetrack: 길이·축, 축은 [0,360)으로 정규화, 길이 0은 필드 없음", () => {
    const tc = decode(cm().mission({ kind: "hold", center: P, radiusM: 800, direction: TurnDirection.CW, racetrack: { legLengthM: 5000, axisHeadingDeg: -30 } }, ["uav-001"]));
    if (tc.task.case !== "hold") throw new Error("hold");
    expect(tc.task.value.racetrack).toMatchObject({ legLengthM: 5000, axisHeadingDeg: 330 });
    expect(tc.task.value.radiusM).toBe(800);
    expect(tc.task.value.center).toMatchObject(P);
    const none = decode(cm().mission({ kind: "hold", center: P, direction: TurnDirection.CW, racetrack: { legLengthM: 0, axisHeadingDeg: 0 } }, ["uav-001"]));
    if (none.task.case === "hold") expect(none.task.value.racetrack).toBeUndefined();
  });

  it("LoiterAction.racetrack", () => {
    const wps = [{ position: P, action: { kind: "loiter" as const, durationS: 90, radiusM: 600, direction: TurnDirection.CCW, racetrack: { legLengthM: 3000, axisHeadingDeg: 180 } } }];
    const tc = decode(cm().mission({ kind: "route", waypoints: wps, loop: false }, ["uav-001"]));
    if (tc.task.case !== "route") throw new Error("route");
    const a = tc.task.value.waypoints[0].action;
    expect(a.case).toBe("loiter");
    if (a.case === "loiter") expect(a.value.racetrack).toMatchObject({ legLengthM: 3000, axisHeadingDeg: 180 });
  });
});

describe("TC-UI-027 목 소스 레이스트랙 비행", () => {
  for (const [dir, name] of [[TurnDirection.CW, "시계"], [TurnDirection.CCW, "반시계"]] as const) {
    it(`${name}: 기체가 도형 위를 유지하며 두 원 사이를 오간다`, () => {
      const sc = new MockScenario();
      sc.frameAt(0n, 50);
      const g = (n: number, e: number) => ({ latDeg: 36.6 + n / 111320, lonDeg: 127.5 + e / (111320 * Math.cos((36.6 * Math.PI) / 180)), altM: 1500 });
      const mid = { n: 9000, e: -5000 };
      sc.command(
        create(TaskCommandSchema, {
          taskId: "t", assignees: ["uav-001"],
          task: { case: "hold", value: { center: g(mid.n, mid.e), radiusM: 600, direction: dir, racetrack: { legLengthM: 4000, axisHeadingDeg: 90 } } },
        }),
        0,
      );
      const a = sc.actors.find((x) => x.id === "uav-001" && x.kind === EntityKind.UAV)!;
      let maxE = -1e9, minE = 1e9, worst = 0;
      for (let t = 0; t <= 900; t += 0.5) {
        sc.frameAt(BigInt(Math.round(t * 50)), 50);
        if (t < 300) continue;
        const v = toEntityView(sc.entityAt(a, t));
        const p = geodeticToNed({ latDeg: v.lat, lonDeg: v.lon });
        const s = p.e - mid.e, l = p.n - mid.n;
        maxE = Math.max(maxE, s);
        minE = Math.min(minE, s);
        const err = Math.abs(s) <= 2000 ? Math.abs(Math.abs(l) - 600) : Math.abs(Math.hypot(Math.abs(s) - 2000, l) - 600);
        worst = Math.max(worst, err);
      }
      expect(maxE).toBeGreaterThan(2300);
      expect(minE).toBeLessThan(-2300);
      expect(worst).toBeLessThan(250);
    });
  }
});
