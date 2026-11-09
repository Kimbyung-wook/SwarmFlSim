# gateway 추적표 (모듈 코드 GW)

- 근거: DEC-068(단계적 양방향 Gateway, Datalink 경유), DEC-072(`uci_also`, 여러 UCI 대응), DEC-075(외부 승인 응답), DEC-076(임무 계획 수신), DEC-077(`publisher`), DEC-069(agra_lacal 서브모듈 `third_party/agra_lacal` @ 45274ce), PRP-STD-002, DEC-013, DEC-014, DEC-026, REQ-STD-001
- 계약 버전: 0.15.0 (`swarm_api.CONTRACT_VERSION`, wp0-contracts c74b252 병합)
- 4차(2026-11-09): DEC-075(CR-GW-002), DEC-076(CR-GW-003), DEC-077(CR-GW-005, QA O-14)
- 3차(2026-11-09): 문서 교차 검토 불일치 2건. Zenoh가 없으면 실패 종료, cp949 콘솔의 `--help` (wp0-contracts 6a85fb0 병합)
- 2차(2026-11-08): DEC-072 구현(CR-GW-001 해소), QA 15차 D-27(`--no-multicast`), O-13(준비 전 구간 로그·문서). DEC-071(Agent의 VI 상태 GCS 보고)은 WP3 몫이며 Gateway는 기존 VI 변환기로 받는다
- UCI 메시지명과 필드는 공개 XSD(`A-GRA_MessageDefinitions_v6_0_a.xsd`, Distribution A, 스키마 `006.0.ASK`)에서만 가져왔다. Distribution D 표기 문서는 참조하지 않았다.
- P6 완료 기준 "VI·C2·P2P 주요 상호작용을 agra_lacal과 교환": TC-GW-010(실제 CAL Server 왕복)으로 보인다.

## 구현 (IMP)

