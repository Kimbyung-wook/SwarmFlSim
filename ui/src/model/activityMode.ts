// IMP-UI-083: 행동 표시 범위(전체·선택 기체만·끔)와 외삽 배속
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import { SimRunState } from "../gen/swarm/v1/sim_pb";

export type ActivityMode = "all" | "selected" | "off";

export const ACTIVITY_MODE_LABEL: Record<ActivityMode, string> = {
  all: "행동: 전체",
  selected: "행동: 선택 기체",
  off: "행동: 끔",
};

/** 그릴 기체 집합. null이면 전체, "off"면 그리지 않는다 */
export function activityFilter(mode: ActivityMode, selection: readonly string[]): ReadonlySet<string> | null | "off" {
  if (mode === "off") return "off";
  return mode === "selected" ? new Set(selection) : null;
}

/** 보고 위치 외삽에 쓰는 모의 시간 배속. 실행 중이 아니면 0 (일시정지 중에는 움직이지 않는다) */
export function simRate(s: SimStatus | null): number {
  if (!s || s.state !== SimRunState.RUNNING) return 0;
  return s.rateActual > 0 ? s.rateActual : s.rateTarget > 0 ? s.rateTarget : 1;
}
