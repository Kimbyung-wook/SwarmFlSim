# gateway 추적표 (모듈 코드 GW)

- 근거: DEC-068(단계적 양방향 Gateway, Datalink 경유), DEC-072(`uci_also`, 여러 UCI 대응), DEC-075(외부 승인 응답), DEC-076(임무 계획 수신), DEC-077(`publisher`), DEC-088(A-GRA 송신 4종), DEC-089(변화 보고 복구), DEC-090(XSD 상태 표현), DEC-097(외부 명령 상태 Command-2 상태 기계), DEC-098(모의 시각 기준 시각), DEC-109(시작 때 시나리오 조회), DEC-110(하네스 STOMP 백엔드), DEC-111(외부 교환 봉투), DEC-112(QueryDataRequest 응답), DEC-096(`sim/ctrl/scenario` 구독자), QA 29차 D-35·D-36·D-39(`docs/45_standards_report.md` §2, 기준 `docs/44_standards_conformance.md`), DEC-069(agra_lacal 서브모듈 `third_party/agra_lacal` @ 45274ce), PRP-STD-002, DEC-013, DEC-014, DEC-026, REQ-STD-001
- 계약 버전: 0.24.0 (`swarm_api.CONTRACT_VERSION`, 10차에 wp0-contracts 17d2016 병합. 계약 문서와 상수가 같다. `api/python` 패키지 버전은 0.23.0이고 `gateway/uv.lock`도 같아 바꾸지 않았다). 0.24.0은 DEC-109(Core가 적재 중 `sim/ctrl/scenario` 조회에 답함, `Bus.serve`·`Bus.get`, IMP-API-026)를 더했고 Gateway는 IMP-GW-035로 쓴다. 0.23.0·0.24.0의 그 밖의 바뀐 점과 DEC-108은 Gateway가 받는 proto를 바꾸지 않는다. 앞 기록: 0.20.0 (`swarm_api.CONTRACT_VERSION`, wp0-contracts 0d984a1 병합, 9차에 92cdb9c 병합). 계약 문서는 0.22.0이지만 `swarm_api.CONTRACT_VERSION`은 아직 0.20.0이다(WP0 확인 필요). 0.21.0(DEC-100 Agent 구독)·0.22.0(DEC-101~104)은 proto 변경이 없고 Gateway 코드에 영향이 없다. DEC-101 링크 복구 재보고의 `FlightCommandStatus`는 DEC-097 상태 기계가 끝 상태 뒤라 내지 않고, `TaskStatus`는 같은 값이 외부로 한 번 더 나간다(상태 기계 대상 아님). 0.20.0은 `RunSpec.epoch_utc_us`(DEC-098)와 §3.2 `sim/ctrl/scenario` 구독자에 Gateway(DEC-096)를 더했다. `gateway/uv.lock`의 swarm-api 버전을 갱신했다. 0.16.0~0.19.0의 바뀐 점(`GcsHeartbeat`·`lost_link_policy` EXT, `NavigationBatch`·`ControlBatch` SIM, `ordered` 구독, `link/state` 분산)은 Gateway 동작에 영향이 없다. 새 EXT·SIM은 descriptor 매핑으로 내보내지 않는다
- 11차(2026-11-24): DEC-111 봉투(LA-CAL 경로 먼저), DEC-110 STOMP 백엔드, DEC-112 QueryDataRequest 응답 (wp0-contracts 531f0b2 병합, 계약 0.24.0 그대로)
- 10차(2026-11-24): DEC-109(시작 때 `sim/ctrl/scenario` 조회·재시도, 조회·구독 멱등, 시각 기준 전환 시점 로그), QA O-53
- 9차(2026-11-22): QA O-13(재기동 준비 전 외부 PUB 손실) 측정과 (A) 준비 전 수신분 보관 구현
- 8차(2026-11-20): DEC-098(UCI 시각 기준 = 시나리오 `run.epoch_utc_us`), OPN-GW-001·002 해소
- 7차(2026-11-19): DEC-097(외부 명령 상태: 끝 상태 뒤 보고하지 않음, QA D-37·O-47의 Gateway 쪽)
- 6차(2026-11-18): QA 29차 D-35(알려지지 않은 기체 명령 거부·외부 통지), D-36(UCI 시각 = 모의 시각), D-39(`external_c2` `declared.sub`)
- 5차(2026-11-16): DEC-089(늦게 붙은 외부 시스템에 변화 보고 마지막 값), DEC-088(송신 4종 시험), DEC-090(상태 enum 확인), QA O-20(`declared.pub`)
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
| IMP-GW-024 | 변화 보고 보관: XSD 검증을 통과해 내보낸 `SystemStatus`, `FlightCapability`, `FlightCommandStatus`(command_id별, 7차부터 뺌: IMP-GW-032), `SensorActivity`·`JammerActivity`(payload_id별), `StrikeActivity`(payload_id·weapon_entity별), `StoreLoadout`, `TaskStatus`(task_id별)를 (UCI 메시지, 토픽, 보고 기체, 키)별 마지막 값으로 둔다. 키는 Agent 변화 보고 키(`swarm_agent.reporting`)와 같고, 종료 상태를 받은 키는 지운다. 최대 4096건. 주기 보고(`NavigationReport`, `PeerStatus`)와 사건성 메시지(`ApprovalRequest`, `LeaderUpdate`, `TrackShare`)는 두지 않는다 | `src/swarm_gateway/retain.py`(`RetainedReports`), `gateway.py` | DEC-089, QA O-19 | TC-GW-028 통과 |
| IMP-GW-025 | 늦게 붙은 외부 구독자 전달: OWP 1.0에는 보관 메시지·구독 알림이 없어 CAL Server 관리 포트 `/graph/events`(agra_lacal 그래프 API)로 새 구독(`edge_added` sub 간선, 접속·재접속 스냅샷의 모르던 구독, 다른 서버는 `remote_updated` 뒤 `GET /graph`)을 알아내고, 그 (메시지, 토픽)의 마지막 값을 한 번 다시 PUB한다. 몰린 구독은 0.2 s 안에서 한 번으로 합친다. 평소 보고량은 그대로다. 관리 포트에 못 붙으면 경고하고 2 s마다 다시 시도하며 1·2단계는 그대로 돈다. CLI `--lacal-admin`(기본 `--lacal` 호스트의 8766, `none`이면 끔) | `src/swarm_gateway/retain.py`(`LateJoinReplayer`), `runner.py`, `__main__.py` | DEC-089 | TC-GW-029, TC-GW-030 통과 |
| IMP-GW-026 | DEC-088 송신 4종(`ApprovalRequest`, `LeaderUpdate`, `TrackShare`→`MA_Entity`, `StoreLoadout`): 변환기는 그대로이고, Agent 모양 봉투(`publisher` 비움, `rx_time_us`, 브로드캐스트 dst)와 값 변형으로 외부까지 나가는지 시험을 더했다. 코드 변경 없음 | `tests/test_reports_088.py` | DEC-088 | TC-GW-031, TC-GW-032 통과 |
| IMP-GW-027 | DEC-090 확인: 외부 상태는 공개 XSD enum 그대로다. `MA_FlightCommandStatus`는 `CommandProcessingStateEnum`(RECEIVED·ACCEPTED·REJECTED·CANCELED)뿐이라 EXECUTING·COMPLETED가 ACCEPTED로 보이고, 수행·완료는 `MA_TaskStatus`(`RequirementExecutionStateEnum`의 EXECUTING·COMPLETED)에서 읽는다. 확장 필드는 없다. 코드 변경 없음 | `src/swarm_gateway/converters/vi.py`, `c2.py`, `ms.py` | DEC-090, QA O-17 | TC-GW-033 통과 |
| IMP-GW-028 | CAL Server 설정 `declared.pub`에 `MA_PositionReport@swarm.vi`, `@swarm.p2p`를 넣었다. 선언이 Gateway의 실제 PUB·SUB와 같은지 시험으로 묶었다 | `config/lacal_server.yaml` | QA O-20, DEC-072 | TC-GW-034 통과 |
| IMP-GW-029 | 알려진 기체 확인: 외부 `MA_TaskCommand`·`MA_RoutePlan`·`MA_MissionPlan`이 가리키는 기체(`dst`)가 하나라도 알려지지 않았으면 버스에 내지 않고 다른 부정 입력처럼 거부로 기록한다(`Gateway.rejections`, `ext_rejected`, 경고 로그 `unknown entity [...]`). 알려진 기체 = `sim/ctrl/scenario`(`Scenario`)의 `ENTITY_KIND_UAV` + 이 GCS rx로 보고를 보낸 엔티티(`LinkEnvelope.header.source`). truth는 읽지 않는다. 시나리오가 바뀌면 두 목록을 새로 시작한다. 작업 ID가 있는 거부(`TaskCommand`, `MissionPlan`)는 모르는 기체별 `MA_TaskStatus`(`DROPPED`, 사유)를 `swarm.c2`로 내 외부에 알린다. `RoutePlan`은 알릴 상태 메시지가 없어 기록만 남는다. 구독이 `sim/ctrl/scenario` 하나 늘었다(OPN-GW-001) | `src/swarm_gateway/entities.py`, `gateway.py` | QA D-35 | TC-GW-035, TC-GW-036 통과 |
| IMP-GW-030 | UCI 시각 = 모의 시각: 머리 `Timestamp`와 위치·속도·자세 시각은 메시지 `header.sim_time_us`(비면 봉투 머리)의 UTC다. `MA_Entity`의 운동·식별 시각은 `observed_time_us`. UTC = 기준 시각 + 모의 시각이며, 기준 시각은 `--sim-epoch`(ISO 8601, 시간대 필수) 또는 처음 받은 메시지에서 한 번 정한다(벽시계 − 그 모의 시각, 로그에 남김). 정한 뒤 바꾸지 않아 일시정지·배속에서 (Timestamp − 모의 시각)이 일정하다. 계약에 대응이 없어 OPN-GW-002로 올린다 | `src/swarm_gateway/converters/base.py`(`SimClock`), `converters/p2p.py`, `gateway.py`, `__main__.py` | QA D-36 | TC-GW-037 통과 |
| IMP-GW-031 | CAL Server 설정 `external_c2` `declared.sub`를 Gateway가 외부로 내는 흐름 15개 전부(= `swarm_gateway` `declared.pub`, README 교환 표 발행 행)로 고쳤다. 전에는 `MA_TaskStatus`, `MA_NavigationReport` 둘뿐이었다 | `config/lacal_server.yaml` | QA D-39 | TC-GW-038 통과 |
| IMP-GW-032 | 외부 명령 상태 상태 기계: 내보낼 OMS JSON의 `MessageData`에 `CommandID`·`CommandProcessingState`가 있는 메시지(메시지 이름 하드코딩 없음, 지금은 `MA_FlightCommandStatus`)를 (UCI 메시지, 보고 기체, CommandID)별로 본다. 끝 상태(ACCEPTED·REJECTED·CANCELED)를 낸 뒤의 보고와 RECEIVED 반복은 내지 않는다(`skipped_command_state`, 결과 `skipped_command_state`). 첫 보고는 무엇이든 낸다(첫 CANCELED 포함). 기억은 최근 65536개 ID. `FlightCommandStatus`를 변화 보고 보관(IMP-GW-024)에서 뺐다. 재기동하면 기억이 비고, 처음 보는 ID의 보고를 첫 보고로 낸다(README) | `src/swarm_gateway/command_state.py`, `gateway.py`, `retain.py` | DEC-097 | TC-GW-039~041 통과 |
| IMP-GW-033 | UCI 시각 기준 시각의 출처와 우선순위(계약 0.20.0 §1): `--sim-epoch`(명시 재정의) > `sim/ctrl/scenario`의 `Scenario.run.epoch_utc_us`(0이 아닐 때) > 시나리오 전 첫 메시지 벽시계 기준(경고 로그). 첫 메시지 기준으로 정한 뒤 시나리오 값이 오면 시나리오 값으로 바꾸고 차이를 경고 로그와 `epoch_changed`에 남긴다. 새 시나리오의 다른 값이면 다시 정하고, 같은 값 재발행·0은 그대로 둔다. `--sim-epoch`가 있으면 시나리오 값은 로그만 남긴다. 시나리오는 한 번 해석해 알려진 기체(IMP-GW-029)와 시각에 함께 쓴다 | `src/swarm_gateway/converters/base.py`(`SimClock.on_scenario_epoch`), `gateway.py`, `entities.py`, `__main__.py` | DEC-098, QA D-36 | TC-GW-042, TC-GW-043 통과 |
| IMP-GW-034 | 준비 전 외부 명령 보관(QA O-13, 안 A): LA-CAL 접속 직후 외부 명령 4종을 SUB한다. 구독 목록은 XSD 없이 descriptor·변환기로 정한다(`inbound_entries`). XSD 적재·매핑 생성은 스레드에서 하고(`asyncio.to_thread`) 그동안 받은 메시지는 `PreReadyInbox`에 받은 순서대로 둔다(최대 256, 넘으면 오래된 것 버림·`pre_ready_dropped`). 준비 뒤 `settle_s`(기본 1.5 s) 동안 시나리오·수신 보고로 알려진 기체를 모은 다음 순서대로 처리한다(`pre_ready_flushed`, 건별 로그). 처리 전에 온 것도 같은 줄에 붙여 순서를 지킨다. `Running.subscribed_after_s`. 남는 손실(SUB 전·Gateway 부재)은 외부 C2 재송신 책임으로 문서화(README) | `src/swarm_gateway/runner.py`, `gateway.py`, `tools/measure_o13.py` | QA O-13, P-GW-001 | TC-GW-015, TC-GW-044~046 통과, 측정(메모) |
| IMP-GW-035 | 시작 때 시나리오 조회(DEC-109, 계약 0.24.0): `sim/ctrl/scenario` 구독을 연 다음 스레드에서 `Bus.get`으로 조회한다. 응답이 없으면 `scenario_query_interval_s`(기본 0.5 s) 뒤 다시, 최대 `scenario_query_attempts`(기본 5)번, 한 번 `scenario_query_timeout_s`(기본 1.0 s). 구독으로 먼저 받으면 멈추고, 다 해도 없으면 경고 뒤 구독을 기다린다. 조회 실패는 구독에 영향 없음. 같은 시나리오 바이트는 한 번만 반영(`scenario_duplicate`, 보고 목록·기준 시각 그대로), 다른 시나리오는 IMP-GW-029·033 규칙. 시각 기준 우선순위는 그대로이고, 전환 로그에 받은 길·앞 기준 경과 시간·마지막 모의 시각을 남긴다(`SimClock.last_change`). CLI `--scenario-query-attempts/-interval/-timeout` | `src/swarm_gateway/gateway.py`(`query_scenario`, `_on_scenario`), `converters/base.py`(`SimClock`), `__main__.py` | DEC-109, QA O-53, IMP-API-026 | TC-GW-047~051 통과 |
| IMP-GW-036 | 외부 교환 봉투(DEC-111): 송신은 `MA_TxDataPayloadCommand`(내부 머리 복사, 새 CommandID, NEW, Priority 1/1, MessageType, 내부 머리 시각, 선택 SpecificDestinationID, DestinationRouting TOPIC_AND_SPECIFIC_DESTINATION, 봉투·내부 XSD 검증), 수신은 `MA_RxDataPayload`(봉투 검증 → EncodedPayload hex → 내부 XML XSD 검증 → OMS JSON → 기존 수신). 목적지가 비었거나 우리 UUID 포함일 때만 받고 아니면 무시. MessageType은 XSD `MessageTypeEnum`에서 이름 변환으로 찾고 내부와 맞아야 한다. 봉투 켜면 내보낼 문자열을 ASCII로(é→e, 그 밖 ?), 받은 비ASCII는 거부, 봉투 없는 메시지 거부. 거부 통지·늦게 붙은 구독자 재전송도 봉투(`MA_TxDataPayloadCommand@<토픽>`). LA-CAL 토픽은 내부 메시지 토픽 그대로. CLI `--envelope on|off`(기본 on), `--envelope-dest`. 라이브러리 `GatewayConfig.envelope` 기본은 꺼짐. CAL Server 설정 `lacal_server.yaml`(봉투 흐름)·`lacal_server_raw.yaml`(끔) | `src/swarm_gateway/envelope.py`, `gateway.py`(`outbound`, `handle_incoming`), `runner.py`, `retain.py`, `__main__.py`, `config/` | DEC-111, OPN-085 | TC-GW-052~056 통과 |
| IMP-GW-037 | 시험 하네스 STOMP 경로(DEC-110): asyncio STOMP 1.2 클라이언트(CONNECT accept-version 1.2·heart-beat 0,0, SUBSCRIBE ack auto, SEND content-length, 머리 이스케이프, 의존성 추가 없음). `/topic/<UCI 이름>`에 XSD 검증한 UCI XML(UUID 32자 hex)을 내고, 봉투면 `/topic/MA_RxDataPayload`, 끄면 수신 UCI 이름 토픽을 받아 XML 검증 → OMS JSON → 봉투·수신 처리. 구독은 XSD 적재 전, 그동안 온 것은 PreReadyInbox. 시작·정지 신호에 `TestHarness_SignalAck`(RequestID 그대로, COMPLETED·CANCELED, 바로 응답). `--transport lacal|stomp`, `--stomp`, `--stomp-login/passcode`, `--system-uuid`(기본 GCS uuid5), `--schema-version`(기본 006.0.ASK), `--exclude`(005로 시작하면 기본 MA_NavigationReport·MA_Entity) | `src/swarm_gateway/stomp.py`, `runner.py`(`start_stomp_gateway`), `gateway.py`(`handle_xml`, `signal_ack`, `schema_version`, `exclude_messages`), `__main__.py` | DEC-110, OPN-091 | TC-GW-057~061 통과 |
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
| TC-GW-009 | 구독은 `swarm/gcs-01/rx/**`와 `sim/ctrl/scenario`(D-35)뿐, `truth/**`·`onboard/**`·`link/**`·다른 엔티티 키 미수신, 발행은 `swarm/gcs-01/tx/c2/**`뿐, CLI가 `open_bus` 사용, `--no-multicast`가 멀티캐스트를 끔 | `tests/test_bus_scope.py` | DEC-068, DEC-026 | 통과 |
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
| TC-GW-028 | 변화 보고만 보관(7차부터 `FlightCommandStatus` 제외 7종), 같은 키는 덮어쓰고 기체·payload·무장별로 따로 둠, 종료 상태(IMPACT, COMPLETED, CANCELLED, 표본의 REJECTED)는 지움, 검증 실패분은 두지 않음, 건수 상한 | `tests/test_late_join.py` | IMP-GW-024 | 통과 |
| TC-GW-029 | 그래프 이벤트 처리: 새 sub 간선마다 한 번, 몰린 구독 합침, 보관 값 없는 대상·pub 간선·알던 구독은 보내지 않음, 해제 뒤 재구독은 다시 보냄, `remote_updated`는 `GET /graph`로 비교, 기본 관리 주소 | `tests/test_late_join.py` | IMP-GW-025 | 통과 |
| TC-GW-030 | 실제 CAL Server: 보고 뒤에 구독한 외부 클라이언트가 `SystemStatus` 마지막 값(NOMINAL)과 `MA_FlightCapability`를 받음, 새 구독이 없으면 다시 보내지 않음, 주기 재송신 없음. `admin_url=None`이면 끔, 관리 포트가 없어도 1단계는 동작, CLI `--lacal-admin` | `tests/test_late_join.py` | IMP-GW-025 | 통과 |
| TC-GW-031 | DEC-088 4종 × 값 변형 2개가 Agent 모양 봉투로 와서 별도 적재한 공개 XSD 통과, `swarm.<iface>`로 발행, 내용(요청·작업 ID와 응답 대상 기억, 지도자 유무, 위치·속도·연결 표적·환경, 스테이션별 잔량), 브로드캐스트 dst, 다른 GCS rx는 받지 않음 | `tests/test_reports_088.py` | IMP-GW-026 | 통과 |
| TC-GW-032 | 실제 CAL Server: 4종 변형 8건이 외부 구독자에게 도달(서버 XSD 검증 통과) | `tests/test_reports_088.py` | IMP-GW-026 | 통과 |
| TC-GW-033 | 모든 `CommandState`·`StrikeState` 값의 외부 표현이 공개 XSD enum 안, FlightCommandStatus EXECUTING·COMPLETED → ACCEPTED, TaskStatus는 EXECUTING·COMPLETED 그대로, 내보낸 XML을 다시 읽으면 같은 JSON(표준 밖 필드 없음) | `tests/test_reports_088.py` | IMP-GW-027 | 통과 |
| TC-GW-035 | 시나리오·수신 보고에 없는 `uav-999`를 가리키는 `MA_TaskCommand`(단독·알려진 기체와 섞임)·`MA_RoutePlan`·`MA_MissionPlan`은 거부 기록, 버스 발행 0. 시나리오만·수신 보고만으로 알려짐, 시나리오가 바뀌면 보고 목록 비움, UAV가 아닌 엔티티·GCS 자신은 대상 아님, 못 읽는 시나리오는 무시(`bad_scenario`) | `tests/test_qa29.py` | IMP-GW-029 | 통과 |
| TC-GW-036 | 거부한 작업 명령은 `MA_TaskStatus`(`DROPPED`, 대상 `uav-999`, 사유)로 외부에 알림(공개 XSD 통과). 실제 CAL Server: 외부 `external_c2`가 `uav-999` 명령을 PUB하면 tx 발행 없이 `MA_TaskStatus`(`DROPPED`)를 받음 | `tests/test_qa29.py` | IMP-GW-029 | 통과 |
| TC-GW-037 | 가짜 벽시계로 40 s·259 s 정지와 10배속을 넣어도 `MA_NavigationReport`·`MA_PositionReport`의 모든 시각(머리, Position·DomainVelocity·Orientation)에서 (Timestamp − 모의 시각)이 하나. `--sim-epoch`면 정확한 값, `MA_Entity` 머리는 보고 모의 시각·운동·식별 시각은 관측 모의 시각. `SimClock` 기준 고정, CLI `--sim-epoch` 해석(시간대 없으면 거부) | `tests/test_qa29.py` | IMP-GW-030 | 통과 |
| TC-GW-038 | `external_c2` `declared.sub` = Gateway가 외부로 내는 흐름(15) = `swarm_gateway` `declared.pub`, 각 UCI 메시지가 README 교환 표에 있음. 11차부터 봉투 끔 설정 `lacal_server_raw.yaml` 기준(봉투 설정은 TC-GW-056) | `tests/test_qa29.py` | IMP-GW-031 | 통과 |
| TC-GW-039 | 내부 ACCEPTED→EXECUTING→COMPLETED·CANCELLED·FAILED, REJECTED→EXECUTING, 첫 CANCELLED(→ACCEPTED), RECEIVED 반복→ACCEPTED→COMPLETED, 첫 보고 EXECUTING, ACCEPTED 반복이 외부로 끝 상태 한 번(docs/44 C5 '명령 상태' 규칙 통과). ID·기체별 분리, `MA_TaskStatus`는 상태 기계 밖 | `tests/test_command_state.py` | IMP-GW-032 | 통과 |
| TC-GW-040 | 게이트 단위 규칙(RECEIVED 반복, 끝 상태 뒤 거부, 명령 상태가 아닌 메시지, 상한). 재기동한 Gateway는 끝난 ID의 다음 보고를 한 번 내고 그 뒤 막음 | `tests/test_command_state.py` | IMP-GW-032 | 통과 |
| TC-GW-041 | `MA_FlightCommandStatus`는 늦게 붙은 구독자 전달 대상이 아님 | `tests/test_command_state.py`, `tests/test_late_join.py` | IMP-GW-032, IMP-GW-024 | 통과 |
| TC-GW-042 | 우선순위: 시나리오 기준 시각을 씀(`epoch_set`), `--sim-epoch`가 시나리오 값보다 우선, 시나리오 값 0이면 첫 메시지 벽시계 기준과 경고 로그 | `tests/test_epoch.py` | IMP-GW-033 | 통과 |
| TC-GW-043 | 첫 메시지 기준 뒤 시나리오 값이 오면 바꾸고 경고(`epoch_changed`), 그 뒤 (Timestamp − 모의 시각) 일정. 같은 값 재발행은 그대로, 새 시나리오 다른 값은 다시 정함, 0은 그대로. `SimClock` 단위 규칙, proto 필드 번호 | `tests/test_epoch.py` | IMP-GW-033 | 통과 |
| TC-GW-044 | `PreReadyInbox`: 준비 전 버스 발행 없음, 받은 순서 유지, 상한 넘으면 오래된 것부터 버림, 처리 뒤 바로 처리. 기다리는 동안 온 수신 보고로 알려진 기체가 되어 발행, 보고·시나리오가 없으면 D-35대로 거부 | `tests/test_pre_ready.py` | IMP-GW-034 | 통과 |
| TC-GW-045 | 실제 CAL Server: SUB 뒤 XSD 적재(1 s로 흉내) 동안 외부가 PUB한 명령 4건이 준비·settle 뒤 순서대로 tx로 나감, SUB 완료 < 1 s ≤ 준비, 준비 뒤 명령은 바로 | `tests/test_pre_ready.py` | IMP-GW-034 | 통과 |
| TC-GW-046 | XSD 없이 정한 준비 전 SUB 목록 = XSD를 적재한 Gateway의 수신 목록(4종) | `tests/test_pre_ready.py` | IMP-GW-034 | 통과 |
| TC-GW-047 | Core 발행을 놓친 뒤 시작: 구독을 연 다음 조회 한 번으로 시나리오를 받아 알려진 기체·기준 시각(`epoch_set`)을 정함. 구독이 조회보다 먼저 | `tests/test_scenario_query.py` | IMP-GW-035 | 통과 |
| TC-GW-048 | 조회로 받은 뒤 같은 시나리오 재발행 3번·재조회: `scenario_duplicate`만 늘고 보고 목록·기준 시각 그대로(`epoch_changed` 0). 다른 시나리오(재적재)는 보고 목록을 비우고 기준 시각을 바꿈 | `tests/test_scenario_query.py` | IMP-GW-035, IMP-GW-029, IMP-GW-033 | 통과 |
| TC-GW-049 | 응답자 없음: 설정한 시간 초과로 다시 조회하고 두 번째 조회 중 발행으로 받으면 세 번째는 하지 않음. 끝까지 없으면 횟수만큼 뒤 경고·`scenario_query_none`, 그 뒤 발행으로 받음. 조회 끔(0), 간격 대기 중 `close`로 바로 끝남, 조회 예외에도 구독 동작 | `tests/test_scenario_query.py` | IMP-GW-035 | 통과 |
| TC-GW-050 | 알려진 기체 확인(IMP-GW-029)이 조회로 받은 목록을 씀: 보고 없이 조회 목록의 기체 명령은 발행, 목록 밖 UAV·비UAV는 거부 | `tests/test_scenario_query.py` | IMP-GW-035, IMP-GW-029 | 통과 |
| TC-GW-051 | 첫 메시지 기준 뒤 조회로 시나리오가 오면 전환하고 경고 로그 한 줄에 `by query`, 앞 기준 경과(0.515 s), 마지막 모의 시각을 남김. `--sim-epoch`는 조회한 시나리오 값보다 우선 | `tests/test_scenario_query.py` | IMP-GW-035, IMP-GW-033 | 통과 |
| TC-GW-052 | 송신 봉투: 토픽 그대로, MessageType·NEW·Priority·DestinationRouting·SpecificDestinationID, EncodedPayload 대문자 hex·XML 선언·ASCII, 내부 머리 복사, 매번 새 CommandID, 봉투·내부 XSD 통과, MessageData 순서, XML UUID 32자 hex, XSD 860개 이름 모두 MessageTypeEnum 대응 | `tests/test_envelope.py` | IMP-GW-036 | 통과 |
| TC-GW-053 | 수신 봉투: 목적지 없음·우리 UUID·여러 UUID 중 우리 것이면 tx 발행(C2·MP), 다른 UUID만이면 무시(거부 아님), MessageType 불일치·비ASCII·내부 XSD 위반·hex 아님은 거부, 봉투 켜면 봉투 없는 메시지 거부, D-35 거부 통지도 봉투 | `tests/test_envelope.py` | IMP-GW-036 | 통과 |
| TC-GW-054 | 봉투 켜면 비ASCII 자유 문장(거부 사유)을 ASCII로 바꿔 내고 `envelope_ascii_replaced`를 셈 | `tests/test_envelope.py` | IMP-GW-036 | 통과 |
| TC-GW-055 | 실제 CAL Server: 외부가 `MA_RxDataPayload`로 보낸 명령이 tx로 나가고, 외부는 `MA_TxDataPayloadCommand`(vi·c2)로 NavigationReport·PositionReport·TaskStatus를 받아 풂. 다른 목적지 봉투는 무시 | `tests/test_envelope.py` | IMP-GW-036 | 통과 |
| TC-GW-056 | 늦게 붙은 구독자 대상에 `MA_TxDataPayloadCommand@<토픽>`이 들어감, CAL Server 설정 두 벌의 declared가 각 모드의 실제 흐름과 같음, CLI 기본값 | `tests/test_envelope.py` | IMP-GW-036, IMP-GW-026 | 통과 |
| TC-GW-057 | STOMP 프레임 부호화·해석(머리 이스케이프, content-length로 NUL 포함 본문, 심장 박동 줄 건너뜀, CONNECT 머리 이스케이프 안 함), 가짜 브로커로 CONNECT(1.2, 0,0)·SUBSCRIBE·SEND·MESSAGE | `tests/test_stomp.py` | IMP-GW-037 | 통과 |
| TC-GW-058 | 봉투 켬: 구독 `/topic/MA_RxDataPayload`·신호 2개, 우리 UUID 봉투는 tx 발행, 다른 목적지는 무시, XML 아님은 거부. XSD 적재 중 온 봉투는 쌓았다가 처리, 그때 온 신호도 응답 | `tests/test_stomp.py` | IMP-GW-037 | 통과 |
| TC-GW-059 | 송신 `/topic/MA_TxDataPayloadCommand` XML이 XSD 통과, UUID 모두 32자 hex, SystemID = 플랫폼 UUID, 내부 SchemaVersion. 봉투 끄면 `/topic/MA_TaskCommand` 구독·`/topic/MA_TaskStatus` 송신 | `tests/test_stomp.py` | IMP-GW-037 | 통과 |
| TC-GW-060 | 시작·정지 신호 → `TestHarness_SignalAck` `ServiceConfigurationChangeRequestStatus`(XSD 통과, RequestID 그대로, COMPLETED·CANCELED), 읽을 수 없는 신호에도 응답 | `tests/test_stomp.py` | IMP-GW-037 | 통과 |
| TC-GW-061 | `--schema-version 005.0a.ASK`: MA_NavigationReport·MA_Entity 안 냄(`excluded.*`), 머리 SchemaVersion 005.0a.ASK. CLI 기본값·`--exclude none`·`--system-uuid` 32자 hex 입력·uuid5 기본 | `tests/test_stomp.py` | IMP-GW-037 | 통과 |
| TC-GW-034 | `lacal_server_raw.yaml`(11차 전 `lacal_server.yaml`)의 `swarm_gateway` `declared.pub`·`sub`이 Gateway의 실제 PUB·SUB와 같음(`MA_PositionReport` 포함), `external_c2` pub = Gateway 수신 | `tests/test_reports_088.py` | IMP-GW-028 | 통과 |
| TC-GW-015 | 실제 CAL Server 접속에서 로그 순서: connected → SUB → receiving → XSD → ready (9차부터 SUB가 XSD 앞) | `tests/test_roundtrip.py` | IMP-GW-017 | 통과 |

