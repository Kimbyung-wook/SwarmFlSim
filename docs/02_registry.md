# 요구·제안·결정사항 등록부

ID 규칙은 [01_id_convention.md](01_id_convention.md)를 따른다. 기준일은 2026-11-01이다.

## 1. 요구사항 (REQ)

| ID | 요구사항 | 근거 | 상태 |
|---|---|---|---|
| REQ-UI-001 | 군집 무인기의 거동을 지도 위에 2D/3D로 전시한다 | 사용자 요구 | Draft |
| REQ-UI-002 | RTS식 선택: 드래그 박스, 부대 그룹 지정·호출 | 사용자 요구 | Draft |
| REQ-UI-003 | 선택한 대상(개별/그룹)에 대해 수행 가능한 액션을 메뉴로 고른다 | 사용자 요구 | Draft |
| REQ-UI-004 | 개별 통제와 군집/편대 통제를 모두 제공한다 | 사용자 요구 | Draft |
| REQ-UI-005 | 비행체와 지상체(GCS, 지상 표적·지상 장비)별로 메시지 트래픽을 모니터링하는 도구를 제공한다: 송수신 메시지 목록, 빈도·크기·지연·손실, 재밍으로 인한 손실 구분, 시퀀스 타임라인, 메시지 내용 조회 | 사용자 요구 | Draft |
| REQ-UI-006 | 여러 통제·관전 UI가 동시에 접속할 수 있다 | DEC-020 | Draft |
| REQ-UI-007 | 선택한 무인기·미사일·FPV의 1인칭 시점으로 카메라를 전환한다. 센서(짐벌) 시점과 3인칭 추적 시점도 제공한다 | 사용자 요구 | Draft |
| REQ-DYN-001 | 무인기 모델을 2/3/5/6-DoF 중에서 선택한다 | 사용자 요구 | Draft |
| REQ-DYN-002 | 2/3-DoF는 알고리즘 시험용, 5/6-DoF는 실기체 모사용으로 쓴다 | 사용자 요구 | Draft |
| REQ-DYN-003 | 제어·통신 프레임은 50–100 Hz로 실행한다 | 사용자 요구 | Draft |
| REQ-DYN-004 | 수치 적분기를 선택할 수 있다(RK4 고정 스텝, 가변 스텝) | 사용자 요구, DEC-005 | Draft |
| REQ-DYN-005 | 무장(미사일, FPV 드론)을 자체 동역학을 가진 엔티티로 모의한다 | 사용자 요구 | Draft |
| REQ-GNC-001 | 단일 비행체의 하위 유도/제어 계층을 설계·교체할 수 있다 | 사용자 요구 | Draft |
| REQ-BHV-001 | 상위 행동결정 계층을 설계·교체할 수 있다 | 사용자 요구 | Draft |
| REQ-BHV-002 | 경로 계획과 재계획 계층을 설계·교체할 수 있다 | 사용자 요구 | Draft |
| REQ-BHV-003 | 편대/군집 형성 행위를 설계·교체할 수 있다 | 사용자 요구 | Draft |
| REQ-BHV-004 | 계층마다 기본 제공 구현과 사용자 설계 구현 중에서 고를 수 있다 | 사용자 요구 | Draft |
| REQ-NET-001 | 통제 UI와 시뮬레이션을 이종 컴퓨터에 분산해 실행할 수 있다 | 사용자 요구 | Draft |
| REQ-PRF-001 | 20대 이상을 필수로 지원하고, 수백 대까지 확장할 수 있는 구조로 만든다 | 사용자 요구, DEC-006 | Draft |
| REQ-PRF-002 | 가속 목표: 6-DoF 20대 ≥10배, 3-DoF 100대 ≥10배, 6-DoF 300대 ≥실시간. 벤치마크로 확정한다 | 사용자 문의 | Draft |
| REQ-LNK-001 | 데이터링크의 지연, 손실, 대역폭 제한을 모의한다 | 사용자 요구 | Draft |
| REQ-LNK-002 | 재밍으로 인한 통제소 연결 불능을 모의한다 | 사용자 요구 | Draft |
| REQ-LNK-003 | 특정 비행체의 연결 불능을 모의한다 | 사용자 요구 | Draft |
| REQ-LNK-004 | 무인기 간 링크와 지상통제소-무인기 간 링크를 모두 모의한다 | 사용자 요구 | Draft |
| REQ-CFG-001 | 무인기 초기 상태를 GUI에서 설정한다 | 사용자 요구 | Draft |
| REQ-CFG-002 | 무인기 초기 상태를 JSON 파일로 설정하며, GUI와 파일이 같은 형식을 쓴다 | 사용자 요구 | Draft |
| REQ-PAY-001 | 무인기마다 다른 특성을 부여한다 | 사용자 요구 | Draft |
| REQ-PAY-002 | 센서(카메라) 성능 차이(FOV, 최대 탐지 거리)를 모의한다 | 사용자 요구, DEC-018 | Draft |
| REQ-PAY-003 | 특정 범위에 대한 전자전 재밍을 수행한다 | 사용자 요구 | Draft |
| REQ-PAY-004 | 물리적 타격(하드킬)을 수행한다 | 사용자 요구 | Draft |
| REQ-PAY-005 | 무장 탑재 구성(종류, 수량)을 기체별로 정한다: 단거리 공대공 미사일, 공대지 미사일, FPV 자폭 드론 | 사용자 요구 | Draft |
| REQ-SIM-001 | 공중·지상 표적과 적 엔티티를 모의한다(스크립트 경로 또는 알고리즘 기동) | REQ-PAY-005 파생 | Draft |
| REQ-SIM-002 | 실시간, 가속, 비결정론 실행 모드를 제공한다 | 사용자 요구, DEC-005 | Draft |
| REQ-SIM-003 | 오프라인 지도와 DEM 지형을 사용한다. 초기 범위는 한반도 전역, 저해상도 | DEC-004, DEC-016 | Draft |
| REQ-LOG-001 | 시뮬레이션 전체를 기록하고 재생한다 | DEC-011 | Draft |
| REQ-STD-001 | A-GRA 구조를 준용하고, 나중에 L1 전면 준수로 확장할 수 있게 만든다 | 사용자 요구, DEC-013 | Draft |

