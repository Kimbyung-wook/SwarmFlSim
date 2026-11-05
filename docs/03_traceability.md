# 추적 매트릭스

- 각 요구사항(REQ)이 어떤 제안(PRP)과 결정(DEC)으로 이어지고, 어떤 구현(IMP)과 시험(TC)으로 검증되는지 추적한다.
- ID 규칙은 [01_id_convention.md](01_id_convention.md)를 따른다.
- 각 항목의 정의는 [02_registry.md](02_registry.md)에 있다.

## 갱신 규칙
- IMP를 추가하면 해당 REQ 행의 IMP 열에 적는다. TC도 같은 방식으로 적는다.
- `WP`는 [제안서 §12](00_proposal.md#12-작업-분할wbs과-멀티-에이전트-개발-dec-015)의 작업 패키지다.
- 검증 상태:
  - `-`: 미착수
  - `구현중`
  - `구현완료`: IMP 완료, TC 미통과
  - `검증완료`: 연결된 TC 모두 통과

## 매트릭스

| REQ | PRP | DEC | WP | IMP | TC | 검증 상태 |
|---|---|---|---|---|---|---|
| REQ-UI-001 | PRP-UI-001 | DEC-003, DEC-004, DEC-046 | WP5 | IMP-UI-003~005, 008~010, 012, 014~016, 018~019, 060~066, IMP-INT-001 | TC-UI-001~003, 005~006, 008~009, 046~053, TC-INT-001 | 구현중 |
| REQ-UI-002 | PRP-UI-001 | DEC-003 | WP5 | IMP-UI-006, 016~017, 019, 025~026, 031, 034, IMP-INT-001 | TC-UI-004, 009, 018~019, TC-INT-003 | 구현중 |
| REQ-UI-003 | PRP-UI-001 | DEC-014, DEC-033 | WP5 | IMP-API-010, IMP-UI-025, 027~032, 034~041 | TC-UI-008, 018~025 | 구현중 |
| REQ-UI-004 | PRP-UI-001, PRP-BHV-001 | DEC-008, DEC-033 | WP5, WP3 | IMP-UI-025, 027, 031, 034~041, IMP-AGT-016~018 | TC-UI-018~025, TC-AGT-016~018 | 구현중 |
| REQ-UI-005 | PRP-UI-002, PRP-LNK-002 | DEC-011, DEC-031, DEC-032 | WP6, WP4 | IMP-MON-001~026, IMP-LNK-008~009 | TC-MON-001~013, TC-LNK-001, 004~006, 008~011 | 구현중 |
| REQ-UI-006 | PRP-UI-001, PRP-NET-002 | DEC-020 | WP5 | IMP-UI-021~022, 024, 034, IMP-MON-003 | TC-UI-011~017, 019, TC-MON-002 | 구현중 |
| REQ-UI-007 | PRP-UI-001 | DEC-003 | WP5 | IMP-UI-003, 007, 014, 017 | TC-UI-001, 007, 009 | 구현중 |
| REQ-DYN-001 | PRP-DYN-001 | DEC-007 | WP2 | IMP-CORE-004, 008, IMP-DYN-001~002, 006, IMP-INT-002 | TC-CORE-005, 007~008, 013, 017, TC-DYN-001~003, 009, 011~012, TC-INT-001 | 구현중 |
| REQ-DYN-002 | PRP-DYN-001 | DEC-007 | WP2 | IMP-DYN-001~002, 007 | TC-DYN-001~003, 009, 011, 013 | 구현중 |
| REQ-DYN-003 | PRP-DYN-002, PRP-SIM-002 | DEC-005 | WP1, WP2 | IMP-API-006, IMP-CORE-002, 017, 020, 021, IMP-DYN-004 | TC-CORE-001~006, 009~010, 028~030, 032, 033, TC-DYN-001, 005~008 | 검증완료 |
| REQ-DYN-004 | PRP-DYN-002 | DEC-005 | WP2 | IMP-API-006, IMP-CORE-008, IMP-DYN-003~004, 006 | TC-CORE-013, 017, TC-DYN-001, 004~008, 012 | 검증완료 |
| REQ-DYN-005 | PRP-DYN-003 | DEC-012 | WP2, WP8 | IMP-PAY-005 | TC-PAY-008~010, 014 | 구현중 |
| REQ-GNC-001 | PRP-GNC-001, PRP-BHV-001 | DEC-013, DEC-034 | WP3 | IMP-API-011, IMP-AGT-004, 006~007, 019 | TC-AGT-001~005, 019~023 | 구현중 |
| REQ-BHV-001 | PRP-BHV-001, PRP-SIM-003 | DEC-008, DEC-013 | WP3 | IMP-AGT-002~006, 008~009, 011, 013, IMP-INT-003 | TC-AGT-006~013, 015, TC-INT-002~003 | 구현중 |
| REQ-BHV-002 | PRP-BHV-001, PRP-BHV-003 | DEC-013, DEC-033, DEC-034 | WP3 | IMP-API-010~011, IMP-AGT-011, 013, 016~020, IMP-UI-042~044 | TC-AGT-015~023, TC-UI-026~027 | 구현중 |
| REQ-BHV-003 | PRP-BHV-001, PRP-BHV-003 | DEC-008 | WP3 | IMP-AGT-014~015 | TC-AGT-016~019 | 구현중 |
| REQ-BHV-004 | PRP-BHV-002, PRP-BHV-003 | DEC-001 | WP3 | IMP-API-005, IMP-AGT-005, 012 | TC-AGT-006, 014 | 구현중 |
| REQ-NET-001 | PRP-NET-001, PRP-NET-002, PRP-NET-003, PRP-SIM-002 | DEC-002, DEC-010 | WP0, WP1 | IMP-API-001, 003~004, 007, IMP-CORE-007, IMP-LNK-011, IMP-LOG-005, 007, IMP-UI-001, 011, 020~022, IMP-INT-001, IMP-LOG-009, IMP-API-014, IMP-CORE-014, IMP-AGT-023, IMP-LNK-015~016 | TC-API-001~005, TC-CORE-012, 024~025, TC-AGT-035~037, TC-LNK-016, TC-UI-002, 008, 010~016, TC-INT-001~004 | 구현중 |
| REQ-PRF-001 | PRP-BHV-002, PRP-SIM-001 | DEC-006 | WP1, WP3, WP10 | IMP-CORE-003, 008, IMP-MON-008, IMP-SCN-005, IMP-AGT-010, IMP-INT-002 | TC-CORE-002, 007, 013, TC-MON-009, TC-SCN-001, TC-INT-001 | 구현중 |
| REQ-PRF-002 | PRP-BHV-002 | DEC-005, DEC-006 | WP10, WP3 | IMP-AGT-010 | | 구현중 |
| REQ-LNK-001 | PRP-LNK-001 | DEC-002, DEC-029, DEC-032 | WP4 | IMP-LNK-001~006, 008, 011, 014~016 | TC-LNK-001~002, 004~006, 008~009, 011, 014~015 | 구현중 |
| REQ-LNK-002 | PRP-LNK-001 | DEC-009, DEC-028, DEC-030 | WP4 | IMP-CORE-011, IMP-LNK-007, 010, 012~013 | TC-CORE-016, TC-LNK-003, 007, 012~013 | 구현중 |
| REQ-LNK-003 | PRP-LNK-001 | DEC-009 | WP4 | IMP-CORE-011, IMP-LNK-010 | TC-CORE-016, TC-LNK-007 | 구현중 |
| REQ-LNK-004 | PRP-LNK-001, PRP-LNK-002 | DEC-008 | WP4 | IMP-LNK-001, 008 | TC-LNK-001, 004~006, 008~009, 011 | 구현중 |
| REQ-CFG-001 | PRP-CFG-001 | DEC-029 | WP5, WP7 | IMP-API-008~010, IMP-CORE-006~007, IMP-SCN-001, 003, 006~008 | TC-CORE-009, 011~012, TC-SCN-001~002, 004~010 | 구현중 |
| REQ-CFG-002 | PRP-CFG-001 |  | WP7 | IMP-SCN-001~004 | TC-SCN-001~007 | 구현중 |
| REQ-CFG-003 | PRP-CFG-001 | DEC-035, DEC-036 | WP1, WP3, WP5, WP7 | IMP-API-012~013, IMP-SCN-009, IMP-CORE-013, IMP-DYN-008, IMP-AGT-021~022, IMP-UI-045~051 | TC-API-006~007, TC-SCN-011, TC-DYN-014, TC-CORE-019~023, TC-AGT-029~034, TC-UI-028~031 | 구현중 |
| REQ-PAY-001 | PRP-PAY-001, PRP-CFG-001 | DEC-046 | WP8, WP7 | IMP-PAY-002, IMP-SCN-010 | TC-PAY-013, TC-SCN-012~013 | 구현중 |
| REQ-PAY-002 | PRP-PAY-001 | DEC-018, DEC-047 | WP8 | IMP-PAY-001, 003, IMP-CORE-022 | TC-PAY-001~004, TC-CORE-034 | 구현중 |
| REQ-PAY-003 | PRP-PAY-001, PRP-LNK-001 | DEC-009 | WP8, WP4 | IMP-PAY-004, IMP-CORE-022 | TC-PAY-005, TC-CORE-035 | 구현중 |
| REQ-PAY-004 | PRP-PAY-001, PRP-DYN-003 | DEC-012 | WP8 | IMP-PAY-005~006, IMP-CORE-022 | TC-PAY-006~011, TC-CORE-034 | 구현중 |
| REQ-PAY-005 | PRP-PAY-001, PRP-DYN-003 | DEC-012, DEC-019 | WP8 | IMP-PAY-002, 006 | TC-PAY-006, 009, 013 | 구현중 |
| REQ-SIM-001 | PRP-SIM-001 | DEC-017 | WP8 | IMP-CORE-010 | TC-CORE-015 | 구현중 |
| REQ-SIM-002 | PRP-SIM-002 | DEC-005 | WP1 | IMP-CORE-002, 007, IMP-SCN-006 | TC-CORE-001~006, 009~010, 012, TC-SCN-008 | 검증완료 |
| REQ-SIM-003 | PRP-UI-001 | DEC-004, DEC-016 | WP5, WP2 | IMP-CORE-009, IMP-DYN-005, IMP-SCN-002, 005, IMP-UI-002, 013 | TC-CORE-014, TC-DYN-008, 010, TC-SCN-001~003, TC-UI-009 | 구현중 |
| REQ-LOG-001 | PRP-LOG-001 | DEC-011, DEC-031 | WP7 | IMP-LOG-001~005, 008, IMP-LOG-009, IMP-LOG-010~011, IMP-INT-001 | TC-LOG-001~010, TC-INT-004 | 검증완료 |
| REQ-STD-001 | PRP-STD-001, PRP-STD-002, PRP-GNC-001 | DEC-013, DEC-014 | WP0, WP9 | IMP-API-002, 005 |  | 구현중 |

## 구현·시험 항목

- WP별 IMP·TC 상세(내용, 위치, 근거, 시험 결과)는 각 디렉터리의 `TRACE.md`에 있다: `core/`, `dynamics/`, `datalink/`, `bridge/`, `ui/`, `ui/monitor/`, `scenario/`, `logger/`, `agent/`, `algorithms/`, `payload/`. 위 매트릭스는 그 근거 열(REQ, DEC)로부터 모은 것이다.
- `검증완료`는 그 REQ의 범위를 구현했고 연결된 TC가 모두 통과한 경우다. 일부만 구현했으면 TC가 통과해도 `구현중`으로 둔다.
- 아래 첫 표는 WP0(`API`) 항목, 둘째 표는 통합(`INT`) 항목이다. 통합 실행 방법과 확인 화면은 [20_p0_demo.md](20_p0_demo.md)에 있다.

| ID | 내용 | 위치 | 근거 |
|---|---|---|---|
| IMP-API-001 | 모노레포 루트 빌드: CMake 프리셋(MSVC+vcpkg, MSYS2, Linux), uv workspace | `CMakeLists.txt`, `CMakePresets.json`, `vcpkg.json`, `pyproject.toml` | DEC-001, DEC-010, DEC-021, DEC-022 |
| IMP-API-002 | Protobuf 스키마 `swarm.v1`, A-GRA 매핑 옵션 | `proto/swarm/v1/` | PRP-STD-001, DEC-013, DEC-014 |
| IMP-API-003 | Zenoh 키 체계 (Python, C++) | `api/*/keys.*` | PRP-NET-003 |
| IMP-API-004 | ASB 버스 계약, 인메모리 백엔드 | `api/*/bus.*` | PRP-NET-001 |
| IMP-API-005 | MA/FA 플러그인 API, L1 포트 | `api/python/src/swarm_api/{ports,plugin}.py`, `api/cpp/include/swarm/api/plugin.hpp` | PRP-BHV-001, PRP-BHV-002, DEC-008, DEC-013 |
| IMP-API-006 | Core ⇄ 동역학 인터페이스. 0.2.0: `to_kinematic`에 `Environment` | `api/cpp/include/swarm/api/dynamics.hpp` | PRP-DYN-002, DEC-005, DEC-023 |
| IMP-API-007 | 공용 버스 라이브러리 `swarm_bus`(InMemory, Zenoh, `open_bus`, 공통 명령행 옵션)와 Python `open_bus` | `bus/`, `api/python/src/swarm_api/bus.py` | PRP-NET-001, DEC-026 |
| IMP-API-008 | 계약 0.2.0: `Scenario`·`MapSpec`·`RunSpec` 메시지, `LoadScenario.scenario` | `proto/swarm/v1/sim.proto` | DEC-024, DEC-025 |
| IMP-API-009 | 계약 0.3.0: `LinkProfile`·`Scenario.link_profiles`, `JamZoneEvent.area`, `SimStatus.replay`, 데이터링크 판정 규칙 | `proto/swarm/v1/{link,sim,truth}.proto`, `docs/10_contracts.md` §3.3 | DEC-028~032 |
| IMP-API-010 | 계약 0.4.0: `HoldTask` 매개변수, `RouteTask`·`RouteWaypoint`·`LoiterAction`·`ReconAction`, 지도 임무 명령 규칙 | `proto/swarm/v1/c2.proto`, `docs/10_contracts.md` §3.3 | DEC-033 |
| IMP-API-011 | 계약 0.5.0: `RacetrackShape`(HoldTask·LoiterAction), VI `RacetrackCurve`, 유도 방식 매개변수 규칙 | `proto/swarm/v1/{c2,vi}.proto`, `docs/10_contracts.md` §3.3 | DEC-034 |
| IMP-API-012 | 계약 0.6.0: `ParamLayer`·`ParamSpec`·`EntitySpec.dynamics_params`, `ParamOwner`·`SetParams`·`EntityParams`, 키 `sim/param/<entity>/<owner>`, 플러그인 `ParamDef`·`PARAMS`·`on_params`·`resolve_params`, `DynamicsModel::param_descs` | `proto/swarm/v1/{entity,sim}.proto`, `api/*/keys.*`, `api/python/src/swarm_api/plugin.py`, `api/cpp/include/swarm/api/dynamics.hpp`, `docs/10_contracts.md` §3.3·§5 | DEC-035 |
| IMP-API-013 | 계약 0.7.0: `ParamSpec.choices`, 거부 사유 `choice`, `ParamDef.choices` | `proto/swarm/v1/{entity,sim}.proto`, `api/python/src/swarm_api/plugin.py`, `docs/10_contracts.md` | DEC-036 |
| IMP-API-014 | 계약 0.8.0: 키 `sim/ctrl/scenario`, lockstep 준비 신호 `FrameDone{frame=0}` | `api/*/keys.*`, `docs/10_contracts.md` §3.2~3.3 | DEC-037 |
| IMP-API-015 | 계약 0.9.0: `SimStatus.waiting_participants`, 참여자 응답 없음·재생 한계 규칙 | `proto/swarm/v1/sim.proto`, `docs/10_contracts.md` §3.2 | DEC-041, DEC-042 |
| IMP-API-016 | 버스 QoS: lockstep 경로 키 BLOCK, 전 키 우선순위 DATA·비express (C++·Python) | `bus/src/zenoh_bus.cpp`, `api/python/src/swarm_api/bus.py` | DEC-043 |
| IMP-API-017 | 계약 0.10.0: `FrameDone.sent_count`, 송신 개수 장벽 규칙 | `proto/swarm/v1/sim.proto`, `docs/10_contracts.md` §3.3 | DEC-044 |
| IMP-API-018 | lockstep rx 소비 시점 문구를 틱 f-1 기준으로 정정 | `docs/10_contracts.md` §3.3 | DEC-045 |
| IMP-API-019 | P5 착수: WP8 Payload 지시문, SENSOR 고장 효과 정의 | `docs/11_wp_briefs.md` WP8 | DEC-046, DEC-047 |
| TC-API-001 | 키 생성, 엔티티 ID 검증, 키 표현식 일치 | `api/python/tests/test_keys.py` | IMP-API-003 |
| TC-API-002 | InMemoryBus 발행·구독·해제 | `api/python/tests/test_bus.py` | IMP-API-004 |
| TC-API-003 | C++ 키·버스, 생성 코드 링크 | `api/cpp/tests/test_api.cpp` | IMP-API-002~004 |
| TC-API-004 | C++ `open_bus` 백엔드 선택·명령행 옵션, Zenoh 두 세션 간 송수신·인코딩 보존 | `bus/tests/test_bus.cpp` | IMP-API-007 |
| TC-API-005 | Python `open_bus` 백엔드 선택, Zenoh 두 세션 간 송수신 | `api/python/tests/test_open_bus.py` | IMP-API-007 |
| TC-API-006 | 매개변수 해석: 기본값·재정의, 거부 사유(unknown·type·range·not_runtime)와 거부 시 기존 값 유지 | `api/python/tests/test_plugin.py` | IMP-API-012 |
| TC-API-007 | 허용 목록 밖 문자열은 `choice`로 거부하고 기존 값을 유지한다 | `api/python/tests/test_plugin.py` | IMP-API-013 |

| ID | 내용 | 위치 | 근거 |
|---|---|---|---|
| IMP-INT-001 | P0 데모 실행기 `live`·`replay`: Logger·Datalink·Agent·브리지·Core·UI(·Monitor)를 실제 Zenoh 버스(완전 연결 tcp, 멀티캐스트 끔)로 띄우고 시나리오 .pb 내보내기, 프로세스별 로그, Ctrl+C·STOP 파일 정상 종료 | `scripts/run_p0_demo.py` | DEC-015, DEC-026, DEC-027, DEC-031, REQ-NET-001 |
| IMP-INT-002 | 통합 시나리오: 2-DoF 고정익 20대(4×5 격자, 1200 m, 20 m/s, MA `waypoint`) + GCS 1, realtime 50 Hz, 전원 hold 임무 | `scenario/examples/p0_demo_20.json` | REQ-DYN-001, REQ-PRF-001, DEC-007, DEC-029 |
| IMP-INT-003 | 실행기 `probe`: GCS로 버스에 붙어 UI와 같은 LinkEnvelope(TaskCommand move_to)를 보내고 truth/state 도달·TaskStatus 수신을 판정 | `scripts/run_p0_demo.py` | DEC-013, DEC-014, REQ-BHV-001 |
| IMP-INT-004 | 실행기 `probe --kind hold\|racetrack\|route\|params`: 임무 명령(UI와 같은 TaskCommand) 실제 비행 궤적 판정, `SimCommand.set_params`로 FA·MA·동역학 변경·거부·복원과 `sim/param/<entity>/<owner>` 발행 판정 | `scripts/run_p0_demo.py` | DEC-013, DEC-033, DEC-034, DEC-035, REQ-BHV-001, REQ-CFG-003 |
| IMP-INT-005 | 실행기 `live --lockstep --rate --late-agent-s`: lockstep에서 Core만 `--scenario`를 받고 Datalink·Agent는 `sim/ctrl/scenario`로 수신(DEC-037). 참여자는 시나리오의 `run.mode`로 준비 신호를 정하므로 내보내는 시나리오에 `run.mode=lockstep`·`rate`·`participants`를 넣는다. `probe --kind params`에 `racetrack_guidance=foo` → `choice` 거부 판정 추가 | `scripts/run_p0_demo.py` | DEC-036, DEC-037, DEC-005 |
| TC-INT-001 | live: UI(source=bus) 2D 지도에 20대 + GCS 표시, 연결·실행 상태 | `docs/20_p0_demo.md` §5, `docs/img/p0_demo/01_*.jpg` | IMP-INT-001~002 |
| TC-INT-002 | probe: MoveTo → C2 → Datalink → Agent → 기체 300 m 안 도달, TaskStatus ACCEPTED·EXECUTING·COMPLETED가 GCS에 도착 | `scripts/run_p0_demo.py probe` | IMP-INT-001, IMP-INT-003 |
| TC-INT-003 | UI 드래그 선택 + 우클릭 MoveTo → 선택 5대 도달, UI에 완료 100% | `docs/img/p0_demo/02~05_*.jpg` | IMP-INT-001 |
| TC-INT-004 | live 기록 MCAP 재생 → `SimStatus.replay`=true, Monitor `재생 (MCAP)` 배지, UI에 기동 재현 | `scripts/run_p0_demo.py replay`, `docs/img/p0_demo/06~08_*.jpg` | IMP-INT-001, IMP-LOG-008~009 |
| TC-INT-005 | probe hold·racetrack·route: 임무 명령이 C2 → Datalink → Agent → Core로 실제 선회·레이스트랙·항로 비행, TaskStatus 수신 | `scripts/run_p0_demo.py probe --kind …` | IMP-INT-004 |
| TC-INT-006 | probe params(fa·ma·dynamics): runtime 항목 변경 반영, unknown·range·not_runtime 거부 사유와 기존 값 유지 | `scripts/run_p0_demo.py probe --kind params` | IMP-INT-004 |
| TC-INT-007 | UI: 12대 선택 → 레이스트랙 선회 임무 전송 → 수행 표시·비행, 매개변수 패널 적용·범위 검증·기본값 복원 | `docs/img/p0_demo/09~10_*.jpg` | IMP-INT-001, IMP-INT-004 |
| TC-INT-008 | lockstep: Core만 `--scenario`로 시작, Datalink·Agent에는 시나리오를 주지 않아도 `sim/ctrl/scenario`로 받아 준비 신호 후 첫 틱이 나가고 probe move 통과 | `scripts/run_p0_demo.py live --lockstep` | IMP-INT-005 |
| TC-INT-009 | lockstep 지각 참여자: Core 뒤 6 s에 Agent를 켜도 준비 신호 후 첫 틱이 나간다 | `scripts/run_p0_demo.py live --lockstep --late-agent-s 6` | IMP-INT-005 |
| TC-INT-010 | probe params: `racetrack_guidance=foo`가 `choice`로 거부되고 기존 값 유지 | `scripts/run_p0_demo.py probe --kind params` | IMP-INT-005 |
| TC-INT-011 | UI·Monitor 재확인: 12대 선택 시 `전송` 버튼 비가림, 재생 표시·버튼 비활성, 3배속 재생 Monitor 링크 지연 정상 | `docs/img/p0_demo/11~14_*.jpg` | IMP-INT-001 |
| TC-QA-001 | s1 6기 3-DoF 편대 120 s 안정성 | `qa/run_qa.py --only 001` | DEC-005 |
| TC-QA-002 | s2 20기 임무 혼합(hold·route·racetrack·search_area) 240 s | `qa/run_qa.py --only 002` | DEC-005 |
| TC-QA-003 | s3 불완전 링크 프로파일, 거리 밖 기체 | `qa/run_qa.py --only 003` | DEC-032 |
| TC-QA-004 | s4 적·표적·센서·무장 선언 시나리오 견고성 | `qa/run_qa.py --only 004` | DEC-017, DEC-018, DEC-019 |
| TC-QA-005 | s5 2/3-DoF·기체 혼합, dof5/dof6 적재 | `qa/run_qa.py --only 005` | DEC-017 |
| TC-QA-006 | 50기 lockstep 2배속 부하 | `qa/run_qa.py --only 006` | DEC-005 |
| TC-QA-007 | 100기 lockstep 1배속 부하 | `qa/run_qa.py --only 007` | DEC-005 |
| TC-QA-008 | 100기 flocking(P2P) 부하 | `qa/run_qa.py --only 008` | DEC-005 |
| TC-QA-009 | 100기 realtime 실시간성 | `qa/run_qa.py --only 009` | DEC-005 |
| TC-QA-010 | 통제 명령: pause·resume·step·set_rate·reset | `qa/run_qa.py --only 010` | DEC-014 |
| TC-QA-011 | 모드 전환 lockstep·realtime·freerun | `qa/run_qa.py --only 011` | DEC-005, DEC-037 |
| TC-QA-012 | 잘못된 SimCommand·시나리오 적재 | `qa/run_qa.py --only 012` | DEC-014 |
| TC-QA-013 | 임무 명령 연속·충돌·중복 task_id | `qa/run_qa.py --only 013` | DEC-013 |
| TC-QA-014 | 잘못된 임무 값(범위·NaN·빈 값) | `qa/run_qa.py --only 014` | DEC-013 |
| TC-QA-015 | 명령 홍수 10 s | `qa/run_qa.py --only 015` | DEC-013 |
| TC-QA-016 | 실행 중 매개변수 변경과 거부 | `qa/run_qa.py --only 016` | DEC-035, DEC-036 |
| TC-QA-017 | 고장 주입(LINK_CUT·GCS_LINK_CUT·ENGINE·NAV·KILL·SENSOR) | `qa/run_qa.py --only 017` | DEC-014 |
| TC-QA-018 | 재밍 구역 on/off | `qa/run_qa.py --only 018` | DEC-032 |
| TC-QA-019 | Agent·Datalink·Core 재시작(realtime) | `qa/run_qa.py --only 019` | DEC-026 |
| TC-QA-020 | lockstep 지각 참여, 이탈 후 Reset+Start 복구, 대기 참여자 로그 | `qa/run_qa.py --only 020` | DEC-037, DEC-038 |
| TC-QA-021 | Logger 기록·info·재생(배속 변경) | `qa/run_qa.py --only 021` | DEC-031 |
| TC-QA-022 | 같은 시나리오 lockstep 결정성 | `qa/run_qa.py --only 022` | DEC-005 |
| TC-QA-023 | 20기 realtime 10분 CPU·RSS 추세 | `qa/run_qa.py --only 023` | DEC-005 |
| TC-QA-024 | 결정성 추가: 시드 2종, 불완전 링크 s3 | `qa/run_qa.py --only 024` | DEC-005 |
| TC-QA-025 | Agent 프로세스 CPU·RSS(50기 realtime 90 s) | `uv run --with psutil python qa/run_qa.py --only 025` | DEC-003 |
| TC-QA-026 | Monitor 통계 대 독립 집계(s3 라이브) | `qa/link_count.py` + Monitor | DEC-028 |
| TC-QA-027 | 임무 중 Core·Datalink 재시작과 UI 복구 | `qa/recovery_stack.py` + 브라우저 | DEC-026, DEC-027 |
| TC-QA-028 | lockstep 중 Datalink 이탈·재기동 | `uv run --with psutil python qa/run_qa.py --only 028` | DEC-038 |
| TC-QA-029 | QA-008 재생 전달 판별 | `uv run --with mcap python qa/qa008_replay.py <rec.mcap>` | DEC-009 |
| TC-QA-030 | lockstep 참여자 이탈 시 `SimStatus.waiting_participants` | `uv run --with psutil python qa/run_qa.py --only 030` | DEC-041 |
| TC-QA-031 | P5: 센서 판정 Detection이 Agent MS 포트에 도착(버스 건수 = MS 포트 건수) | `uv run python qa/p5_e2e.py --mode lockstep` | DEC-046, DEC-018 |
| TC-QA-032 | P5: SENSOR 고장 중 Detection 0·`SensorActivity.active=false`, 해제 뒤 재개 | `qa/p5_e2e.py --fault` | DEC-047, DEC-012 |
| TC-QA-033 | P5: StrikeCommand → launch·spawn → 생성 엔티티 이동 → impact·kill → 대상 alive=false | `qa/p5_e2e.py` + `qa/p5_probe_agent.py` | DEC-046, DEC-019 |
| TC-QA-034 | P5: jam_zone 이벤트가 Datalink 구역에 반영되어 구역 안 수신이 JAMMED | `qa/p5_e2e.py` | DEC-009, DEC-028 |
| TC-QA-035 | P5: 같은 시드 lockstep 반복의 truth·이벤트 동일 | `qa/p5_e2e.py --compare <A> <B>` | DEC-005, DEC-044 |
| TC-QA-036 | P5: UI 구역·궤적·영향 반경·센서 FOV 표시(TC-UI-051, 실버스) | `qa/p5_e2e.py --mode realtime --bridge --ui` + 앱 내장 브라우저 | DEC-003, DEC-046 |

## 시험 결과

| TC | 결과 | 일자 | 환경 |
|---|---|---|---|
| TC-API-001 | 통과 | 2026-11-01 | Windows, uv + CPython 3.12 |
| TC-API-002 | 통과 | 2026-11-01 | Windows, uv + CPython 3.12 |
| TC-API-003 | 통과 | 2026-11-01 | Windows, MSVC + vcpkg (`msvc-debug`) |
| TC-API-004 | 통과 | 2026-11-01 | Windows, MSVC + vcpkg + Zenoh 1.10.2 (`msvc-debug`) |
| TC-API-005 | 통과 | 2026-11-01 | Windows, uv + CPython 3.12 + eclipse-zenoh 1.10.2 |
| TC-INT-001 | 통과 | 2026-11-02 | Windows, MSVC + vcpkg (`msvc-debug`) + uv + Zenoh 1.10.2, Chromium(앱 내장 브라우저) |
| TC-INT-002 | 통과 | 2026-11-02 | 위와 같음 |
| TC-INT-003 | 통과 | 2026-11-02 | 위와 같음 |
| TC-INT-004 | 통과 | 2026-11-02 | 위와 같음, 3배속 재생 |
| TC-INT-005 | 통과 | 2026-11-02 | 위와 같음, 계약 0.6.0 병합 후 (wp0-contracts dacf4be) |
| TC-INT-006 | 통과 | 2026-11-02 | 위와 같음, 계약 0.6.0 병합 후 (wp0-contracts dacf4be) |
| TC-INT-007 | 통과 | 2026-11-02 | 위와 같음, 계약 0.6.0 병합 후 (wp0-contracts dacf4be) |
| TC-INT-008 | 통과 | 2026-11-02 | 계약 0.8.0(wp0-contracts fde329c까지). 시나리오의 run.mode=lockstep일 때만. CLI `--mode lockstep`만으로는 준비 신호가 없어 교착. lockstep `--rate 1`에서 probe hold·racetrack·route·params도 통과 |
| TC-INT-009 | 불합격 | 2026-11-02 | 지각 Agent가 시나리오를 받지 못해 틱이 나가지 않는다. 담당 WP1(Core). `docs/20_p0_demo.md` §6 |
| TC-INT-010 | 통과 | 2026-11-02 | `{'racetrack_guidance': 'choice'}` 거부, 기존 값 유지 |
| TC-INT-011 | 통과 | 2026-11-02 | 12대 선택 `전송 (12대)` 최상단, 재생 배지·버튼 비활성, 3배속 지연 평균 약 21 ms |
| TC-API-006 | 통과 | 2026-11-02 | Windows, uv + CPython 3.12 |
| TC-API-007 | 통과 | 2026-11-02 | Windows, uv + CPython 3.12 |
| TC-QA-001 | 통과 | 2026-11-03 | `msvc-debug`, 계약 0.8.0 (4e3c4c3). 결과·결함은 `docs/21_qa_report.md` |
| TC-QA-002 | 통과 | 2026-11-03 | 위와 같음 |
| TC-QA-003 | 통과 | 2026-11-03 | 위와 같음 |
| TC-QA-004 | 통과 | 2026-11-03 | 위와 같음. 견고성만, 탐지·교전은 Core 미구현 |
| TC-QA-005 | 통과 | 2026-11-03 | 위와 같음. dof5/dof6은 Core 종료(결정 확인 D-3) |
| TC-QA-006 | 통과 | 2026-11-05 | 4차 DEC-044 후 1.61배 (`docs/21_qa_report.md` §11) |
| TC-QA-007 | 통과 | 2026-11-05 | 4차 0.92배 |
| TC-QA-008 | 통과 | 2026-11-05 | 4차 0.27배 |
| TC-QA-009 | 통과 | 2026-11-03 | 위와 같음. sim/벽시계 1.00 |
| TC-QA-010 | 통과 | 2026-11-03 | 위와 같음. 비정상 rate 거부 확인(QA-003 수정), 2차 재시험 |
| TC-QA-011 | 통과 | 2026-11-03 | 위와 같음 |
| TC-QA-012 | 통과 | 2026-11-03 | 2차: 비유한 위치·dof5/6·빈 시나리오 거부 후 생존(QA-001·003, D-3 수정 확인) |
| TC-QA-013 | 통과 | 2026-11-03 | 2차: 기준 변경(순서 뒤바뀜 허용, 간격 둔 마지막 명령 도달) |
| TC-QA-014 | 불합격 | 2026-11-03 | 2차: 경로·hold 반경 NaN 무응답(QA-014). 나머지 REJECTED 일관 |
| TC-QA-015 | 불합격 | 2026-11-03 | 2차: 홍수 후 lockstep 영구 정지, Datalink 대기(QA-012) |
| TC-QA-016 | 통과 | 2026-11-03 | 2차: `inf`·`NaN` 포함 모두 range 거부, Agent 생존(QA-002 수정 확인) |
| TC-QA-017 | 통과 | 2026-11-03 | SENSOR 고장은 기록만(결정 확인 D-2) |
| TC-QA-018 | 통과 | 2026-11-03 | `jam_zone`은 시험이 직접 발행 |
| TC-QA-019 | 통과 | 2026-11-03 | realtime. Core 재기동 후 재개 |
| TC-QA-020 | 통과 | 2026-11-03 | 2차: Agent 이탈 정지, Core 대기 로그, Reset+Start 복구(DEC-038) |
| TC-QA-021 | 통과 | 2026-11-03 | 고배속 재생 프레임 감소(QA-008) |
| TC-QA-022 | 통과 | 2026-11-03 | 2579 프레임 최대 차이 0.000000 m |
| TC-QA-023 | 통과 | 2026-11-03 | Core·Datalink 안정, Logger +5 MB(QA-006) |
| TC-QA-024 | 통과 | 2026-11-05 | 4차: DEC-044 후 s3 시드 7·20261104, s6 flocking 100기 모두 불일치 0 (QA-016 해결) |
| TC-QA-025 | 통과 | 2026-11-03 | Agent 평균 63%, RSS 4.5→72.7 MB, 증가 없음 |
| TC-QA-026 | 통과 | 2026-11-05 | 5차(ee0f234): flocking 100기 손실률 1.905% 대 Monitor 1.9%, 평균 지연 20.0 ms 일치. QA-018 재현 안 됨 |
| TC-QA-027 | 통과 | 2026-11-03 | Core·Datalink 재시작 후 UI 복구. Core 정지 시 붉은 배지 표시(QA-015 수정) |
| TC-QA-028 | 통과 | 2026-11-05 | 4차: 이탈 시 정지·Core 대기 로그, Reset+Start 복구. waiting_participants 필드는 미확인 |
| TC-QA-029 | 해석 | 2026-11-05 | 4차: 20배속 수신기 1358/관찰자 1082, 설계 한계 |
| TC-QA-030 | 통과 | 2026-11-05 | 5.5 s 뒤 agent-0 표시, Reset 뒤 비움. UI 경고·재생 누락 프레임 표시도 브라우저로 확인(§12) |
| TC-QA-031 | 통과 | 2026-11-05 | 6차 P5: 버스 Detection 건수 = MS 포트 건수(lockstep 11쌍). 지형 가림은 DEM 없음(QA-022)으로 미확인 |
| TC-QA-032 | 통과 | 2026-11-05 | 고장 중 Detection 0·active=false, 해제 프레임부터 재개(lockstep·realtime) |
| TC-QA-033 | 부분 통과 | 2026-11-05 | AGM 1건 launch→spawn→2,501 m→impact·kill→alive=false. 평지만(QA-022), 승인 흐름·AAM·FPV 미확인 |
| TC-QA-034 | 통과 | 2026-11-05 | 구역 안 수신 27,121건 모두 JAMMED. 늦은 구독자는 구역을 못 받음(QA-021) |
| TC-QA-035 | 불합격 | 2026-11-05 | 3회 중 1회가 프레임 11,427부터 최대 2 mm 어긋남(QA-019) |
| TC-QA-036 | 불합격 | 2026-11-05 | 구역 표시됨. 발사 순간 렌더링 중지(QA-023), FOV 입력 없음(QA-020) |

## 프로세스 결정

| DEC | 적용 범위 |
|---|---|
| DEC-015 | 전체 개발 프로세스: WBS 작업 패키지별 병렬 세션, WP0 계약 우선 |
| DEC-021 | 저장소 구조: 모노레포, WP별 디렉터리, worktree 병렬 작업 |
| DEC-022 | 빌드 환경: MSVC+vcpkg, MSYS2 GCC, Linux/WSL2 GCC 프리셋 병행 (IMP-API-001) |