| ID | 내용 | 위치 | 근거 | 시험 결과 |
|---|---|---|---|---|
| IMP-GW-001 | agra_lacal 연결부: 서브모듈 루트를 sys.path에 넣고 `server.omsjson.OmsJsonCodec`(OMS JSON ⇄ XML, lxml XSD 검증), `client.lacal_client.LaCalClient`를 읽기만 한다. 위치는 `SWARM_AGRA_LACAL`로 바꿀 수 있다 | `src/swarm_gateway/lacal.py` | DEC-069 | TC-GW-003, TC-GW-010 통과 |
| IMP-GW-002 | 매핑 표: proto 옵션 `(uci_name)`, `(mapping)`, `(l1)`을 descriptor에서 읽는다. 하드코딩 없음. `exportable` = STD이고 uci_name 있음 | `src/swarm_gateway/mapping.py` | DEC-013, DEC-014, 계약 §4 | TC-GW-001, TC-GW-002 통과 |
| IMP-GW-003 | ID 변환: 내부 ID → UUIDv5(고정 이름공간) + DescriptiveLabel, 역방향은 Label 우선 | `src/swarm_gateway/ids.py` | REQ-STD-001 | TC-GW-007 통과 |
| IMP-GW-004 | 변환기 플러그인 틀: 내부 메시지별 `Converter`(`to_uci`/`from_uci`), 내장 등록 + 엔트리 포인트 `swarm_gateway.converters`. UCI 이름은 매핑 표에서 받는다. STD가 아니거나 XSD에 없는 변환기는 쓰지 않는다 | `src/swarm_gateway/converters/base.py`, `gateway.py` | DEC-013, PRP-STD-002 | TC-GW-002 통과 |
| IMP-GW-005 | VI 변환기: NavigationReport, SystemStatus, FlightCommandStatus, FlightCapability | `src/swarm_gateway/converters/vi.py` | DEC-068 | TC-GW-003 통과 |
| IMP-GW-006 | C2 변환기: TaskStatus, ApprovalRequest(발행), TaskCommand(수신, hold·return_to_base·취소) | `src/swarm_gateway/converters/c2.py` | DEC-068 | TC-GW-003, TC-GW-007, TC-GW-008 통과 |
| IMP-GW-007 | P2P 변환기: PeerStatus, LeaderUpdate, TrackShare | `src/swarm_gateway/converters/p2p.py` | DEC-068 | TC-GW-003 통과 |
| IMP-GW-008 | MS 변환기: SensorActivity(FOV LOS 방위·고각), JammerActivity, StrikeActivity(IMPACT→COMPLETED, DEC-067), StoreLoadout | `src/swarm_gateway/converters/ms.py` | DEC-051, DEC-067, DEC-068 | TC-GW-003 통과 |
| IMP-GW-009 | 1단계 발행: `swarm/<gcs>/rx/**` 구독 → LinkEnvelope 해석 → STD만 변환 → UCI 봉투(SecurityInformation, MessageHeader Mode=SIMULATION) → XSD 검증 → outbox. EXT·SIM·알 수 없는 형식은 건너뛰고, 실패는 카운터·`rejections`·로그에 남긴다. 외부에서 받는 명령 종류는 되돌려 보내지 않는다 | `src/swarm_gateway/gateway.py` | DEC-068, DEC-014 | TC-GW-003~006, TC-GW-009 통과 |
| IMP-GW-010 | 2단계 수신: 외부 UCI → 메시지명·XSD 검증 → STD·L1=C2이고 `from_uci`가 있는 변환기 → `swarm/<gcs>/tx/c2/<msg>` LinkEnvelope(dst=수행 기체, 키별 seq). 매핑 없음·검증 실패·변환 불가는 거부하고 기록한다 | `src/swarm_gateway/gateway.py` | DEC-068, 계약 §3.3 | TC-GW-007, TC-GW-008 통과 |
| IMP-GW-011 | LA-CAL 실행기: CAL Client 접속, outbox → `PUB <prefix>.<iface>`, `SUB MA_TaskCommand <prefix>.c2` → 2단계. 전송 오류(-ERR)는 `send_failed`로 세고 계속한다 | `src/swarm_gateway/runner.py` | PRP-STD-002 | TC-GW-010, TC-GW-011 통과 |
| IMP-GW-012 | 진입점 `python -m swarm_gateway --gcs gcs-01 --lacal <주소>`. 버스는 `open_bus(BusConfig)`, Windows는 Selector 루프 | `src/swarm_gateway/__main__.py` | DEC-026 | TC-GW-009 통과, 수동 기동 확인 |
| IMP-GW-014 | `MA_PositionReport` 변환기(`AlsoConverter`): `kinematics`를 InertialState로 싣는다. Position(Point4D, rad·MSL·시각), PositionUncertainty(`position_sigma_m`가 있으면 원형 타원), DomainVelocity(NED), Orientation(NED→FRD 쿼터니언의 ZYX 오일러각, 쿼터니언이 비면 뺌). SystemID·DisplayName = 발신 엔티티 | `src/swarm_gateway/converters/position.py` | DEC-072 | TC-GW-013 통과 |
| IMP-GW-015 | `uci_also` 매핑: 매핑 표가 `(uci_also)`를 descriptor에서 읽고(`uci_targets` = uci_name + uci_also), 추가 UCI는 UCI 메시지별 `AlsoConverter`(`register_also`, 엔트리 포인트 지원)가 맡는다. 어느 내부 메시지에 쓸지는 descriptor만 정한다. Gateway는 대상마다 따로 변환·검증·발행하고, 하나가 실패해도 나머지를 보낸다(`Outcome.also`) | `src/swarm_gateway/mapping.py`, `converters/base.py`, `gateway.py` | DEC-072, DEC-013 | TC-GW-012~014 통과 |
| IMP-GW-016 | CLI `--no-multicast` → `BusConfig.multicast_scouting=False` | `src/swarm_gateway/__main__.py`, `README.md` | QA D-27, DEC-026 | TC-GW-009 통과 |
| IMP-GW-017 | 준비 전 구간 로그: LA-CAL 접속(“not ready yet”), XSD 적재, SUB 완료, ready를 기동 기준 경과 s와 함께 INFO로 남기고 `Running.ready_after_s`에 둔다. README에 준비 전 상태를 적었다. 동작은 바꾸지 않았다(제안 P-GW-001) | `src/swarm_gateway/runner.py`, `README.md` | QA O-13 | TC-GW-015 통과 |
| IMP-GW-018 | 버스 백엔드 선택: `--bus` 기본값을 `zenoh`로 고정하고 선택지는 `zenoh`, `memory`로 제한한다. 기본 실행에서 Zenoh를 쓸 수 없으면 버스·LA-CAL을 열지 않고 설치 방법을 stderr에 알리며 종료 코드 1로 끝난다. 인메모리 버스는 `--bus memory`를 줄 때만 쓰고 경고를 남긴다 | `src/swarm_gateway/__main__.py`, `README.md` | DEC-026, 문서 교차 검토 | TC-GW-016, TC-GW-017 통과 |
| IMP-GW-019 | 콘솔 인코딩: 도움말의 `⇄`를 `<->`로 바꾸고, 진입점 시작에서 stdout·stderr를 `errors=replace`로 재설정해 표현할 수 없는 문자가 있어도 인코딩 오류로 끝나지 않게 한다. `PYTHONUTF8` 없이 동작한다 | `src/swarm_gateway/__main__.py` | 문서 교차 검토 | TC-GW-018 통과 |
| IMP-GW-020 | 외부 승인 응답: `MA_ApprovalRequestStatus` → `ApprovalResponse`, `tx/c2`. COMPLETED의 APPROVED·REJECTED만 받는다. 내보낸 요청의 요청 기체를 기억해 `dst`로 쓰고, 모르면 `dst`를 비운다. GCS rx의 `ApprovalResponse`는 되돌려 내보내지 않는다 | `src/swarm_gateway/converters/c2.py` | DEC-075 | TC-GW-019, TC-GW-020 통과 |
| IMP-GW-021 | 임무 계획 수신: `MA_RoutePlan` → `RoutePlan`(`NextPathSegment` 순서, rad→도, 속력), `MA_MissionPlan` → `MissionPlan`(참조한 경로를 `move_to`·`route` 작업으로 편다). 허용 목록 밖 요소는 임시 규칙 없이 거부한다 | `src/swarm_gateway/converters/mp.py`, `base.py`(`BoundedStore`) | DEC-076 | TC-GW-021~024 통과 |
| IMP-GW-022 | 2단계 범위를 STD C2·MP로 넓힌다. 발행 키는 `tx/c2/**`, `tx/mp/**`로 제한하고(`publish_inbound`), MP는 LA-CAL 토픽 `<prefix>.mp`로 구독한다 | `src/swarm_gateway/gateway.py`, `runner.py`, `config/lacal_server.yaml` | DEC-076, DEC-068 | TC-GW-026, TC-GW-027 통과 |
| IMP-GW-023 | `LinkEnvelope.publisher`를 참여자 ID로 채운다. `--participant`, 기본 `gateway-0`, 엔티티 ID 형식 검증. `header.seq`는 발행자·키별이다 | `src/swarm_gateway/gateway.py`, `__main__.py` | DEC-077, QA O-14 | TC-GW-025 통과 |
| IMP-GW-013 | CAL Server 설정(서비스 `swarm_gateway`, `external_c2`, 토픽 `swarm.*`)과 기동 래퍼(서브모듈 수정 없음) | `config/lacal_server.yaml`, `src/swarm_gateway/lacal_server.py` | DEC-069 | TC-GW-010 통과, 수동 기동 확인 |