## 2. 제안사항 (PRP)

| ID | 제안 | 관련 REQ | 상태 |
|---|---|---|---|
| PRP-SIM-001 | 컴포넌트 구성: Sim Core, Vehicle Agent, Datalink Emulator, GCS/UI, Traffic Monitor, Scenario Manager, Logger/Replay, A-GRA Gateway | 전체 | Draft |
| PRP-SIM-002 | 시간 관리: 프레임 단위 lockstep(결정론적), 비동기 free-run(비결정론적) | REQ-SIM-002, REQ-NET-001 | Draft |
| PRP-SIM-003 | 전지적 상태(ground truth)와 기체 인지 상태를 분리한다. 기체는 센서와 데이터링크로 받은 정보만 본다 | REQ-BHV-001, REQ-LNK-* | Draft |
| PRP-DYN-001 | 2-DoF 이중적분기/유니사이클, 3-DoF 질점, 5-DoF 질점 + 롤·피치(협조선회), 6-DoF 고정익 강체 | REQ-DYN-001 | Draft |
| PRP-DYN-002 | 고정 프레임 + 프레임 안의 가변 스텝 RK45(Dormand-Prince). RK4 고정 스텝 선택 가능 | REQ-DYN-003, REQ-DYN-004 | Draft |
| PRP-DYN-003 | 미사일: 질점 + 비례항법(PN), 탐색기 FOV와 락온 조건, 추력·연소 시간. FPV: 소형 멀티콥터 3-DoF + 종말 유도 | REQ-DYN-005, REQ-PAY-005 | Draft |
| PRP-GNC-001 | MA→FA 명령은 A-GRA VI 제어 모드(HSA, Waypoint Following, Curve Following)를 따른다 | REQ-GNC-001, REQ-STD-001 | Draft |
| PRP-BHV-001 | 기체 계층 스택: 행동결정(BT/FSM) → 군집/편대 → 경로 계획 → 유도 → 제어 → 동역학. 계층마다 플러그인 인터페이스를 둔다 | REQ-BHV-*, REQ-GNC-001 | Draft |
| PRP-BHV-002 | 플러그인 API는 기체별 호출과 군집 일괄(NumPy 벡터화) 호출을 모두 제공한다 | REQ-PRF-001, REQ-PRF-002 | Draft |
| PRP-BHV-003 | 기본 제공 알고리즘: Reynolds/Olfati-Saber flocking, leader-follower, virtual structure, consensus 편대, A*/RRT*/Dubins 경로, PN/L1/vector field 유도, PID/LQR 제어 | REQ-BHV-004 | Draft |
| PRP-NET-001 | ASB 추상 계층 → Zenoh 백엔드. 테스트용 인메모리 백엔드 | REQ-NET-001 | Draft |
| PRP-NET-002 | Zenoh 키 체계: `swarm/<entity>/<iface>/<msg>`, 시뮬레이션 통제는 `sim/ctrl/**`로 분리 | REQ-NET-001, DEC-014 | Draft |
| PRP-NET-003 | PRP-NET-002 상세: 데이터링크 경유 `swarm/<src>/tx/**` → `swarm/<dst>/rx/**`, 기체 내부 `onboard/<id>/**`, 시간 분배 `sim/clock/**`, 링크 관측 `link/**`. 상세는 [10_contracts.md](10_contracts.md) §3 | REQ-NET-001, REQ-LNK-*, DEC-014 | Draft |
| PRP-LNK-001 | 링크 모델: 거리 기반 경로손실, Gilbert-Elliott 버스트 손실, 지연·지터, 대역폭 큐, 재밍 영역(영역 안 100% 손실) | REQ-LNK-* | Draft |
| PRP-LNK-002 | 모든 기체 간·지상-기체 간 메시지가 Datalink Emulator를 거치게 한다. 각 메시지에 전달/손실 사유를 태깅해 Traffic Monitor와 MCAP으로 보낸다 | REQ-LNK-*, REQ-UI-005 | Draft |
| PRP-UI-001 | CesiumJS 기반 2D/3D 단일 뷰(2D/Columbus/3D 전환), RTS 입력 계층 | REQ-UI-001~004 | Draft |
| PRP-UI-002 | Traffic Monitor: 엔티티 트리(비행체/지상체), 엔티티별 송수신 통계(빈도·크기·지연·손실·재밍 손실), 시퀀스 타임라인, 메시지 echo, 필터. 실시간 모드와 MCAP 재생 모드를 지원한다 | REQ-UI-005 | Draft |
| PRP-CFG-001 | 시나리오 JSON 구조는 A-GRA MP(Mission Data Bundle) 개념을 따른다: 기체·특성·무장·초기 상태·임무 계획·교전 기준. JSON Schema로 검증한다 | REQ-CFG-* | Draft |
| PRP-PAY-001 | 임무장비는 A-GRA MS 서비스 개념으로 모델링한다: PO(카메라), EA(재밍), Strike·Store(무장) | REQ-PAY-* | Draft |
| PRP-LOG-001 | MCAP 채널은 Zenoh 키와 1:1로 대응시킨다. Ground truth 채널을 별도로 기록한다 | REQ-LOG-001 | Draft |
| PRP-STD-001 | 내부 메시지는 A-GRA 상호작용 단위의 경량 스키마(Protobuf)로 정의하고, UCI 메시지와의 매핑 표를 유지한다 | REQ-STD-001 | Draft |
| PRP-STD-002 | A-GRA Gateway: 상호작용별 변환기 플러그인, agra_lacal에 LA-CAL 클라이언트로 접속, 외부로는 STD 메시지만 내보낸다 | REQ-STD-001 | Draft |

