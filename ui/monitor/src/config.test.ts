// TC-MON-017: 브리지 주소 쿼리 `bridge=`와 별칭 `url=` (IMP-MON-029, DEC-091)
import { describe, expect, it } from "vitest";
import { readConfig } from "./App";
import { DEFAULT_BRIDGE_URL } from "./bridge/frame";

describe("readConfig 브리지 주소", () => {
  it("bridge=를 받는다", () => {
    const c = readConfig("?source=bridge&bridge=ws://10.0.0.5:9000/bus");
    expect(c.source).toBe("bridge");
    expect(c.url).toBe("ws://10.0.0.5:9000/bus");
  });
  it("url=은 별칭으로 남는다", () => {
    expect(readConfig("?source=bridge&url=ws://127.0.0.1:48765/bus").url).toBe("ws://127.0.0.1:48765/bus");
  });
  it("둘 다 있으면 bridge=가 우선", () => {
    expect(readConfig("?bridge=ws://a/bus&url=ws://b/bus").url).toBe("ws://a/bus");
    expect(readConfig("?url=ws://b/bus&bridge=ws://a/bus").url).toBe("ws://a/bus");
  });
  it("없거나 비어 있으면 기본 주소", () => {
    expect(readConfig("").url).toBe(DEFAULT_BRIDGE_URL);
    expect(readConfig("?bridge=").url).toBe(DEFAULT_BRIDGE_URL);
    expect(readConfig("?bridge=&url=ws://b/bus").url).toBe("ws://b/bus");
  });
});
