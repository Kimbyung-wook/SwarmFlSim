// TC-UI-032~033: 거부 사유 표시와 재생 중 통제 버튼 비활성 (IMP-UI-048~049, DEC-035, DEC-031)
// DOM 환경이 없으므로 서버 렌더링 결과 문자열로 확인한다.
import { create } from "@bufbuild/protobuf";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MockParams } from "../data/mockParams";
import { RunMode, SimRunState, SimStatusSchema, ParamOwner } from "../gen/swarm/v1/sim_pb";
import { toBinary } from "@bufbuild/protobuf";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { C2Commander } from "../model/commands";
import { TaskLog } from "../model/taskLog";
import { CommandPanel } from "./CommandPanel";
import { ParamStore, flockingEntities } from "../model/params";
import { EntityParamsSchema } from "../gen/swarm/v1/sim_pb";
import { LiveState, STALL_MS, isStalled } from "../model/liveState";
import { RouteEditor } from "./MissionPanel";
import { addWaypoint, emptyRoute } from "../model/routeDraft";
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

describe("TC-UI-035 선택지(choices) 항목", () => {
  it("choices가 있으면 드롭다운(select)으로, 없으면 입력칸으로 그린다", () => {
    const html = panel(new MockParams());
    const row = html.match(/<div class="param-row[^"]*"><div class="param-name"[^>]*><b>racetrack_guidance<\/b>.*?<\/div><\/div><\/div>/)?.[0] ?? "";
    expect(row).toContain("<select");
    expect(row).toContain('<option value="dubins" selected');
    expect(row).toContain('<option value="vector_field"');
    expect(html.match(/<select/g)?.length).toBe(1);
    expect(html).toMatch(/<b>formation<\/b>[\s\S]*?<input type="text"/);
  });

  it("choice 거부 사유 문구가 항목에 붙는다 (목 소스가 허용 목록 밖 값을 거부)", () => {
    const mp = new MockParams();
    expect(mp.apply("uav-001", ParamOwner.FA, { racetrack_guidance: "spiral" })).toEqual([{ name: "racetrack_guidance", reason: "choice" }]);
    const html = panel(mp);
    expect(html).toContain("거부: 허용 목록에 없는 값");
    expect(html).toContain('<option value="dubins" selected');
    expect(mp.apply("uav-001", ParamOwner.FA, { racetrack_guidance: "vector_field" })).toEqual([]);
    expect(panel(mp)).toContain('<option value="vector_field" selected');
  });

  it("여러 기체의 값이 다르면 '혼합' 선택지가 맨 앞에 생긴다", () => {
    const mp = new MockParams();
    mp.apply("uav-002", ParamOwner.FA, { racetrack_guidance: "vector_field" });
    expect(panel(mp, ["uav-001", "uav-002"])).toContain('<option value="" selected="">혼합</option>');
  });
});

describe("TC-UI-036 realtime 배속 고정 (QA-009)", () => {
  const tb = (mode: RunMode) =>
    renderToStaticMarkup(
      <Toolbar
        source="bus" onSource={() => {}} conn={null} gcs="gcs-01"
        status={create(SimStatusSchema, { state: SimRunState.RUNNING, mode, rateTarget: 1 })}
        simTimeUs={0n} frame={0n} entityCount={0} mapStatus={null} viewMode="3d" onViewMode={() => {}}
        onStart={() => {}} onPause={() => {}} onResume={() => {}} onStep={() => {}} onReset={() => {}} onRate={() => {}} onFit={() => {}}
      />,
    );
  const rate = (html: string, l: string) => html.match(new RegExp(`<button[^>]*>${l}</button>`))?.[0] ?? "";
  it("realtime: 배속 버튼 비활성과 안내", () => {
    const h = tb(RunMode.REALTIME);
    for (const l of ["×1", "×2", "×5", "×10"]) expect(rate(h, l)).toContain("disabled");
    expect(h).toContain("실시간에서는 배속 고정");
  });
  it("lockstep·freerun: 배속 버튼 활성, 안내 없음", () => {
    for (const m of [RunMode.LOCKSTEP, RunMode.FREERUN]) {
      const h = tb(m);
      expect(rate(h, "×5")).not.toContain("disabled");
      expect(h).not.toContain("실시간에서는 배속 고정");
    }
  });
});