## 3. 결정사항 (DEC)

| ID | 결정 | 근거 | 상태 |
|---|---|---|---|
| DEC-001 | 언어: Sim Core C++20(CMake, Eigen), 알고리즘 플러그인 Python 3.12(uv, pybind11/nanobind), UI TypeScript, Gateway Python. Rust는 검토 후 기각 | OPN-001, 사용자: "언어는 C++ 으로 하자" | Confirmed |
| DEC-002 | 통신은 Zenoh만 쓰고 DDS는 쓰지 않는다. Gateway는 agra_lacal에 WebSocket(OWP)으로 접속한다 | OPN-002, OPN-014, 사용자: "Zenoh 만으로도 … 문제가 없다면 DDS 을 사용하지 않아도 된다" | Confirmed |
| DEC-003 | UI는 CesiumJS. Qt는 라이선스 때문에 제외 | OPN-003 | Confirmed |
| DEC-004 | 지도와 지형은 오프라인. DEM이 필요하다 | OPN-004 | Confirmed |
| DEC-005 | 실행 모드는 실시간, 가속 lockstep, 비동기 free-run. 적분은 고정 프레임 + 가변 스텝(RK45)이며, RK4 고정 스텝도 선택 가능 | OPN-005, 사용자: "수치 오차가 크지 않다면 가변 스텝 … 선택해도 됨" | Confirmed |
| DEC-006 | 규모: 수백 대까지 확장할 수 있는 프레임워크 | OPN-006 | Confirmed |
| DEC-007 | 기체: 고정익 기준 | OPN-007 | Confirmed |
| DEC-008 | 의사결정: 중앙집중형과 분산형을 모두 지원하고, 선택은 알고리즘에 맡긴다 | OPN-008 | Confirmed |
| DEC-009 | 재밍: 재밍 영역 안에서는 링크 100% 손실 | OPN-009 | Confirmed |
| DEC-010 | OS: Windows 네이티브 우선, WSL2/Linux 호환 | OPN-010 | Confirmed |
| DEC-011 | 기록·재생 포맷은 MCAP | OPN-011 | Confirmed |
| DEC-012 | 피해 판정: 탄체 위치는 동역학으로 계산하고, 살상반경 안의 대상은 즉시 파괴 | OPN-012 | Confirmed |
| DEC-013 | A-GRA: 구조 준용 + Gateway로 시작해 L1 전면 준수로 확장한다. MA는 L1 포트로만 통신한다 | OPN-015 | Confirmed |
| DEC-014 | A-GRA로 표현할 수 없는 운용 C2는 EXT 메시지로 추가한다. 시뮬레이션 통제는 별도 채널로 분리한다 | 사용자 문의 | Draft |
| DEC-015 | 개발은 WBS 작업 패키지 단위로 멀티 에이전트(병렬 세션) 구조로 나눈다. 패키지 간 계약은 인터페이스 스키마(Protobuf, Zenoh 키, 플러그인 API)로 먼저 고정한다 | 사용자: "멀티 에이전트 구조로 나누어서 개발해도 좋아" | Confirmed |
| DEC-016 | 지도·DEM: 한반도 전역을 저해상도로 준비한다. 고해상도 지역과 지역 변경은 추후에 한다 | OPN-016, 사용자: "한반도 전역을 저해상도로 해줘. 고해상도 및 지역 변경은 추후에 하자." | Confirmed |
| DEC-017 | 표적/적 엔티티: 기본은 스크립트 경로·고정 위치. 아군과 같은 MA 플러그인 인터페이스를 쓸 수 있어 적 군집 알고리즘도 붙일 수 있다 | OPN-017 | Confirmed |
| DEC-018 | 센서 탐지: FOV, 최대 거리, DEM 가시선(LOS)으로만 판정한다. 확률 모델은 도입하지 않는다 | OPN-018, 사용자: "FOV/거리/가시선 판정으로 정리하자. 확률은 도입하지 말고." | Confirmed |
| DEC-019 | 무장 성능: 공개 문헌의 일반값으로 기본 프로파일을 두고, 시나리오 JSON에서 재정의한다. 실제 체계 제원은 넣지 않는다 | OPN-019 | Confirmed |
| DEC-020 | 통제 UI: 여러 UI의 동시 접속(관전·통제)을 지금 구조에 반영한다. 역할별 권한(A-GRA C2 RBAC)은 P6 이후에 추가한다 | OPN-020 | Confirmed |
| DEC-021 | 저장소: 현재 저장소 하나를 모노레포로 쓰고, WP별 디렉터리로 나눈다. 병렬 세션은 worktree로 작업한다 | OPN-021 | Confirmed |
| DEC-022 | 빌드 툴체인을 하나로 고정하지 않는다. MSVC + vcpkg, MSYS2 UCRT64 GCC + pacman 패키지, Linux/WSL2 GCC + 배포판 패키지를 모두 CMake 프리셋으로 지원한다. 의존성은 `find_package`로만 찾는다 | DEC-010, 사용자: "msvc 와 vcpkg 가 없이 사용하는 안에 대해서도 대응되도록" (MSVC 라이선스 검토) | Confirmed |

