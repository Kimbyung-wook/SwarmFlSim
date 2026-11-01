// TC-MON-001: 브리지 프로토콜 v1 프레임 인코딩·해석 (IMP-MON-002)
import { describe, expect, it } from "vitest";
import { decodeFrame, encodeFrame, FrameError, parseServerMsg, protobufTypeName } from "./frame";

describe("바이너리 프레임", () => {
  it("왕복한다(UTF-8 키, 빈 페이로드 포함)", () => {
    for (const f of [
      { key: "link/outcome/uav-001/gcs-01", encoding: "application/protobuf;swarm.v1.LinkOutcome", payload: new Uint8Array([1, 2, 3]) },
      { key: "키/한글", encoding: "", payload: new Uint8Array() },
    ]) {
      const d = decodeFrame(encodeFrame(f));
      expect(d.key).toBe(f.key);
      expect(d.encoding).toBe(f.encoding);
      expect([...d.payload]).toEqual([...f.payload]);
    }
  });

  it("길이는 little-endian uint16이다", () => {
    const b = encodeFrame({ key: "ab", encoding: "xyz", payload: new Uint8Array([9]) });
    expect([...b]).toEqual([2, 0, 0x61, 0x62, 3, 0, 0x78, 0x79, 0x7a, 9]);
  });

  it("오프셋이 있는 버퍼도 해석한다", () => {
    const inner = encodeFrame({ key: "k", encoding: "e", payload: new Uint8Array([7, 8]) });
    const outer = new Uint8Array(inner.length + 5);
    outer.set(inner, 5);
    const d = decodeFrame(outer.subarray(5));
    expect(d.key).toBe("k");
    expect([...d.payload]).toEqual([7, 8]);
  });

  it("잘린 프레임은 FrameError", () => {
    const b = encodeFrame({ key: "abc", encoding: "def", payload: new Uint8Array() });
    expect(() => decodeFrame(b.subarray(0, 3))).toThrow(FrameError);
    expect(() => decodeFrame(b.subarray(0, 7))).toThrow(FrameError);
    expect(() => decodeFrame(new Uint8Array([2, 0, 0xff, 0xfe, 0, 0]))).toThrow(FrameError);
  });

  it("인코딩에서 메시지 이름을 꺼낸다", () => {
    expect(protobufTypeName("application/protobuf;swarm.v1.TruthFrame")).toBe("swarm.v1.TruthFrame");
    expect(protobufTypeName("text/plain")).toBeUndefined();
  });
});

describe("텍스트 프레임", () => {
  it("welcome·error를 해석하고 나머지는 거부한다", () => {
    expect(parseServerMsg('{"op":"welcome","protocol":1,"contract":"0.2.0"}')).toEqual({ op: "welcome", protocol: 1, contract: "0.2.0" });
    expect(parseServerMsg('{"op":"error","code":"forbidden","msg":"x"}')).toEqual({ op: "error", code: "forbidden", msg: "x" });
    expect(() => parseServerMsg("nope")).toThrow(FrameError);
    expect(() => parseServerMsg('{"op":"what"}')).toThrow(FrameError);
  });
});