describe("TC-UI-037 임무 응답 표시: 거부·실패 사유", () => {
  it("TaskStatus REJECTED·FAILED는 응답 칸에 사유가 보이고 정상 응답은 그대로", () => {
    const log = new TaskLog();
    const out = new C2Commander("gcs-01", "ui-q", () => ({ simTimeUs: 0n, frame: 0n })).task("hold", ["uav-001", "uav-002", "uav-003"]);
    log.sent(out);
    const rx = (src: string, state: CommandState, reason: string) =>
      log.received(
        "swarm/gcs-01/rx/c2/TaskStatus",
        create(LinkEnvelopeSchema, {
          header: { source: src },
          msgType: "swarm.v1.TaskStatus",
          payload: toBinary(TaskStatusSchema, create(TaskStatusSchema, { header: { source: src }, taskId: out.taskId!, state, reason })),
        }),
      );
    rx("uav-001", CommandState.REJECTED, "연료 부족");
    rx("uav-002", CommandState.FAILED, "엔진 고장");
    rx("uav-003", CommandState.EXECUTING, "");
    const html = renderToStaticMarkup(
      <CommandPanel targets={[]} disabledReason={null} groups={[]} tasks={log.list()} rx={[]} onHold={() => {}} onRtb={() => {}} onFormation={() => {}} onAssignGroup={() => {}} onRecallGroup={() => {}} onEditRoute={() => {}} />,
    );
    expect(html).toContain("uav-001 거부 (연료 부족)");
    expect(html).toContain("uav-002 실패 (엔진 고장)");
    expect(html).not.toContain("uav-003 실행 (");
    expect(html.match(/task-bad/g)?.length).toBe(2);
    // 전송 실패는 오류로 표시
    log.sent(new C2Commander("gcs-01", "ui-q", () => ({ simTimeUs: 0n, frame: 0n })).task("hold", ["uav-001"]), "브리지에 연결되어 있지 않다");
    expect(renderToStaticMarkup(<CommandPanel targets={[]} disabledReason={null} groups={[]} tasks={log.list()} rx={[]} onHold={() => {}} onRtb={() => {}} onFormation={() => {}} onAssignGroup={() => {}} onRecallGroup={() => {}} onEditRoute={() => {}} />)).toContain("전송 실패: 브리지에 연결되어 있지 않다");
  });
});