## 4. 미결정사항 (OPN)

| ID | 질문 | 상태 |
|---|---|---|
| OPN-001 | 코어 언어 | Resolved by DEC-001 |
| OPN-002 | 미들웨어 | Resolved by DEC-002 |
| OPN-003 | UI 기술 | Resolved by DEC-003 |
| OPN-004 | 지도/지형 데이터 | Resolved by DEC-004 |
| OPN-005 | 시간 모델과 적분 | Resolved by DEC-005 |
| OPN-006 | 목표 규모 | Resolved by DEC-006 |
| OPN-007 | 우선 기체 유형 | Resolved by DEC-007 |
| OPN-008 | 군집 의사결정 방식 | Resolved by DEC-008 |
| OPN-009 | 재밍 모델 충실도 | Resolved by DEC-009 |
| OPN-010 | 개발/실행 OS | Resolved by DEC-010 |
| OPN-011 | 기록·재생 포맷 | Resolved by DEC-011 |
| OPN-012 | 타격 피해 판정 | Resolved by DEC-012 |
| OPN-013 | Rust 채택 여부 | Resolved by DEC-001 |
| OPN-014 | DDS 필요 여부 | Resolved by DEC-002 |
| OPN-015 | A-GRA 적용 범위 | Resolved by DEC-013 |
| OPN-016 | 지도·DEM 대상 지역과 해상도 | Resolved by DEC-016 |
| OPN-017 | 표적/적 엔티티의 행동 수준 | Resolved by DEC-017 |
| OPN-018 | 센서(카메라) 탐지 모델 충실도 | Resolved by DEC-018 |
| OPN-019 | 미사일·FPV 성능 파라미터 출처 | Resolved by DEC-019 |
| OPN-020 | 다중 통제 UI 동시 접속과 역할 기반 권한 | Resolved by DEC-020 |
| OPN-021 | 저장소 구조 | Resolved by DEC-021 |