시험 결과: `cd gateway && uv run pytest` → 182 passed (2026-11-24, 11차 STOMP 단계, Windows 11, Python 3.12, 계약 0.24.0, Zenoh 미설치 환경). 11차 봉투 단계는 173 passed (2026-11-24, Windows 11, Python 3.12, 계약 0.24.0, Zenoh 미설치 환경). 10차는 152 passed (2026-11-24, Windows 11, Python 3.12, 계약 0.24.0, Zenoh 미설치 환경. Zenoh 버스 조회는 시험하지 않음). 9차는 142 passed (2026-11-22, Windows 11, Python 3.12, 계약 0.20.0, Zenoh 미설치 환경). 8차는 137 passed (2026-11-20, Windows 11, Python 3.12, 계약 0.20.0, Zenoh 미설치 환경). 7차는 131 passed (2026-11-19, Windows 11, Python 3.12, 계약 0.19.0, Zenoh 미설치 환경). 6차는 117 passed (2026-11-18, Windows 11, Python 3.12, 계약 0.19.0, Zenoh 미설치 환경). 5차는 106 passed (2026-11-16, Windows 11, Python 3.12, 계약 0.19.0, Zenoh 미설치 환경). 4차는 85 passed(`--extra zenoh` 환경 84 passed, 1 skipped). 3차는 51 passed. 2차는 43 passed (2026-11-08), 1차는 35 passed (2026-11-07).

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
| CR-GW-009 | 등록부(DEC), 시나리오 | 계획 대상 `ApplicableToIDs`의 `PackageID`·`ALL`을 엔티티로 펴는 규칙. 필요하면 그룹 ↔ 패키지 대응과 GCS가 지휘하는 기체 목록을 Gateway에 알리는 방법을 정한다 | Gateway는 그룹 구성원을 읽지 않아 `dst`를 채울 수 없다. 지금은 거부한다. 6차부터 시나리오 엔티티 목록은 읽는다(IMP-GW-029) |
| ~~OPN-GW-001~~ | 해소: DEC-096 (계약 0.20.0 §3.2 표에 Gateway 추가). 원문 대상: 계약 §3.2 키 표 `sim/ctrl/scenario` 구독자 | 구독자에 Gateway를 더한다(용도: 알려진 기체 목록, 읽기만) | D-35는 "알려진 엔티티를 truth가 아니라 Gateway가 받을 수 있는 정보로" 정하라고 했다. 시나리오는 늦게 켠 참여자도 받는 유일한 엔티티 목록이다. 지금 표에는 Datalink·Agent·Logger·UI만 있다. 계약 변경 없이 쓰려면 수신 보고만으로 정해야 하는데, 그러면 아직 보고하지 않은 기체(기동 직후)에 대한 정상 명령이 거부된다 |
| ~~OPN-GW-002~~ | 해소: DEC-098 (계약 0.20.0 `RunSpec.epoch_utc_us`), IMP-GW-033. 원문 대상: 계약 시각 규칙(`Header.sim_time_us`), `Scenario` | 모의 시각 0의 UTC(기준 시각)를 계약에 정한다. 예: `Scenario`에 `epoch_utc` 필드를 두거나 "UTC = 시나리오 시작 벽시계 + 모의 시각" 규칙을 적는다 | D-36은 "모의 시각과 UTC 기준 시각의 대응은 기존 계약을 따르라"고 했으나 계약에는 대응이 없다. Gateway는 `--sim-epoch` 또는 첫 메시지 기준으로 정해 (Timestamp − 모의 시각)을 일정하게 했다. 참여자마다(Logger·UI 등) 기준이 다를 수 있고, Gateway 재기동 시 기준이 바뀐다(`--sim-epoch`로 고정 가능) |
| (원문) CR-GW-001 | `proto/swarm/v1/vi.proto`, `p2p.proto`, 등록부 §5 | `NavigationReport`의 `uci_name`을 `MA_PositionReport`로 바꾸거나, 한 내부 메시지가 UCI 메시지 여러 개에 대응할 수 있게 옵션을 늘린다(예: `repeated string uci_also`). `PeerStatus`의 운동 상태도 같은 방식으로 `MA_PositionReport`에 싣는다 | 공개 XSD의 `MA_NavigationReport`·`MA_PackagePartnerStatusReport`에는 위치가 없다. 위치는 `MA_PositionReport`(InertialState: Position·DomainVelocity·Orientation)에 있다. 등록부 §5도 후보로 `MA_PositionReport`를 적었다 |
| CR-GW-004 | 루트 `pyproject.toml` | `[tool.uv.workspace] members`, `[tool.uv.sources]`, dev 그룹, `testpaths`에 `gateway`(`swarm-gateway`)를 추가한다. 루트 시험에 넣으려면 CI·개발 환경에서 서브모듈 초기화가 필요하다 | 지금은 `gateway/` 밖 수정 금지라 독립 uv 프로젝트(`gateway/uv.lock`)로 두었다 |
| CR-GW-006 | 등록부 §5 | §5 표를 proto 기준으로 갱신한다: STD 21종의 실제 대응(예: `PeerStatus`→`MA_PackagePartnerStatusReport`, `TrackShare`→`MA_Entity`) | 계약 §4: 어긋나면 proto가 기준. Gateway가 descriptor로 만든 표(위)를 그대로 옮기면 된다 |