## 시험 (TC)

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-GW-001 | descriptor로 매핑 표 생성. STD uci_name 21종이 모두 XSD 전역 요소, EXT·SIM은 uci_name 없음 | `tests/test_mapping.py` | IMP-GW-002 | 통과 |
| TC-GW-002 | 변환기는 UCI 이름을 갖지 않고, 모든 변환기가 STD 항목에 대응, 표 출력 | `tests/test_mapping.py` | IMP-GW-002, IMP-GW-004 | 통과 |
| TC-GW-003 | 상태 13종(VI 4, C2 2, P2P 3, MS 4)이 rx → UCI XML → 별도 적재한 공개 XSD로 재검증 통과, 토픽 `swarm.<iface>`, 값 변환(도→rad, LOS, ID Label) | `tests/test_export.py` | IMP-GW-005~009 | 통과 |
| TC-GW-004 | EXT(Detection, PeerAlgorithmMessage, FormationCommand)는 내보내지 않음 | `tests/test_export.py` | DEC-014 | 통과 |
| TC-GW-005 | XSD 위반(위도 120°), 비유한 값, 깨진 봉투·payload는 거부·기록, 다음 메시지는 정상 발행 | `tests/test_export.py` | IMP-GW-009 | 통과 |
| TC-GW-006 | SIM 메시지·알 수 없는 msg_type 미발행, 수신 명령 종류 되돌림 없음 | `tests/test_export.py` | IMP-GW-009 | 통과 |
| TC-GW-007 | 외부 MA_TaskCommand(hold, return_to_base, 취소) → `swarm/gcs-01/tx/c2/TaskCommand`, dst·iface·msg_type·seq 확인 | `tests/test_import.py` | IMP-GW-010 | 통과 |
| TC-GW-008 | 필수 요소 누락·잘못된 열거값(XSD), 매핑 없는 메시지, 엔티티가 아닌 Capability 라벨, 미지원 작업 종류는 거부, 발행 없음 | `tests/test_import.py` | IMP-GW-010 | 통과 |
| TC-GW-009 | 구독은 `swarm/gcs-01/rx/**`뿐, `truth/**`·`onboard/**`·`link/**`·다른 엔티티 키 미수신, 발행은 `swarm/gcs-01/tx/c2/**`뿐, CLI가 `open_bus` 사용, `--no-multicast`가 멀티캐스트를 끔 | `tests/test_bus_scope.py` | DEC-068, DEC-026 | 통과 |
| TC-GW-010 | 프로세스 안 agra_lacal CAL Server와 왕복: 상태 13종을 외부 클라이언트가 수신(서버 XSD 검증 통과), EXT 미도달, 외부 MA_TaskCommand → tx/c2, 잘못된 외부 메시지는 서버가 거부 | `tests/test_roundtrip.py` | P6 완료 기준, DEC-068 | 통과 |
| TC-GW-011 | 서버가 거부한 PUB(허용되지 않은 토픽)는 `send_failed`로 세고 계속 동작 | `tests/test_roundtrip.py` | IMP-GW-011 | 통과 |
| TC-GW-012 | `uci_also`를 descriptor에서 읽음(NavigationReport·PeerStatus → `MA_PositionReport`), `by_uci`·표 출력, 변환기 결합은 descriptor 기준(TrackShare에는 붙지 않음) | `tests/test_position_report.py` | IMP-GW-015 | 통과 |
| TC-GW-013 | NavigationReport·PeerStatus 한 건 → uci_name과 `MA_PositionReport` 각각 발행, 같은 토픽(`swarm.vi`/`swarm.p2p`), 별도 적재한 공개 XSD 통과, 위치·속도·자세(yaw 90°)·불확도 값 확인. TC-GW-003·010도 uci_also 포함 15건으로 갱신 | `tests/test_position_report.py`, `test_export.py`, `test_roundtrip.py` | IMP-GW-014, IMP-GW-015 | 통과 |
| TC-GW-014 | 추가 UCI 실패(kinematics 없음, 위도 95° XSD 위반)는 그 메시지만 거부·기록하고 uci_name 메시지는 나감 | `tests/test_position_report.py` | IMP-GW-015 | 통과 |
| TC-GW-016 | Zenoh가 없을 때 기본 실행과 `--bus zenoh`는 `open_bus`를 부르지 않고 종료 코드 1, stderr에 `uv sync --extra zenoh`와 `--bus memory` 안내. Zenoh 없는 환경에서는 실제 프로세스로도 확인(Traceback·ready 없음) | `tests/test_cli.py` | IMP-GW-018 | 통과 (프로세스 시험은 Zenoh 설치 시 건너뜀) |
| TC-GW-017 | `--bus memory`는 Zenoh가 없어도 InMemoryBus로 뜨고 경고를 남긴다. 기본값은 `zenoh`, 그 밖의 값은 사용법 오류(종료 코드 2) | `tests/test_cli.py` | IMP-GW-018 | 통과 |
| TC-GW-018 | cp949 stdout의 실제 프로세스(`PYTHONUTF8=0`)에서 `--help`가 종료 코드 0으로 끝나고 한글이 그대로 나온다. 표현할 수 없는 문자도 오류 없이 `?`로 나온다 | `tests/test_cli.py` | IMP-GW-019 | 통과 |
| TC-GW-019 | 외부 승인 응답(APPROVED, REJECTED) → `tx/c2/ApprovalResponse`, `dst`=요청 기체. 모르는 요청은 `dst` 비움. rx의 `ApprovalResponse`는 되돌림 없음 | `tests/test_inbound_plans.py` | IMP-GW-020 | 통과 |
| TC-GW-020 | PENDING, CANCELED, 처리 중 상태는 거부, 발행 없음 | `tests/test_inbound_plans.py` | IMP-GW-020 | 통과 |
| TC-GW-021 | `MA_RoutePlan` → `tx/mp/RoutePlan`: `dst`·`entity_id`, 뒤섞인 배열의 연결 순서, 위치, 속력 | `tests/test_inbound_plans.py` | IMP-GW-021 | 통과 |
| TC-GW-022 | XSD는 통과하지만 표현할 수 없는 경로 계획 14종(계획 전용, Window, ALL·Package, 비엔티티, 비PRIMARY, 여러 경로, 순환, 끊김, Climb, AGL, 고도 없음, CAS) 거부·기록 | `tests/test_inbound_plans.py` | IMP-GW-021 | 통과 |
| TC-GW-023 | `MA_MissionPlan`의 경로 참조 → `tx/mp/MissionPlan`: 항로점 2개는 `route`, 1개는 `move_to`, `dst`와 위치 값 | `tests/test_inbound_plans.py` | IMP-GW-021 | 통과 |
| TC-GW-024 | 받지 못한 경로, 다른 기체 경로, TaskPlan 참조, 빈 계획, 계획 전용, 판 불일치 거부. 잘못된 XML(필수 누락, UUID 형식, 열거값) 3종 거부 | `tests/test_inbound_plans.py` | IMP-GW-021, IMP-GW-010 | 통과 |
| TC-GW-025 | `publisher` 채움(지정값, 기본 `gateway-0`), 잘못된 ID 거부, seq 키별 | `tests/test_inbound_plans.py` | IMP-GW-023 | 통과 |
| TC-GW-026 | 2단계 전 종류를 보내도 발행 키는 `tx/c2/**`, `tx/mp/**`뿐, 구독은 `rx/**` 하나, 그 밖의 L1 발행 시도는 예외 | `tests/test_inbound_plans.py` | IMP-GW-022 | 통과 |
| TC-GW-027 | 실제 CAL Server 왕복: 외부 승인 응답·`MA_RoutePlan`·`MA_MissionPlan` → `tx`, `publisher`, `dst`, 위치, 잘못된 메시지는 서버가 거부 | `tests/test_roundtrip.py` | IMP-GW-020~023 | 통과 |
| TC-GW-015 | 실제 CAL Server 접속에서 로그 순서: connected/not ready → XSD → SUB → ready | `tests/test_roundtrip.py` | IMP-GW-017 | 통과 |

