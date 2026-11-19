"""판정 결과 → docs/45_standards_report.md (마크다운). 내용은 모두 결과 dict에서 만든다."""
from __future__ import annotations

from collections import Counter

import judges as J
from confcommon import md_cell as c

ITEMS = [("C1", "적용 범위 표"), ("C2", "형식 검증 (UCI)"), ("C3", "값 의미 검증 (UCI)"), ("C4", "A-GRA 기체 계층 경계"),
         ("C5", "상호작용 상태 흐름"), ("C6", "OMS / LA-CAL 왕복"), ("C7", "AMS-GRA 개념 차용 추적과 적용성")]

C7_TABLE = [
    ("ASB(Abstract Service Bus)", "`open_bus` 추상 계층, Zenoh 백엔드", "PRP-NET-001, DEC-002, DEC-026",
     "모든 프로세스가 `open_bus`로만 버스를 여는지 소스 점검"),
    ("OMS 서비스 분해", "임무장비를 서비스(카메라·재머·무장)별 Command/Activity로 모델링", "PRP-PAY-001",
     "MS 메시지가 장비 서비스별로 나뉘는지 C1 표에서 확인"),
    ("Time Distribution", "Sim Core 고정 프레임, lockstep 장벽", "DEC-005, DEC-043", "lockstep 결정론 시험 결과 링크"),
    ("Armament", "무장 서비스·탑재 구성 명명(`StoreLoadoutConfiguration`)", "DEC-019, DEC-088", "C1 표의 MS 행"),
]


def table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(c(x) for x in r) + " |" for r in rows]
    return out


def fmt(x: float) -> str:
    if x == 0:
        return "0"
    return f"{x:.3g}"


