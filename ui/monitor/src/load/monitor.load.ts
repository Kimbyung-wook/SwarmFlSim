// TC-MON-009: 부하 측정. 20대 × 50 Hz 브로드캐스트 트래픽을 집계가 실시간 안에 처리하는지 본다 (REQ-UI-005, REQ-PRF-001)
// npm run bench. 목 생성 비용은 빼고 (바이트 프레임 → 해석 → 집계·타임라인·echo) 경로만 잰다.
import { describe, expect, it } from "vitest";
import type { BusFrame } from "../bridge/frame";
import { decodeFrame, encodeFrame } from "../bridge/frame";
import { MockTraffic } from "../mock/mockTraffic";
import { MonitorStore } from "../model/store";

interface Result {
  name: string;
  simS: number;
  frames: number;
  outcomes: number;
  framesPerSimS: number;
  msPerSimS: number;
  usPerFrame: number;
  realtimeFactor: number;
}

function measure(name: string, uavs: number, peerHz: number, simS: number): Result {
  // 바이트열로 미리 만들어 둔다(브리지 WebSocket 수신과 같은 입력)
  const wire: Uint8Array[] = [];
  const g = new MockTraffic((f: BusFrame) => wire.push(encodeFrame(f)), { uavs, peerHz });
  for (let i = 0; i < simS * g.frameHz; i++) g.stepFrame();

  const store = new MonitorStore();
  // 워밍업 (JIT)
  const warm = new MonitorStore();
  for (let i = 0; i < Math.min(wire.length, 20_000); i++) warm.handleFrame(decodeFrame(wire[i]));

  const t0 = performance.now();
  for (const b of wire) store.handleFrame(decodeFrame(b));
  const ms = performance.now() - t0;
  const r: Result = {
    name,
    simS,
    frames: wire.length,
    outcomes: g.counts.outcome,
    framesPerSimS: wire.length / simS,
    msPerSimS: ms / simS,
    usPerFrame: (ms * 1000) / wire.length,
    realtimeFactor: (simS * 1000) / ms,
  };
  return r;
}

describe("부하 측정", () => {
  it("20대 × 50 Hz PeerStatus 브로드캐스트", () => {
    const rows = [measure("20대 × 10 Hz (목 기본값)", 20, 10, 20), measure("20대 × 50 Hz", 20, 50, 20), measure("40대 × 50 Hz", 40, 50, 10)];
    // vitest가 console 출력을 숨기므로 stdout에 직접 쓴다
    const lines = [
      "| 경우 | 프레임/s | outcome/s | 처리 ms/s | µs/프레임 | 실시간 배수 |",
      "|---|---|---|---|---|---|",
      ...rows.map(
        (r) =>
          `| ${r.name} | ${Math.round(r.framesPerSimS)} | ${Math.round(r.outcomes / r.simS)} | ${r.msPerSimS.toFixed(1)} | ${r.usPerFrame.toFixed(2)} | ${r.realtimeFactor.toFixed(1)} |`,
      ),
    ];
    process.stdout.write(["", ...lines, "", ""].join("\n"));
    // 20대 × 50 Hz를 실시간의 2배 이상으로 처리해야 한다(화면 갱신·브라우저 여유분)
    expect(rows[1].realtimeFactor).toBeGreaterThan(2);
  });
});
