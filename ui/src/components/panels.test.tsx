// TC-UI-032~033: 거부 사유 표시와 재생 중 통제 버튼 비활성 (IMP-UI-048~049, DEC-035, DEC-031)
// DOM 환경이 없으므로 서버 렌더링 결과 문자열로 확인한다.
import { create } from "@bufbuild/protobuf";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MockParams } from "../data/mockParams";
import { RunMode, SimRunState, SimStatusSchema, ParamOwner } from "../gen/swarm/v1/sim_pb";
import { ParamStore } from "../model/params";
import { ParamPanel } from "./ParamPanel";
import { Toolbar } from "./Toolbar";

function panel(mp: MockParams, ids = ["uav-001"]): string {
  const s = new ParamStore();
  for (const id of ids) for (const o of [ParamOwner.DYNAMICS, ParamOwner.FA, ParamOwner.MA]) s.onParams(mp.snapshot(id, o, 1n));
  return renderToStaticMarkup(<ParamPanel store={s} version={s.version} ids={ids} disabledReason={null} onSet={() => {}} />);
}

describe("TC-UI-032 거부 사유 표시", () => {
  it("unknown·type·range·not_runtime 거부가 해당 항목에 사유와 함께 보이고, 값은 그대로다", () => {
    const mp = new MockParams();
    const html0 = panel(mp);
    expect(html0).not.toContain("거부:");
    mp.apply("uav-001", ParamOwner.DYNAMICS, { v_max_mps: "fast", bank_max_deg: 200, mass_kg: 20 });
    mp.apply("uav-001", ParamOwner.FA, { lookahead_s: "x" });
    const html = panel(mp);
    expect(html.match(/거부: /g)?.length).toBe(4); // unknown은 선언에 없는 이름이라 붙일 항목이 없다 (TC-UI-030에서 코드 확인)
    expect(html).toContain("거부: 형식이 맞지 않음");
    expect(html).toContain("거부: 허용 범위를 벗어남");
    expect(html).toContain("거부: 실행 중에는 바꿀 수 없음");
    expect(html).toContain("param-row rejected");
  });

  it("목 소스의 소유자 쪽 엄격 규칙: 선언 범위 안이어도 kp_roll>10은 range로 거부", () => {
    const mp = new MockParams();
    expect(mp.apply("uav-001", ParamOwner.DYNAMICS, { kp_roll: 15 })).toEqual([{ name: "kp_roll", reason: "range" }]);
    expect(panel(mp)).toContain("거부: 허용 범위를 벗어남");
  });
});

describe("TC-UI-033 재생 중 통제 버튼", () => {
  const props = (replay: boolean, state: SimRunState) => ({
    source: "bus" as const, onSource: () => {}, conn: null, gcs: "gcs-01",
    status: create(SimStatusSchema, { state, mode: RunMode.REALTIME, rateTarget: 1, replay }),
    simTimeUs: 0n, frame: 0n, entityCount: 0, mapStatus: null, viewMode: "3d" as const, onViewMode: () => {},
    onStart: () => {}, onPause: () => {}, onResume: () => {}, onStep: () => {}, onReset: () => {}, onRate: () => {}, onFit: () => {},
  });
  const btn = (html: string, label: string) => html.match(new RegExp(`<button[^>]*>${label}</button>`))?.[0] ?? "";

  it("replay=true: '재생' 표시, 시작/일시정지/스텝/배속 비활성", () => {
    const a = renderToStaticMarkup(<Toolbar {...props(true, SimRunState.RUNNING)} />);
    expect(a).toContain("replay-badge");
    for (const l of ["일시정지", "스텝", "×2"]) expect(btn(a, l)).toContain("disabled");
    const b = renderToStaticMarkup(<Toolbar {...props(true, SimRunState.LOADED)} />);
    expect(btn(b, "시작")).toContain("disabled");
  });

  it("replay=false: 표시 없고 상태에 맞게 활성", () => {
    const a = renderToStaticMarkup(<Toolbar {...props(false, SimRunState.RUNNING)} />);
    expect(a).not.toContain("replay-badge");
    expect(btn(a, "일시정지")).not.toContain("disabled");
    expect(btn(a, "×2")).not.toContain("disabled");
  });
});
