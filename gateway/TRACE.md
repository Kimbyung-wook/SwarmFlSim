# gateway 추적표 (모듈 코드 GW)

- 근거: DEC-068(단계적 양방향 Gateway, Datalink 경유), DEC-069(agra_lacal 서브모듈 `third_party/agra_lacal` @ 45274ce), PRP-STD-002, DEC-013, DEC-014, DEC-026, REQ-STD-001
- 계약 버전: 0.13.0 (`swarm_api.CONTRACT_VERSION`)
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
| IMP-GW-013 | CAL Server 설정(서비스 `swarm_gateway`, `external_c2`, 토픽 `swarm.*`)과 기동 래퍼(서브모듈 수정 없음) | `config/lacal_server.yaml`, `src/swarm_gateway/lacal_server.py` | DEC-069 | TC-GW-010 통과, 수동 기동 확인 |

## 시험 (TC)

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-GW-001 | descriptor로 매핑 표 생성. STD uci_name 21종이 모두 XSD 전역 요소, EXT·SIM은 uci_name 없음 | `tests/test_mapping.py` | IMP-GW-002 | 통과 |
| TC-GW-002 | 변환기는 UCI 이름을 갖지 않고, 모든 변환기가 STD 항목에 대응, 표 출력 | `tests/test_mapping.py` | IMP-GW-002, IMP-GW-004 | 통과 |
| TC-GW-003 | 상태 13종(VI 4, C2 2, P2P 3, MS 4)이 rx → UCI XML → 별도 적재한 공개 XSD로 재검증 통과, 토픽 `swarm.<iface>`, 값 변환(도→rad, LOS, ID Label) | `tests/test_export.py` | IMP-GW-005~009 | 통과 |
| TC-GW-004 | EXT(Detection, PeerAlgorithmMessage, FormationCommand, ApprovalResponse)는 내보내지 않음 | `tests/test_export.py` | DEC-014 | 통과 |
| TC-GW-005 | XSD 위반(위도 120°), 비유한 값, 깨진 봉투·payload는 거부·기록, 다음 메시지는 정상 발행 | `tests/test_export.py` | IMP-GW-009 | 통과 |
| TC-GW-006 | SIM 메시지·알 수 없는 msg_type 미발행, 수신 명령 종류 되돌림 없음 | `tests/test_export.py` | IMP-GW-009 | 통과 |
| TC-GW-007 | 외부 MA_TaskCommand(hold, return_to_base, 취소) → `swarm/gcs-01/tx/c2/TaskCommand`, dst·iface·msg_type·seq 확인 | `tests/test_import.py` | IMP-GW-010 | 통과 |
| TC-GW-008 | 필수 요소 누락·잘못된 열거값(XSD), 매핑 없는 메시지, 엔티티가 아닌 Capability 라벨, 미지원 작업 종류는 거부, 발행 없음 | `tests/test_import.py` | IMP-GW-010 | 통과 |
| TC-GW-009 | 구독은 `swarm/gcs-01/rx/**`뿐, `truth/**`·`onboard/**`·`link/**`·다른 엔티티 키 미수신, 발행은 `swarm/gcs-01/tx/c2/**`뿐, CLI가 `open_bus` 사용 | `tests/test_bus_scope.py` | DEC-068, DEC-026 | 통과 |
| TC-GW-010 | 프로세스 안 agra_lacal CAL Server와 왕복: 상태 13종을 외부 클라이언트가 수신(서버 XSD 검증 통과), EXT 미도달, 외부 MA_TaskCommand → tx/c2, 잘못된 외부 메시지는 서버가 거부 | `tests/test_roundtrip.py` | P6 완료 기준, DEC-068 | 통과 |
| TC-GW-011 | 서버가 거부한 PUB(허용되지 않은 토픽)는 `send_failed`로 세고 계속 동작 | `tests/test_roundtrip.py` | IMP-GW-011 | 통과 |

시험 결과: `cd gateway && uv run pytest` → 35 passed (2026-11-07, Windows 11, Python 3.12).