def build(R: dict) -> str:  # noqa: C901, PLR0912, PLR0915
    v, res, meta = R["versions"], R["results"], R["meta"]
    L: list[str] = []
    dirty = " (작업 트리에 커밋 전 변경 있음)" if v.get("dirty") else ""
    L.append(f"커밋 `{v['commit']}`{dirty} · 계약 {v['contract']} · agra_lacal `{v['agra_lacal']}` · 실행 {meta['date']}")
    L.append("")
    L.append("# 표준 적합성 점검 보고 (REQ-STD-001, DEC-092)")
    L.append("")
    L.append(f"이 문서는 `qa/conformance/run.py`가 만든다(손으로 고치지 않는다). 판정 기준은 "
             f"[44_standards_conformance.md](44_standards_conformance.md) C1~C7이다. 원자료는 `{meta['out']}`에 있다.")
    L.append("자체 점검이다(기준 §4). 공식 A-GRA 적합성 도구와 Distribution D 문서는 쓰지 않았다.")
    L.append("")
    # 1. 요약
    L.append("## 1. 요약")
    L.append("")
    rows = []
    for k, name in ITEMS:
        r = res[k]
        ids = ", ".join(f["id"] for f in R["findings"] if f["item"] == k and (f["hits"] or not f["match"]))
        rows.append([k, name, r["verdict"], R["key"][k], ids or "—"])
    L += table(["항목", "내용", "판정", "핵심 수치", "발견"], rows)
    L.append("")
    n = Counter(res[k]["verdict"] for k, _ in ITEMS)
    L.append(f"통과 {n.get('통과', 0)}, 실패 {n.get('실패', 0)}, 정보 {n.get('정보', 0)}. 실패 항목은 고치지 않고 아래 발견으로 "
             "담당 WP에 보낸다.")
    L.append("")
    # 2. 발견
    L.append("## 2. 발견")
    L.append("")
    rows = [[f["id"], f["item"], f["title"], f["wp"], f["level"],
             "재현" if f["hits"] else ("해당 없음(문서·기존)" if not f["match"] else "이번 실행에 없음")]
            for f in R["findings"]]
    L += table(["ID", "항목", "내용", "담당", "중요도", "이번 실행"], rows)
    L.append("")
    for f in R["findings"]:
        L.append(f"- **{f['id']}** {f['detail']}")
        if f.get("resolution"):
            L.append(f"  - 조치: {f['resolution']}")
        for h in f["hits"][:4]:
            L.append(f"  - 판정 문구: {h}")
    L.append("")
    if R["loose"]:
        L.append("미분류 실패(발견 목록에 아직 없는 실패):")
        L.append("")
        for item, t in R["loose"]:
            L.append(f"- {item}: {t}")
    else:
        L.append("미분류 실패는 없다(모든 실패가 위 발견 중 하나에 걸린다).")
    L.append("")
    # 3. 실행 조건
    m = R["run"]
    L.append("## 3. 점검 실행")
    L.append("")
    L += table(["구분", "내용"], [
        ["구성", "Logger(MCAP) · Datalink(participant datalink-0) · Agent(`agent_probe.py`가 감싼 swarm_agent.cli, agent-0) · "
                 "Core(lockstep 1배속, 50 Hz, 평지) · CAL Server(agra_lacal, `lacal_server.yaml`에서 포트·server_id만 바꿈) · "
                 "Gateway(`qa/gw_wrap.py`) · 외부 클라이언트(`qa/gw_ext_client.py`, external_c2)"],
        ["시나리오", f"`{m['scenario']}` 시드 {m['seed']}. gcs-01, 기체 {m['n_vehicles']}대(waypoint 8, 정지 사수 1, formation 3, "
                     "flocking_basic 3), 표적 1. 손실 없는 링크"],
        ["포트", f"CAL {m['cal']}, Zenoh {m['zenoh']} (기본 데모 8765/8766·7447과 겹치지 않음)"],
        ["시간", f"모의 {m['sim_s']} s, 벽시계 {m['wall_s']} s (점검 전체 {meta['elapsed_s']} s)"],
        ["프로세스 종료", f"띄운 PID만 정리: {m['pids']}. 끝날 때 죽어 있던 프로세스: "
                       f"{[x for x in (m['dead'] or []) if x != 'ext'] or '없음'}"
                       + (" (외부 클라이언트 ext는 STOP 파일을 받고 스스로 끝난다. 정상)" if "ext" in (m["dead"] or []) else "")],
        ["로그 이상", f"{len(m['log_issues'])}줄" + (f" (예: {m['log_issues'][0][:120]})" if m['log_issues'] else "")],
    ])
    L.append("")
    L.append("입력은 Core를 일시정지한 프레임에서 넣었다(StepFrames로 정확한 프레임까지 간 뒤). 유효 입력은 Gateway가 버스에 낸 것을 "
             "관측기가 본 뒤 재개했다.")
    L.append("")
    L += table(["모의 s", "프레임", "입력", "CAL 응답", "버스(GCS 송신)"],
               [[e["sim_s"], e["frame"], e["tag"], (e.get("pub") or "")[:60], "; ".join(
                   f"{b[0]} {b[1]}" if isinstance(b, list) else f"{b['msg']} {b['id']}" for b in e.get("bus") or [])]
                for e in m["events"] if not e["tag"].startswith(("end",))])
    L.append("")
    if R.get("repeat"):
        rp = R["repeat"]
        L.append(f"같은 커밋 재실행 {rp['runs']}회의 판정 비교: {rp['summary']}")
        L.append("")
        L += table(["항목", *[f"실행 {i + 1}" for i in range(rp["runs"])], "판정·문구 같음(수치 제외)", "수치까지 같음"],
                   rp["rows"])
        L.append("")
        L.append("- 괄호는 실패 문구 수. 외부 클라이언트의 승인 응답과 수신은 실행 중에 오가므로 건수·Timestamp 차 같은 수치는 "
                 "실행마다 조금 다를 수 있다(기준 §4).")
        L.append("")
    # 4. C1
    r1 = res["C1"]
    s = r1["summary"]
    L.append("## 4. C1 적용 범위 표")
    L.append("")
    L.append(f"판정: **{r1['verdict']}**. 공개 XSD 최상위 요소 {s['xsd_top']}개, 그중 `MA_` {s['xsd_ma']}개. proto가 대응한 UCI 메시지 "
             f"{s['mapped_uci']}개(`MA_` {s['mapped_uci_ma']}), 송신 {s['send']}·수신 {s['recv']}. proto 구분 STD {s['std']}, "
             f"EXT {s['ext']}, SIM {s['sim']}. 상태별 행 수 {s['status']}.")
    L.append("")
    L.append("구현·시험됨 = 변환기가 있고 이번 실행에서 외부와 실제로 오갔고 gateway/TRACE.md에 IMP·TC가 있다. 부분 = 변환기는 있으나 "
             "셋 중 하나가 없다. 미구현은 실패가 아니다(범위 표시). "
             f"{J.INSIDE} = GCS 경계를 넘지 않는 STD라 변환기 없음을 실패로 보지 않는다(DEC-094).")
    L.append("")
    L += table(["L1", "상호작용", "UCI 메시지", "방향", "구분", "범위", "내부 메시지", "변환기", "구현 ID", "시험 ID", "상태"],
               [[x["l1"], x["interaction"], x["uci"], x["dir"], x["cls"], x.get("scope", "—"), x["internal"], x["converter"],
                 x["imp"], x["tc"], x["status"]] for x in r1["rows"]])
    L.append("")
    sc = r1.get("scope") or {}
    if sc:
        L.append("범위 구분(DEC-094, 기준 C1 '범위 구분'): 계약 docs/10_contracts.md §3.2 키 표의 메시지 칸(이름, `*Command` 같은 끝 "
                 "맞춤, 그 메시지의 필드)이 가리키는 키를 모으고, §3.3 글머리 중 `swarm/` 키가 있는 덩어리에 이름이 나오는지 본다. "
                 "swarm 밖 키로만 오가고 swarm 근거도 Gateway 변환기도 없으면 기체 내부다. 목록을 손으로 두지 않는다.")
        L.append("")
        L += table(["STD 메시지", "swarm 밖 키", "swarm 근거(§3.3)", "범위"],
                   [[k, ", ".join(v.get("named_keys", [])) or "—", "; ".join(v.get("swarm_ctx", [])) or "—",
                     "기체 내부" if v["inside_eff"] else ("GCS 경계(변환기 있음)" if v.get("inside") else "GCS 경계")]
                    for k, v in sc.items() if v.get("named_keys") or v["inside_eff"]])
        L.append("")
        L.append("- 표에 없는 STD 메시지는 키 표가 swarm 밖 키로 가리키지 않아 `swarm/**`(LinkEnvelope)로 오가는 GCS 경계로 본다.")
        L.append("")
    if r1["fail"]:
        L.append("실패 사유:")
        L += [f"- {t}" for t in r1["fail"]]
        L.append("")
    for t in r1.get("info", []):
        L.append(f"- 정보: {t}")
    if r1.get("info"):
        L.append("")
    # 5. C2
    r2 = res["C2"]
    L.append("## 5. C2 형식 검증")
    L.append("")
    L.append(f"판정: **{r2['verdict']}**. 외부 클라이언트가 공개 XSD를 따로 적재해 받은 메시지와 보낸 메시지를 다시 검증했다.")
    L.append("")
    L += table(["수신 UCI", "건수", "재검증 실패"], [[k, x["n"], x["fail"]] for k, x in r2["rx"].items()])
    L.append("")
    L += table(["송신 UCI(정상 입력)", "건수", "재검증 실패"], [[k, x["n"], x["fail"]] for k, x in r2["sent"].items()])
    L.append("")
    L += table(["부정 입력", "내용", "외부 사전 검증", "CAL Server", "거부 기록", "버스로 나감"],
               [[x["tag"], x["why"], "통과" if x["client_xsd_ok"] else "XSD 위반", "+OK" if x["pub"].startswith("+OK")
                 else "-ERR", x["how"] or "없음", x["bus_key"] or "아니오"] for x in r2["negatives"]])
    L.append("")
    if r2["fail"]:
        L += [f"- 실패: {t}" for t in r2["fail"]]
        L.append("")
    # 6. C3
    r3 = res["C3"]
    tol = r3["tol"]
    L.append("## 6. C3 값 의미 검증")
    L.append("")
    L.append(f"판정: **{r3['verdict']}**. Gateway 입력(GCS 수신 NavigationReport·PeerStatus, 도·m)과 UCI `MA_PositionReport`"
             f"(swarm.vi·swarm.p2p, rad·m)를 기체·토픽별 도착 순서로 짝지어 {r3['n_pos']}쌍을 대조했다. 자세는 도구가 쿼터니언에서 "
             "회전행렬을 거쳐 따로 구한 ZYX 오일러각과 비교했다(Gateway 식과 다른 계산 경로).")
    L.append("")
    w = r3["worst"]
    ts = r3["ts"]
    L += table(["대조", "허용 오차", "최대 차", "판정"], [
        ["위도·경도 (rad)", tol["pos_rad"], fmt(max(w["lat"], w["lon"])), "통과" if max(w["lat"], w["lon"]) <= tol["pos_rad"] else "실패"],
        ["고도 MSL (m)", tol["alt_m"], fmt(w["alt"]), "통과" if w["alt"] <= tol["alt_m"] else "실패"],
        ["NED 속도 (m/s)", tol["vel_mps"], fmt(w["vel"]), "통과" if w["vel"] <= tol["vel_mps"] else "실패"],
        ["NED→FRD 오일러각 (rad)", tol["att_rad"], fmt(w["att"]), "통과" if w["att"] <= tol["att_rad"] else "실패"],
        ["Timestamp − 모의 시각 변동 (s)", tol["ts_spread_s"], fmt(ts.get("spread", 0.0)) if ts else "—",
         "통과" if ts and ts["spread"] <= tol["ts_spread_s"] else "실패"],
        ["수신 RoutePlan 좌표 (°) / 고도 (m)", f"{tol['route_deg']} / {tol['route_alt_m']}",
         " · ".join(f"{x['where']} {fmt(x['deg_max'])}/{fmt(x['alt_max'])} ({x['n_sent']}→{x['n_bus']}점)" for x in r3["routes"]),
         "통과" if not any("수신 경로" in t for t in r3["fail"]) else "실패"],
    ])
    L.append("")
    if ts:
        L.append(f"Timestamp: {ts['n']}건, (Timestamp − 모의 시각) 최소 {ts['min']:.3f} s, 최대 {ts['max']:.3f} s. 값이 UNIX 시각 "
                 "크기라 모의 시각 0에 묶인 기준이 아니고, 변동 폭이 실행 중 일시정지한 벽시계 시간과 비슷하다.")
        L.append("")
    un = {k: x for k, x in r3["unpaired"].items() if k not in ("states", "header_system_uuid")}
    if un:
        L.append("짝짓기 참고(건수 차이나 어긋남이 있는 기체·토픽): " + ", ".join(f"{k} {x}" for k, x in un.items()))
        L.append("")
    L += table(["식별자 종류", "참조 수", "내부 ID 수", "같은 ID에 UUID 여럿", "같은 UUID에 표지 여럿", "표지 없음"],
               [[k, x["refs"], x["labels"], len(x["label_multi_uuid"]), len(x["uuid_multi_label"]), x["empty_label"]]
                for k, x in r3["ids"].items()])
    L.append("")
    hs = r3["unpaired"].get("header_system_uuid", {})
    L.append(f"머리 SystemID(Gateway 자신): {len(hs)}종 {list(hs.items())[:2]}.")
    L.append("")
    st = r3["states"]
    L.append(f"상태값(DEC-090): 내부↔외부 순서 짝 {st['n']}. 표와 다른 대응 {len(st['bad'])}종. 대응 표:")
    L.append("")
    L += table(["메시지", *J.STATE_MAP["TaskStatus"].keys()],
               [[m, *[J.STATE_MAP[m].get(k, "") for k in J.STATE_MAP["TaskStatus"]]] for m in J.STATE_MAP])
    L.append("")
    sun = r3["unpaired"].get("states", {})
    if sun:
        L.append("상태 보고 건수 차이(내부 ↔ 외부): " + ", ".join(f"{k} {x['internal']}↔{x['external']}" for k, x in sun.items()))
        L.append("")
    if r3["fail"]:
        L += [f"- 실패: {t}" for t in r3["fail"]]
        L.append("")
    # 7. C4
    r4 = res["C4"]
    L.append("## 7. C4 기체 계층 경계")
    L.append("")
    L.append(f"판정: **{r4['verdict']}**. Agent 프로세스를 `qa/conformance/agent_probe.py`로 감싸 실제 진입점이 연 구독 키 표현식·발행 키·"
             "L1 포트 메시지를 기록했다(MCAP에는 발행자 정보가 없어 프로세스별 키는 래퍼에서 얻고, 발행 키는 MCAP 채널과 대조한다).")
    L.append("")
    L.append("허용 키(계약 docs/10_contracts.md §3.2의 Agent 행 + 보충 2개):")
    L.append("")
    L += table(["방향", "키 패턴", "근거"], [["발행", a["pattern"], a["src"]] for a in r4["allowed"]["pub"]]
               + [["구독", a["pattern"], a["src"]] for a in r4["allowed"]["sub"]])
    L.append("")
    L += table(["Agent 구독 키 표현식", "허용"], [[x["key"], "예" if x["ok"] else f"아니오 {x['why']}"] for x in r4["subs"]])
    L.append("")
    pref = Counter("/".join(x["key"].split("/")[:1] + x["key"].split("/")[2:3]) for x in r4["puts"])
    bad_puts = [x for x in r4["puts"] if not x["ok"]]
    L.append(f"Agent 발행 키 {len(r4['puts'])}개(접두·종류별 {dict(pref)}), 허용 밖 {len(bad_puts)}개. MCAP 채널 {r4['mcap'].get('channels')}개, "
             f"Agent 발행 키 중 MCAP에 없는 것 {len(r4['mcap'].get('agent_put_missing_in_mcap', []))}개. truth 채널 "
             f"{r4['mcap'].get('truth_channels')}는 Core 발행이고 Agent 구독·수신 기록에는 없다.")
    L.append("")
    kinds = Counter(x["kind"] for x in r4["imports"])
    L.append(f"MA 소스(algorithms/src/swarm_algorithms) import {len(r4['imports'])}건: {dict(kinds)}. 금지 목록: "
             f"{', '.join(J.FORBIDDEN_IMPORTS)}.")
    L.append("")
    L += table(["L1 포트", "방향", "메시지", "건수", "L1", "구분", "허용"],
               [[x["port"], x["dir"], x["msg"], x["n"], x["l1"], x["mapping"], "예" if x["ok"] else "아니오"]
                for x in sorted(r4["ports"], key=lambda y: (y["port"], y["dir"], y["msg"]))])
    L.append("")
    for t in r4["fail"]:
        L.append(f"- 실패: {t}")
    for t in r4["info"]:
        L.append(f"- 정보: {t}")
    L.append("")
    # 8. C5
    r5 = res["C5"]
    L.append("## 8. C5 상호작용 상태 흐름")
    L.append("")
    L.append(f"판정: **{r5['verdict']}**. 허용 전이 표(도구 `judges.py`에 있는 그대로). 같은 상태 반복은 허용(변화 보고 재송신), "
             "끝 상태 뒤 다른 상태는 위반. '끝 상태 뒤 반복도 위반' 표시가 있는 표는 끝 상태 뒤 같은 상태 반복도 위반(DEC-097).")
    L.append("")
    for name, t in r5["tables"].items():
        L.append(f"- {name}: " + "; ".join(f"{'(첫 보고)' if a == 'None' else a} → {', '.join(b)}"
                                          for a, b in t["transitions"].items()) + f". 끝 상태 {', '.join(t['terminal'])}"
                 + (". 끝 상태 뒤 반복도 위반" if t.get("strict_terminal") else ""))
    L.append("")
    L += table(["표", "대상 수", "위반 대상"], [[k, x["targets"], ", ".join(x["bad"]) or "없음"] for k, x in r5["seq"].items()])
    L.append("")
    L += table(["기체", "작업", "승인 필요", "요청", "응답", "응답 모의 s", "첫 EXECUTING 모의 s", "판정"],
               [[a["entity"], a["task"], "예" if a["need"] else "아니오", "예" if a.get("requested") else "아니오",
                 a["response"] or "없음", a["t_resp"] if a["t_resp"] is not None else "—",
                 a["t_exec"] if a["t_exec"] is not None else "—", "통과" if a.get("ok", True) else "실패"]
                for a in r5["approvals"]])
    L.append("")
    L += table(["외부 명령", "기체", "작업", "받은 내부 상태", "상태 보고"],
               [[x["src"], x["entity"], x["task"], ", ".join(x["states"]), "있음" if x["status_seen"] else "없음"]
                for x in R["c5_commands"]])
    L.append("")
    for t in r5["fail"]:
        L.append(f"- 실패: {t}")
    L.append("")
    # 9. C6
    r6 = res["C6"]
    L.append("## 9. C6 OMS / LA-CAL 왕복")
    L.append("")
    L.append(f"판정: **{r6['verdict']}**. 선언은 실행에 쓴 `lacal_server.yaml`(gateway/config에서 포트·server_id만 바꿈)의 "
             "declared, 실제 교환은 종료 직전 CAL Server `/graph`의 pub·sub 간선이다. `/tap`은 외부 클라이언트가 시작부터 연 관리 포트 "
             "WebSocket으로 센 Gateway 발신 건수다.")
    L.append("")
    L += table(["서비스", "방향", "흐름", "건수", "상태"], [[x["service"], x["kind"], x["flow"], x["count"], x["state"]]
                                                       for x in r6["declared"]])
    L.append("")
    L += table(["흐름", "/tap", "외부 수신", "일치"], [[x["flow"], x["tap"], x["ext"], "예" if x["ok"] else "아니오"]
                                                for x in r6["tap"]])
    L.append("")
    L.append("외부 송신 → 버스(GCS 송신, neg- 제외): " + ", ".join(f"{k} {n}건" for k, n in r6["inbound_bus"].items())
             + ". 기체 반영은 C5 상태 보고 표에서 본다.")
    L.append("")
    for t in r6["fail"]:
        L.append(f"- 실패: {t}")
    L.append("")
    # 10. C7
    r7 = res["C7"]
    L.append("## 10. C7 AMS-GRA 개념 차용 추적과 적용성")
    L.append("")
    L.append(f"판정: **{r7['verdict']}** (추적 항목. 준수를 주장하지 않는다, DEC-093).")
    L.append("")
    L.append("### 10.1 차용 개념 추적")
    L.append("")
    auto = {
        "ASB(Abstract Service Bus)": f"진입점 {sum(r7['entries'].values())}/{len(r7['entries'])}이 open_bus 사용 "
                                     f"({', '.join(k for k, x in r7['entries'].items() if x)}). 버스 계층 밖 직접 열기 "
                                     f"{len(r7['direct_open'])}건",
        "OMS 서비스 분해": "; ".join(f"{k}: {', '.join(x)}" for k, x in r7["ms_services"].items()),
        "Time Distribution": r7["determinism"]["text"],
        "Armament": "; ".join(r7["loadout"]) or "—",
    }
    L += table(["AMS-GRA 개념", "반영", "근거", "확인 방법", "자동 확인 결과"],
               [[a, b, g, h, auto[a]] for a, b, g, h in C7_TABLE])
    L.append("")
    ap = r7.get("applicability")
    if ap:
        L.append("### 10.2 요구별 적용성 ([46_amsgra_applicability.md](46_amsgra_applicability.md) §3)")
        L.append("")
        L.append("해당·부분은 AMS-GRA 준수를 뜻하지 않는다(문서 46 §1). 아래 요약표는 문서 46 §3을 그대로 옮겼다.")
        L.append("")
        L += table(ap["summary_head"], ap["summary"])
        L.append("")
        n_miss = sum(1 for x in ap["rows"] if x["missing"])
        n_p = sum(len(x["paths"]) for x in ap["rows"])
        n_d = sum(len(x["decs"]) for x in ap["rows"])
        L.append(f"해당·부분 {len(ap['rows'])}행의 근거 확인: 파일 경로 {n_p}개(백틱 안 확장자 있는 것)와 DEC ID {n_d}개를 "
                 f"저장소 파일 목록(`git ls-files`)과 등록부 §3에서 찾았다. 근거가 없는 행 {n_miss}개. "
                 f"§4 상세 {ap['n']}행 (해당 {ap['counts']['해당']}, 부분 {ap['counts']['부분']}, "
                 f"해당없음 {ap['counts']['해당없음']}).")
        L.append("")
        L += table(["ID", "판정", "근거 파일", "근거 DEC", "없음"],
                   [[x["id"], x["verdict"], ", ".join(f"`{p}`" for p in x["paths"]) or "—", ", ".join(x["decs"]) or "—",
                     ", ".join(x["missing"]) or "—"] for x in ap["rows"]])
        L.append("")
        L.append("- 코드 식별자(`open_bus`, `SystemStatus` 등), 버스 키, WP, 계약 절 번호는 확인하지 않는다.")
        L.append("")
    for t in r7["fail"]:
        L.append(f"- 실패: {t}")
    for t in r7.get("info", []):
        L.append(f"- 정보: {t}")
    L.append("")
    # 11. 도구
    L.append("## 11. 도구와 한계")
    L.append("")
    L += table(["파일", "역할"], [
        ["`qa/conformance/run.py`", "진입점. 정적 수집 → 점검 실행 → 판정 → 이 문서와 결과 폴더"],
        ["`qa/conformance/judges.py`", "판정 함수(C1~C7). 입력은 dict·list뿐이라 단위 시험이 위반 입력으로 직접 부른다"],
        ["`qa/conformance/harness_run.py`", "lockstep 실행, 프레임 지정 입력, 관측기(GCS 수신·송신, 기체 수신)"],
        ["`qa/conformance/analyze.py`", "원자료 짝짓기(위치 쌍, 상태 쌍, 식별자 수집, 전이 열)"],
        ["`qa/conformance/static.py`, `gw_dump.py`", "XSD·등록부·TRACE·MA import·open_bus 소스 점검, proto 옵션·변환기 등록 덤프"],
        ["`qa/conformance/agent_probe.py`", "Agent 진입점 래퍼(구독·발행 키, L1 포트 메시지)"],
        ["`qa/conformance/mcap_lite.py`", "압축 없는 MCAP 최소 읽기(채널·건수)"],
        ["`qa/conformance/findings.py`", "발견 목록과 판정 문구 대응"],
        ["`qa/conformance/tests/test_judges.py`", "판정 로직 단위 시험(위반 입력은 실패해야 한다)"],
    ])
    L.append("")
    if R.get("limits"):
        L.append("기준 문서 [44_standards_conformance.md](44_standards_conformance.md) §4 한계(그대로 옮김):")
        L.append("")
        L += [f"- {t}" for t in R["limits"]]
        L.append("")
        L.append("도구 자체의 한계:")
        L.append("")
    L.append("- 위치 대조는 기체·토픽별 도착 순서로 짝짓는다(손실 없는 링크, 앞쪽 40개로 어긋남 0을 확인). 손실이 있는 링크에서는 "
             "건수가 달라 짝짓기 방법을 바꿔야 한다.")
    L.append("- 결과 파일은 임시 파일에 쓴 뒤 바꿔 넣고, Windows에서 읽는 프로세스 때문에 PermissionError가 나면 재시도한다"
             "(`confcommon.write_json`, `qa/gw_ext_client.py`·`qa/gw_wrap.py`도 같은 방식으로 바꿨다).")
    L.append("- 외부 입력은 일시정지 중에 넣어 도착 틱을 고정했지만, 외부 클라이언트의 승인 응답은 실행 중에 나가므로 틱이 "
             "실행마다 다를 수 있다(기준 §4). 판정은 건수·전이·대조 오차로 한다.")
    L.append("")
    return "\n".join(L) + "\n"