시험 결과: `cd gateway && uv run pytest` → 85 passed (2026-11-09, Windows 11, Python 3.12, 계약 0.15.0, Zenoh 미설치 환경). `--extra zenoh` 환경에서는 84 passed, 1 skipped(TC-GW-016의 Zenoh 없는 프로세스 시험). 3차는 51 passed. 2차는 43 passed (2026-11-08), 1차는 35 passed (2026-11-07).

## 매핑 표 (descriptor에서 생성, `MappingTable.markdown()`)

`uci_also`: `NavigationReport`, `PeerStatus` → `MA_PositionReport` (DEC-072, 같은 토픽으로 발행).

| 내부 메시지 | UCI 메시지 | 구분 | L1 | Gateway |
|---|---|---|---|---|
| `ApprovalRequest` | `MA_ApprovalRequest` | STD | c2 | 발행 |
| `TaskCommand` | `MA_TaskCommand` | STD | c2 | 수신 |
| `ApprovalResponse` | `MA_ApprovalRequestStatus` | STD | c2 | 수신 (DEC-075) |
| `TaskStatus` | `MA_TaskStatus` | STD | c2 | 발행 |
| `EngagementCriteria` | `MA_EngagementCriteria` | STD | mp | 변환기 없음 |
| `MissionPlan` | `MA_MissionPlan` | STD | mp | 수신 (DEC-076) |
| `RoutePlan` | `MA_RoutePlan` | STD | mp | 수신 (DEC-076) |
| `JammerActivity` | `EA_Activity` | STD | ms | 발행 |
| `JammerCommand` | `EA_Command` | STD | ms | 변환기 없음 (GCS rx에 오지 않음) |
| `SensorActivity` | `PO_Activity` | STD | ms | 발행 |
| `SensorCommand` | `PO_Command` | STD | ms | 변환기 없음 (GCS rx에 오지 않음) |
| `StoreLoadout` | `StoreLoadoutConfiguration` | STD | ms | 발행 |
| `StrikeActivity` | `StrikeActivity` | STD | ms | 발행 |
| `StrikeCommand` | `StrikeCommand` | STD | ms | 변환기 없음 (GCS rx에 오지 않음) |
| `LeaderUpdate` | `MA_LeaderUpdateRequest` | STD | p2p | 발행 |
| `PeerStatus` | `MA_PackagePartnerStatusReport` + `MA_PositionReport` | STD | p2p | 발행 |
| `TrackShare` | `MA_Entity` | STD | p2p | 발행 |
| `FlightCapability` | `MA_FlightCapability` | STD | vi | 발행 |
| `FlightCommand` | `MA_FlightCommand` | STD | vi | 변환기 없음 (MA→FA, GCS rx에 오지 않음) |
| `FlightCommandStatus` | `MA_FlightCommandStatus` | STD | vi | 발행 |
| `NavigationReport` | `MA_NavigationReport` + `MA_PositionReport` | STD | vi | 발행 |
| `SystemStatus` | `SystemStatus` | STD | vi | 발행 |
| `FormationCommand` | — | EXT | c2 | 내보내지 않음 |
| `GroupAssignment` | — | EXT | c2 | 내보내지 않음 |
| `Detection` | — | EXT | ms | 내보내지 않음 |
| `PeerAlgorithmMessage` | — | EXT | p2p | 내보내지 않음 |
| SIM 13종 (`LinkEnvelope`, `TruthFrame` 등) | — | SIM | — | 내보내지 않음 |

