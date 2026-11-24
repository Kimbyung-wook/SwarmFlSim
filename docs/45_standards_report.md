커밋 `e012aab` (작업 트리에 커밋 전 변경 있음) · 계약 0.24.0 · agra_lacal `45274ce` · 실행 2026-11-24

# 표준 적합성 점검 보고 (REQ-STD-001, DEC-092)

이 문서는 `qa/conformance/run.py`가 만든다(손으로 고치지 않는다). 판정 기준은 [44_standards_conformance.md](44_standards_conformance.md) C1~C7이다. 원자료는 `qa/out/conformance/2026-11-24-env2`에 있다.
자체 점검이다(기준 §4). 공식 A-GRA 적합성 도구와 Distribution D 문서는 쓰지 않았다.

## 1. 요약

| 항목 | 내용 | 판정 | 핵심 수치 | 발견 |
|---|---|---|---|---|
| C1 | 적용 범위 표 | 통과 | XSD 860(MA_ 179), 대응 UCI 23, 송신 14·수신 4, 실패 0 | — |
| C2 | 형식 검증 (UCI) | 통과 | 수신 9313건·실패 0, 부정 입력 14종 중 버스로 나감 0 | — |
| C3 | 값 의미 검증 (UCI) | 통과 | 위치 2030쌍 최대 차 0 rad, Timestamp 변동 0.00 s | — |
| C4 | A-GRA 기체 계층 경계 | 통과 | 구독 103·발행 125키, 허용 밖 0, SIM 포트 메시지 0 | O-50 |
| C5 | 상호작용 상태 흐름 | 통과 | 전이 위반 0건, 승인 필요 4건 중 위반 0 | — |
| C6 | OMS / LA-CAL 왕복 | 통과 | 선언 불일치 0, /tap 불일치 0 | O-45 |
| C7 | AMS-GRA 개념 차용 추적과 적용성 | 정보 | 버스 직접 열기 0, 진입점 open_bus 6/6, 적용성 해당·부분 30행 중 근거 없음 0 | — |

통과 6, 실패 0, 정보 1. 실패 항목은 고치지 않고 아래 발견으로 담당 WP에 보낸다.

## 2. 발견