## 매핑 표 (descriptor에서 생성, `MappingTable.markdown()`)

| 내부 메시지 | UCI 메시지 | 구분 | L1 | Gateway |
|---|---|---|---|---|
| `ApprovalRequest` | `MA_ApprovalRequest` | STD | c2 | 발행 |
| `TaskCommand` | `MA_TaskCommand` | STD | c2 | 수신 |
| `TaskStatus` | `MA_TaskStatus` | STD | c2 | 발행 |
| `EngagementCriteria` | `MA_EngagementCriteria` | STD | mp | 변환기 없음 |
| `MissionPlan` | `MA_MissionPlan` | STD | mp | 변환기 없음 |
| `RoutePlan` | `MA_RoutePlan` | STD | mp | 변환기 없음 |
| `JammerActivity` | `EA_Activity` | STD | ms | 발행 |
| `JammerCommand` | `EA_Command` | STD | ms | 변환기 없음 (GCS rx에 오지 않음) |
| `SensorActivity` | `PO_Activity` | STD | ms | 발행 |
| `SensorCommand` | `PO_Command` | STD | ms | 변환기 없음 (GCS rx에 오지 않음) |
| `StoreLoadout` | `StoreLoadoutConfiguration` | STD | ms | 발행 |
| `StrikeActivity` | `StrikeActivity` | STD | ms | 발행 |
| `StrikeCommand` | `StrikeCommand` | STD | ms | 변환기 없음 (GCS rx에 오지 않음) |
| `LeaderUpdate` | `MA_LeaderUpdateRequest` | STD | p2p | 발행 |
| `PeerStatus` | `MA_PackagePartnerStatusReport` | STD | p2p | 발행 |
| `TrackShare` | `MA_Entity` | STD | p2p | 발행 |
| `FlightCapability` | `MA_FlightCapability` | STD | vi | 발행 |
| `FlightCommand` | `MA_FlightCommand` | STD | vi | 변환기 없음 (MA→FA, GCS rx에 오지 않음) |
| `FlightCommandStatus` | `MA_FlightCommandStatus` | STD | vi | 발행 |
| `NavigationReport` | `MA_NavigationReport` | STD | vi | 발행 |
| `SystemStatus` | `SystemStatus` | STD | vi | 발행 |
| `ApprovalResponse` | — | EXT | c2 | 내보내지 않음 |
| `FormationCommand` | — | EXT | c2 | 내보내지 않음 |
| `GroupAssignment` | — | EXT | c2 | 내보내지 않음 |
| `Detection` | — | EXT | ms | 내보내지 않음 |
| `PeerAlgorithmMessage` | — | EXT | p2p | 내보내지 않음 |
| SIM 13종 (`LinkEnvelope`, `TruthFrame` 등) | — | SIM | — | 내보내지 않음 |

## 변환에서 빠지는 정보

공개 XSD의 대응 메시지에 자리가 없어 싣지 않는 값이다. 계약 변경 요청과 함께 본다.

| 내부 메시지 | 빠지는 값 | 사유 |
|---|---|---|
| `NavigationReport` | `kinematics`(위치·속도·자세), `position_sigma_m` | `MA_NavigationReport`는 항법 모드·비행 가능 시간 보고이고 위치 필드가 없다 (CR-GW-001) |
| `PeerStatus` | `kinematics`, `current_task_id`, `energy_frac` | `MA_PackagePartnerStatusReport`는 패키지 참여 상태 보고다 (CR-GW-001) |
| `SystemStatus` | `energy_frac`, 하위 시스템별 health | SubsystemID 목록만 싣는다 |
| `TaskStatus` | `progress` | `MA_TaskStatus`에 진행률 필드가 없다 |
| `ApprovalRequest` | `target_id`, `description` | 승인 항목은 TaskID로만 참조한다 |
| `JammerActivity` | `zone`(원 영역) | EA_Activity 공개 필드에서 대응 위치를 정하지 못했다 |
| `TrackShare` | 진영(side) | `TrackShare`에 진영 필드가 없어 StandardIdentity는 UNKNOWN |