남은 요청: CR-GW-004, CR-GW-006, CR-GW-007, CR-GW-008, CR-GW-009. OPN-GW-001(DEC-096)·OPN-GW-002(DEC-098)는 해소. CR-GW-006(등록부 §5 갱신)에는 `uci_also`(`MA_PositionReport`) 열도 넣어야 한다. CR-GW-002·003·005의 원문은 위 해소 줄로 정리했다.

## 제안 (동작 변경, 미구현)

| ID | 내용 | 근거 |
|---|---|---|
| ~~P-GW-001~~ | 9차 IMP-GW-034로 (1)을 넘어 SUB를 XSD 적재 앞으로 옮기고 준비 전 수신분을 보관했다. (2)의 외부 재송신 규칙은 README에 외부 C2 책임으로 적었다. 원문: 준비 전 구간 줄이기(O-13). (1) XSD 적재·매핑 생성을 LA-CAL 접속 **앞**으로 옮긴다. 지금은 INIT 뒤 XSD 적재(대부분의 시간)가 끝나야 SUB가 걸리므로, 순서만 바꿔도 "접속돼 보이지만 받지 못하는" 구간이 SUB 왕복 시간으로 준다. (2) 근본적으로는 외부 C2가 준비를 알 수 있어야 한다: 예를 들어 ready 시점에 Gateway가 `SystemStatus`(SystemID = Gateway 서비스, Communications ACTIVE)를 한 번 발행하거나, 외부 C2가 명령 뒤 `MA_TaskStatus`가 일정 시간 안에 오지 않으면 다시 보내는 규칙을 둔다. (2)는 계약(등록부) 결정이 필요하다 | QA 15차 O-13 |