| ID | 항목 | 내용 | 담당 | 중요도 | 이번 실행 |
|---|---|---|---|---|---|
| D-35 | C2 | 시나리오에 없는 기체(uav-999)를 가리키는 외부 MA_TaskCommand가 버스로 나간다 | WP9 | 중간 | 이번 실행에 없음 |
| D-36 | C3 | UCI Timestamp가 모의 시각이 아니라 Gateway 벽시계다 | WP9 | 중간 | 이번 실행에 없음 |
| D-37 | C5 | 편대 추종기가 거부된 FlightCommand ID를 다시 써서 REJECTED 뒤 EXECUTING이 된다 | WP3(formation MA)·WP4(FA) | 낮음 | 이번 실행에 없음 |
| D-38 | C1 | STD로 표시됐지만 Gateway 변환기가 없는 메시지 5종 | WP0(분류)·WP9(변환기) | 낮음 | 이번 실행에 없음 |
| D-39 | C6 | external_c2의 declared.sub가 실제 구독과 다르다 | WP9 | 낮음 | 이번 실행에 없음 |
| D-40 | C5 | Gateway가 끝 상태 ACCEPTED를 보낸 CommandID에 상태를 더 보낸다(DEC-097) | WP9(Gateway) | 낮음 | 이번 실행에 없음 |
| O-47 | C5 | 편대 리더 명령의 첫 상태 보고가 CANCELLED(superseded)다 | WP4(FA) | 매우 낮음 | 이번 실행에 없음 |
| O-48 | C4 | 내장 MA가 플러그인 API 밖의 Agent 런타임 모듈(swarm_agent.geo, swarm_agent.racetrack)을 import한다 | WP3·WP4 | 매우 낮음 | 이번 실행에 없음 |
| O-49 | C4 | Agent가 swarm/*/rx/** 와일드카드 구독으로 gcs-01 수신 키까지 받는다 | WP4 | 매우 낮음 | 이번 실행에 없음 |
| O-50 | C4 | 계약 §3.2 키 표와 §3.3 본문의 Agent 구독 키가 다르다 (3개) | WP0(계약 문서) | 문서 | 해당 없음(문서·기존) |
| O-53 | C3 | 시작 때 Gateway가 sim/ctrl/scenario를 기체 보고보다 늦게 받거나 받지 못해 첫 메시지 기준을 쓴다 | WP1(Core)·WP9(Gateway) | 보통 (38차) | 이번 실행에 없음 |
| O-45 | C6 | 기본 MA에 무장 경로가 없어 StrikeActivity는 시험 전용 주입으로만 나온다 (기존 O-45) | WP3 | 낮음 (28차) | 해당 없음(문서·기존) |

- **D-35** Gateway는 CapabilityID 표지의 엔티티 이름 형식만 보고 기체가 있는지는 보지 않는다. swarm/gcs-01/tx/c2/TaskCommand(dst uav-999)가 나가고 Datalink에서 버려진다. 거부 기록도 TaskStatus도 없어 외부는 명령이 처리되지 않았다는 것을 알 수 없다.
- **D-36** ConvContext.now 기본값이 datetime.now(UTC)이고 변환기의 Position·DomainVelocity·Orientation Timestamp와 머리 Timestamp가 모두 이 값이다. (Timestamp − 메시지 모의 시각)이 실행 중 일시정지 시간만큼 커진다. lockstep 일시정지·배속 실행에서 외부가 보는 시각이 모의 시각과 어긋난다.
- **D-37** 첫 틱에 리더 정보가 없어 mode 없는 FlightCommand(<기체>-fmn-beta)를 내고 FA가 REJECTED(no mode)로 답한다. 다음 틱부터 같은 command_id로 유효한 명령을 내 EXECUTING이 된다. 끝 상태(REJECTED) 뒤 전이가 내부·외부 (MA_FlightCommandStatus REJECTED → ACCEPTED) 모두에 보인다.
- **D-38** EngagementCriteria(MA_EngagementCriteria), SensorCommand(PO_Command), JammerCommand(EA_Command), StrikeCommand, FlightCommand(MA_FlightCommand). 기체 안쪽(MA→장비·FA) 메시지이거나 아직 가져오지 않는 계획 메시지다. 기준(§3 C1)은 'STD인데 변환기 없음'을 실패로 정한다. 분류를 바꿀지(예: 기체 안 STD는 Gateway 범위 밖으로 표시) 변환기를 둘지 결정이 필요하다.
  - 조치: DEC-094: 기체 내부 STD(계약 키 표상 swarm 밖 키로만 오감)는 'Gateway 범위 밖(기체 내부)'으로 표시하고 변환기 없음을 실패로 보지 않는다. 30차 도구부터 이 판정 문구가 나오지 않는다
- **D-39** gateway/config/lacal_server.yaml의 external_c2 declared.sub는 MA_TaskStatus·MA_NavigationReport 둘뿐이다. 외부 클라이언트(gateway/README.md 교환 메시지 표대로)는 Gateway 발행 15흐름을 모두 구독해 받는다. accept_unknown_services=false여도 CAL Server는 선언 밖 구독을 막지 않는다.
- **D-40** 외부 MA_FlightCommandStatus에서 ACCEPTED 뒤 CANCELED(내부 CANCELLED를 그대로 냄)나 ACCEPTED 반복이 나온다. DEC-097은 ACCEPTED·REJECTED·CANCELED를 끝 상태로 두고, 같은 CommandID에 그 뒤 보고를 내지 않게 한다. 29·31차 원자료를 32차 도구로 다시 판정해 찾았다(실제 재점검 전).
  - 조치: IMP-GW-032(ee7aad2): Gateway가 CommandID마다 끝 상태를 보낸 뒤 상태를 더 보내지 않는다. 32차 실행(2026-11-19)에서 나오지 않았다
- **O-47** 리더의 <기체>-fmn-lead가 접수된 같은 틱에 task-1 명령으로 바뀌어, 변화 보고(DEC-056)가 ACCEPTED 없이 CANCELLED만 보낸다. 받은 쪽은 접수된 적 없는 명령의 취소를 본다. 도구 전이 표(첫 보고 ACCEPTED·EXECUTING·REJECTED·FAILED)는 그대로 두었다. 첫 보고 CANCELLED를 허용할지는 기준 문서에서 정할 일이다.
  - 조치: DEC-097: 내부 FlightCommandStatus는 첫 보고 CANCELLED(접수 전 대체)를 허용하고, 외부 MA_*CommandStatus는 첫 보고 CANCELED를 허용한다(UCI Command-2 상태 기계). 32차 도구부터 이 판정 문구가 나오지 않는다
- **O-48** 버스·truth·Core 모듈은 아니어서 DEC-013 경계 위반은 아니다(정보). 계약 §5 플러그인 API에 기하 도우미가 없어 런타임 모듈을 직접 쓴다. 외부 플러그인이 같은 도우미를 쓰려면 API로 올리거나 algorithms 안에 두어야 한다.
- **O-49** Agent 런타임은 맡은 기체 수신만 쓰지만 구독은 엔티티 자리를 '*'로 연다. gcs-01(Gateway가 맡음)의 수신 표본도 Agent 프로세스로 온다. MA 포트 기록에는 SIM 표시 메시지가 없어 경계 위반은 아니고 받는 양만 늘어난다.
- **O-50** sim/ctrl/cmd(set_params, DEC-035)와 sim/clock/done/*(DEC-040·044)는 §3.3 본문이 Agent 구독을 정하지만 §3.2 표의 구독자 칸에는 Agent가 없다. swarm/<e>/rx/**는 §3.3(DEC-044) 표기이고 §3.2 표는 swarm/<dst>/rx/<iface>/<msg>다(Agent는 rx/**로 구독한다). 도구는 세 키를 근거와 함께 보충 허용 키로 둔다(judges.SUPPLEMENT_SUB). 기준 문서(docs/44)와 계약 문서는 고치지 않았다.
  - 조치: 계약 42c7e06(0.20.0 유지): §3.2 swarm/<dst>/rx/<iface>/<msg> 구독자 칸에 '수신 엔티티의 Agent 런타임(자기 기체 swarm/<dst>/rx/**로 구독)'을 적었다. sim/clock/done/*·sim/ctrl/cmd는 30차에 이미 §3.2 구독자 칸에 있다. 34차에 parse_contract_keys가 구독자 칸의 구독 키 표현식도 읽게 해 SUPPLEMENT_SUB를 비웠다
- **O-53** Gateway SimClock은 시나리오를 받기 전 첫 메시지 벽시계로 기준을 정한다. 뒤에 시나리오가 오면 바꾸고(epoch_changed), 끝내 오지 않으면 첫 메시지 기준이 남는다. 38차 적합성 8회 중 3회. 이때 'UCI Timestamp가 모의 시각을 따르지 않음' 문구가 같이 나오면 D-36(벽시계 Timestamp)이 아니라 이 관찰 때문이다. epoch_changed와 epoch 불일치 문구도 시작 때 기준이 바뀐 결과라 이 관찰로 묶는다(적합성 실행은 실행 중 시나리오를 다시 적재하지 않는다).
  - 조치: DEC-109(계약 0.24.0): Core가 sim/ctrl/scenario 조회에 답하고(WP1) Gateway가 시작 때 조회한다(WP9). 구현·병합 뒤 다시 시험한다
- **O-45** 계획 strike(task-003)는 기본 TaskTracker가 보고 없이 거른다. 이번 실행은 관측기가 모의 30 s에 onboard/uav-005/StrikeCommand를 직접 내 StrikeActivity 흐름을 만들었다(Agent 발행이 아니라 C4 대상 밖).

미분류 실패는 없다(모든 실패가 위 발견 중 하나에 걸린다).

## 3. 점검 실행

| 구분 | 내용 |
|---|---|
| 구성 | Logger(MCAP) · Datalink(participant datalink-0) · Agent(`agent_probe.py`가 감싼 swarm_agent.cli, agent-0) · Core(lockstep 1배속, 50 Hz, 평지) · CAL Server(agra_lacal, `lacal_server.yaml`에서 포트·server_id만 바꿈) · Gateway(`qa/gw_wrap.py`) · 외부 클라이언트(`qa/gw_ext_client.py`, external_c2) |
| 시나리오 | `qa/out/conformance/2026-11-24-env2/run1/scenario.json` 시드 20261117. gcs-01, 기체 14대(waypoint 8, 정지 사수 1, formation 3, flocking_basic 3), 표적 1. 손실 없는 링크 |
| 포트 | CAL 28765/28766, Zenoh 48900~48930 (기본 데모 8765/8766·7447과 겹치지 않음) |
| 시간 | 모의 70.0 s, 벽시계 88 s (점검 전체 271 s) |
| 프로세스 종료 | 띄운 PID만 정리: {'logger': 12424, 'datalink': 18392, 'agent': 1644, 'core': 24432, 'calsrv': 23580, 'ext': 680, 'gateway.1': 36428}. 끝날 때 죽어 있던 프로세스: 없음 (외부 클라이언트 ext는 STOP 파일을 받고 스스로 끝난다. 정상) |
| 로그 이상 | 0줄 |
| 외부 교환(39차) | 봉투 켬(DEC-111, `lacal_server.yaml`). Gateway를 Core보다 먼저 띄움. Gateway 시나리오 받음: ['run1: query=5 by_query=0 by_subscription=1 duplicate=0 query_none=1 query_error=0', 'run2: query=5 by_query=0 by_subscription=1 duplicate=0 query_none=1 query_error=0', 'run3: query=5 by_query=0 by_subscription=1 duplicate=0 query_none=1 query_error=0'] |

입력은 Core를 일시정지한 프레임에서 넣었다(StepFrames로 정확한 프레임까지 간 뒤). 유효 입력은 Gateway가 버스에 낸 것을 관측기가 본 뒤 재개했다.

| 모의 s | 프레임 | 입력 | CAL 응답 | 버스(GCS 송신) |
|---|---|---|---|---|
| 10.0 | 500 | send ap-yes hold uav-001 | +OK | TaskCommand ap-yes |
| 10.0 | 500 | send ap-no hold uav-002 | +OK | TaskCommand ap-no |
| 10.0 | 500 | send ap-to hold uav-003 | +OK | TaskCommand ap-to |
| 10.0 | 500 | send x-hold hold uav-009 | +OK | TaskCommand x-hold |
| 10.0 | 500 | send x-rtb return_to_base uav-010 | +OK | TaskCommand x-rtb |
| 10.0 | 500 | send route r-c1 uav-011 | +OK | RoutePlan r-c1 |
| 14.0 | 700 | send mission plan-c1 uav-011 | +OK | MissionPlan plan-c1 |
| 22.0 | 1100 | query q-c1 MA_TASK_STATUS | +OK |  |
| 22.0 | 1100 | send cancel x-hold uav-009 | +OK | TaskCommand x-hold |
| 26.0 | 1300 | neg neg-xsd-cmdstate | +OK |  |
| 26.0 | 1300 | neg neg-strike | +OK |  |
| 26.0 | 1300 | neg neg-unknown | +OK |  |
| 26.0 | 1300 | neg neg-caplabel | +OK |  |
| 26.0 | 1300 | neg neg-pending | +OK |  |
| 26.0 | 1300 | neg neg-xsd-enum | +OK |  |
| 26.0 | 1300 | neg neg-route-all | +OK |  |
| 26.0 | 1300 | neg neg-route-cycle | +OK |  |
| 26.0 | 1300 | neg neg-mission-unknown | +OK |  |
| 26.0 | 1300 | neg neg-xsd-route | +OK |  |
| 26.0 | 1300 | neg neg-env-notaddr | +OK |  |
| 26.0 | 1300 | neg neg-env-mtype | +OK |  |
| 26.0 | 1300 | neg neg-env-none | +OK |  |
| 26.0 | 1300 | neg neg-env-ascii | +OK |  |
| 30.0 | 1500 | strike stimulus onboard/uav-005/StrikeCommand (시험 전용) |  |  |

같은 커밋 재실행 3회의 판정 비교: 판정과 실패 문구(수치 제외)가 모두 같다

| 항목 | 실행 1 | 실행 2 | 실행 3 | 판정·문구 같음(수치 제외) | 수치까지 같음 |
|---|---|---|---|---|---|
| C2 | 통과 (0) | 통과 (0) | 통과 (0) | 예 | 예 |
| C3 | 통과 (0) | 통과 (0) | 통과 (0) | 예 | 예 |
| C4 | 통과 (0) | 통과 (0) | 통과 (0) | 예 | 예 |
| C5 | 통과 (0) | 통과 (0) | 통과 (0) | 예 | 예 |
| C6 | 통과 (0) | 통과 (0) | 통과 (0) | 예 | 예 |

- 괄호는 실패 문구 수. 외부 클라이언트의 승인 응답과 수신은 실행 중에 오가므로 건수·Timestamp 차 같은 수치는 실행마다 조금 다를 수 있다(기준 §4).

## 4. C1 적용 범위 표

판정: **통과**. 공개 XSD 최상위 요소 860개, 그중 `MA_` 179개. proto가 대응한 UCI 메시지 23개(`MA_` 15), 송신 14·수신 4. proto 구분 STD 22, EXT 5, SIM 14. 상태별 행 수 {'Gateway 범위 밖(기체 내부)': 5, '구현·시험됨': 19, '미구현': 13, '확장(외부 비공개)': 8}.

구현·시험됨 = 변환기가 있고 이번 실행에서 외부와 실제로 오갔고 gateway/TRACE.md에 IMP·TC가 있다. 부분 = 변환기는 있으나 셋 중 하나가 없다. 미구현은 실패가 아니다(범위 표시). Gateway 범위 밖(기체 내부) = GCS 경계를 넘지 않는 STD라 변환기 없음을 실패로 보지 않는다(DEC-094).

| L1 | 상호작용 | UCI 메시지 | 방향 | 구분 | 범위 | 내부 메시지 | 변환기 | 구현 ID | 시험 ID | 상태 |
|---|---|---|---|---|---|---|---|---|---|---|
| VI | 비행 명령(HSA/Waypoint/Curve)과 수락·거부 | MA_FlightCommand | — | STD | 기체 내부 | FlightCommand | 없음 |  |  | Gateway 범위 밖(기체 내부) |
| VI | 비행 명령(HSA/Waypoint/Curve)과 수락·거부 | MA_FlightCommandStatus | 송신 | STD | GCS 경계 | FlightCommandStatus | 있음 | IMP-GW-005, IMP-GW-024, IMP-GW-027, IMP-GW-032 | TC-GW-003, TC-GW-028, TC-GW-033, TC-GW-039, TC-GW-040, TC-GW-041 | 구현·시험됨 |
| VI | 비행 성능 조회 | MA_FlightCapability | 송신 | STD | GCS 경계 | FlightCapability | 있음 | IMP-GW-005, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| VI | 비행 성능 조회 | MA_FlightCapabilityStatus | — | STD | — | — | 없음 |  |  | 미구현 |
| VI | 기체 상태·위치 | PositionReport | — | STD | — | — | 없음 |  |  | 미구현 |
| VI | 기체 상태·위치 | MA_PositionReport | 송신 | STD | GCS 경계 | PeerStatus | 있음 | IMP-GW-007, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| VI | 기체 상태·위치 | MA_PositionReport | 송신 | STD | GCS 경계 | NavigationReport | 있음 | IMP-GW-005, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| VI | 기체 상태·위치 | MA_NavigationReport | 송신 | STD | GCS 경계 | NavigationReport | 있음 | IMP-GW-005, IMP-GW-024, IMP-GW-031 | TC-GW-003, TC-GW-028, TC-GW-038 | 구현·시험됨 |
| VI | 하위 시스템 상태 | SystemStatus | 송신 | STD | GCS 경계 | SystemStatus | 있음 | IMP-GW-005, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| VI | 하위 시스템 상태 | SubsystemStatus | — | STD | — | — | 없음 |  |  | 미구현 |
| C2 | 임무 부여 | MA_TaskCommand | 수신 | STD | GCS 경계 | TaskCommand | 있음 | IMP-GW-006, IMP-GW-011, IMP-GW-029 | TC-GW-003, TC-GW-007, TC-GW-008, TC-GW-010, TC-GW-011, TC-GW-035, TC-GW-036 | 구현·시험됨 |
| C2 | 임무 부여 | MA_TaskStatus | 송신 | STD | GCS 경계 | TaskStatus | 있음 | IMP-GW-006, IMP-GW-024, IMP-GW-027, IMP-GW-029, IMP-GW-031 | TC-GW-003, TC-GW-007, TC-GW-008, TC-GW-028, TC-GW-033, TC-GW-035, TC-GW-036, TC-GW-038 | 구현·시험됨 |
| C2 | 팀(패키지) 구성 | MA_PackageManagementCommand | — | STD | — | — | 없음 |  |  | 미구현 |
| C2 | 팀(패키지) 구성 | MA_PackageManagementCommandStatus | — | STD | — | — | 없음 |  |  | 미구현 |
| C2 | 타격 승인 | MA_ApprovalRequest | 송신 | STD | GCS 경계 | ApprovalRequest | 있음 | IMP-GW-006, IMP-GW-024, IMP-GW-026 | TC-GW-003, TC-GW-007, TC-GW-008, TC-GW-028, TC-GW-031, TC-GW-032 | 구현·시험됨 |
| C2 | 타격 승인 | MA_ApprovalRequestStatus | 수신 | STD | GCS 경계 | ApprovalResponse | 있음 | IMP-GW-020 | TC-GW-019, TC-GW-020 | 구현·시험됨 |
| C2 | 타격 승인 | StrikeConsentRequest | — | STD | — | — | 없음 |  |  | 미구현 |
| C2 | 운용자 역할(RBAC) | MA_OperatorRole | — | STD | — | — | 없음 |  |  | 미구현 |
| C2 | 운용자 역할(RBAC) | MA_Authorization | — | STD | — | — | 없음 |  |  | 미구현 |
| C2 | 편대 형태 지정(RTS 명령) | — | — | EXT | — |  | — |  |  | 확장(외부 비공개) |
| C2 | 항로점별 행위가 있는 항로 비행(`RouteTask`) | — | — | EXT | — |  | — |  |  | 확장(외부 비공개) |
| P2P | 리더 선출 | MA_RaftVoteRequest | — | STD | — | — | 없음 |  |  | 미구현 |
| P2P | 리더 선출 | MA_RaftAppendEntriesRequest | — | STD | — | — | 없음 |  |  | 미구현 |
| P2P | 리더 선출 | MA_LeaderUpdateRequest | 송신 | STD | GCS 경계 | LeaderUpdate | 있음 | IMP-GW-007, IMP-GW-024, IMP-GW-026 | TC-GW-003, TC-GW-028, TC-GW-031, TC-GW-032 | 구현·시험됨 |
| P2P | COP 공유 | MA_Entity | 송신 | STD | GCS 경계 | TrackShare | 있음 | IMP-GW-007, IMP-GW-024, IMP-GW-026, IMP-GW-030 | TC-GW-003, TC-GW-028, TC-GW-031, TC-GW-032, TC-GW-037 | 구현·시험됨 |
| P2P | COP 공유 | MA_PackagePartnerStatusReport | 송신 | STD | GCS 경계 | PeerStatus | 있음 | IMP-GW-007, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| MS | 데이터 전송(DMS) | MA_TxDataPayloadCommand | — | STD | — | — | 없음 |  |  | 미구현 |
| MS | 데이터 전송(DMS) | MA_RxDataPayload | — | STD | — | — | 없음 |  |  | 미구현 |
| MS | 카메라 | PO_Command | — | STD | 기체 내부 | SensorCommand | 없음 |  |  | Gateway 범위 밖(기체 내부) |
| MS | 카메라 | PO_Activity | 송신 | STD | GCS 경계 | SensorActivity | 있음 | IMP-GW-008, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| MS | 재밍 | EA_Command | — | STD | 기체 내부 | JammerCommand | 없음 |  |  | Gateway 범위 밖(기체 내부) |
| MS | 재밍 | EA_Activity | 송신 | STD | GCS 경계 | JammerActivity | 있음 | IMP-GW-008, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| MS | 타격·무장 | StrikeCommand | — | STD | 기체 내부 | StrikeCommand | 없음 |  |  | Gateway 범위 밖(기체 내부) |
| MS | 타격·무장 | StrikeActivity | 송신 | STD | GCS 경계 | StrikeActivity | 있음 | IMP-GW-008, IMP-GW-024 | TC-GW-003, TC-GW-028 | 구현·시험됨 |
| MS | 타격·무장 | StoreLoadoutConfiguration | 송신 | STD | GCS 경계 | StoreLoadout | 있음 | IMP-GW-008, IMP-GW-024, IMP-GW-026 | TC-GW-003, TC-GW-028, TC-GW-031, TC-GW-032 | 구현·시험됨 |
| MS | 타격·무장 | MA_WEZ | — | STD | — | — | 없음 |  |  | 미구현 |
| MP | 임무 계획, 교전 기준 | MA_MissionPlan | 수신 | STD | GCS 경계 | MissionPlan | 있음 | IMP-GW-021, IMP-GW-029 | TC-GW-021, TC-GW-022, TC-GW-023, TC-GW-024, TC-GW-035, TC-GW-036 | 구현·시험됨 |
| MP | 임무 계획, 교전 기준 | MA_EngagementCriteria | — | STD | 기체 내부 | EngagementCriteria | 없음 |  |  | Gateway 범위 밖(기체 내부) |
| MP | 임무 계획, 교전 기준 | MA_RoutePlan | 수신 | STD | GCS 경계 | RoutePlan | 있음 | IMP-GW-021, IMP-GW-029 | TC-GW-021, TC-GW-022, TC-GW-023, TC-GW-024, TC-GW-035, TC-GW-036 | 구현·시험됨 |
| Sim | 일시정지, 배속, 고장 주입, 리셋 | — | — | EXT | — |  | — |  |  | 확장(외부 비공개) |
| C2 | (proto EXT) | — | — | EXT | — | GcsHeartbeat | 없음 |  |  | 확장(외부 비공개) |
| C2 | (proto EXT) | — | — | EXT | — | FormationCommand | 없음 |  |  | 확장(외부 비공개) |
| C2 | (proto EXT) | — | — | EXT | — | GroupAssignment | 없음 |  |  | 확장(외부 비공개) |
| MS | (proto EXT) | — | — | EXT | — | Detection | 없음 |  |  | 확장(외부 비공개) |
| P2P | (proto EXT) | — | — | EXT | — | PeerAlgorithmMessage | 없음 |  |  | 확장(외부 비공개) |

범위 구분(DEC-094, 기준 C1 '범위 구분'): 계약 docs/10_contracts.md §3.2 키 표의 메시지 칸(이름, `*Command` 같은 끝 맞춤, 그 메시지의 필드)이 가리키는 키를 모으고, §3.3 글머리 중 `swarm/` 키가 있는 덩어리에 이름이 나오는지 본다. swarm 밖 키로만 오가고 swarm 근거도 Gateway 변환기도 없으면 기체 내부다. 목록을 손으로 두지 않는다.

| STD 메시지 | swarm 밖 키 | swarm 근거(§3.3) | 범위 |
|---|---|---|---|
| TaskCommand | sim/ctrl/cmd, sim/ctrl/scenario, onboard/<id>/<msg> | GCS Heartbeat와 링크 상실 행동 (DEC-078) | GCS 경계 |
| MissionPlan | sim/ctrl/cmd, sim/ctrl/scenario | — | GCS 경계(변환기 있음) |
| EngagementCriteria | sim/ctrl/cmd, sim/ctrl/scenario | — | 기체 내부 |
| SensorCommand | onboard/<id>/<msg> | — | 기체 내부 |
| SensorActivity | onboard/<id>/<msg> | 임무장비 상태 보고 (DEC-051) | GCS 경계 |
| JammerCommand | onboard/<id>/<msg> | — | 기체 내부 |
| JammerActivity | onboard/<id>/<msg> | 임무장비 상태 보고 (DEC-051) | GCS 경계 |
| StrikeCommand | onboard/<id>/<msg> | — | 기체 내부 |
| StrikeActivity | onboard/<id>/<msg> | 임무장비 상태 보고 (DEC-051) | GCS 경계 |
| FlightCommand | onboard/<id>/<msg> | — | 기체 내부 |
| NavigationReport | onboard_batch/NavigationBatch | 기체 VI 상태 보고 (DEC-071) | GCS 경계 |
| SystemStatus | onboard/<id>/<msg> | 기체 VI 상태 보고 (DEC-071) | GCS 경계 |

- 표에 없는 STD 메시지는 키 표가 swarm 밖 키로 가리키지 않아 `swarm/**`(LinkEnvelope)로 오가는 GCS 경계로 본다.

- 정보: MissionPlan: 계약 키 표로는 swarm 밖 키(sim/ctrl/cmd, sim/ctrl/scenario)로만 오가지만 Gateway 변환기가 있어 GCS 경계로 본다

## 5. C2 형식 검증

판정: **통과**. 외부 클라이언트가 공개 XSD를 따로 적재해 받은 메시지와 보낸 메시지를 다시 검증했다.

| 수신 UCI | 건수 | 재검증 실패 |
|---|---|---|
| EA_Activity | 70 | 0 |
| MA_ApprovalRequest | 5 | 0 |
| MA_Entity | 117 | 0 |
| MA_FlightCapability | 14 | 0 |
| MA_FlightCommandStatus | 19 | 0 |
| MA_LeaderUpdateRequest | 1 | 0 |
| MA_NavigationReport | 980 | 0 |
| MA_PackagePartnerStatusReport | 1050 | 0 |
| MA_PositionReport | 2030 | 0 |
| MA_TaskStatus | 33 | 0 |
| PO_Activity | 4969 | 0 |
| QueryDataRequestStatus | 2 | 0 |
| StoreLoadoutConfiguration | 8 | 0 |
| StrikeActivity | 1 | 0 |
| SystemStatus | 14 | 0 |

| 송신 UCI(정상 입력) | 건수 | 재검증 실패 |
|---|---|---|
| MA_ApprovalRequestStatus | 3 | 0 |
| MA_MissionPlan | 1 | 0 |
| MA_RoutePlan | 1 | 0 |
| MA_TaskCommand | 6 | 0 |
| QueryDataRequest | 1 | 0 |

봉투(DEC-111): 받은 봉투 9313건(MA_TxDataPayloadCommand) — 봉투 재검증 실패 0, MessageType 불일치 0, ASCII 아님 0, 봉투 머리 ≠ 내부 머리 0(정보), 봉투 없이 받음 0. 보낸 봉투(정상 입력) 12건 중 재검증 실패 0. 위 수신·송신 표는 봉투를 푼 내부 메시지 기준이다.

| 부정 입력 | 내용 | 외부 사전 검증 | CAL Server | 거부 기록 | 버스로 나감 |
|---|---|---|---|---|---|
| neg-xsd-cmdstate | XSD 위반 CommandState | XSD 위반 | +OK | Gateway 거부: rejected:MA_RxDataPayload:inner message invalid: schema validation failed: line 2: Element '{https://www.vdl.afrl.af.mil/programs/oam}CommandState': [facet 'enumeration'] The value 'BOGUS' is not an e | 아니오 |
| neg-strike | 가져오기 범위 밖 작업(strike) | 통과 | +OK | Gateway 거부: rejected:MA_TaskCommand:TaskCommand: unsupported task kind(s) ['strike'] | 아니오 |
| neg-unknown | 시나리오에 없는 기체 uav-999 | 통과 | +OK | Gateway 거부: rejected:MA_TaskCommand:TaskCommand: unknown entity ['uav-999'] (not in scenario or reports to gcs-01) | 아니오 |
| neg-caplabel | CapabilityID 표지가 '<엔티티>/<작업>' 형식이 아님 | 통과 | +OK | Gateway 거부: rejected:MA_TaskCommand:TaskCommand: CapabilityID label 'not an entity' does not name an entity | 아니오 |
| neg-pending | 최종 응답이 아닌 승인 상태(PENDING) | 통과 | +OK | Gateway 거부: rejected:MA_ApprovalRequestStatus:ApprovalResponse: ApprovalRequestProcessingState PENDING has no internal form | 아니오 |
| neg-xsd-enum | XSD 위반 enum(RequestProcessingState DONE) | XSD 위반 | +OK | Gateway 거부: rejected:MA_RxDataPayload:inner message invalid: schema validation failed: line 2: Element '{https://www.vdl.afrl.af.mil/programs/oam}RequestProcessingState': [facet 'enumeration'] The value 'DONE' is | 아니오 |
| neg-route-all | 적용 대상 ALL(기체 하나가 아님) | 통과 | +OK | Gateway 거부: rejected:MA_RoutePlan:RoutePlan: RoutePlan: only ApplicableToIDs/SystemID is supported, got ['ALL'] | 아니오 |
| neg-route-cycle | 경로 구간 순환 | 통과 | +OK | Gateway 거부: rejected:MA_RoutePlan:RoutePlan: segment cycle at 3a5780ca-930b-5310-8ca9-03b68063d239 | 아니오 |
| neg-mission-unknown | 받은 적 없는 RoutePlan을 가리키는 MissionPlan | 통과 | +OK | Gateway 거부: rejected:MA_MissionPlan:MissionPlan: RoutePlan b16ac80f-ac7e-50c6-ae13-ec66e5360f62 was not received (or version differs) | 아니오 |
| neg-xsd-route | XSD 위반(필수 요소 없음) | XSD 위반 | +OK | Gateway 거부: rejected:MA_RxDataPayload:inner message invalid: schema validation failed: line 2: Element '{https://www.vdl.afrl.af.mil/programs/oam}MessageData': Missing child element(s). Expected is one of ( {http | 아니오 |
| neg-env-notaddr | SpecificDestinationID에 Gateway UUID가 없다(무시해야 한다) | 통과 | +OK | Gateway 거부: envelope_not_addressed (무시) | 아니오 |
| neg-env-mtype | 봉투 MessageType이 내부 메시지와 다르다 | 통과 | +OK | Gateway 거부: rejected:MA_RxDataPayload:MessageType MA_ROUTE_PLAN does not match inner MA_TaskCommand | 아니오 |
| neg-env-none | 봉투 없이 내부 메시지를 그대로 보냄 | 통과 | +OK | Gateway 구독 없음: MA_TaskCommand@swarm.c2는 Gateway에 배달되지 않음(/graph) | 아니오 |
| neg-env-ascii | 내부 XML에 ASCII가 아닌 바이트 | XSD 위반 | +OK | Gateway 거부: rejected:MA_RxDataPayload:EncodedPayload is not ASCII | 아니오 |

## 6. C3 값 의미 검증

판정: **통과**. Gateway 입력(GCS 수신 NavigationReport·PeerStatus, 도·m)과 UCI `MA_PositionReport`(swarm.vi·swarm.p2p, rad·m)를 기체·토픽별 도착 순서로 짝지어 2030쌍을 대조했다. 자세는 도구가 쿼터니언에서 회전행렬을 거쳐 따로 구한 ZYX 오일러각과 비교했다(Gateway 식과 다른 계산 경로).

| 대조 | 허용 오차 | 최대 차 | 판정 |
|---|---|---|---|
| 위도·경도 (rad) | 1e-09 | 0 | 통과 |
| 고도 MSL (m) | 1e-06 | 0 | 통과 |
| NED 속도 (m/s) | 1e-09 | 0 | 통과 |
| NED→FRD 오일러각 (rad) | 1e-06 | 0 | 통과 |
| Timestamp − 모의 시각 변동 (s) | 0.5 | 2.38e-07 | 통과 |
| 수신 RoutePlan 좌표 (°) / 고도 (m) | 1e-09 / 1e-09 | GCS 송신 mp/RoutePlan 0/0 (3→3점) · uav-011 수신 0/0 (3→3점) | 통과 |
| Timestamp − 모의 시각 = 시나리오 epoch (s) | 0.5 | 0.000000 | 통과 |
| Gateway epoch_changed | 0 | 0 | 통과 |
| Gateway 시각 기준 | scenario | scenario | 통과 |

Timestamp: 2030건, (Timestamp − 모의 시각) 최소 1795501429.945747 s, 최대 1795501429.945747 s.

시각 기준(DEC-098): 관측한 `sim/ctrl/scenario` epoch_utc_us [1795501429945747], Gateway 카운터 {'epoch_set': 1, 'epoch_changed': 0}. Gateway 로그의 기준 관련 줄 0건.

| 식별자 종류 | 참조 수 | 내부 ID 수 | 같은 ID에 UUID 여럿 | 같은 UUID에 표지 여럿 | 표지 없음 |
|---|---|---|---|---|---|
| RequestID | 8 | 7 | 0 | 0 | 0 |
| OperatorRoleID | 5 | 1 | 0 | 0 | 0 |
| ApprovalPolicyID | 5 | 1 | 0 | 0 | 0 |
| TaskID | 51 | 10 | 0 | 0 | 0 |
| CapabilityID | 5054 | 24 | 0 | 0 | 0 |
| StoreLoadoutConfigurationID | 8 | 8 | 0 | 0 | 0 |
| SystemID | 4237 | 15 | 0 | 0 | 0 |
| RequestingSystemID | 1 | 1 | 0 | 0 | 0 |
| ProposedLeaderID | 1 | 1 | 0 | 0 | 0 |
| ApplicablePackageID | 1 | 1 | 0 | 0 | 0 |
| CommandID | 1069 | 20 | 0 | 0 | 0 |
| SubsystemID | 5096 | 66 | 0 | 0 | 0 |
| ActivityID | 5040 | 10 | 0 | 0 | 0 |
| PackageID | 1050 | 1 | 0 | 0 | 0 |
| EntityID | 117 | 2 | 0 | 0 | 0 |
| AssociatedID | 117 | 1 | 0 | 0 | 0 |

머리 SystemID(Gateway 자신): 1종 [('2a7d4c1e-6b0f-4e3a-9c55-0d8e7f1a2b30', 9313)].

상태값(DEC-090): 내부↔외부 순서 짝 {'TaskStatus': 32, 'FlightCommandStatus': 19}. 표와 다른 대응 0종. 대응 표:

| 메시지 | UNSPECIFIED | ACCEPTED | EXECUTING | COMPLETED | REJECTED | FAILED | CANCELLED |
|---|---|---|---|---|---|---|---|
| TaskStatus | EXECUTION_PENDING | EXECUTION_PENDING | EXECUTING | COMPLETED | DROPPED | FAILED | CANCELED |
| FlightCommandStatus | RECEIVED | ACCEPTED | ACCEPTED | ACCEPTED | REJECTED | REJECTED | CANCELED |

상태 보고 건수 차이(내부 ↔ 외부): TaskStatus uav-999/neg-unknown 0↔1, FlightCommandStatus /uav-001-task-1 2↔1, FlightCommandStatus /uav-009-task-1 2↔1, FlightCommandStatus /uav-010-task-1 2↔1, FlightCommandStatus /uav-010-task-2 2↔1, FlightCommandStatus /uav-011-task-1 2↔1, FlightCommandStatus /uav-011-task-2 2↔1

## 7. C4 기체 계층 경계

판정: **통과**. Agent 프로세스를 `qa/conformance/agent_probe.py`로 감싸 실제 진입점이 연 구독 키 표현식·발행 키·L1 포트 메시지를 기록했다(MCAP에는 발행자 정보가 없어 프로세스별 키는 래퍼에서 얻고, 발행 키는 MCAP 채널과 대조한다).

허용 키(계약 docs/10_contracts.md §3.2의 Agent 행과 그 구독자 칸에 적힌 구독 키, 보충 없음):

| 방향 | 키 패턴 | 근거 |
|---|---|---|
| 발행 | sim/clock/done/* | §3.2 `sim/clock/done/<participant>` 발행: 참여자 |
| 발행 | sim/param/*/* | §3.2 `sim/param/<entity>/<owner>` 발행: Core(`dynamics`), Agent 런타임(`fa`, `ma`) |
| 발행 | swarm/*/tx/*/* | §3.2 `swarm/<src>/tx/<iface>/<msg>` 발행: 송신 엔티티 런타임, UI(GCS), Gateway(GCS 쪽, `c2`·`mp`만) |
| 발행 | onboard/*/* | §3.2 `onboard/<id>/<msg>` 발행: Core ⇄ 해당 기체 런타임 |
| 발행 | onboard_batch/ControlBatch/* | §3.2 `onboard_batch/ControlBatch/<participant>` 발행: Agent 런타임 |
| 구독 | sim/clock/tick | §3.2 `sim/clock/tick` 구독: 모든 참여자의 런타임 |
| 구독 | sim/clock/done/* | §3.2 `sim/clock/done/<participant>` 구독: Core (lockstep 장벽), Datalink·Agent 런타임 (서로의 장벽, DEC-040·044) |
| 구독 | sim/ctrl/cmd | §3.2 `sim/ctrl/cmd` 구독: Core, Agent 런타임 (`set_params`, §3.3) |
| 구독 | sim/ctrl/scenario | §3.2 `sim/ctrl/scenario` 구독: Datalink, Agent 런타임, Logger, UI, Gateway(알려진 기체 목록, 읽기만, DEC-096) (늦게 붙는 참여자는 조회) |
| 구독 | swarm/*/rx/*/* | §3.2 `swarm/<dst>/rx/<iface>/<msg>` 구독: 수신 엔티티의 Agent 런타임(맡은 기체마다 `swarm/<dst>/rx/**`로 따로 구독, 엔티티 자리 와일드카드 금지 DEC-100, DEC-044 개수 확인 단위), UI(GCS), Gateway(GCS 쪽) |
| 구독 | swarm/*/rx/** | §3.2 `swarm/<dst>/rx/<iface>/<msg>` 구독자 칸의 구독 키 `swarm/*/rx/**` |
| 구독 | onboard/*/* | §3.2 `onboard/<id>/<msg>` 구독: 해당 기체 런타임, Core |
| 구독 | onboard_batch/NavigationBatch | §3.2 `onboard_batch/NavigationBatch` 구독: Agent 런타임, Logger |

