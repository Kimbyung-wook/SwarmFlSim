// TC-UI-084: 운용 시나리오 보완 패널 렌더링 — 임무 창 탭·상실 정책, 취소 단추, 승인 패널, 고장 주입, 교전 기준 (IMP-UI-085~092)
// DOM 환경이 없으므로 서버 렌더링 결과 문자열로 확인한다.
import { create, toBinary } from "@bufbuild/protobuf";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApprovalRequestSchema, ApprovalResponseSchema } from "../gen/swarm/v1/c2_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { Side } from "../gen/swarm/v1/entity_pb";
import { FaultKind } from "../gen/swarm/v1/sim_pb";
import { ApprovalStore } from "../model/approvals";
import { C2Commander } from "../model/commands";
import { TaskLog } from "../model/taskLog";
import { ApprovalPanel } from "./ApprovalPanel";
import { CommandPanel } from "./CommandPanel";
import { CriteriaPanel } from "./CriteriaPanel";
import { FaultPanel } from "./FaultPanel";
import { MissionMenu } from "./MissionPanel";

const UI = "ui-me";

describe("TC-UI-084 운용 시나리오 보완 패널", () => {
  it("임무 창에 추적·재밍 탭과 링크 상실 정책 선택이 있다", () => {
    const html = renderToStaticMarkup(
      <MissionMenu
        menu={{ point: { latDeg: 37.5, lonDeg: 127, heightM: 50 }, targetId: null }}
        targetCount={2}
        disabledReason={null}
        defaultAltM={1000}
        onPreview={() => {}}
        onSend={() => {}}
        onClose={() => {}}
      />,
    );
    expect(html).toContain(">추적<");
    expect(html).toContain(">재밍<");
    expect(html).toContain(">정찰<");
    expect(html).toContain("상실");
    expect(html).toContain("계속 수행");
  });

  it("진행 중 임무에는 취소 단추가 있고, 보낸 뒤에는 '취소 중'", () => {
    const log = new TaskLog();
    const c = new C2Commander("gcs-01", UI, () => ({ simTimeUs: 0n, frame: 0n }));
    const out = c.mission({ kind: "returnToBase" }, ["uav-001"]);
    log.sent(out);
    const render = () =>
      renderToStaticMarkup(
        <CommandPanel targets={[]} disabledReason={null} groups={[]} tasks={log.list()} rx={[]} onHold={() => {}} onRtb={() => {}} onFormation={() => {}} onAssignGroup={() => {}} onRecallGroup={() => {}} onEditRoute={() => {}} onCancelTask={() => {}} />,
      );
    expect(render()).toContain(">취소<");
    log.cancelSent(out.taskId!);
    expect(render()).toContain("취소 중");
  });

  it("승인 패널: 대기는 승인·거부 단추와 남은 시간, 처리된 요청은 먼저 처리한 쪽(gateway)과 늦은 응답", () => {
    const s = new ApprovalStore(UI);
    const req = (rid: string) =>
      create(LinkEnvelopeSchema, {
        header: { source: "uav-001" },
        msgType: "swarm.v1.ApprovalRequest",
        payload: toBinary(ApprovalRequestSchema, create(ApprovalRequestSchema, { header: { source: "uav-001" }, requestId: rid, taskId: "t-1", targetId: "tgt-001", description: "strike t-1" })),
      });
    const resp = (rid: string, approved: boolean, publisher: string, seq: number) =>
      create(LinkEnvelopeSchema, {
        publisher,
        header: { source: publisher, seq },
        msgType: "swarm.v1.ApprovalResponse",
        payload: toBinary(ApprovalResponseSchema, create(ApprovalResponseSchema, { requestId: rid, approved })),
      });
    s.onRx("k", req("r1"));
    s.onRx("k", req("r2"));
    s.onTx("k", resp("r2", true, "gateway", 1));
    s.onTx("k", resp("r2", false, UI, 1));
    const html = renderToStaticMarkup(
      <ApprovalPanel pending={s.pending()} recent={s.list().filter((v) => !s.pending().includes(v))} remainingS={() => 42} disabledReason={null} onAnswer={() => {}} />,
    );
    expect(html).toContain("대기 1");
    expect(html).toContain(">승인</button>");
    expect(html).toContain(">거부</button>");
    expect(html).toContain("남은 42 s");
    expect(html).toContain("표적 tgt-001");
    expect(html).toContain("승인 처리 (gateway)");
    expect(html).toContain("늦은 응답(무시): 이 UI 거부");
    // 관찰 전용이면 단추가 비활성
    const ro = renderToStaticMarkup(<ApprovalPanel pending={s.pending()} recent={[]} remainingS={() => null} disabledReason="관찰 전용" onAnswer={() => {}} />);
    expect(ro).toContain("시간 제한 없음");
    expect(ro.match(/disabled=""/g)?.length).toBe(2);
    // 아무것도 없으면 그리지 않는다
    expect(renderToStaticMarkup(<ApprovalPanel pending={[]} recent={[]} remainingS={() => null} disabledReason={null} onAnswer={() => {}} />)).toBe("");
  });

  it("고장 주입 메뉴는 시험 진행자용으로 분리되고, 활성 고장과 해제 단추를 보인다. KILL은 해제가 없다", () => {
    const html = renderToStaticMarkup(
      <FaultPanel
        ids={["uav-001"]}
        disabledReason={null}
        active={[
          { entityId: "uav-001", fault: FaultKind.GCS_LINK_CUT, atUs: 0n, durationS: 30, remainingS: 25 },
          { entityId: "uav-002", fault: FaultKind.KILL, atUs: 0n, durationS: 0, remainingS: null },
        ]}
        onInject={() => {}}
        onClear={() => {}}
      />,
    );
    expect(html).toContain("시험 진행자: 고장 주입");
    expect(html).toContain("주입 (1)");
    expect(html).toContain("남은 25 s");
    expect(html.match(/>해제</g)?.length).toBe(1);
  });

  it("교전 기준 배포: 진영·승인 필요·영역 수와 배포 대상 수", () => {
    const html = renderToStaticMarkup(
      <CriteriaPanel
        value={{ hostileSides: [Side.RED], requireApproval: true, weaponsFree: [{ center: { latDeg: 37, lonDeg: 127, altM: 0 }, radiusM: 3000 }], noStrike: [] }}
        onChange={() => {}}
        point={null}
        dstCount={3}
        dstLabel="비행 중 아군 전체"
        disabledReason={null}
        onSend={() => {}}
      />,
    );
    expect(html).toContain("교전 기준 배포");
    expect(html).toContain("타격 전 승인 필요");
    expect(html).toContain("무기 사용 영역 1");
    expect(html).toContain("타격 금지 영역 0");
    expect(html).toContain("배포 (3대)");
  });
});