## 메모

- DEC-089 전달 방식: OWP 1.0(agra_lacal)에는 보관(retained·durable) 메시지, 구독 알림, 상태 요청이 없다. 구독 시점을 아는 유일한 곳이 CAL Server 관리 포트의 그래프 API라 이를 쓴다. 관리 포트는 OWP 포트와 따로 열리고(기본 127.0.0.1:8766) 인증이 없다. 다른 PC에서 CAL Server를 띄우면 관리 포트를 Gateway에 열어 주거나 `--lacal-admin`을 지정해야 한다. 열 수 없으면 늦게 붙은 외부 시스템은 다음 변화까지 기다린다(1·2단계는 영향 없음).
- 다시 PUB한 값은 OWP에 수신자 지정이 없어 같은 (메시지, 토픽)의 기존 구독자에게도 한 번 더 간다. 변화 보고는 마지막 상태라 뜻이 바뀌지 않는다. `MessageHeader.Timestamp`는 원래 보고 시각 그대로다.
- Gateway가 재기동하면 보관 값이 없다. 그 경우의 복구는 Agent의 링크 복구 재송신(DEC-089 Agent 쪽)이나 다음 변화에 맡긴다.
- DEC-088 확인 중 본 점: `MA_Entity`의 `KinematicsTimeStamp`·`IdentityTimestamp`가 벽시계였던 것은 6차 IMP-GW-030에서 관측 모의 시각으로 고쳤다. `LeaderUpdate.group_id`가 비면 `ApplicablePackageID`가 빈 이름의 UUID가 된다(XSD는 통과).