## 변환에서 빠지는 정보

공개 XSD의 대응 메시지에 자리가 없어 싣지 않는 값이다. 계약 변경 요청과 함께 본다.

| 내부 메시지 | 빠지는 값 | 사유 |
|---|---|---|
| `NavigationReport` | 각속도(`angular_rate_frd_rps`) | 위치·속도·자세·불확도는 `MA_PositionReport`로 나간다(DEC-072). 기체축 각속도는 OrientationRate(오일러각 변화율)로 바꿔야 해서 싣지 않았다 |
| `PeerStatus` | `current_task_id`, `energy_frac`, 각속도 | 위치·속도·자세는 `MA_PositionReport`로 나간다(DEC-072). 나머지는 대응 필드가 없다 |
| `SystemStatus` | `energy_frac`, 하위 시스템별 health | SubsystemID 목록만 싣는다 |
| `TaskStatus` | `progress` | `MA_TaskStatus`에 진행률 필드가 없다 |
| `ApprovalRequest` | `target_id`, `description` | 승인 항목은 TaskID로만 참조한다 |
| `JammerActivity` | `zone`(원 영역) | EA_Activity 공개 필드에서 대응 위치를 정하지 못했다 |
| `TrackShare` | 진영(side) | `TrackShare`에 진영 필드가 없어 StandardIdentity는 UNKNOWN |

