// TC-MON-012: 재생 표시는 SimStatus.replay로 판단하고 ?replay=1은 SimStatus 수신 전에만 쓴다 (IMP-MON-024, DEC-031)
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Header } from "../components/Header";
import { SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { MockTraffic } from "../mock/mockTraffic";
import { MonitorStore } from "./store";
import { frameOf } from "./testutil";

const status = (t: number, replay: boolean) => frameOf("sim/ctrl/status", SimStatusSchema, { simTimeUs: BigInt(t), replay });

function badge(s: MonitorStore): string {
  const html = renderToStaticMarkup(
    createElement(Header, {
      store: s,
      sourceName: "bridge",
      status: { state: "open" },
      load: { framesPerS: 0, busyPct: 0 },
      frozen: false,
      onFreeze: () => {},
      onClear: () => {},
      onToggleView: () => {},
    }),
  );
  const m = /<button class="badge ([^"]+)"[^>]*>([^<]+)</.exec(html);
  return `${m![1]}|${m![2]}`;
}

describe("재생 표시 (DEC-031)", () => {
  it("SimStatus 수신 전에는 ?replay=1, 수신 후에는 SimStatus.replay를 따른다", () => {
    const s = new MonitorStore();
    s.viewHint = "replay";
    expect([s.view, s.viewSource]).toEqual(["replay", "query"]);
    expect(badge(s)).toBe("badge-replay|▶ 재생 (MCAP)");
    s.handleFrame(status(1_000_000, false));
    expect([s.view, s.viewSource]).toEqual(["live", "status"]);
    expect(badge(s)).toBe("badge-live|● 실시간");
  });

  it("실행 중 SimStatus.replay가 바뀌면 표시가 바뀌고, 수동 전환은 그때 풀린다", () => {
    const s = new MonitorStore();
    s.handleFrame(status(10_000_000, false));
    expect(badge(s)).toBe("badge-live|● 실시간");
    s.handleFrame(status(1_000_000, true)); // 재생기가 0 근처부터 다시 발행
    expect(s.view).toBe("replay");
    expect(badge(s)).toBe("badge-replay|▶ 재생 (MCAP)");
    expect(s.rewinds).toBe(1);
    s.toggleView();
    s.handleFrame(status(1_020_000, true));
    expect([s.view, s.viewSource]).toEqual(["live", "manual"]);
    s.handleFrame(status(2_000_000, false));
    expect([s.view, s.viewSource]).toEqual(["live", "status"]);
    s.handleFrame(status(2_020_000, true));
    expect(s.view).toBe("replay");
  });

  it("목 생성기의 replay 옵션은 SimStatus.replay=true로 나온다", () => {
    const s = new MonitorStore({ noTiming: true });
    const g = new MockTraffic((f) => s.handleFrame(f), { wire: true, replay: true, uavs: 2 });
    for (let i = 0; i < g.frameHz; i++) g.stepFrame();
    expect(s.status?.replay).toBe(true);
    expect(s.view).toBe("replay");
  });
});