- `MA_MissionPlan`의 대상 표현(XSD 확인): `Applicability`의 `ApplicableToIDs`가 `ALL | NON | PackageID | SystemID`의 선택이다. Gateway는 `SystemID` 하나만 `dst`로 쓴다. `PlannedForID`는 XSD 주석상 계획의 사용자(상위 C2일 수 있음)라 대상으로 쓰지 않는다. `MA_RoutePlan`은 `Plan/Applicability`에 같은 구조로 있다. 임무 계획 자체는 작업 내용 없이 하위 계획을 ID로 참조한다.
- QA O-14(재기동 시 `header.seq`가 0부터): DEC-077에 따라 seq는 발행자·키별이고 `publisher`로 구분한다. 재기동한 Gateway가 같은 `publisher`로 0부터 다시 매기는 것은 새 발행 세션으로 보며, 이번에 동작을 바꾸지 않았다. Datalink·Agent는 seq 연속성에 의존하지 않는다(QA 15차 TC-QA-073).

- SecurityInformation은 스키마 필수 요소라 공개 스키마 예제와 같은 값(`U`, `USA`)을 기본으로 넣는다. `GatewayConfig.classification`, `owner_producer`로 바꾼다.
- 시각은 메시지 모의 시각의 UTC다(IMP-GW-030, `SimClock`). 기준 시각은 시나리오 값(IMP-GW-033)이다. 메시지를 하나도 받기 전 시각(예: 첫 보고 전 거부 통지)만 벽시계다. `MA_ApprovalRequest.RespondBy`는 그 보고 시각 + 승인 창이다.
- D-35 거부 통지 `MA_TaskStatus`는 Gateway가 만든 상태 보고다. `ExecutingSystemOrPackage`는 명령이 가리킨 기체, 머리 `SystemID`는 Gateway 서비스다. 시각은 마지막으로 본 모의 시각이다.
- 외부 C2 수신은 LA-CAL 쪽 검증(서버)과 Gateway 쪽 검증(코덱)을 모두 거친다.