## 계약 변경 요청

| ID | 대상 | 요청 | 사유 |
|---|---|---|---|
| ~~CR-GW-001~~ | 해소: DEC-072 (계약 0.14.0) | — | — |
| ~~CR-GW-002~~ | 해소: DEC-075 (계약 0.15.0), IMP-GW-020 | — | — |
| ~~CR-GW-003~~ | 해소: DEC-076 (계약 0.15.0), IMP-GW-021. 경로로 표현되지 않는 작업은 CR-GW-007 | — | — |
| ~~CR-GW-005~~ | 해소: DEC-077 (계약 0.15.0), IMP-GW-023 | — | — |
| CR-GW-007 | proto `mp`/`c2`, 등록부 §5 | `MA_MissionPlan`의 `TaskPlanID` 내용을 받으려면 `MA_TaskPlan`·`MA_Task`에 대응하는 내부 STD 매핑이 필요하다. 영역 탐색 등 경로가 아닌 위치 작업은 이 매핑 뒤에 받는다 | 공개 XSD의 `MA_MissionPlan`은 하위 계획을 ID로만 참조하고, 작업 내용은 별도 메시지 `MA_Task`(TaskType 선택)에 있다. proto에 대응 메시지가 없다 |
| CR-GW-008 | WP3 Agent, `algorithms/` (`TaskTracker`) | 실행 중 받은 `MissionPlan`을 작업 대기열에 반영한다. 지금은 `TaskTracker`와 `formation`이 `mission_plan()`을 초기화 때 한 번만 읽어, `MPPortImpl`이 받은 새 계획을 수행하지 않는다 | Gateway는 `tx/mp/MissionPlan`까지 보내지만 내장 MA가 쓰지 않는다. 실행 중 바로 수행되는 경로는 `waypoint` MA의 `RoutePlan`뿐이다 (`algorithms/src/swarm_algorithms/common.py:71`, `waypoint.py:36`) |
| CR-GW-009 | 등록부(DEC), 시나리오 | 계획 대상 `ApplicableToIDs`의 `PackageID`·`ALL`을 엔티티로 펴는 규칙. 필요하면 그룹 ↔ 패키지 대응과 GCS가 지휘하는 기체 목록을 Gateway에 알리는 방법을 정한다 | Gateway는 그룹 구성원과 시나리오를 읽지 않아 `dst`를 채울 수 없다. 지금은 거부한다 |
| (원문) CR-GW-001 | `proto/swarm/v1/vi.proto`, `p2p.proto`, 등록부 §5 | `NavigationReport`의 `uci_name`을 `MA_PositionReport`로 바꾸거나, 한 내부 메시지가 UCI 메시지 여러 개에 대응할 수 있게 옵션을 늘린다(예: `repeated string uci_also`). `PeerStatus`의 운동 상태도 같은 방식으로 `MA_PositionReport`에 싣는다 | 공개 XSD의 `MA_NavigationReport`·`MA_PackagePartnerStatusReport`에는 위치가 없다. 위치는 `MA_PositionReport`(InertialState: Position·DomainVelocity·Orientation)에 있다. 등록부 §5도 후보로 `MA_PositionReport`를 적었다 |
| CR-GW-004 | 루트 `pyproject.toml` | `[tool.uv.workspace] members`, `[tool.uv.sources]`, dev 그룹, `testpaths`에 `gateway`(`swarm-gateway`)를 추가한다. 루트 시험에 넣으려면 CI·개발 환경에서 서브모듈 초기화가 필요하다 | 지금은 `gateway/` 밖 수정 금지라 독립 uv 프로젝트(`gateway/uv.lock`)로 두었다 |
| CR-GW-006 | 등록부 §5 | §5 표를 proto 기준으로 갱신한다: STD 21종의 실제 대응(예: `PeerStatus`→`MA_PackagePartnerStatusReport`, `TrackShare`→`MA_Entity`) | 계약 §4: 어긋나면 proto가 기준. Gateway가 descriptor로 만든 표(위)를 그대로 옮기면 된다 |

