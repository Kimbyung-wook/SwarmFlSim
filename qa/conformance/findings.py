"""29차 발견 목록. 판정 결과의 실패·정보 문구를 match(부분 문자열)로 찾아 이번 실행에서 재현됐는지 붙인다.

번호는 QA 규칙(docs/21_qa_report.md)을 따른다: 결함 D-, 관찰 O-. 이 차수는 D-35·O-47부터. 고치지 않고 담당 WP로 보낸다.
어느 발견에도 걸리지 않은 실패는 보고서에 '미분류 실패'로 따로 나온다(새 실패를 놓치지 않게).
"""
from __future__ import annotations

FINDINGS = [
    {"id": "D-35", "item": "C2", "wp": "WP9", "level": "중간",
     "match": ["부정 입력 neg-unknown: 버스로 나감"],
     "title": "시나리오에 없는 기체(uav-999)를 가리키는 외부 MA_TaskCommand가 버스로 나간다",
     "detail": "Gateway는 CapabilityID 표지의 엔티티 이름 형식만 보고 기체가 있는지는 보지 않는다. "
               "swarm/gcs-01/tx/c2/TaskCommand(dst uav-999)가 나가고 Datalink에서 버려진다. 거부 기록도 TaskStatus도 없어 "
               "외부는 명령이 처리되지 않았다는 것을 알 수 없다."},
    {"id": "D-36", "item": "C3", "wp": "WP9", "level": "중간",
     "match": ["UCI Timestamp가 모의 시각을 따르지 않음"],
     "title": "UCI Timestamp가 모의 시각이 아니라 Gateway 벽시계다",
     "detail": "ConvContext.now 기본값이 datetime.now(UTC)이고 변환기의 Position·DomainVelocity·Orientation Timestamp와 "
               "머리 Timestamp가 모두 이 값이다. (Timestamp − 메시지 모의 시각)이 실행 중 일시정지 시간만큼 커진다. "
               "lockstep 일시정지·배속 실행에서 외부가 보는 시각이 모의 시각과 어긋난다."},
    {"id": "D-37", "item": "C5", "wp": "WP3(formation MA)·WP4(FA)", "level": "낮음",
     "match": ["fmn-beta: 허용 전이 밖 REJECTED→"],
     "title": "편대 추종기가 거부된 FlightCommand ID를 다시 써서 REJECTED 뒤 EXECUTING이 된다",
     "detail": "첫 틱에 리더 정보가 없어 mode 없는 FlightCommand(<기체>-fmn-beta)를 내고 FA가 REJECTED(no mode)로 답한다. "
               "다음 틱부터 같은 command_id로 유효한 명령을 내 EXECUTING이 된다. 끝 상태(REJECTED) 뒤 전이가 내부·외부 "
               "(MA_FlightCommandStatus REJECTED → ACCEPTED) 모두에 보인다."},
    {"id": "D-38", "item": "C1", "wp": "WP0(분류)·WP9(변환기)", "level": "낮음",
     "match": ["STD인데 변환기가 없다"],
     "title": "STD로 표시됐지만 Gateway 변환기가 없는 메시지 5종",
     "detail": "EngagementCriteria(MA_EngagementCriteria), SensorCommand(PO_Command), JammerCommand(EA_Command), "
               "StrikeCommand, FlightCommand(MA_FlightCommand). 기체 안쪽(MA→장비·FA) 메시지이거나 아직 가져오지 않는 "
               "계획 메시지다. 기준(§3 C1)은 'STD인데 변환기 없음'을 실패로 정한다. 분류를 바꿀지(예: 기체 안 STD는 "
               "Gateway 범위 밖으로 표시) 변환기를 둘지 결정이 필요하다.",
     "resolution": "DEC-094: 기체 내부 STD(계약 키 표상 swarm 밖 키로만 오감)는 'Gateway 범위 밖(기체 내부)'으로 표시하고 "
                   "변환기 없음을 실패로 보지 않는다. 30차 도구부터 이 판정 문구가 나오지 않는다"},
    {"id": "D-39", "item": "C6", "wp": "WP9", "level": "낮음",
     "match": ["external_c2 sub", "선언 밖 교환"],
     "title": "external_c2의 declared.sub가 실제 구독과 다르다",
     "detail": "gateway/config/lacal_server.yaml의 external_c2 declared.sub는 MA_TaskStatus·MA_NavigationReport 둘뿐이다. "
               "외부 클라이언트(gateway/README.md 교환 메시지 표대로)는 Gateway 발행 15흐름을 모두 구독해 받는다. "
               "accept_unknown_services=false여도 CAL Server는 선언 밖 구독을 막지 않는다."},
    {"id": "D-40", "item": "C5", "wp": "WP9(Gateway)", "level": "낮음",
     "match": ["MA_FlightCommandStatus(외부)", "허용 전이 밖 ACCEPTED→"],
     "title": "Gateway가 끝 상태 ACCEPTED를 보낸 CommandID에 상태를 더 보낸다(DEC-097)",
     "detail": "외부 MA_FlightCommandStatus에서 ACCEPTED 뒤 CANCELED(내부 CANCELLED를 그대로 냄)나 ACCEPTED 반복이 나온다. "
               "DEC-097은 ACCEPTED·REJECTED·CANCELED를 끝 상태로 두고, 같은 CommandID에 그 뒤 보고를 내지 않게 한다. "
               "29·31차 원자료를 32차 도구로 다시 판정해 찾았다(실제 재점검 전).",
     "resolution": "IMP-GW-032(ee7aad2): Gateway가 CommandID마다 끝 상태를 보낸 뒤 상태를 더 보내지 않는다. 32차 실행(2026-11-19)에서 "
                   "나오지 않았다"},
    {"id": "O-47", "item": "C5", "wp": "WP4(FA)", "level": "매우 낮음",
     "match": ["fmn-lead: 허용 전이 밖 시작→CANCEL"],
     "title": "편대 리더 명령의 첫 상태 보고가 CANCELLED(superseded)다",
     "detail": "리더의 <기체>-fmn-lead가 접수된 같은 틱에 task-1 명령으로 바뀌어, 변화 보고(DEC-056)가 ACCEPTED 없이 "
               "CANCELLED만 보낸다. 받은 쪽은 접수된 적 없는 명령의 취소를 본다. 도구 전이 표(첫 보고 ACCEPTED·EXECUTING·"
               "REJECTED·FAILED)는 그대로 두었다. 첫 보고 CANCELLED를 허용할지는 기준 문서에서 정할 일이다.",
     "resolution": "DEC-097: 내부 FlightCommandStatus는 첫 보고 CANCELLED(접수 전 대체)를 허용하고, 외부 "
                   "MA_*CommandStatus는 첫 보고 CANCELED를 허용한다(UCI Command-2 상태 기계). 32차 도구부터 이 판정 문구가 "
                   "나오지 않는다"},
    {"id": "O-48", "item": "C4", "wp": "WP3·WP4", "level": "매우 낮음",
     "match": ["플러그인 API(§5) 밖의 Agent 런타임 모듈"],
     "title": "내장 MA가 플러그인 API 밖의 Agent 런타임 모듈(swarm_agent.geo, swarm_agent.racetrack)을 import한다",
     "detail": "버스·truth·Core 모듈은 아니어서 DEC-013 경계 위반은 아니다(정보). 계약 §5 플러그인 API에 기하 도우미가 "
               "없어 런타임 모듈을 직접 쓴다. 외부 플러그인이 같은 도우미를 쓰려면 API로 올리거나 algorithms 안에 두어야 한다."},
    {"id": "O-49", "item": "C4", "wp": "WP4", "level": "매우 낮음",
     "match": ["엔티티 와일드카드 구독으로 맡지 않은 엔티티 키를 받음"],
     "title": "Agent가 swarm/*/rx/** 와일드카드 구독으로 gcs-01 수신 키까지 받는다",
     "detail": "Agent 런타임은 맡은 기체 수신만 쓰지만 구독은 엔티티 자리를 '*'로 연다. gcs-01(Gateway가 맡음)의 수신 표본도 "
               "Agent 프로세스로 온다. MA 포트 기록에는 SIM 표시 메시지가 없어 경계 위반은 아니고 받는 양만 늘어난다."},
    {"id": "O-50", "item": "C4", "wp": "WP0(계약 문서)", "level": "문서",
     "match": [],
     "title": "계약 §3.2 키 표와 §3.3 본문의 Agent 구독 키가 다르다 (3개)",
     "detail": "sim/ctrl/cmd(set_params, DEC-035)와 sim/clock/done/*(DEC-040·044)는 §3.3 본문이 Agent 구독을 정하지만 §3.2 표의 "
               "구독자 칸에는 Agent가 없다. swarm/<e>/rx/**는 §3.3(DEC-044) 표기이고 §3.2 표는 swarm/<dst>/rx/<iface>/<msg>다"
               "(Agent는 rx/**로 구독한다). 도구는 세 키를 근거와 함께 보충 허용 키로 둔다(judges.SUPPLEMENT_SUB). "
               "기준 문서(docs/44)와 계약 문서는 고치지 않았다.",
     "resolution": "계약 42c7e06(0.20.0 유지): §3.2 swarm/<dst>/rx/<iface>/<msg> 구독자 칸에 '수신 엔티티의 Agent 런타임"
                   "(자기 기체 swarm/<dst>/rx/**로 구독)'을 적었다. sim/clock/done/*·sim/ctrl/cmd는 30차에 이미 §3.2 구독자 칸에 있다. "
                   "34차에 parse_contract_keys가 구독자 칸의 구독 키 표현식도 읽게 해 SUPPLEMENT_SUB를 비웠다"},
    {"id": "O-45", "item": "C6", "wp": "WP3", "level": "낮음 (28차)",
     "match": [],
     "title": "기본 MA에 무장 경로가 없어 StrikeActivity는 시험 전용 주입으로만 나온다 (기존 O-45)",
     "detail": "계획 strike(task-003)는 기본 TaskTracker가 보고 없이 거른다. 이번 실행은 관측기가 모의 30 s에 "
               "onboard/uav-005/StrikeCommand를 직접 내 StrikeActivity 흐름을 만들었다(Agent 발행이 아니라 C4 대상 밖)."},
]


def attach(results: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """results: {C1: judge 결과, ...} → (발견에 이번 실행 근거를 붙인 목록, 미분류 실패 [(항목, 문구)])"""
    texts = []
    for item, r in results.items():
        for t in r.get("fail", []):
            texts.append((item, "fail", t))
        for t in r.get("info", []):
            texts.append((item, "info", t))
    used = set()
    out = []
    for f in FINDINGS:
        hits = []
        for i, (item, kind, t) in enumerate(texts):
            if item == f["item"] and f["match"] and all(m in t for m in f["match"]):
                hits.append(t)
                used.add(i)
        out.append({**f, "hits": hits})
    loose = [(item, t) for i, (item, kind, t) in enumerate(texts) if kind == "fail" and i not in used]
    return out, loose