- QA O-13 측정(9차, `uv run python tools/measure_o13.py`, 2026-11-22, 이 PC): CAL Server 별도 프로세스, 외부 C2가 0.5 s 간격으로 `MA_TaskCommand` PUB, Gateway를 매 회 새 프로세스로 재기동(5회). 시간은 앞 Gateway 종료 기준 s, `lost`는 그 회에 tx로 나가지 않은 PUB 수.
  - 고치기 전(8차 코드: 접속 → XSD 적재 → SUB):

| run | down_to_spawn_s | spawn_to_connected_s | connected_to_sub_s | sub_to_ready_s | exit_to_ready_s | lost | lost_after_connected | lost_after_sub | loss_span_s | first_received_after_exit_s | rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.196 | 0.897 | 4.28 | 0.001 | 5.374 | 11 | 8 | 0 | 5.004 | 5.487 | 0 |
| 2 | 0.197 | 0.828 | 4.294 | 0.002 | 5.32 | 10 | 8 | 0 | 4.515 | 5.403 | 0 |
| 3 | 0.188 | 0.821 | 4.294 | 0.002 | 5.304 | 10 | 8 | 0 | 4.503 | 5.377 | 0 |
| 4 | 0.218 | 0.821 | 4.281 | 0.001 | 5.322 | 10 | 8 | 0 | 4.517 | 5.367 | 0 |
| 5 | 0.186 | 0.869 | 4.477 | 0.001 | 5.533 | 11 | 9 | 0 | 5.011 | 5.824 | 0 |

  - 고친 뒤(IMP-GW-034: 접속 → SUB → XSD 적재, 준비 전 보관):