남은 요청: CR-GW-004, CR-GW-006, CR-GW-007, CR-GW-008, CR-GW-009. CR-GW-006(등록부 §5 갱신)에는 `uci_also`(`MA_PositionReport`) 열도 넣어야 한다. CR-GW-002·003·005의 원문은 위 해소 줄로 정리했다.

## 제안 (동작 변경, 미구현)

| ID | 내용 | 근거 |
|---|---|---|
| P-GW-001 | 준비 전 구간 줄이기(O-13). (1) XSD 적재·매핑 생성을 LA-CAL 접속 **앞**으로 옮긴다. 지금은 INIT 뒤 XSD 적재(대부분의 시간)가 끝나야 SUB가 걸리므로, 순서만 바꿔도 "접속돼 보이지만 받지 못하는" 구간이 SUB 왕복 시간으로 준다. (2) 근본적으로는 외부 C2가 준비를 알 수 있어야 한다: 예를 들어 ready 시점에 Gateway가 `SystemStatus`(SystemID = Gateway 서비스, Communications ACTIVE)를 한 번 발행하거나, 외부 C2가 명령 뒤 `MA_TaskStatus`가 일정 시간 안에 오지 않으면 다시 보내는 규칙을 둔다. (2)는 계약(등록부) 결정이 필요하다 | QA 15차 O-13 |

