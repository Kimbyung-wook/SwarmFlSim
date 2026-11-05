// TC-UI-043: 프레임 번호 공백 계산과 헤더 엿보기 (IMP-UI-059, DEC-042)
import { create, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { FrameGapCounter, peekFrameNumber, waitingWarning } from "./frameGap";

describe("TC-UI-043 frameGap", () => {
  it("peekFrameNumber: TruthFrame 헤더에서 프레임 번호만 꺼낸다", () => {
    const big = create(TruthFrameSchema, {
      header: { frame: 123456789n, simTimeUs: 5n },
      entities: Array.from({ length: 300 }, (_, i) => ({ id: `uav-${i}` })),
    });
    expect(peekFrameNumber(toBinary(TruthFrameSchema, big))).toBe(123456789n);
    expect(peekFrameNumber(new Uint8Array())).toBeNull();
    expect(peekFrameNumber(new Uint8Array([0x0a, 0x7f, 1]))).toBeNull();
  });

  it("공백만큼 센다. 같은 번호 반복은 세지 않는다", () => {
    const c = new FrameGapCounter();
    for (const n of [1n, 2n, 2n, 4n, 8n]) c.feed(n, true);
    expect(c.missed).toBe(1 + 3);
  });

  it("재생이 아니면 세지 않고, 새로 재생이 시작되거나 되감기면 0부터", () => {
    const c = new FrameGapCounter();
    c.feed(1n, false);
    c.feed(10n, false);
    expect(c.missed).toBe(0);
    c.feed(1n, true);
    c.feed(5n, true);
    expect(c.missed).toBe(3);
    c.feed(2n, true);
    expect(c.missed).toBe(0);
    c.feed(4n, true);
    expect(c.missed).toBe(1);
    c.feed(9n, false);
    c.feed(9n, true);
    expect(c.missed).toBe(0);
  });

  it("waitingWarning", () => {
    expect(waitingWarning(undefined)).toBeNull();
    expect(waitingWarning([])).toBeNull();
    expect(waitingWarning(["a"])).toBe("참여자 응답 없음: a — Reset 후 Start로 복구");
  });
});