## 계약 변경 요청

| ID | 대상 | 요청 | 사유 |
|---|---|---|---|
| CR-GW-001 | `proto/swarm/v1/vi.proto`, `p2p.proto`, 등록부 §5 | `NavigationReport`의 `uci_name`을 `MA_PositionReport`로 바꾸거나, 한 내부 메시지가 UCI 메시지 여러 개에 대응할 수 있게 옵션을 늘린다(예: `repeated string uci_also`). `PeerStatus`의 운동 상태도 같은 방식으로 `MA_PositionReport`에 싣는다 | 공개 XSD의 `MA_NavigationReport`·`MA_PackagePartnerStatusReport`에는 위치가 없다. 위치는 `MA_PositionReport`(InertialState: Position·DomainVelocity·Orientation)에 있다. 등록부 §5도 후보로 `MA_PositionReport`를 적었다 |
| CR-GW-002 | `proto/swarm/v1/c2.proto` | `ApprovalResponse`를 STD로 바꾸고 `uci_name = "MA_ApprovalRequestStatus"`를 단다 | 공개 XSD에 `MA_ApprovalRequestStatus`가 있다(c2.proto 주석: "WP9에서 XSD로 확정"). STD가 되면 외부 운용자의 타격 승인을 2단계로 받을 수 있다 (변환기 추가 필요) |
| CR-GW-003 | 등록부(DEC), `docs/10_contracts.md` | 외부 `MA_TaskCommand`의 작업 내용 표현 규칙을 정한다. 제안: 임무 계획(`MA_MissionPlan`/TaskPlan) 연동 전까지 Gateway의 임시 규칙(CapabilityID Label = `<엔티티>/<작업 종류>`, hold·return_to_base·취소만)을 인정하고, 위치가 필요한 작업은 MP 연동 뒤에 받는다 | `MA_TaskCommand`는 TaskID·CapabilityID 참조만 담고 목적지·영역이 없다 |
| CR-GW-004 | 루트 `pyproject.toml` | `[tool.uv.workspace] members`, `[tool.uv.sources]`, dev 그룹, `testpaths`에 `gateway`(`swarm-gateway`)를 추가한다. 루트 시험에 넣으려면 CI·개발 환경에서 서브모듈 초기화가 필요하다 | 지금은 `gateway/` 밖 수정 금지라 독립 uv 프로젝트(`gateway/uv.lock`)로 두었다 |
| CR-GW-005 | `docs/10_contracts.md` §3.2 키 목록 | `swarm/<dst>/rx/<iface>/<msg>` 구독자와 `swarm/<src>/tx/<iface>/<msg>` 발행자에 "Gateway(GCS 쪽, `swarm/<gcs>/tx/c2/**`만)"를 적는다. Bridge `role=control`의 발행 허용과 같은 범위다 | DEC-068로 Gateway가 GCS 키를 같이 쓴다. 같은 GCS 키에 UI와 Gateway가 함께 발행하면 `header.seq`가 발행자별로 따로 매겨진다(계약 §3.3 "발행자·키별 일련번호"와는 맞지만 Datalink·Logger가 source만으로 구분할 수 없다) |
| CR-GW-006 | 등록부 §5 | §5 표를 proto 기준으로 갱신한다: STD 21종의 실제 대응(예: `PeerStatus`→`MA_PackagePartnerStatusReport`, `TrackShare`→`MA_Entity`) | 계약 §4: 어긋나면 proto가 기준. Gateway가 descriptor로 만든 표(위)를 그대로 옮기면 된다 |

## 메모

- SecurityInformation은 스키마 필수 요소라 공개 스키마 예제와 같은 값(`U`, `USA`)을 기본으로 넣는다. `GatewayConfig.classification`, `owner_producer`로 바꾼다.
- 시각은 벽시계 UTC다(`ConvContext.now`). lockstep 모의 시각과 맞추려면 `now`를 바꿔 끼우면 된다.
- 외부 C2 수신은 LA-CAL 쪽 검증(서버)과 Gateway 쪽 검증(코덱)을 모두 거친다.