## 메모

- `MA_MissionPlan`의 대상 표현(XSD 확인): `Applicability`의 `ApplicableToIDs`가 `ALL | NON | PackageID | SystemID`의 선택이다. Gateway는 `SystemID` 하나만 `dst`로 쓴다. `PlannedForID`는 XSD 주석상 계획의 사용자(상위 C2일 수 있음)라 대상으로 쓰지 않는다. `MA_RoutePlan`은 `Plan/Applicability`에 같은 구조로 있다. 임무 계획 자체는 작업 내용 없이 하위 계획을 ID로 참조한다.
- QA O-14(재기동 시 `header.seq`가 0부터): DEC-077에 따라 seq는 발행자·키별이고 `publisher`로 구분한다. 재기동한 Gateway가 같은 `publisher`로 0부터 다시 매기는 것은 새 발행 세션으로 보며, 이번에 동작을 바꾸지 않았다. Datalink·Agent는 seq 연속성에 의존하지 않는다(QA 15차 TC-QA-073).

- SecurityInformation은 스키마 필수 요소라 공개 스키마 예제와 같은 값(`U`, `USA`)을 기본으로 넣는다. `GatewayConfig.classification`, `owner_producer`로 바꾼다.
- 시각은 벽시계 UTC다(`ConvContext.now`). lockstep 모의 시각과 맞추려면 `now`를 바꿔 끼우면 된다.
- 외부 C2 수신은 LA-CAL 쪽 검증(서버)과 Gateway 쪽 검증(코덱)을 모두 거친다.