describe("TC-UI-033 재생 중 통제 버튼", () => {
  const props = (replay: boolean, state: SimRunState, mode: RunMode = RunMode.LOCKSTEP) => ({
    source: "bus" as const, onSource: () => {}, conn: null, gcs: "gcs-01",
    status: create(SimStatusSchema, { state, mode, rateTarget: 1, replay }),
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

describe("TC-UI-039 Core 정지 표시 (QA-015)", () => {
  const status = (state: SimRunState) => create(SimStatusSchema, { state, mode: RunMode.REALTIME, rateTarget: 1 });
  const bar = (stalled: boolean) =>
    renderToStaticMarkup(
      <Toolbar
        source="bus" onSource={() => {}} conn={{ state: "open", detail: "" }} gcs="gcs-01"
        status={status(SimRunState.RUNNING)} stalled={stalled}
        simTimeUs={0n} frame={0n} entityCount={0} mapStatus={null} viewMode="3d" onViewMode={() => {}}
        onStart={() => {}} onPause={() => {}} onResume={() => {}} onStep={() => {}} onReset={() => {}} onRate={() => {}} onFit={() => {}}
      />,
    );

  it("isStalled: 수신 전에는 아니고, 임계 초과일 때만 true", () => {
    expect(isStalled(10_000, null)).toBe(false);
    expect(isStalled(1000 + STALL_MS, 1000)).toBe(false);
    expect(isStalled(1001 + STALL_MS, 1000)).toBe(true);
  });

  it("status만 계속 오는 일시정지는 정지가 아니고, 아무것도 안 오면 정지, 다시 오면 해제", () => {
    const live = new LiveState();
    live.onStatus(status(SimRunState.PAUSED), 0);
    for (let t = 1000; t <= 10_000; t += 1000) {
      live.onStatus(status(SimRunState.PAUSED), t);
      expect(live.stalled(t)).toBe(false);
    }
    expect(live.stalled(10_000 + STALL_MS + 1)).toBe(true);
    live.onStatus(status(SimRunState.RUNNING), 20_000);
    expect(live.stalled(20_500)).toBe(false);
  });

  it("truth만 와도 갱신으로 본다", () => {
    const live = new LiveState();
    live.lastRxMs = 0;
    expect(live.stalled(STALL_MS + 1)).toBe(true);
    live.lastRxMs = STALL_MS;
    expect(live.stalled(STALL_MS + 1)).toBe(false);
  });

  it("배지는 stalled일 때만 보인다", () => {
    expect(bar(true)).toContain("시뮬레이션 응답 없음");
    expect(bar(false)).not.toContain("시뮬레이션 응답 없음");
  });
});

describe("TC-UI-040 Route 거부 사유와 flocking 안내 (D-10, DEC-039)", () => {
  it("unsupported task route 거부 사유가 응답 칸에 보인다", () => {
    const log = new TaskLog();
    const out = new C2Commander("gcs-01", "ui-q", () => ({ simTimeUs: 0n, frame: 0n })).task("hold", ["uav-001"]);
    log.sent(out);
    log.received(
      "swarm/gcs-01/rx/c2/TaskStatus",
      create(LinkEnvelopeSchema, {
        header: { source: "uav-001" },
        msgType: "swarm.v1.TaskStatus",
        payload: toBinary(TaskStatusSchema, create(TaskStatusSchema, { header: { source: "uav-001" }, taskId: out.taskId!, state: CommandState.REJECTED, reason: "unsupported task route" })),
      }),
    );
    const html = renderToStaticMarkup(
      <CommandPanel targets={[]} disabledReason={null} groups={[]} tasks={log.list()} rx={[]} onHold={() => {}} onRtb={() => {}} onFormation={() => {}} onAssignGroup={() => {}} onRecallGroup={() => {}} onEditRoute={() => {}} />,
    );
    expect(html).toContain("uav-001 거부 (unsupported task route)");
  });

  it("선택에 flocking MA가 있으면 Route 편집기에 안내가 붙고 전송은 막히지 않는다", () => {
    const store = new ParamStore();
    const ma = (id: string, plugin: string) => store.onParams(create(EntityParamsSchema, { entityId: id, owner: ParamOwner.MA, plugin }));
    ma("uav-001", "flocking");
    ma("uav-002", "waypoint_follow");
    expect(flockingEntities(store, ["uav-001", "uav-002", "uav-003"])).toEqual(["uav-001"]);
    const draft = addWaypoint(emptyRoute(), { latDeg: 37, lonDeg: 127 }, { altM: 500 });
    const render = (flocking: string[]) =>
      renderToStaticMarkup(
        <RouteEditor draft={draft} targetCount={2} disabledReason={null} flocking={flocking}
          onAltitude={() => {}} onSpeed={() => {}} onAction={() => {}} onRemove={() => {}} onReorder={() => {}} onLoop={() => {}} onSend={() => {}} onCancel={() => {}} />,
      );
    const a = render(["uav-001"]);
    expect(a).toContain("route-flock-note");
    expect(a).toContain("unsupported task route");
    expect(a).not.toMatch(/<button[^>]*class="primary"[^>]*disabled/);
    expect(render([])).not.toContain("route-flock-note");
  });
});

describe("TC-UI-042 참여자 응답 없음 경고와 재생 누락 프레임 (DEC-041, DEC-042)", () => {
  const st = (init: Parameters<typeof create<typeof SimStatusSchema>>[1]) =>
    create(SimStatusSchema, { state: SimRunState.RUNNING, mode: RunMode.REALTIME, rateTarget: 1, ...init });
  const bar = (live: LiveState) =>
    renderToStaticMarkup(
      <Toolbar
        source="bus" onSource={() => {}} conn={{ state: "open", detail: "" }} gcs="gcs-01"
        status={live.status} waitingWarning={live.waitingWarning()} missedFrames={live.missedFrames}
        simTimeUs={0n} frame={0n} entityCount={0} mapStatus={null} viewMode="3d" onViewMode={() => {}}
        onStart={() => {}} onPause={() => {}} onResume={() => {}} onStep={() => {}} onReset={() => {}} onRate={() => {}} onFit={() => {}}
      />,
    );

  it("waiting_participants가 있으면 이름과 복구 안내를 보이고, 비면 지운다", () => {
    const live = new LiveState();
    live.onStatus(st({ waitingParticipants: ["guidance-1", "gcs-01"] }));
    expect(bar(live)).toContain("참여자 응답 없음: guidance-1, gcs-01 — Reset 후 Start로 복구");
    live.onStatus(st({ waitingParticipants: [] }));
    expect(bar(live)).not.toContain("참여자 응답 없음");
  });

  it("재생 중에만 프레임 번호 공백을 센다. 재생이 아니면 표시하지 않는다", () => {
    const live = new LiveState();
    live.onStatus(st({ replay: true }));
    for (const n of [1n, 2n, 5n, 6n, 10n]) live.onFrameSeq(n);
    expect(live.missedFrames).toBe(5);
    expect(bar(live)).toContain("누락 프레임 5");
    live.onStatus(st({ replay: false }));
    live.onFrameSeq(20n);
    expect(live.missedFrames).toBe(0);
    expect(bar(live)).not.toContain("누락 프레임");
  });
});