## 5. A-GRA 메시지 매핑 (골격)

- 메시지명은 공개 XSD(`A-GRA_MessageDefinitions_v6_0_a.xsd`, Distribution A)에서 가져왔다.
- 내부 메시지명은 구현 단계에서 확정한다.
- 구분: `STD`는 UCI/A-GRA 메시지에 대응하고, `EXT`는 자체 확장 메시지다.

| L1 | 시뮬레이터 상호작용 | 후보 UCI/A-GRA 메시지 | 구분 |
|---|---|---|---|
| VI | 비행 명령(HSA/Waypoint/Curve)과 수락·거부 | `MA_FlightCommand`, `MA_FlightCommandStatus` | STD |
| VI | 비행 성능 조회 | `MA_FlightCapability`, `MA_FlightCapabilityStatus` | STD |
| VI | 기체 상태·위치 | `PositionReport`, `MA_PositionReport`, `MA_NavigationReport` | STD |
| VI | 하위 시스템 상태 | `SystemStatus`, `SubsystemStatus` | STD |
| C2 | 임무 부여 | `MA_TaskCommand`, `MA_TaskStatus` | STD |
| C2 | 팀(패키지) 구성 | `MA_PackageManagementCommand`, `MA_PackageManagementCommandStatus` | STD |
| C2 | 타격 승인 | `MA_ApprovalRequest`, `MA_ApprovalRequestStatus`, `StrikeConsentRequest` | STD |
| C2 | 운용자 역할(RBAC) | `MA_OperatorRole`, `MA_Authorization` | STD |
| C2 | 편대 형태 지정(RTS 명령) | 대응 메시지 없음 | EXT |
| P2P | 리더 선출 | `MA_RaftVoteRequest`, `MA_RaftAppendEntriesRequest`, `MA_LeaderUpdateRequest` | STD |
| P2P | COP 공유 | `MA_Entity`, `MA_PackagePartnerStatusReport` | STD |
| MS | 데이터 전송(DMS) | `MA_TxDataPayloadCommand`, `MA_RxDataPayload` | STD |
| MS | 카메라 | `PO_Command`, `PO_Activity` | STD |
| MS | 재밍 | `EA_Command`, `EA_Activity` | STD |
| MS | 타격·무장 | `StrikeCommand`, `StrikeActivity`, `StoreLoadoutConfiguration`, `MA_WEZ` | STD |
| MP | 임무 계획, 교전 기준 | `MA_MissionPlan`, `MA_EngagementCriteria`, `MA_RoutePlan` | STD |
| MD | 기록·재생 | MCAP (메시지 교환 없음) | — |
| Sim | 일시정지, 배속, 고장 주입, 리셋 | `sim/ctrl/**` 전용 | EXT (외부 비공개) |
