// TC-UI-001: 자세·방향 변환 (IMP-UI-003)
import { describe, expect, it } from "vitest";
import { DEG, eulerToQuat, flightPathAngle, headingFromVelocity, quatToEuler, wrap2Pi, wrapPi } from "./attitude";

describe("attitude", () => {
  it("오일러 → 쿼터니언 → 오일러 왕복", () => {
    for (const yaw of [-170, -90, 0, 45, 135, 179]) {
      for (const pitch of [-60, -10, 0, 20, 80]) {
        for (const roll of [-70, 0, 30, 170]) {
          const e = { yaw: yaw * DEG, pitch: pitch * DEG, roll: roll * DEG };
          const q = eulerToQuat(e);
          expect(Math.hypot(q.w, q.x, q.y, q.z)).toBeCloseTo(1, 12);
          const r = quatToEuler(q);
          expect(wrapPi(r.yaw - e.yaw)).toBeCloseTo(0, 9);
          expect(r.pitch).toBeCloseTo(e.pitch, 9);
          expect(wrapPi(r.roll - e.roll)).toBeCloseTo(0, 9);
        }
      }
    }
  });

  it("yaw 90°는 z축 회전 쿼터니언", () => {
    const q = eulerToQuat({ yaw: 90 * DEG, pitch: 0, roll: 0 });
    expect(q.w).toBeCloseTo(Math.SQRT1_2, 12);
    expect(q.z).toBeCloseTo(Math.SQRT1_2, 12);
    expect(q.x).toBeCloseTo(0, 12);
    expect(q.y).toBeCloseTo(0, 12);
  });

  it("NED 속도의 진행 방향: 북 0, 동 90°, 남 180°, 서 270°", () => {
    expect(headingFromVelocity(10, 0)).toBeCloseTo(0, 12);
    expect(headingFromVelocity(0, 10)).toBeCloseTo(90 * DEG, 12);
    expect(headingFromVelocity(-10, 0)).toBeCloseTo(180 * DEG, 12);
    expect(headingFromVelocity(0, -10)).toBeCloseTo(270 * DEG, 12);
    expect(headingFromVelocity(0.1, 0.1)).toBeNull();
  });

  it("상승각은 vd가 음수일 때 양수", () => {
    expect(flightPathAngle(10, 0, -10)).toBeCloseTo(45 * DEG, 12);
    expect(flightPathAngle(10, 0, 0)).toBeCloseTo(0, 12);
  });

  it("각도 정규화", () => {
    expect(wrap2Pi(-0.5)).toBeCloseTo(2 * Math.PI - 0.5, 12);
    expect(wrapPi(3 * Math.PI / 2)).toBeCloseTo(-Math.PI / 2, 12);
  });
});