| run | down_to_spawn_s | spawn_to_connected_s | connected_to_sub_s | sub_to_ready_s | exit_to_ready_s | lost | lost_after_connected | lost_after_sub | loss_span_s | first_received_after_exit_s | rejected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.201 | 0.863 | 0.017 | 4.367 | 5.448 | 2 | 0 | 0 | 0.514 | 1.322 | 0 |
| 2 | 0.202 | 0.823 | 0.018 | 4.364 | 5.407 | 2 | 0 | 0 | 0.484 | 1.173 | 0 |
| 3 | 0.193 | 0.874 | 0.018 | 4.339 | 5.424 | 3 | 0 | 0 | 1.002 | 1.552 | 0 |
| 4 | 0.199 | 0.831 | 0.017 | 4.318 | 5.365 | 2 | 0 | 0 | 0.501 | 1.41 | 0 |
| 5 | 0.191 | 0.818 | 0.016 | 4.305 | 5.331 | 2 | 0 | 0 | 0.499 | 1.346 | 0 |

  - 해석: 고치기 전 손실 10~11건(약 4.5~5.0 s 폭) 중 8~9건은 접속 뒤 XSD 적재(약 4.3 s) 동안이었다. 고친 뒤에는 접속 뒤 손실 0이고, 남은 2~3건은 앞 Gateway 종료 → 새 프로세스 기동·접속(약 1.1 s) 동안이다. 이 구간은 받는 구독이 없어 Gateway가 고칠 수 없다(OWP 보관 메시지 없음).
  - 안 선택: (A). 손실의 대부분(약 80%)이 Gateway가 접속은 했으나 구독하지 않은 구간이라 Gateway가 없앨 수 있었다. (B)만으로는 외부가 매 재기동마다 약 5 s를 잃고 재송신해야 한다. 남은 약 1 s는 (B) 외부 재송신 책임으로 README에 적었다.