| Agent 구독 키 표현식 | 허용 |
|---|---|
| onboard/uav-001/Detection | 예 |
| onboard/uav-001/JammerActivity | 예 |
| onboard/uav-001/SensorActivity | 예 |
| onboard/uav-001/StoreLoadout | 예 |
| onboard/uav-001/StrikeActivity | 예 |
| onboard/uav-001/SystemStatus | 예 |
| onboard/uav-002/Detection | 예 |
| onboard/uav-002/JammerActivity | 예 |
| onboard/uav-002/SensorActivity | 예 |
| onboard/uav-002/StoreLoadout | 예 |
| onboard/uav-002/StrikeActivity | 예 |
| onboard/uav-002/SystemStatus | 예 |
| onboard/uav-003/Detection | 예 |
| onboard/uav-003/JammerActivity | 예 |
| onboard/uav-003/SensorActivity | 예 |
| onboard/uav-003/StoreLoadout | 예 |
| onboard/uav-003/StrikeActivity | 예 |
| onboard/uav-003/SystemStatus | 예 |
| onboard/uav-004/Detection | 예 |
| onboard/uav-004/JammerActivity | 예 |
| onboard/uav-004/SensorActivity | 예 |
| onboard/uav-004/StoreLoadout | 예 |
| onboard/uav-004/StrikeActivity | 예 |
| onboard/uav-004/SystemStatus | 예 |
| onboard/uav-005/Detection | 예 |
| onboard/uav-005/JammerActivity | 예 |
| onboard/uav-005/SensorActivity | 예 |
| onboard/uav-005/StoreLoadout | 예 |
| onboard/uav-005/StrikeActivity | 예 |
| onboard/uav-005/SystemStatus | 예 |
| onboard/uav-006/Detection | 예 |
| onboard/uav-006/JammerActivity | 예 |
| onboard/uav-006/SensorActivity | 예 |
| onboard/uav-006/StoreLoadout | 예 |
| onboard/uav-006/StrikeActivity | 예 |
| onboard/uav-006/SystemStatus | 예 |
| onboard/uav-007/Detection | 예 |
| onboard/uav-007/JammerActivity | 예 |
| onboard/uav-007/SensorActivity | 예 |
| onboard/uav-007/StoreLoadout | 예 |
| onboard/uav-007/StrikeActivity | 예 |
| onboard/uav-007/SystemStatus | 예 |
| onboard/uav-008/Detection | 예 |
| onboard/uav-008/JammerActivity | 예 |
| onboard/uav-008/SensorActivity | 예 |
| onboard/uav-008/StoreLoadout | 예 |
| onboard/uav-008/StrikeActivity | 예 |
| onboard/uav-008/SystemStatus | 예 |
| onboard/uav-009/Detection | 예 |
| onboard/uav-009/JammerActivity | 예 |
| onboard/uav-009/SensorActivity | 예 |
| onboard/uav-009/StoreLoadout | 예 |
| onboard/uav-009/StrikeActivity | 예 |
| onboard/uav-009/SystemStatus | 예 |
| onboard/uav-010/Detection | 예 |
| onboard/uav-010/JammerActivity | 예 |
| onboard/uav-010/SensorActivity | 예 |
| onboard/uav-010/StoreLoadout | 예 |
| onboard/uav-010/StrikeActivity | 예 |
| onboard/uav-010/SystemStatus | 예 |
| onboard/uav-011/Detection | 예 |
| onboard/uav-011/JammerActivity | 예 |
| onboard/uav-011/SensorActivity | 예 |
| onboard/uav-011/StoreLoadout | 예 |
| onboard/uav-011/StrikeActivity | 예 |
| onboard/uav-011/SystemStatus | 예 |
| onboard/uav-012/Detection | 예 |
| onboard/uav-012/JammerActivity | 예 |
| onboard/uav-012/SensorActivity | 예 |
| onboard/uav-012/StoreLoadout | 예 |
| onboard/uav-012/StrikeActivity | 예 |
| onboard/uav-012/SystemStatus | 예 |
| onboard/uav-013/Detection | 예 |
| onboard/uav-013/JammerActivity | 예 |
| onboard/uav-013/SensorActivity | 예 |
| onboard/uav-013/StoreLoadout | 예 |
| onboard/uav-013/StrikeActivity | 예 |
| onboard/uav-013/SystemStatus | 예 |
| onboard/uav-014/Detection | 예 |
| onboard/uav-014/JammerActivity | 예 |
| onboard/uav-014/SensorActivity | 예 |
| onboard/uav-014/StoreLoadout | 예 |
| onboard/uav-014/StrikeActivity | 예 |
| onboard/uav-014/SystemStatus | 예 |
| onboard_batch/NavigationBatch | 예 |
| sim/clock/done/datalink-0 | 예 |
| sim/clock/tick | 예 |
| sim/ctrl/cmd | 예 |
| sim/ctrl/scenario | 예 |
| swarm/uav-001/rx/** | 예 |
| swarm/uav-002/rx/** | 예 |
| swarm/uav-003/rx/** | 예 |
| swarm/uav-004/rx/** | 예 |
| swarm/uav-005/rx/** | 예 |
| swarm/uav-006/rx/** | 예 |
| swarm/uav-007/rx/** | 예 |
| swarm/uav-008/rx/** | 예 |
| swarm/uav-009/rx/** | 예 |
| swarm/uav-010/rx/** | 예 |
| swarm/uav-011/rx/** | 예 |
| swarm/uav-012/rx/** | 예 |
| swarm/uav-013/rx/** | 예 |
| swarm/uav-014/rx/** | 예 |

Agent 발행 키 125개(접두·종류별 {'onboard_batch/agent-0': 1, 'sim/done': 1, 'sim/uav-001': 2, 'sim/uav-002': 2, 'sim/uav-003': 2, 'sim/uav-004': 2, 'sim/uav-005': 2, 'sim/uav-006': 2, 'sim/uav-007': 2, 'sim/uav-008': 2, 'sim/uav-009': 2, 'sim/uav-010': 2, 'sim/uav-011': 2, 'sim/uav-012': 2, 'sim/uav-013': 2, 'sim/uav-014': 2, 'swarm/tx': 95}), 허용 밖 0개. MCAP 채널 479개, Agent 발행 키 중 MCAP에 없는 것 0개. truth 채널 ['truth/state']는 Core 발행이고 Agent 구독·수신 기록에는 없다.

MA 소스(algorithms/src/swarm_algorithms) import 34건: {'API': 17, '일반': 17}. 금지 목록: zenoh, swarm_api.bus, swarm_api.keys, swarm.v1.truth_pb2, swarm.v1.sim_pb2, swarm.v1.link_pb2, swarm.v1.fa_pb2, swarm_core, swarm_bus, swarm_bridge, swarm_gateway, swarm_datalink, swarm_logger, swarm_agent.runtime, swarm_agent.cli, swarm_agent.vehicle, swarm_agent.ports.

| L1 포트 | 방향 | 메시지 | 건수 | L1 | 구분 | 허용 |
|---|---|---|---|---|---|---|
| C2 | MA-> | swarm.v1.ApprovalRequest | 5 | C2 | STD | 예 |
| C2 | MA-> | swarm.v1.TaskStatus | 32 | C2 | STD | 예 |
| C2 | MA<- | swarm.v1.ApprovalResponse | 3 | C2 | STD | 예 |
| C2 | MA<- | swarm.v1.GcsHeartbeat | 980 | C2 | EXT | 예 |
| C2 | MA<- | swarm.v1.TaskCommand | 6 | C2 | STD | 예 |
| MD | MA-> | md.record | 358 | MD | — | 예 |
| MP | MA<- | swarm.v1.EngagementCriteria | 11 | MP | STD | 예 |
| MP | MA<- | swarm.v1.MissionPlan | 52532 | MP | STD | 예 |
| MP | MA<- | swarm.v1.RoutePlan | 2997 | MP | STD | 예 |
| MS | MA<- | swarm.v1.Detection | 9507 | MS | EXT | 예 |
| MS | MA<- | swarm.v1.JammerActivity | 3499 | MS | STD | 예 |
| MS | MA<- | swarm.v1.SensorActivity | 27992 | MS | STD | 예 |
| MS | MA<- | swarm.v1.StrikeActivity | 1 | MS | STD | 예 |
| P2P | MA-> | swarm.v1.LeaderUpdate | 1 | P2P | STD | 예 |
| P2P | MA-> | swarm.v1.PeerStatus | 2100 | P2P | STD | 예 |
| P2P | MA-> | swarm.v1.TrackShare | 117 | P2P | STD | 예 |
| P2P | MA<- | swarm.v1.LeaderUpdate | 13 | P2P | STD | 예 |
| P2P | MA<- | swarm.v1.PeerStatus | 15750 | P2P | STD | 예 |
| P2P | MA<- | swarm.v1.TrackShare | 1521 | P2P | STD | 예 |
| VI | MA-> | swarm.v1.FlightCommand | 17509 | VI | STD | 예 |
| VI | MA<- | swarm.v1.FlightCommandStatus | 17529 | VI | STD | 예 |
| VI | MA<- | swarm.v1.NavigationReport | 53565 | VI | STD | 예 |


## 8. C5 상호작용 상태 흐름

판정: **통과**. 허용 전이 표(도구 `judges.py`에 있는 그대로). 같은 상태 반복은 허용(변화 보고 재송신), 끝 상태 뒤 다른 상태는 위반. '끝 상태 뒤 반복도 위반' 표시가 있는 표는 끝 상태 뒤 같은 상태 반복도 위반(DEC-097).

- TaskStatus(내부): (첫 보고) → ACCEPTED, EXECUTING, FAILED, REJECTED; ACCEPTED → CANCELLED, EXECUTING, FAILED, REJECTED; EXECUTING → CANCELLED, COMPLETED, FAILED. 끝 상태 CANCELLED, COMPLETED, FAILED, REJECTED
- FlightCommandStatus(내부): (첫 보고) → ACCEPTED, CANCELLED, EXECUTING, REJECTED; ACCEPTED → CANCELLED, COMPLETED, EXECUTING, FAILED, REJECTED; EXECUTING → CANCELLED, COMPLETED, FAILED. 끝 상태 CANCELLED, COMPLETED, FAILED, REJECTED
- MA_TaskStatus(외부): (첫 보고) → DROPPED, EXECUTING, EXECUTION_PENDING, FAILED; EXECUTION_PENDING → CANCELED, DROPPED, EXECUTING, FAILED; EXECUTING → CANCELED, COMPLETED, FAILED. 끝 상태 CANCELED, COMPLETED, DROPPED, FAILED
- MA_FlightCommandStatus(외부): (첫 보고) → ACCEPTED, CANCELED, RECEIVED, REJECTED; RECEIVED → ACCEPTED, CANCELED, REJECTED. 끝 상태 ACCEPTED, CANCELED, REJECTED. 끝 상태 뒤 반복도 위반

| 표 | 대상 수 | 위반 대상 |
|---|---|---|
| TaskStatus(내부) | 14 | 없음 |
| FlightCommandStatus(내부) | 19 | 없음 |
| MA_TaskStatus(외부) | 15 | 없음 |
| MA_FlightCommandStatus(외부) | 19 | 없음 |

| 기체 | 작업 | 승인 필요 | 요청 | 응답 | 응답 모의 s | 첫 EXECUTING 모의 s | 판정 |
|---|---|---|---|---|---|---|---|
| uav-001 | ap-yes | 예 | 예 | approved | 11.04 | 11.18 | 통과 |
| uav-002 | ap-no | 예 | 예 | rejected | 11.04 | — | 통과 |
| uav-003 | ap-to | 예 | 예 | 없음 | — | — | 통과 |
| uav-004 | task-001 | 예 | 예 | approved | 0.1 | 0.24 | 통과 |
| uav-009 | x-hold | 아니오 | 아니오 | 없음 | — | 10.12 | 통과 |
| uav-010 | x-rtb | 아니오 | 아니오 | 없음 | — | 10.14 | 통과 |

| 외부 명령 | 기체 | 작업 | 받은 내부 상태 | 상태 보고 |
|---|---|---|---|---|
| 외부 hold | uav-001 | ap-yes | ACCEPTED, EXECUTING | 있음 |
| 외부 hold | uav-002 | ap-no | REJECTED | 있음 |
| 외부 hold | uav-003 | ap-to | REJECTED | 있음 |
| 외부 hold | uav-009 | x-hold | ACCEPTED, CANCELLED, EXECUTING | 있음 |
| 외부 return_to_base | uav-010 | x-rtb | ACCEPTED, COMPLETED, EXECUTING | 있음 |
| 외부 cancel | uav-009 | x-hold | ACCEPTED, CANCELLED, EXECUTING | 있음 |


## 9. C6 OMS / LA-CAL 왕복

판정: **통과**. 선언은 실행에 쓴 `lacal_server.yaml`(gateway/config에서 포트·server_id만 바꿈)의 declared, 실제 교환은 종료 직전 CAL Server `/graph`의 pub·sub 간선이다. `/tap`은 외부 클라이언트가 시작부터 연 관리 포트 WebSocket으로 센 Gateway 발신 건수다.

| 서비스 | 방향 | 흐름 | 건수 | 상태 |
|---|---|---|---|---|
| swarm_gateway | pub | MA_TxDataPayloadCommand@swarm.c2 | 40 | 일치 |
| swarm_gateway | pub | MA_TxDataPayloadCommand@swarm.ms | 5048 | 일치 |
| swarm_gateway | pub | MA_TxDataPayloadCommand@swarm.p2p | 2218 | 일치 |
| swarm_gateway | pub | MA_TxDataPayloadCommand@swarm.vi | 2007 | 일치 |
| swarm_gateway | sub | MA_RxDataPayload@swarm.c2 | 19 | 일치 |
| swarm_gateway | sub | MA_RxDataPayload@swarm.mp | 6 | 일치 |
| external_c2 | pub | MA_RxDataPayload@swarm.c2 | 19 | 일치 |
| external_c2 | pub | MA_RxDataPayload@swarm.mp | 6 | 일치 |
| external_c2 | pub | MA_TaskCommand@swarm.c2 | 1 | 선언 밖(부정 입력) |
| external_c2 | sub | MA_TxDataPayloadCommand@swarm.c2 | 40 | 일치 |
| external_c2 | sub | MA_TxDataPayloadCommand@swarm.ms | 5048 | 일치 |
| external_c2 | sub | MA_TxDataPayloadCommand@swarm.p2p | 2218 | 일치 |
| external_c2 | sub | MA_TxDataPayloadCommand@swarm.vi | 2007 | 일치 |

| 흐름 | /tap | 외부 수신 | 일치 |
|---|---|---|---|
| MA_TxDataPayloadCommand@swarm.c2 | 40 | 40 | 예 |
| MA_TxDataPayloadCommand@swarm.ms | 5048 | 5048 | 예 |
| MA_TxDataPayloadCommand@swarm.p2p | 2218 | 2218 | 예 |
| MA_TxDataPayloadCommand@swarm.vi | 2007 | 2007 | 예 |

외부 송신 → 버스(GCS 송신, neg- 제외): MA_ApprovalRequestStatus 3건, MA_MissionPlan 1건, MA_RoutePlan 1건, MA_TaskCommand 6건, QueryDataRequest(→QueryDataRequestStatus) 2건. 기체 반영은 C5 상태 보고 표에서 본다.


## 10. C7 AMS-GRA 개념 차용 추적과 적용성

판정: **정보** (추적 항목. 준수를 주장하지 않는다, DEC-093).

### 10.1 차용 개념 추적

| AMS-GRA 개념 | 반영 | 근거 | 확인 방법 | 자동 확인 결과 |
|---|---|---|---|---|
| ASB(Abstract Service Bus) | `open_bus` 추상 계층, Zenoh 백엔드 | PRP-NET-001, DEC-002, DEC-026 | 모든 프로세스가 `open_bus`로만 버스를 여는지 소스 점검 | 진입점 6/6이 open_bus 사용 (Sim Core, Datalink, Logger, Agent, Bridge, Gateway). 버스 계층 밖 직접 열기 0건 |
| OMS 서비스 분해 | 임무장비를 서비스(카메라·재머·무장)별 Command/Activity로 모델링 | PRP-PAY-001 | MS 메시지가 장비 서비스별로 나뉘는지 C1 표에서 확인 | Sensor: SensorCommand(STD, PO_Command), SensorActivity(STD, PO_Activity); 기타: Detection(EXT); Jammer: JammerCommand(STD, EA_Command), JammerActivity(STD, EA_Activity); Strike: StrikeCommand(STD, StrikeCommand), StrikeActivity(STD, StrikeActivity); Store: StoreLoadout(STD, StoreLoadoutConfiguration) |
| Time Distribution | Sim Core 고정 프레임, lockstep 장벽 | DEC-005, DEC-043 | lockstep 결정론 시험 결과 링크 | docs/21_qa_report.md §28(20차, TC-QA-106~113): 같은 시드 lockstep 반복에서 truth 궤적·LinkOutcome·GCS 수신이 같았다(손실 없음·있음, 고장 주입, 임무장비, 50기, Gateway 포함 외부 입력 없는 구성). §31(23차 회귀)에서 다시 같았다. 이 도구의 같은 커밋 3회 실행: 판정과 실패 문구(수치 제외)가 모두 같다 |
| Armament | 무장 서비스·탑재 구성 명명(`StoreLoadoutConfiguration`) | DEC-019, DEC-088 | C1 표의 MS 행 | StrikeActivity (StrikeActivity, 송신, 구현·시험됨); StoreLoadoutConfiguration (StoreLoadout, 송신, 구현·시험됨) |

### 10.2 요구별 적용성 ([46_amsgra_applicability.md](46_amsgra_applicability.md) §3)

해당·부분은 AMS-GRA 준수를 뜻하지 않는다(문서 46 §1). 아래 요약표는 문서 46 §3을 그대로 옮겼다.

| 요구 군 | 정의 볼륨 | 계 | 해당 | 부분 | 해당없음 |
|---|---|---|---|---|---|
| `GRA-MS` (Mission System) | Assembly, Mission System | 59 | 0 | 6 | 53 |
| `GRA-MASI` (MASI) | Assembly, MASI, Mission System, Software Architecture | 26 | 2 | 10 | 14 |
| `GRA-MPU` (MPU 공통·볼륨별) | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU, Time Distribution | 79 | 0 | 12 | 67 |
| `GRA-DK` (Development Kit) | DPP MPU, MFA MPU | 43 | 0 | 0 | 43 |
| `GRA-CYMAN` (Cyber Manager) | Mission System | 9 | 0 | 0 | 9 |
| `GRA-CYAGE` (Cyber Agent) | Mission System | 4 | 0 | 0 | 4 |
| `GRA-CYMON` (Cyber Monitor) | Mission System | 4 | 0 | 0 | 4 |
| 계 |  | 224 | 2 | 28 | 194 |

해당·부분 30행의 근거 확인: 파일 경로 5개(백틱 안 확장자 있는 것)와 DEC ID 20개를 저장소 파일 목록(`git ls-files`)과 등록부 §3에서 찾았다. 근거가 없는 행 0개. §4 상세 224행 (해당 2, 부분 28, 해당없음 194).

| ID | 판정 | 근거 파일 | 근거 DEC | 없음 |
|---|---|---|---|---|
| GRA-MS-002 | 부분 | — | DEC-002, DEC-026, DEC-069 | — |
| GRA-MS-004 | 부분 | — | DEC-005, DEC-043 | — |
| GRA-MS-009 | 부분 | — | DEC-068, DEC-069 | — |
| GRA-MS-054 | 부분 | — | DEC-041 | — |
| GRA-MS-065 | 부분 | `gateway/config/lacal_server.yaml` | DEC-027 | — |
| GRA-MS-079 | 부분 | — | DEC-068 | — |
| GRA-MASI-001 | 부분 | `scripts/run_p0_demo.py` | — | — |
| GRA-MASI-002 | 부분 | — | — | — |
| GRA-MASI-006 | 부분 | — | — | — |
| GRA-MASI-010 | 부분 | — | — | — |
| GRA-MASI-011 | 부분 | — | — | — |
| GRA-MASI-012 | 부분 | — | DEC-041 | — |
| GRA-MASI-013 | 부분 | — | — | — |
| GRA-MASI-015 | 부분 | — | DEC-041 | — |
| GRA-MASI-024 | 해당 | — | DEC-002, DEC-026 | — |
| GRA-MASI-028 | 부분 | — | — | — |
| GRA-MASI-029 | 해당 | — | DEC-086 | — |
| GRA-MASI-030 | 부분 | — | DEC-041 | — |
| GRA-MPU-019 | 부분 | — | DEC-069 | — |
| GRA-MPU-020 | 부분 | — | — | — |
| GRA-MPU-021 | 부분 | — | DEC-068 | — |
| GRA-MPU-025 | 부분 | — | — | — |
| GRA-MPU-046 | 부분 | `docs/03_traceability.md` | — | — |
| GRA-MPU-047 | 부분 | — | — | — |
| GRA-MPU-048 | 부분 | — | DEC-022 | — |
| GRA-MPU-051 | 부분 | `uv.lock`, `vcpkg.json` | — | — |
| GRA-MPU-071 | 부분 | — | DEC-022 | — |
| GRA-MPU-077 | 부분 | — | — | — |
| GRA-MPU-085 | 부분 | — | — | — |
| GRA-MPU-092 | 부분 | — | — | — |

- 코드 식별자(`open_bus`, `SystemStatus` 등), 버스 키, WP, 계약 절 번호는 확인하지 않는다.


## 11. 도구와 한계

| 파일 | 역할 |
|---|---|
| `qa/conformance/run.py` | 진입점. 정적 수집 → 점검 실행 → 판정 → 이 문서와 결과 폴더 |
| `qa/conformance/judges.py` | 판정 함수(C1~C7). 입력은 dict·list뿐이라 단위 시험이 위반 입력으로 직접 부른다 |
| `qa/conformance/harness_run.py` | lockstep 실행, 프레임 지정 입력, 관측기(GCS 수신·송신, 기체 수신) |
| `qa/conformance/analyze.py` | 원자료 짝짓기(위치 쌍, 상태 쌍, 식별자 수집, 전이 열) |
| `qa/conformance/static.py`, `gw_dump.py` | XSD·등록부·TRACE·MA import·open_bus 소스 점검, proto 옵션·변환기 등록 덤프 |
| `qa/conformance/agent_probe.py` | Agent 진입점 래퍼(구독·발행 키, L1 포트 메시지) |
| `qa/conformance/mcap_lite.py` | 압축 없는 MCAP 최소 읽기(채널·건수) |
| `qa/conformance/findings.py` | 발견 목록과 판정 문구 대응 |
| `qa/conformance/tests/test_judges.py` | 판정 로직 단위 시험(위반 입력은 실패해야 한다) |

기준 문서 [44_standards_conformance.md](44_standards_conformance.md) §4 한계(그대로 옮김):

- 자체 점검이다. 같은 팀이 기준과 구현을 함께 만들었다. 외부 클라이언트를 Gateway 코드와 따로 두어 일부만 줄인다.
- 공식 A-GRA 적합성 시험 도구와 Distribution D 인터페이스 볼륨의 상세 규칙은 쓰지 않는다.
- A-GRA는 MA L1 준수 문서(요구 MA-L1-001~025, 최소 메시지 집합)와 자동 L1 준수 시험 도구가 있다고 안내한다. 이 저장소 자료에는 도구가 없다. 공식 판정이 필요하면 입수해야 한다.
- 2026-11-24에 받은 공개 저장소 zip(A-GRA standard, test-harness)을 대조했다. 스키마 두 개와 인터페이스 볼륨은 기존 6.0a와 내용이 같다. 시험 하네스 zip에는 5.0a 문서만 있고 시험 코드는 별도 릴리스다(OPN-088). 하네스가 요구하는 외부 데이터 봉투(OPN-085)와 6.0a에 추가된 오류·확인 응답 인터랙션(OPN-086)은 아직 점검 항목이 아니다.
- 6.0a 인터랙션 변경의 근거는 `ASK_6.0a_Change_Log.pdf`(5.0a→6.0a)의 변경 번호(`6-A1.GRA-M.0xx`, `6-A1.GRA-A.0xx`)로 적는다. 새 VI 볼륨에는 Distribution D 표기가 없지만 Distribution A 표기도 없으므로, 공개 승인이 확인될 때까지 배포 제한 문서로 취급한다.
- A-GRA MA-L1-009~012·025는 DMS의 DDS 사용을 요구한다. DEC-002(Zenoh만 사용)와 충돌하므로 이 점검으로는 L1 전면 준수를 보일 수 없다. 미들웨어 변경은 보류한다(DEC-099).
- AMS-GRA에는 시험 도구가 없다. 준수 평가는 요구별 통과·실패·해당없음 평가표와 가중 점수, Tier 0~3로 하는 자체 평가이고 최종 판단은 획득 기관이 한다. 이 저장소는 준수를 주장하지 않으므로 평가표 대신 적용성 표(46)를 둔다.
- 외부 입력이 있으면 같은 시드에서도 기체 궤적이 실행마다 조금 달라진다(외부 입력 도착 틱 차이). 판정은 건수·전이·대조 오차로 하고 궤적 일치는 보지 않는다.

도구 자체의 한계:

- 위치 대조는 기체·토픽별 도착 순서로 짝짓는다(손실 없는 링크, 앞쪽 40개로 어긋남 0을 확인). 손실이 있는 링크에서는 건수가 달라 짝짓기 방법을 바꿔야 한다.
- 결과 파일은 임시 파일에 쓴 뒤 바꿔 넣고, Windows에서 읽는 프로세스 때문에 PermissionError가 나면 재시도한다(`confcommon.write_json`, `qa/gw_ext_client.py`·`qa/gw_wrap.py`도 같은 방식으로 바꿨다).
- 외부 입력은 일시정지 중에 넣어 도착 틱을 고정했지만, 외부 클라이언트의 승인 응답은 실행 중에 나가므로 틱이 실행마다 다를 수 있다(기준 §4). 판정은 건수·전이·대조 오차로 한다.

