// TC-UI-064: UI가 보내는 모든 C2 LinkEnvelope에 publisher를 채운다. seq는 발행자·키별 (IMP-UI-076, DEC-077)
import { fromBinary, toBinary } from "@bufbuild/protobuf";
import { describe, expect, it } from "vitest";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { C2Commander } from "./commands";

const c = (ui = "ui-01") => new C2Commander("gcs-01", ui);

describe("LinkEnvelope.publisher", () => {
  it("task·mission·formation·group 봉투 모두 UI 참여자 ID를 싣고 직렬화 뒤에도 유지된다", () => {
    const cmd = c();
    const pt = { latDeg: 36.5, lonDeg: 127.4, altM: 800 };
    const outs = [
      cmd.task("hold", ["uav-001"]),
      cmd.task("returnToBase", ["uav-001"]),
      cmd.task("moveTo", ["uav-001"], pt),
      cmd.mission({ kind: "moveTo", destination: pt }, ["uav-001"]),
      cmd.mission({ kind: "search", center: pt, radiusM: 1500 }, ["uav-001"]),
      cmd.formation("grp-1", ["uav-001", "uav-002"], 1, 100),
      cmd.group("grp-1", ["uav-001"]),
      cmd.group("grp-1", [], ["uav-001"]),
    ];
    for (const out of outs) {
      expect(out.key.startsWith("swarm/gcs-01/tx/")).toBe(true);
      expect(fromBinary(LinkEnvelopeSchema, toBinary(LinkEnvelopeSchema, out.envelope)).publisher).toBe("ui-01");
    }
  });

  it("header.source는 GCS 그대로이고 publisher만 UI ID다", () => {
    const env = c().task("hold", ["uav-001"]).envelope;
    expect(env.header?.source).toBe("gcs-01");
    expect(env.publisher).toBe("ui-01");
  });

  it("seq는 UI 인스턴스(발행자)·키별로 따로 센다", () => {
    const a = c("ui-01");
    const b = c("ui-02");
    expect(a.task("hold", ["uav-001"]).envelope.header?.seq).toBe(1);
    expect(a.task("hold", ["uav-001"]).envelope.header?.seq).toBe(2);
    expect(a.group("grp-1", ["uav-001"]).envelope.header?.seq).toBe(1);
    const other = b.task("hold", ["uav-001"]).envelope;
    expect(other.header?.seq).toBe(1);
    expect(other.publisher).toBe("ui-02");
  });
});
