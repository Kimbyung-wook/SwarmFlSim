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
| REQ-CFG-003 | 비행체별 제어·유도·행위·결정 매개변수는 기본값을 가지며, 시작 시와 실행 중에 기체별로 설정할 수 있다 | 사용자 요구: "비행체 별로 제어/유도/행위/결정 파라미터는 기본 값이 있되, 설정할 수 있어야해." | Draft |
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
| DEC-012 | 피해 판정: 유도 객체 위치는 동역학으로 계산하고, 살상반경 안의 대상은 즉시 파괴 | OPN-012 | Confirmed |
| DEC-013 | A-GRA: 구조 준용 + Gateway로 시작해 L1 전면 준수로 확장한다. MA는 L1 포트로만 통신한다 | OPN-015 | Confirmed |
| DEC-014 | A-GRA로 표현할 수 없는 운용 C2는 EXT 메시지로 추가한다. 시뮬레이션 통제는 별도 채널로 분리한다 | 사용자 문의 | Draft |
| DEC-015 | 개발은 WBS 작업 패키지 단위로 멀티 에이전트(병렬 세션) 구조로 나눈다. 패키지 간 계약은 인터페이스 스키마(Protobuf, Zenoh 키, 플러그인 API)로 먼저 고정한다 | 사용자: "멀티 에이전트 구조로 나누어서 개발해도 좋아" | Confirmed |
| DEC-016 | 지도·DEM: 한반도 전역을 저해상도로 준비한다. 고해상도 지역과 지역 변경은 추후에 한다 | OPN-016, 사용자: "한반도 전역을 저해상도로 해줘. 고해상도 및 지역 변경은 추후에 하자." | Superseded by DEC-053 (분해능) |
| DEC-017 | 표적/적 엔티티: 기본은 스크립트 경로·고정 위치. 아군과 같은 MA 플러그인 인터페이스를 쓸 수 있어 적 군집 알고리즘도 붙일 수 있다 | OPN-017 | Confirmed |
| DEC-018 | 센서 탐지: FOV, 최대 거리, DEM 가시선(LOS)으로만 판정한다. 확률 모델은 도입하지 않는다 | OPN-018, 사용자: "FOV/거리/가시선 판정으로 정리하자. 확률은 도입하지 말고." | Confirmed |
| DEC-019 | 무장 성능: 공개 문헌의 일반값으로 기본 프로파일을 두고, 시나리오 JSON에서 재정의한다. 실제 체계 제원은 넣지 않는다 | OPN-019 | Confirmed |
| DEC-020 | 통제 UI: 여러 UI의 동시 접속(관전·통제)을 지금 구조에 반영한다. 역할별 권한(A-GRA C2 RBAC)은 P6 이후에 추가한다 | OPN-020 | Confirmed |
| DEC-021 | 저장소: 현재 저장소 하나를 모노레포로 쓰고, WP별 디렉터리로 나눈다. 병렬 세션은 worktree로 작업한다 | OPN-021 | Confirmed |
| DEC-022 | 빌드 툴체인을 하나로 고정하지 않는다. MSVC + vcpkg, MSYS2 UCRT64 GCC + pacman 패키지, Linux/WSL2 GCC + 배포판 패키지를 모두 CMake 프리셋으로 지원한다. 의존성은 `find_package`로만 찾는다 | DEC-010, 사용자: "msvc 와 vcpkg 가 없이 사용하는 안에 대해서도 대응되도록" (MSVC 라이선스 검토) | Confirmed |
| DEC-023 | `DynamicsModel::to_kinematic`에 `const Environment&`를 인자로 추가한다. 바람을 반영한 대지 속도와 실제 중력값을 출력에 쓴다 | OPN-022, WP2 계약 변경 요청 | Confirmed |
| DEC-024 | 시나리오를 proto `Scenario` 메시지(map, run, entities, mission_plan, engagement_criteria)로 정의하고 WP7 JSON Schema와 구조를 맞춘다. `LoadScenario.scenario`로 전달하며 `scenario_json`은 폐기 예정 | OPN-023, WP7 계약 변경 요청 | Confirmed |
| DEC-025 | lockstep 참여자 목록은 `RunSpec.participants`에 둔다. 동적 참여자 등록은 2차에 검토한다 | OPN-024, WP1 계약 변경 요청 | Confirmed |
| DEC-026 | 버스 구현(InMemory, Zenoh)을 공용 라이브러리 `bus/`(WP0 소유)로 두고 `open_bus(BusConfig)`로 생성한다. Python은 `swarm_api.open_bus` | OPN-025, WP7 계약 변경 요청 | Confirmed |
| DEC-027 | 브라우저(UI, Traffic Monitor)는 Zenoh에 직접 붙지 않고 WebSocket 브리지로만 연동한다. 브리지는 Python, `bridge/`, WP5 담당. 발행 허용 키 제한과 클라이언트별 전송 주기 제한을 브리지에서 한다 | OPN-026, 사용자: "일관성을 위해서 WebSocket 브리지로만 연동" | Confirmed |
| DEC-028 | 재밍 판정은 수신단 기준이다. 메시지의 수신 엔티티가 재밍 영역 안이면 손실(JAMMED). 링크 상태(`link/state`)는 양쪽 중 하나라도 영역 안이면 jammed로 표시한다. DEC-009를 구체화한다 | OPN-027, DEC-009, 제안서 §4, 사용자: "권고대로 진행" | Confirmed |
| DEC-029 | 링크 프로파일을 시나리오 `link_profiles`(proto `LinkProfile`)로 추가·재정의한다. base 프로파일을 복사한 뒤 값이 있는 필드만 덮어쓴다. `EntitySpec.link_profile`이 이름으로 참조한다 | OPN-028, WP4 계약 변경 요청, 사용자: "권고대로 진행" | Confirmed |
| DEC-030 | 재밍 영역은 `JamZoneEvent.area`(원 또는 다각형 × 고도대)로 정의한다. `zone`(원)은 폐기 예정. 주파수대는 링크 모델에 주파수 선택이 들어갈 때 다시 검토한다 | OPN-029, WP4 계약 변경 요청, 사용자: "권고대로 진행" | Confirmed |
| DEC-031 | 재생 여부는 `SimStatus.replay`로 알린다. MCAP 재생기가 `sim/ctrl/status`를 다시 발행할 때 true로 채운다 | OPN-030, WP6 계약 변경 요청, 사용자: "권고대로 진행" | Confirmed |
| DEC-032 | 브로드캐스트는 같은 편 무전기 엔티티 전원을 수신 대상으로 보고, 닿지 않는 수신자마다 손실 사유(OUT_OF_RANGE 등)를 담은 `LinkOutcome`을 낸다. 손실률은 이 기준으로 집계하고, 거리 밖 제외는 모니터 필터로 한다 | OPN-031, WP6 질의, 사용자: "권고대로 진행" | Confirmed |
| DEC-033 | 지도 임무 명령: `HoldTask`에 중심·반경·시간·방향을 두고, 항로점별 고도·속력·행위(선회 대기·정찰)를 갖는 `RouteTask`를 `TaskCommand`의 EXT 작업으로 추가한다. 지점 타격은 `StrikeTask.aim_point`, 지점 정찰은 원 `SearchAreaTask`를 쓴다 | REQ-UI-003, REQ-UI-004, REQ-BHV-002, 사용자: "비행체를 선택한 후에 맵에 우클릭하면 해당 지점에서 할 수 있는 임무들을 … 항로점 별로 할 수 있는 행위 … 같은 속성을 선택할 수 있으면 좋을 것 같아" | Confirmed |
| DEC-034 | 선회 대기에 레이스트랙 모양을 추가한다. 모양은 중점·반경·직선 길이·축 방향·방향으로 정의하고(두 원 중심 = 중점 ± 직선 길이/2), VI에는 `CurveCommand.racetrack`으로 넘긴다. 유도는 Dubins 경로(원호+접선) 추종을 기본으로 하고, 벡터장(`reference/racetrack_vectorfield.m`)은 FA 매개변수로 추가한다 | REQ-BHV-002, REQ-GNC-001, DEC-033, 사용자: "Race track 모양의 선회 대기도 있으면 좋을 것 같아. 지금은 Dubin's circle 으로 만들고, 추후에는 vector field 으로 만들어보면 좋을 것 같아" | Confirmed |
| DEC-035 | 기체별 매개변수는 소유자(동역학·FA·MA)가 기본값과 함께 선언(`ParamSpec`: 계층·단위·범위·`runtime`)하고, 기본값 → airframe 표 → 시나리오 → 실행 중 `SimCommand.set_params` 순으로 덮어쓴다. 소유자는 `sim/param/<entity>/<owner>`로 선언과 적용 값을 발행한다. 행위·결정은 MA 플러그인 하나를 유지하고 매개변수의 계층 표시로만 구분한다 | REQ-CFG-003, REQ-BHV-004, DEC-014, 사용자 답변: 변경 시점 "시작 시 + 실행 중", MA 분할 "파라미터만 그룹으로 구분" | Confirmed |
| DEC-036 | 문자열 매개변수는 허용 목록 `ParamSpec.choices`를 선언할 수 있고, 목록 밖 값은 거부 사유 `choice`로 `EntityParams.rejected`에 기록한다. 계약 0.7.0 | DEC-035, REQ-CFG-003, P0 통합 점검 결과(`racetrack_guidance`가 `foo`를 받음) | Confirmed |
| DEC-037 | Core가 적재한 시나리오를 `sim/ctrl/scenario`로 1초마다 재발행하고, lockstep 첫 틱은 `RunSpec.participants` 전원의 `FrameDone{frame=0}` 준비 신호 뒤에 낸다. 시작 후 동적 참여는 허용하지 않는다 | DEC-025, OPN-024, P0 통합 점검 결과, 사용자 답변: "Core가 시나리오 재발행" | Confirmed |
| DEC-038 | QA 결과 정리: (1) 입력 검증은 비유한(NaN·inf)·범위 밖 값을 적재·명령 단계에서 거부한다(시나리오는 적재 거부 후 상태 유지, 임무는 `TaskStatus` REJECTED와 사유, 매개변수는 `range`, 실행 설정은 거부). (2) 지원하지 않는 dof5/dof6 시나리오는 Core를 종료하지 않고 적재를 거부한다. (3) `assignees`가 비면 거부한다. (4) lockstep 실행 중 이탈한 참여자의 재합류는 지원하지 않는다(Reset+Start로 복구). (5) realtime에서 `SetRate`는 무시되고 UI는 배속 제어를 비활성으로 표시한다. (6) 중복 `task_id`는 같은 기체에서 이전 임무를 대체한다. (7) KILL된 엔티티는 영구히 `alive=false`다. (8) Datalink 지연·지터에 의한 TaskStatus 순서 뒤바뀜은 현실 모사로 유지한다 | docs/21_qa_report.md §6 (D-3~D-9), 사용자 답변: "현실 모사로 유지" | Confirmed |
| DEC-039 | (1) lockstep 결정성은 불완전 링크(손실·지터)를 포함해 같은 시드에서 같은 결과를 요구한다. 링크 난수는 시드와 프레임 번호로만 정해지고 실행 순서·벽시계에 의존하지 않는다. (2) 입력 폭주에도 Datalink는 `frame_done`을 막지 않는다. 입력 큐는 상한을 두고 초과분은 버리며 DROPPED로 기록한다. (3) flocking MA는 Route를 지원하지 않고 `unsupported task route`로 거부하는 것이 의도이며, UI는 거부 사유를 보여 준다 | docs/21_qa_report.md §9 (QA-012, QA-013, D-10, D-11), DEC-005 | Confirmed |
| DEC-040 | lockstep에서 Datalink→Agent 수신 메시지의 결정적 소비 규칙: (1) Datalink는 틱 f에서 낼 rx를 모두 발행한 뒤에 `FrameDone{f}`를 보낸다. (2) Agent는 틱 f+1을 처리하기 전에 Datalink의 `FrameDone{f}`를 받아야 한다(Datalink가 `RunSpec.participants`에 있을 때). (3) Agent는 틱 t에서 `rx_time_us <= t`인 rx만 소비하고 나머지는 다음 틱으로 미룬다 | docs/21_qa_report.md QA-013, DEC-039, DEC-005 | Confirmed ((3) Superseded by DEC-045) |
| DEC-041 | lockstep에서 참여자가 이탈하면 Core는 계속 기다리고, 벽시계 5 s 넘게 `FrameDone`이 없는 참여자를 `SimStatus.waiting_participants`로 알려 UI가 경고한다. 복구는 Reset+Start(DEC-038 유지) | docs/21_qa_report.md D-12, TC-QA-028, 사용자 답변: "대기+경고 표시" | Confirmed |
| DEC-042 | MCAP 재생은 관찰용이며 속도 조절·배압을 넣지 않는다. 고배속에서 수신 프레임 누락을 설계 한계로 허용하고, UI·Monitor가 프레임 번호 공백으로 누락 수를 표시한다 | docs/21_qa_report.md D-13, QA-008, 사용자 답변: "설계 한계로 명시" | Confirmed |
| DEC-043 | 버스 QoS: Zenoh 버스는 모든 키를 같은 우선순위(DATA)·비express로 보낸다. lockstep 경로 키(`sim/clock/**`, `swarm/**`)는 혼잡 제어를 BLOCK으로 해 혼잡 시에도 버리지 않고 같은 링크 큐에서 순서를 지킨다. 그 밖의 키는 DROP. QA-016 잔여 원인(교차 키 도착 순서) 대응의 1단계이며, 해소되지 않으면 FrameDone 송신 개수 장벽(WP3 제안)을 OPN으로 다시 올린다 | docs/21_qa_report.md QA-016, DEC-040, 사용자 답변: "QoS 통일로 먼저 시도" | Confirmed |
| DEC-044 | lockstep 송신 개수 장벽: `FrameDone.sent_count`(엔티티별 `swarm/<e>/**` 누적 발행 수)를 싣고, 수신 측은 발행 참여자의 `FrameDone{f}`와 누적 수신 수 ≥ `sent_count[e]`를 확인한 뒤에 프레임 f까지의 메시지를 쓴다. 대상은 기체 간·지상-기체 간 메시지(`swarm/**`)뿐이고 동역학·UI 표시(`onboard/**`, `truth/**`)는 대상이 아니다. 누적 수를 써서 프레임별 귀속 판단 없이 지연 도착만 막는다. 계약 0.10.0 | OPN-036, QA-016, DEC-040, DEC-043, 사용자 답변: "UI 상에 동역학 모델의 틱이 일치할 필요는 없어, 하지만 기체 간의 정보 교환 상에는 틱이 중요하기 때문에 프레임에 송신하는 메시지 수를 일단 넣어서 해보자." | Confirmed |
| DEC-045 | lockstep rx 소비 시점(DEC-040 (3) 대체): Agent는 틱 f에서 `rx_time_us <= sim_time_us(틱 f-1)`인 rx만 (rx_time_us, source, seq) 순으로 소비하고, Datalink `FrameDone{f-1}`(DEC-044 개수 장벽 포함)을 받은 뒤에만 틱 f를 처리한다. 틱 0은 rx를 소비하지 않는다. 틱 f의 rx는 Datalink `FrameDone{f}`가 Agent의 `FrameDone{f}`를 기다리므로 틱 f 처리 시점에 확정될 수 없다. 기체 간·지상-기체 간 메시지는 모델 지연에 더해 최소 1틱 늦게 소비된다 | OPN-037, DEC-040, DEC-044, IMP-AGT-027, 사용자 답변: "A안 채택" | Confirmed |
| DEC-046 | P5(임무장비·무장·표적)를 지금 착수한다. 새 WP8 Payload(`payload/`, C++20 라이브러리)가 센서 탐지(DEC-018), 재머·재밍 구역(DEC-009), 무장 발사·비행·탄착·살상반경 판정(DEC-012, DEC-019, PRP-DYN-003)을 맡는다. Core가 이 라이브러리를 링크해 프레임마다 호출하고 `onboard/<id>/Detection`·`*Activity`와 `truth/event/{launch,impact,kill,jam_zone,spawn}`을 발행한다. 별도 프로세스·lockstep 참여자를 두지 않아 결정성은 Core 프레임에 따른다. 통합은 WP1, 이펙트 표시는 WP5가 맡는다 | QA D-1, DEC-001, DEC-009, DEC-012, DEC-017~019, PRP-PAY-001, 사용자 답변: "지금 P5까지 모두" | Confirmed |
| DEC-047 | SENSOR 고장 효과: 고장이 활성인 동안 그 기체의 모든 센서는 Detection을 만들지 않는다. `SensorActivity.active`는 false로 보고한다 | QA D-2, DEC-018, 사용자 답변: "탐지 불가로 정의" | Confirmed |
| DEC-048 | 무장 자체 종료(빗나감·비행 시간 초과)는 KillEvent를 내지 않는다. 마지막 상태를 alive=false로 한 번 더 내고 StrikeActivity MISSED와 ImpactEvent로 사유를 전한다. 계약 변경 없음 | OPN-038, DEC-046, 사용자 답변: "제안안대로 확정" | Confirmed |
| DEC-049 | 엔티티당 재머는 1개다. 2개 이상이면 시나리오 오류로 거부한다. `JamZoneEvent.owner`는 엔티티 ID로 유지한다 | OPN-039, DEC-009, 사용자 답변: "제안안대로 확정" | Confirmed |
| DEC-050 | 시나리오에 정의하는 엔티티 ID는 25자 이하로 제한한다. 무장 ID `wpn-<shooter>-NN`이 엔티티 ID 상한 32자 안에 들게 한다 | OPN-040, DEC-046, 사용자 답변: "제안안대로 확정" | Confirmed |
| DEC-051 | Agent 런타임이 기체의 `*Activity`(SensorActivity·JammerActivity·StrikeActivity)를 변화 시와 1 Hz로 GCS에 자동 보고한다. 보고는 Datalink를 거쳐 `swarm/<gcs>/rx/ms/<Msg>`로 도달하며 MA 구현과 무관하다. UI는 `onboard/**`를 구독하지 않는다 | OPN-041, QA-020, DEC-008, DEC-013, 사용자 답변: "Agent 자동 보고" | Confirmed |
| DEC-052 | Core는 활성 재밍 구역(JamZoneEvent)을 변화 시와 1 s 주기로 다시 발행한다. 수신 측은 owner 기준으로 멱등 처리한다. 키·메시지 변경 없음 | OPN-042, QA-021, DEC-009, 사용자 답변: "1 s 주기 재발행" | Confirmed |
| DEC-053 | 한반도 DEM은 Copernicus GLO-90 공개 자료를 원본 분해능(3″, 약 90 m)으로 쓴다(int16, 약 150 MB). DEC-016의 "저해상도"를 대체한다. 같은 자료를 Core 지면 판정·가시선과 UI 지형에 쓴다(DEC-004). 자료는 저장소 밖 `data/`(Git 미포함)에 두고 내려받기·변환 스크립트만 커밋한다 | OPN-043, QA-022, DEC-016, DEC-004, 사용자 답변: "Copernicus GLO-90", "한반도 지형 데이터는 분해능이 더 높은 것으로 변경", "GLO-90 원본 90 m" | Confirmed |
| DEC-054 | lockstep rx 불변식: Datalink가 틱 k에서 내는 rx는 `rx_time_us >= T_k`(틱 k의 sim_time)이다. 표본 지연이 0이거나 처리량 상한으로 이월된 송신도 도착 시각 하한을 T_k로 둔다. 그래서 DEC-045의 "틱 f에서 `rx_time <= T(f-1)`만 소비"가 벽시계와 무관하게 결정적이다 | OPN-044, QA-019, DEC-044, DEC-045, 사용자 답변: "Datalink 도착 하한" | Confirmed |
| DEC-055 | 재밍 판정은 수신단 기준만 쓴다(DEC-028 유지). 구역 안 송신자가 구역 밖 수신자에게 보내는 메시지는 손실되지 않는다. 구역 안 기체는 GCS 명령을 받지 못하고 상태 보고는 GCS에 도착한다 | OPN-045, DEC-028, 사용자 답변: "현행 유지" | Confirmed |
| DEC-056 | 임무장비 상태 변화 보고(DEC-051)는 (메시지, payload_id)별로 최대 빈도를 둔다. 기본 10 Hz이며 Agent 런타임 설정으로 바꿀 수 있다. 1 Hz 전체 보고는 유지한다. 제한으로 미룬 변화는 다음 허용 시점에 최신 값으로 보낸다 | OPN-046, QA O-4, DEC-051, 사용자 답변: "10Hz 으로 하고, 이는 변경할 수 있도록 해줘." | Confirmed |
| DEC-057 | UI 지도는 오프라인 고해상도로 한다. 영상은 EOX Sentinel-2 cloudless 최신판(10 m, CC BY-NC-SA 4.0, 비상업 연구용, 출처 표기)을 한반도 전역(33–43°N, 124–131°E) z13(약 19 m/px)까지 받는다. 지형은 DEC-053의 GLO-90을 Cesium 지형 타일로 변환한다. 자료는 `data/tiles/`(Git 미포함)에 두고 받기·변환 스크립트만 커밋한다 | OPN-047, DEC-004, DEC-053, 사용자 답변: "지도 해상도를 고해상도로 변경", "Sentinel-2 cloudless 최신", "z13, 약 19 m/px" | Confirmed (영상 출처는 Superseded by DEC-058) |
| DEC-058 | UI 지도 영상 출처는 Copernicus Data Space Ecosystem의 Sentinel-2 분기 cloudless 모자이크(10 m, B04/B03/B02)로 한다. 한반도 전역(33–43°N, 124–131°E)을 z13 타일로 만들어 `data/tiles/imagery`에 둔다. 출처 표기는 Copernicus Sentinel 데이터 법적 고지를 따른다. 범위·확대 수준·지형은 DEC-057을 유지한다 | OPN-048, DEC-057, 사용자 답변: "Copernicus 공개 모자이크" | Superseded by DEC-059 |
| DEC-059 | UI 지도 영상은 계정 없이 받을 수 있는 AWS 공개 Sentinel-2 L2A 장면(B04/B03/B02, COG)에서 구름이 적은 화소를 골라 자체 합성한다. 같은 Copernicus Sentinel 데이터이므로 출처 표기는 Copernicus 법적 고지를 따른다. 범위·z13·지형은 DEC-057을 유지한다 | OPN-049, DEC-058, 사용자 답변: "공개 AWS L2A로 자체 모자이크" | Confirmed |
| DEC-060 | DEM 지형에서 공중 엔티티의 시작 고도가 그 위치 지형보다 낮으면 Core는 시나리오 적재 때 엔티티·고도·지형 높이를 경고로 남기고, 실행을 계속하면 시작 프레임에 kill(cause=ground)로 처리한다. 지상 엔티티는 제외한다 | OPN-050, DEC-053, QA-024, 사용자 답변: "시나리오 적재 때 경고 메시지를 띄우고 그래도 시작하겠다면 시작 프레임에 kill 으로 처리하자." | Confirmed |
| DEC-061 | `--terrain-flat`과 `--terrain-dem`을 함께 주면 Core는 DEM을 쓰고 평지 값을 무시한다는 경고를 남긴다(거부하지 않는다) | OPN-051, DEC-053, QA-025, 사용자 답변: "DEM 우선 + 경고" | Confirmed |
| DEC-062 | Datalink 재시작 직후 다음 재밍 구역 재발행까지(DEC-052, 최대 1 s) 구역 안 수신이 전달되는 것을 허용한다 | OPN-052, DEC-052, O-6, 사용자 답변: "현행 유지" | Confirmed |
| DEC-063 | `StrikeActivity` 변화 보고(DEC-051·056)의 키를 (메시지, payload_id, weapon_entity)로 나눈다. 빈 `weapon_entity`는 그대로 한 키로 쓴다. 종료 상태(IMPACT·MISSED·REJECTED)를 한 번 보낸 무장 키는 1 Hz 전체 보고에서 뺀다. 근거: 메시지가 무장 단위(`weapon_entity`)라 스테이션 단위 키는 같은 프레임·상한 안의 다른 무장 상태를 덮는다(QA-026). 종료 키 제거로 전체 보고 크기가 비행 중 무장 수로 묶인다 | OPN-053, QA-026, D-23, DEC-051, DEC-056, 사용자 답변: "무장별 키로 분리" | Confirmed |
| DEC-064 | 표적 지정 무장은 비행 중에도 프레임마다 탐색기와 표적 사이의 DEM 가시선(DEC-018과 같은 판정)을 본다. 가시선이 끊기면 락을 풀고 마지막으로 본 표적 위치로 좌표 유도하며, 다시 보이고 탐색기 FOV·거리 안이면 재획득한다. 조준점 발사는 좌표 유도이므로 가시선을 보지 않는다. 근거: 저고도 지형 은폐가 군집 알고리즘 평가에 의미를 갖고, 비행 중 무장 수만큼의 계산은 감당할 수 있다 | OPN-054, QA D-24, TC-QA-060, DEC-018, DEC-019, 사용자 답변: "비행 중 가시선 반영" | Confirmed |
| DEC-065 | 비행 중 유도 객체의 상태(따라가기·가시선 상실·좌표 유도)와 유도 지점은 버스로 보고하지 않는다. 계약은 0.13.0을 유지한다. 근거: 이 보고가 필요한 REQ가 없고, QA는 truth 궤적 재계산으로 상태를 프레임 단위로 판정했다(TC-QA-065~068). UI·알고리즘이 필요해지면 새 OPN으로 다시 연다 | OPN-055, QA D-25, IMP-PAY-008, 사용자 답변: "보고하지 않음" | Confirmed |
| DEC-066 | 조준점 발사도 조준점이 발사 기체 기준 탐색 FOV 안에 있어야 발사한다. 벗어나면 REJECTED(reason `out_of_fov`)를 낸다. 근거: 기수에서 크게 벗어난 조준점은 비례항법으로 돌지 않아 유도 객체가 직진한다(QA O-10). 표적 지정 발사와 같은 규칙이 되고 유도 식은 바뀌지 않는다 | OPN-056, QA O-10, DEC-019, 사용자 답변: "FOV 밖이면 거부" | Confirmed |
| DEC-067 | `StrikeActivity`의 IMPACT는 유도 객체의 도달(근접 신관·지면 교차)만 뜻한다. 파괴 효과는 `truth/event/kill`로 판단한다. 비행 중 목표 엔티티가 사라지면 마지막 위치로 좌표 유도하고 IMPACT로 끝나는 현행 동작을 유지한다 | OPN-057, QA O-11, DEC-012, DEC-064, 사용자 답변: "현행 유지·계약 명시" | Confirmed |
| DEC-068 | P6 Gateway(WP9, `gateway/`, Python)는 단계적 양방향으로 만든다. 1단계는 GCS 쪽에서 받은 VI·C2·P2P·MS 상태를 STD 메시지로 바꿔 LA-CAL로 내보낸다. 2단계는 외부 C2 명령(STD)을 받아 내부 메시지로 바꾼다. Gateway는 지상 참여자이며 기체와의 교환은 모두 Datalink를 거친다. `truth/**`와 `onboard/**`는 쓰지 않는다. 외부로는 STD만 내보낸다(DEC-014) | OPN-058, PRP-STD-002, DEC-002, DEC-013, DEC-014, 사용자 답변: "단계적 양방향" | Confirmed |
| DEC-069 | LA-CAL 클라이언트는 agra_lacal 저장소를 git submodule `third_party/agra_lacal`로 넣어 쓴다(커밋 고정). 서브모듈은 수정하지 않는다 | OPN-059, DEC-002, 사용자 답변: "git submodule" | Confirmed |
| DEC-070 | 매뉴얼의 알고리즘 플러그인 예제는 실행 가능한 예제 패키지로 둔다. 위치는 최상위 `examples/plugins/`(패키지 `swarm-plugin-examples`)이고 루트 uv 워크스페이스 멤버로 둔다. `swarm.ma`·`swarm.fa` entry point로 등록하고, 시험을 루트 `testpaths`에 넣는다. 매뉴얼 개발자 4~6장은 이 파일을 가리킨다. 근거: 외부 작성자가 자기 패키지를 만들어 등록하는 실제 경로를 그대로 보여 주고, API가 바뀌면 시험이 깨져 드러난다. `algorithms/`(WP3)는 고치지 않는다 | `docs/30_doc_plan.md` §9.2, DEC-003, 사용자 답변: "Runnable example package" | Confirmed |
| DEC-071 | Agent 런타임이 기체 VI 상태를 GCS에 자동 보고한다. `NavigationReport`는 주기(기본 1 Hz, CLI `--vi-report-hz`), `SystemStatus`·`FlightCommandStatus`는 변화 시, `FlightCapability`는 시작 시 1회 보낸다. 보고는 Datalink를 거쳐 `swarm/<gcs>/rx/vi/<Msg>`로 도달하며 MA 구현과 무관하다. 주기 설정은 DEC-051·DEC-056과 같이 Agent 런타임 설정으로 둔다 | OPN-064, QA D-26, DEC-051, DEC-013, 사용자 답변: "런타임이 보냄" | Confirmed |
| DEC-072 | 메시지 옵션 `repeated string uci_also`를 둔다. STD 메시지 하나가 `uci_name` 외의 UCI 메시지에도 대응할 수 있다. `NavigationReport`와 `PeerStatus`는 `uci_also = "MA_PositionReport"`로 위치·운동 상태를 함께 내보낸다. Gateway는 `uci_name`과 `uci_also` 각각에 변환기를 둔다 | OPN-060, WP9 CR-GW-001, DEC-013, DEC-014, 사용자 답변: "여러 UCI 대응" | Confirmed |
| DEC-073 | Core가 기체마다 `onboard/<id>/SystemStatus`를 발행한다. health·subsystems는 활성 고장(DEC-047)에서, energy_frac는 동역학 상태에서 만든다. 값이 바뀔 때와 1 Hz(모의 시간)로 낸다. Agent 런타임이 이를 GCS에 변화 보고한다(DEC-071) | OPN-065, DEC-047, DEC-071, 사용자 답변: "Core가 발행" | Confirmed |

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
| OPN-022 | 동역학 출력에 바람(대지 속도) 반영 방법 | Resolved by DEC-023 |
| OPN-023 | 시나리오 전달 형식 (JSON 원문 vs proto) | Resolved by DEC-024 |
| OPN-024 | lockstep 참여자 목록의 위치 | Resolved by DEC-025 |
| OPN-025 | 프로세스 간 버스 생성의 공통화 | Resolved by DEC-026 |
| OPN-026 | 브라우저의 Zenoh 연동 방식 | Resolved by DEC-027 |
| OPN-027 | 재밍 판정 기준(송수신 양단 vs 수신단) | Resolved by DEC-028 |
| OPN-028 | 시나리오에서 링크 프로파일 재정의 | Resolved by DEC-029 |
| OPN-029 | 재밍 영역 형상(다각형·고도대·주파수대) | Resolved by DEC-030 |
| OPN-030 | 버스에서 재생 모드 식별 | Resolved by DEC-031 |
| OPN-031 | 브로드캐스트에서 거리 밖 수신자의 LinkOutcome | Resolved by DEC-032 |
| OPN-032 | UI와 Traffic Monitor의 브리지 클라이언트·프레임 코덱·proto 생성 공용 패키지(`ui/shared/`). 보류: 2차 병합 후 WP5가 정리 | Open |
| OPN-033 | 브리지 바이너리 프레임에 구독 ID 포함(겹치는 구독의 중복 수신 해소). 보류: 브리지 프로토콜 v2에서 검토 | Open |
| OPN-034 | 수백 대 규모의 트래픽 관측(데이터링크 주기 집계 메시지 또는 브리지 키 필터). 보류: WP10 성능 단계 | Open |
| OPN-035 | 외부 시뮬레이션 상호운용(HLA/DIS). 제안: 내부 버스는 Zenoh 유지(DEC-002), 별도 Gateway federate(`hla/`, C++20, IEEE 1516e API, 개발 RTI OpenRTI, RPR FOM 2.0)가 `truth/**`를 외부로 발행. 단계: ① 발행 전용 ② lockstep 시간관리 참여(Gateway가 `participants`에 들어가 TAG(f+1) 수신 뒤 `FrameDone{f}`, lookahead 1프레임) ③ 외부 엔티티 수신(Core 입력 채널 신설, truth로만 반영해 DEC-013 유지). 기체 간 통신은 Datalink 경유를 유지하고 HLA로 보내지 않는다. 버스를 RTI로 교체하는 안은 DEC-002·DEC-026·DEC-040 충돌로 기각 제안. 확인 필요: 연동 상대의 표준(HLA/DIS)·FOM·RTI, Gateway C++ 작성에 따른 DEC-001 예외, 외부 연동 시 lockstep 결정성의 조건(외부 입력 동일). 보류: 연동 상대 미정(사용자: "연동상대 정보에 대해서는 아직 정해진 사항은 없어") | Open |
| OPN-036 | lockstep 결정성 잔여 차(QA-016): DEC-043(QoS 통일) 적용 후에도 s3 시드 7·20261104에서 uav-009~012 최대 0.041 m, s6 100기 flocking에서 최대 0.358 m 불일치(프레임 3부터). 같은 rx가 틱 69/70으로 갈림 → 교차 키 도착 순서 문제로 추정. 제안(WP3): `FrameDone`에 틱 f 동안 해당 참여자가 발행한 메시지 수(`sent_count`, 수신자별 또는 키 접두어별)를 싣고, 수신 측(Agent·Datalink)은 그 수만큼 받은 뒤에만 틱을 진행하는 개수 장벽. 계약 변경(proto `FrameDone` 필드 추가, 0.10.0) 필요. 확인 필요: 개수 단위(수신자별/전체), 손실 시 처리(lockstep 경로는 BLOCK이라 손실 없음 전제), 성능 영향 | Resolved by DEC-044 |
| OPN-037 | DEC-040 (3) 문구 정정: WP3 IMP-AGT-027은 Agent가 틱 f에서 `rx_time_us <= sim_time_us(틱 f-1)`인 rx만 (rx_time_us, source, seq) 순으로 소비하고, Datalink `FrameDone{f-1}`을 받은 뒤에만 틱 f를 처리한다(f=0은 소비 없음). 근거: 틱 f 처리 시점에 Datalink는 틱 f의 rx를 아직 내는 중일 수 있어 `FrameDone{f-1}`이 보장하는 시각까지만 확정이다. 현 DEC-040 (3)의 `rx_time_us <= t`와 달라 수신 지연이 1틱 늘어난다. 제안: DEC-040 (3)을 이 조건으로 바꾸는 새 DEC | Resolved by DEC-045 |
| OPN-038 | 무장 자체 종료(빗나감·비행 시간 초과) 표현. `KillEvent.cause`에 해당 값이 없어 WP8은 무장 KillEvent를 내지 않고 마지막 상태를 alive=false로 한 번 더 낸다(StrikeActivity MISSED 동반). 선택: (A) 현행 유지, 계약 변경 없음 (B) cause에 `expired` 추가. 제안: A. 근거: 종료 사유는 StrikeActivity·ImpactEvent에 이미 있다 | Resolved by DEC-048 |
| OPN-039 | 한 엔티티의 재머 복수 탑재. `JamZoneEvent.owner`는 엔티티 ID이고 Datalink가 owner로 구역을 키잉하므로 WP8은 엔티티당 재머 1개만 허용(2개 이상은 시나리오 오류). 선택: (A) 엔티티당 1개로 계약에 명시 (B) owner를 `<id>/<payload_id>`로 확장. 제안: A. 근거: 현 시나리오 요구에 복수 재머가 없고 B는 Datalink·UI 변경을 부른다 | Resolved by DEC-049 |
| OPN-040 | 무장 엔티티 ID 길이. `wpn-<shooter>-NN`은 발사 기체 ID가 25자를 넘으면 엔티티 ID 상한 32자(§2)를 넘는다. 선택: (A) 엔티티 ID 상한을 48자로 늘림 (B) 시나리오 엔티티 ID를 25자 이하로 제한 (C) 무장 ID를 전역 순번 `wpn-NNNN`으로 변경. 제안: B. 근거: 계약 문자열 규칙만 바뀌고 발사 기체가 ID에 남는다 | Resolved by DEC-050 |
| OPN-041 | 센서 활동 상태(SensorActivity)의 GCS 전달 경로(QA-020). Core는 `onboard/<id>/SensorActivity`만 내고 UI는 `swarm/<gcs>/rx/ms/SensorActivity`를 읽어 이어지는 경로가 없다. 선택: (A) Agent 런타임이 *Activity를 변화 시와 1 Hz로 GCS에 자동 보고(Datalink 경유) (B) MA가 MS 포트로 직접 보고 (C) UI가 `onboard/**`를 직접 구독. 제안: A. 근거: 지상 표시가 링크 상태를 반영하고(DEC-008), MA 구현과 무관하며, onboard 채널을 UI에 열지 않는다 | Resolved by DEC-051 |
| OPN-042 | 상태형 truth 이벤트(JamZone)의 늦은 구독자 처리(QA-021). 변화 시 한 번만 발행되어 늦게 붙은 UI·관찰자·재시작한 Datalink가 구역을 모른다. 선택: (A) Core가 활성 구역을 변화 시와 1 s 주기로 다시 발행(수신 측은 owner 기준 멱등) (B) Zenoh queryable로 최신 구역 조회 (C) TruthFrame에 활성 구역 목록 포함. 제안: A. 근거: 키·메시지 변경이 없고 Datalink는 이미 owner로 키잉한다 | Resolved by DEC-052 |
| OPN-043 | 한반도 저해상도 DEM 자료 출처와 저장소 형식(DEC-016, QA-022). 선택: (A) Copernicus GLO-90 공개 DEM을 내려받아 약 1 km 격자로 줄여 저장소 밖(`data/`, Git 미포함)에 두고 변환 스크립트만 커밋 (B) SRTM 3″ 같은 방식 (C) 합성 지형만 사용. 제안: A. 근거: 공개 라이선스, 한반도 전역 포함, 저해상도 변환으로 수 MB 이하 | Resolved by DEC-053 |
| OPN-044 | lockstep rx 불변식(QA-019, QA D-18). Datalink는 지연 표본이 0이면 틱 k에서 `rx_time = T(k-1)`인 rx를 낸다. Agent는 틱 k에서 Datalink `FrameDone{k-1}`만 기다리고 `rx_time <= T(k-1)`을 소비하므로(DEC-045) 그 rx를 소비할지가 벽시계 경쟁이 된다. 선택: (A) Datalink가 틱 k에서 내는 rx의 도착 시각 하한을 T_k로 둔다(이월 송신 포함). 불변식 "Datalink 틱 k가 내는 rx는 rx_time > T(k-1)"을 계약에 적는다 (B) Agent가 rx_time 대신 Datalink가 낸 틱 번호로 소비한다(DEC-045 문구 변경) (C) 둘 다. 제안: A. 근거: 지연 0은 물리적으로 의미가 없고, 고칠 곳이 한 곳이며 DEC-045 문구를 유지한다 | Resolved by DEC-054 |
| OPN-045 | 송신자 쪽 재밍(QA D-19). DEC-028은 수신단 기준이라 재밍 구역 안 기체가 구역 밖 GCS로 보내는 메시지는 손실되지 않는다. 선택: (A) 현행 유지(수신단만), 계약에 명시 (B) 송신자가 구역 안이어도 손실 (C) 메시지 방향별 선택(시나리오 설정). 제안: A. 근거: 재머는 가까운 수신기를 방해한다. 구역 밖 GCS 수신기는 영향을 덜 받는다. 구역 안 기체는 GCS 명령을 받지 못하므로 통제 두절은 이미 모사된다 | Resolved by DEC-055 |
| OPN-046 | 임무장비 상태 보고 빈도(QA O-4). DEC-051의 "변화 시 보고"로 SensorActivity 지향각이 매 프레임 바뀌어 기체마다 50 Hz로 GCS에 보고한다(5기 약 22 kB/s). 선택: (A) 변화 보고를 (메시지, payload_id)별 최대 5 Hz로 제한, 1 Hz 전체 보고는 유지 (B) 지향각 같은 연속값은 변화 판정에서 빼고 1 Hz로만 보고 (C) 현행 유지. 제안: A. 근거: 지도 FOV 표시에 5 Hz면 충분하고 기체 수가 늘어도 GCS 대역이 예측 가능하다 | Resolved by DEC-056 |
| OPN-047 | UI 오프라인 지도 영상의 출처와 확대 수준. 현재 로컬 타일이 없어 내장 저해상도 영상과 타원체로 표시된다. 선택: 출처 (A) Sentinel-2 cloudless 2016(CC BY 4.0) (B) 최신판(CC BY-NC-SA 4.0) (C) NASA Blue Marble(500 m). 수준 z12 / z13 / z14 | Resolved by DEC-057 |
| OPN-048 | DEC-057의 EOX Sentinel-2 cloudless는 일괄 오프라인 사용에 유료 상품 또는 서면 허가가 필요하다. 선택: (A) Copernicus 공개 분기 모자이크 (B) EOX 서면 허가 (C) EOX 상품 구매 (D) 내장 영상 유지 | Resolved by DEC-058 |
| OPN-049 | DEC-058의 CDSE 모자이크 COG는 계정과 S3 키가 있어야 받을 수 있다(익명 401/403). 선택: (A) 사용자가 가입·키 발급 (B) AWS 공개 L2A로 자체 합성 (C) 보류 | Resolved by DEC-059 |
| OPN-050 | DEM 아래에서 시작한 공중 엔티티가 지면 판정 없이 비행한다(QA-024, D-20). 선택: 적재 때 거부 / 시작 프레임 kill / 경고만 | Resolved by DEC-060 |
| OPN-051 | `--terrain-flat`과 `--terrain-dem`을 함께 주면 평지 값이 조용히 무시된다(QA-025, D-22). 선택: 시작 때 거부 / DEM 우선 + 경고 | Resolved by DEC-061 |
| OPN-052 | Datalink 재시작 직후 최대 1 s 동안 구역 안 수신이 전달된다(O-6, D-21). 선택: 현행 유지 / 시작 때 구역 조회 또는 전달 보류 | Resolved by DEC-062 |
| OPN-053 | 같은 스테이션의 무장 변화가 한 프레임 또는 상한 간격 안에 겹치면 앞 변화가 GCS에 보고되지 않는다(QA-026, D-23). 선택: (A) 현행 유지·계약 명시 (B) 키 안 변화 순차 전송 (C) 무장별 키 분리. 제안: C | Resolved by DEC-063 |
| OPN-054 | 무장의 가시선 처리 범위(D-24). 현재 표적 지정 발사 판정만 DEM 가시선을 보고 비행 중 탐색기와 조준점 발사는 보지 않는다. 선택: (A) 현행 유지·명시 (B) 비행 중 가시선 상실 시 락 해제·좌표 유도·재획득 (C) B + 조준점 발사 가시선 확인. 제안: B | Resolved by DEC-064 |
| OPN-055 | 비행 중 무장 유도 상태(TRACKING / LOS_LOST / COORDINATE)와 유도 지점을 버스로 보고할지(WP8 제안). 현재는 C++ 조회 `PayloadSystem::weapon_track`만 있고 GCS·QA는 궤적과 종료 결과로만 판정한다. 선택: (A) 보고하지 않음 (B) `StrikeActivity`에 EXT 필드 추가, 상태 변화 시 보고(계약 변경). 제안: A | Resolved by DEC-065 |
| OPN-056 | 조준점 발사의 발사 허용각(QA O-10). 목표 방향이 발사 기체 기수에서 약 90° 벗어나면 비례항법의 접근 속도가 0에 가까워 유도 객체가 돌지 않고 직진한다. 표적 지정 발사는 탐색 FOV 판정으로 거부되지만 조준점 발사는 판정이 없다. 선택: (A) 현행 유지·명시 (B) 조준점 발사도 탐색 FOV 안이어야 발사, 벗어나면 REJECTED (C) 접근 속도가 작을 때 방향 추종 유도를 섞는다. 제안: B | Resolved by DEC-066 |
| OPN-057 | 비행 중 목표 엔티티가 사라진 유도 객체의 종료 보고(QA O-11). 현재는 마지막 위치로 좌표 유도해 IMPACT(파괴 대상 없음)로 끝난다. 선택: (A) 현행 유지, 계약에 "IMPACT는 도달만 뜻하고 효과는 kill 이벤트로 판단"을 명시 (B) MISSED(reason target_lost)로 끝낸다. 제안: A | Resolved by DEC-067 |
| OPN-058 | P6 Gateway(WP9) 범위. 선택: (A) 발행 전용(시뮬레이터 → 외부 STD 메시지) (B) 단계적 양방향: 1단계 발행, 2단계 외부 C2 명령 수신 (C) 처음부터 양방향. 외부 C2 명령은 기존 규칙대로 Datalink를 거친다. 제안: B | Resolved by DEC-068 |
| OPN-059 | Gateway의 LA-CAL 클라이언트 확보. agra_lacal은 저장소 밖(`../open_arsenal/agra_lacal`)에 있고 패키지로 설치되지 않는다(`package = false`). 선택: (A) uv 경로 의존성(agra_lacal 패키지화 필요) (B) `gateway/` 안에 OWP 클라이언트 최소 구현을 두고, agra_lacal 서버는 시험 상대로만 쓴다 (C) git submodule. 제안: B | Resolved by DEC-069 |
| OPN-060 | 기체 위치의 외부 메시지 대응(WP9 CR-GW-001). 공개 XSD의 `MA_NavigationReport`·`MA_PackagePartnerStatusReport`에는 위치가 없고 위치는 `MA_PositionReport`에 있다. 선택: (A) `NavigationReport`의 `uci_name`을 `MA_PositionReport`로 바꾼다 (B) 한 내부 메시지가 UCI 메시지 여러 개에 대응하도록 옵션을 늘린다(`repeated string uci_also`) — `PeerStatus`의 운동 상태도 같은 방식으로 싣는다. 제안: B | Resolved by DEC-072 |
| OPN-061 | `ApprovalResponse`를 STD로 바꾸고 `uci_name = "MA_ApprovalRequestStatus"`를 단다(WP9 CR-GW-002). STD가 되면 외부 운용자의 승인 응답을 Gateway 2단계로 받을 수 있다. 선택: (A) STD로 바꾼다 (B) EXT로 둔다. 제안: A | Open |
| OPN-062 | 외부 `MA_TaskCommand`의 작업 내용 표현(WP9 CR-GW-003). `MA_TaskCommand`는 TaskID·CapabilityID 참조만 담고 목적지·영역이 없다. 선택: (A) MP(`MA_MissionPlan`) 연동 전까지 Gateway 임시 규칙(CapabilityID Label = `<엔티티>/<작업 종류>`, hold·return_to_base·취소만)을 인정하고 위치가 필요한 작업은 MP 연동 뒤에 받는다 (B) 지금 MP 연동까지 구현한다. 제안: A | Open |
| OPN-063 | 같은 GCS 키에 UI와 Gateway가 함께 발행할 때의 발행자 구분(WP9 CR-GW-005). `header.seq`가 발행자별로 따로 매겨져 Datalink·Logger가 source만으로 구분할 수 없다. 선택: (A) `LinkEnvelope` 헤더에 발행 참여자 ID를 더한다(계약 변경) (B) Gateway를 별도 지상 엔티티(예: `gw-01`)로 시나리오에 둔다 (C) 현행 유지, 구분하지 않는다. 제안: A | Open |
| OPN-064 | 기체 VI 상태의 GCS 보고 경로(QA D-26). 통합 실행에서 Agent가 GCS로 VI를 보내지 않아 외부 시스템이 기체 위치를 모른다. 선택: (A) Agent 런타임이 FA의 VI 상태를 `swarm/<id>/tx/vi/<msg>`로 GCS에 보낸다. `NavigationReport`는 시나리오에서 정하는 주기(기본 1 Hz)로, `SystemStatus`·`FlightCommandStatus`는 바뀔 때, `FlightCapability`는 시작할 때 한 번 보낸다. Datalink를 거치므로 링크 상태가 반영된다 (B) MA 플러그인이 보낼지 정한다 (C) GCS가 `truth/**`에서 얻는다(DEC-013 위반). 제안: A | Resolved by DEC-071 |
| OPN-065 | `onboard/<id>/SystemStatus` 발행 주체(WP3 DEC-071 구현 확인 사항). Agent는 이 키를 받아 GCS에 변화 보고하지만, 지금은 아무도 발행하지 않아 통합 실행에서 SystemStatus가 나가지 않는다. 선택: (A) Core가 발행한다. 활성 고장(DEC-047)에서 health·subsystems, 동역학 상태에서 energy_frac를 만들어 바뀔 때와 1 Hz(모의 시간)로 낸다 (B) Payload 라이브러리가 낸다(센서·재머 subsystem만 앎) (C) Agent FA가 낸다(고장 정보를 truth 없이 알 수 없음). 제안: A | Resolved by DEC-073 |

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
| C2 | 항로점별 행위가 있는 항로 비행(`RouteTask`) | 대응 메시지 없음 | EXT |
| P2P | 리더 선출 | `MA_RaftVoteRequest`, `MA_RaftAppendEntriesRequest`, `MA_LeaderUpdateRequest` | STD |
| P2P | COP 공유 | `MA_Entity`, `MA_PackagePartnerStatusReport` | STD |
| MS | 데이터 전송(DMS) | `MA_TxDataPayloadCommand`, `MA_RxDataPayload` | STD |
| MS | 카메라 | `PO_Command`, `PO_Activity` | STD |
| MS | 재밍 | `EA_Command`, `EA_Activity` | STD |
| MS | 타격·무장 | `StrikeCommand`, `StrikeActivity`, `StoreLoadoutConfiguration`, `MA_WEZ` | STD |
| MP | 임무 계획, 교전 기준 | `MA_MissionPlan`, `MA_EngagementCriteria`, `MA_RoutePlan` | STD |
| MD | 기록·재생 | MCAP (메시지 교환 없음) | — |
| Sim | 일시정지, 배속, 고장 주입, 리셋 | `sim/ctrl/**` 전용 | EXT (외부 비공개) |
