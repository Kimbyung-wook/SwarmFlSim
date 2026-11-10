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
| REQ-UI-001 | PRP-UI-001 | DEC-003, DEC-004, DEC-046 | WP5 | IMP-UI-003~005, 008~010, 012, 014~016, 018~019, 060~068, IMP-INT-001 | TC-UI-001~003, 005~006, 008~009, 046~056, TC-INT-001 | 구현중 |
| REQ-UI-002 | PRP-UI-001 | DEC-003 | WP5 | IMP-UI-006, 016~017, 019, 025~026, 031, 034, IMP-INT-001 | TC-UI-004, 009, 018~019, TC-INT-003 | 구현중 |
| REQ-UI-003 | PRP-UI-001 | DEC-014, DEC-033 | WP5 | IMP-API-010, IMP-UI-025, 027~032, 034~041, 074~075 | TC-UI-008, 018~025, 061~063 | 구현중 |
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
| REQ-BHV-004 | PRP-BHV-002, PRP-BHV-003 | DEC-001, DEC-070 | WP3 | IMP-API-005, IMP-AGT-005, 012, IMP-EXP-001~004 | TC-AGT-006, 014, TC-EXP-001~007 | 구현중 |
| REQ-NET-001 | PRP-NET-001, PRP-NET-002, PRP-NET-003, PRP-SIM-002 | DEC-002, DEC-010 | WP0, WP1 | IMP-API-001, 003~004, 007, IMP-CORE-007, IMP-LNK-011, IMP-LOG-005, 007, IMP-UI-001, 011, 020~022, IMP-INT-001, IMP-LOG-009, IMP-API-014, IMP-CORE-014, IMP-AGT-023, IMP-LNK-015~016 | TC-API-001~005, TC-CORE-012, 024~025, TC-AGT-035~037, TC-LNK-016, TC-UI-002, 008, 010~016, TC-INT-001~004 | 구현중 |
| REQ-PRF-001 | PRP-BHV-002, PRP-SIM-001 | DEC-006 | WP1, WP3, WP10 | IMP-CORE-003, 008, IMP-MON-008, IMP-SCN-005, IMP-AGT-010, IMP-INT-002 | TC-CORE-002, 007, 013, TC-MON-009, TC-SCN-001, TC-INT-001 | 구현중 |
| REQ-PRF-002 | PRP-BHV-002 | DEC-005, DEC-006 | WP10, WP3 | IMP-AGT-010 | TC-QA-114~118 | 구현중 |
| REQ-LNK-001 | PRP-LNK-001 | DEC-002, DEC-029, DEC-032, DEC-039, DEC-077 | WP4 | IMP-LNK-001~006, 008, 011, 014~016, 023 | TC-LNK-001~002, 004~006, 008~009, 011, 014~015, 024~026 | 구현중 |
| REQ-LNK-002 | PRP-LNK-001 | DEC-009, DEC-028, DEC-030, DEC-055 | WP4 | IMP-CORE-011, IMP-LNK-007, 010, 012~013 | TC-CORE-016, TC-LNK-003, 007, 012~013 | 구현중 |
| REQ-LNK-003 | PRP-LNK-001 | DEC-009, DEC-078 | WP3, WP4 | IMP-CORE-011, IMP-LNK-010, IMP-LNK-024, IMP-AGT-037~039 | TC-CORE-016, TC-LNK-007, TC-LNK-027~029, TC-AGT-094~117, TC-QA-119~126 | 구현중 |
| REQ-LNK-004 | PRP-LNK-001, PRP-LNK-002 | DEC-008 | WP4 | IMP-LNK-001, 008 | TC-LNK-001, 004~006, 008~009, 011 | 구현중 |
| REQ-CFG-001 | PRP-CFG-001 | DEC-029, DEC-050 | WP5, WP7 | IMP-API-008~010, IMP-CORE-006~007, 025, IMP-SCN-001, 003, 006~008, 011 | TC-CORE-009, 011~012, 039, TC-SCN-001~002, 004~010, 014 | 구현중 |
| REQ-CFG-002 | PRP-CFG-001 |  | WP7 | IMP-SCN-001~004 | TC-SCN-001~007 | 구현중 |
| REQ-CFG-003 | PRP-CFG-001 | DEC-035, DEC-036 | WP1, WP3, WP5, WP7 | IMP-API-012~013, IMP-SCN-009, IMP-CORE-013, IMP-DYN-008, IMP-AGT-021~022, IMP-UI-045~051 | TC-API-006~007, TC-SCN-011, TC-DYN-014, TC-CORE-019~023, TC-AGT-029~034, TC-UI-028~031 | 구현중 |
| REQ-PAY-001 | PRP-PAY-001, PRP-CFG-001 | DEC-046 | WP8, WP7 | IMP-PAY-002, IMP-SCN-010 | TC-PAY-013, TC-SCN-012~013 | 구현중 |
| REQ-PAY-002 | PRP-PAY-001 | DEC-018, DEC-047, DEC-051, DEC-056, DEC-063 | WP8, WP3 | IMP-PAY-001, 003, IMP-CORE-022, IMP-AGT-029~031 | TC-PAY-001~004, TC-CORE-034, TC-AGT-051~062 | 구현중 |
| REQ-PAY-003 | PRP-PAY-001, PRP-LNK-001 | DEC-009, DEC-049, DEC-052 | WP8, WP4 | IMP-PAY-004, IMP-CORE-022, 024~025 | TC-PAY-005, TC-CORE-035, 038~039 | 구현중 |
| REQ-PAY-004 | PRP-PAY-001, PRP-DYN-003 | DEC-012, DEC-064, DEC-066, DEC-067 | WP8 | IMP-PAY-005~006, 008~009, IMP-CORE-022 | TC-PAY-006~011, 015~018, TC-CORE-034, TC-QA-065~068, 075~077 | 구현중 |
| REQ-PAY-005 | PRP-PAY-001, PRP-DYN-003 | DEC-012, DEC-019 | WP8 | IMP-PAY-002, 006 | TC-PAY-006, 009, 013 | 구현중 |
| REQ-SIM-001 | PRP-SIM-001 | DEC-017 | WP8 | IMP-CORE-010 | TC-CORE-015 | 구현중 |
| REQ-SIM-002 | PRP-SIM-002 | DEC-005, DEC-039, DEC-054 | WP1, WP3, WP4 | IMP-CORE-002, 007, IMP-SCN-006, IMP-LNK-022, IMP-AGT-036 | TC-CORE-001~006, 009~010, 012, TC-SCN-008, TC-LNK-023, TC-AGT-088~093, TC-QA-106~108, 113 | 검증완료 |
| REQ-SIM-003 | PRP-UI-001 | DEC-004, DEC-016, DEC-053, DEC-057, DEC-059, DEC-060, DEC-061 | WP5, WP2 | IMP-CORE-009, 023, 026~027, IMP-DYN-005, 009, IMP-SCN-002, 005, IMP-UI-002, 013, 069~073 | TC-CORE-014, 036~037, 040~042, TC-DYN-008, 010, 015, TC-SCN-001~003, TC-UI-009, 057~060 | 구현중 |
| REQ-LOG-001 | PRP-LOG-001 | DEC-011, DEC-031 | WP7 | IMP-LOG-001~005, 008, IMP-LOG-009, IMP-LOG-010~011, IMP-INT-001 | TC-LOG-001~010, TC-INT-004 | 검증완료 |
| REQ-STD-001 | PRP-STD-001, PRP-STD-002, PRP-GNC-001 | DEC-013, DEC-014, DEC-068, DEC-069, DEC-071, DEC-072, DEC-073, DEC-075, DEC-076, DEC-077 | WP0, WP9, WP3, WP1, WP5 | IMP-API-002, 005, IMP-GW-001~023, IMP-UI-076, IMP-AGT-032~035, IMP-CORE-028 | TC-GW-001~027, TC-UI-064, TC-QA-069~074, 078~113, TC-AGT-063~087, TC-CORE-043 | 구현중 |

## 구현·시험 항목

- WP별 IMP·TC 상세(내용, 위치, 근거, 시험 결과)는 각 디렉터리의 `TRACE.md`에 있다: `core/`, `dynamics/`, `datalink/`, `bridge/`, `ui/`, `ui/monitor/`, `scenario/`, `logger/`, `agent/`, `algorithms/`, `payload/`, `gateway/`, `examples/plugins/`. 위 매트릭스는 그 근거 열(REQ, DEC)로부터 모은 것이다.
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
| IMP-API-020 | 계약 0.12.0: rx 불변식 `rx_time_us >= T_k`, 재밍 수신단 기준 명시, 상태 변화 보고 최대 빈도, DEM 파일 형식 | `docs/10_contracts.md` §3.3·§6·§7 | DEC-054, DEC-055, DEC-056, DEC-053 |
| IMP-API-021 | 계약 0.13.0: `StrikeActivity` 무장별 보고 키, 종료 무장 키의 전체 보고 제외 | `docs/10_contracts.md` §3 임무장비 상태 보고 | DEC-063 |
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
| TC-QA-037 | QA-019 원인 좁히기: 같은 시드 P5 lockstep 6회×4변형(base·nosensor·nopayload·noloss), 프레임별 LinkOutcome·Agent 입력·ControlOutput 비교 | `qa/p5_e2e.py --trace-io`, `qa/qa019_batch.sh`, `qa/qa019_summary.py` | DEC-045, DEC-044, DEC-005 |
| TC-QA-038 | DEC-051: GCS가 `swarm/<gcs>/rx/ms/SensorActivity`를 받고 UI에 센서 FOV 표시(실버스, QA-020 재시험) | `qa/p5_e2e.py --mode realtime --bridge --ui` + 앱 내장 브라우저, `gcs_act.pkl.gz` | DEC-051, DEC-046, DEC-003 |
| TC-QA-039 | DEC-051: GCS 링크 두절(GCS_LINK_CUT 고장, 거리 초과) 동안 그 기체 Activity 미수신, 복구 뒤 1 s 안 재수신 | `qa/p5_e2e.py --link-cut`, `qa/scenarios/qa_p5_range.json` | DEC-051, DEC-009, DEC-028 |
| TC-QA-040 | DEC-051: 같은 시드 lockstep 6회에서 GCS 수신 Activity의 순서·프레임 동일 | `qa/qa019_batch.sh`(PREFIX=a40), `qa/act_det.py` | DEC-051, DEC-045, DEC-005 |
| TC-QA-041 | DEC-054: 같은 시드 lockstep 4변형 × 6회에서 궤적·이벤트·LinkOutcome·MA 입력 동일, 0 지연 전달 없음(QA-019 재시험) | `qa/qa019_batch.sh`(PREFIX=r9), `qa/qa019_summary.py --prefix r9` | DEC-054, DEC-045, DEC-005 |
| TC-QA-042 | DEC-052: 늦게 붙은 구독자·UI가 1 s 안에 활성 재밍 구역 수신, 꺼진 구역 재발행 없음(QA-021 재시험) | `qa/jam_late.py` (+ `--bridge --ui`, 앱 내장 브라우저) | DEC-052, DEC-028 |
| TC-QA-043 | DEC-056: 기본 10 Hz 제한에서 기체당 Activity 보고 빈도·대역 | `qa/act_rate.py` | DEC-056, DEC-051 |
| TC-QA-044 | DEC-053: DEM 지형에서 지면 충돌 프레임·고도가 DEM 보간값과 일치, 격자 밖 0 m(QA-022 재시험) | `qa/dem_check.py --case mtn|north [--flat]` | DEC-053, DEC-060, DEC-016, DEC-004 |
| TC-QA-045 | DEC-053·061: `--terrain-flat`과 `--terrain-dem` 함께 주면 DEM 우선·경고, 없는 DEM 파일 오류 | `swarm_core` 직접 실행(시나리오는 `swarm-scenario export`) | DEC-053, DEC-061 |
| TC-QA-046 | DEC-054: 발사·생성·도달이 있는 84,000 프레임 lockstep 3회 결정성, 0 지연 전달 없음, 자원 추이 | `qa/qa019_batch.sh`(PREFIX=r10L), `qa/qa019_summary.py --prefix r10L` | DEC-054, DEC-045, DEC-005 |
| TC-QA-047 | DEC-051·056: StrikeActivity 변경·1 s 주기 보고, (메시지, payload_id)별 10 Hz 상한 | `link_io.pkl.gz`·`gcs_act.pkl.gz` 분석 | DEC-051, DEC-056 |
| TC-QA-048 | DEC-056: `--activity-max-hz` 2·50·0 실측 | `qa/qa019_batch.sh`(AGENT_ARGS), `qa/act_rate.py` | DEC-056 |
| TC-QA-049 | DEC-052·055: Datalink 재시작 뒤 구역 재발행으로 구역 안 링크 재두절, 수신단 판정 유지 | `qa/dl_restart_jam.py` | DEC-052, DEC-055 |
| TC-QA-050 | O-5: frame 0 단발 이벤트 누락 영향 정리 | r9·r10 trace 분석, 코드 확인 | DEC-052 |
| TC-QA-051 | DEC-057·059: UI 지도 영상·지형 동시 사용 FPS, 콘솔 오류, 출처 표기 | `qa/ui_map_fps.py` (Playwright, 시스템 Chrome) | DEC-057, DEC-059 |
| TC-QA-052 | DEC-018: DEM 지형에서 산릉이 가리면 FOV·거리 안이어도 Detection 없음, 고도를 높이거나 위치를 옮기면 Detection (Python DEM 단면 대조) | `qa/los_check.py --out qa/out/los/dem` | DEC-018, DEC-053 |
| TC-QA-053 | DEC-018: 같은 배치 `--terrain-flat 0` 대조에서 가림 없음 | `qa/los_check.py --out qa/out/los/flat --flat` | DEC-018 |
| TC-QA-054 | DEC-018: 가시선 판정 경계(50 m 표본, 끝점 0.5 m 허용), 경계 고도 ±1 m 판정과 세밀 표본 비교 | `qa/los_check.py --design` | DEC-018 |
| TC-QA-055 | DEC-051·056: 0.1 s 안 StrikeActivity 연속 변경에서 10 Hz 상한의 합침·지연, 마지막 상태 전달 | `qa/strike_burst.py --hz 10 --impact-from …` + `qa/strike_burst_agent.py` | DEC-051, DEC-056 |
| TC-QA-056 | DEC-051·056: `--activity-max-hz 0` 대조, 같은 프레임 안 두 변경의 보고 | `qa/strike_burst.py --hz 0 --impact-from …` | DEC-051, DEC-056 |
| TC-QA-057 | DEC-063: StrikeActivity 무장별 키, 1 s 전체 보고에 비행 중 무장만(종료 무장 제외), 변화 보고 상한이 무장 키별 | `qa/strike_burst.py` + `qa/strike_burst_keys.py` | DEC-063, DEC-051, DEC-056 |
| TC-QA-058 | MISSED expired(max_flight_time 도달)가 GCS에 한 번 도착하고 이후 1 s 전체 보고에서 빠짐 | `qa/strike_cases.py --case cases` + `qa/strike_burst_keys.py` | DEC-063, DEC-048, REQ-PAY-002 |
| TC-QA-059 | MISSED destroyed(무장 자신 파괴)가 한 번 도착하고 이후 빠짐, 비행 중 표적 소멸 시 종료 상태 | `qa/strike_cases.py --case cases` + `qa/strike_burst_keys.py` | DEC-063, DEC-048, REQ-PAY-002 |
| TC-QA-060 | 능선 뒤 표적 Strike: 발사 판정·조준점 발사·비행 중 탐색기의 DEM 가시선 사용 | `qa/strike_cases.py --case ridge --point` | DEC-018, DEC-019, DEC-046 |
| TC-QA-061 | realtime 모드 StrikeActivity 10 Hz 상한과 무장별 키 | `qa/strike_burst.py --realtime` + `qa/strike_burst_keys.py` | DEC-063, DEC-056 |
| TC-QA-062 | SensorActivity·JammerActivity 변화 보고 상한(10 Hz, 0 Hz, realtime) | `qa/strike_cases.py --case cases` | DEC-051, DEC-056 |
| TC-QA-063 | DEM 끝점 0.5 m 허용이 판정을 가르는 배치(지면 표적, 표적 앞 언덕) | `qa/los_edge.py --terrain dem` | DEC-018 |
| TC-QA-064 | 평지 곡률 처짐으로 끝점 표본 하나만 가리는 배치 | `qa/los_edge.py --terrain flat` | DEC-018 |
| TC-QA-065 | DEC-064: 합성 언덕 DEM에서 비행 중 유도 객체의 락 해제·좌표 유도 전환 프레임이 Python 가시선과 같음 | `qa/los_synth.py run --case hill` + `analyse` | DEC-064, DEC-018 |
| TC-QA-066 | DEC-064: 가시선 회복 시 재획득, 연속 전환에서 고정점 갱신 | `qa/los_synth.py run --case hill·edge` + `analyse` | DEC-064 |
| TC-QA-067 | DEC-064: 평지(`--terrain-flat 0`)와 조준점 좌표 유도의 회귀 없음 | `qa/los_synth.py run --case flat·coord` + `analyse` | DEC-064, DEC-019 |
| TC-QA-068 | DEC-064: 같은 시드 2회 실행의 궤적·이벤트·StrikeActivity 결정성 | `qa/los_synth.py same` | DEC-064, DEC-004 |
| TC-QA-069 | DEC-068: 통합 실행에서 외부 클라이언트가 VI·C2·P2P·MS 상태를 받고 공개 XSD 재검증 통과 | `qa/gw_integ.py` + `qa/gw_ext_client.py` | DEC-068, PRP-STD-002 |
| TC-QA-070 | DEC-014: EXT 메시지 외부 미발행(통합 실행) | `qa/gw_integ.py` + `qa/gw_ext_client.py` | DEC-014, DEC-068 |
| TC-QA-071 | DEC-068: 외부 MA_TaskCommand(hold·return_to_base·취소)가 Datalink를 거쳐 기체에 도달하고 동작 변화 | `qa/gw_integ.py` + `qa/gw_ext_client.py` | DEC-068, DEC-013 |
| TC-QA-072 | DEC-068: GCS 링크 차단 시 외부 상태 발행 감소·정지, 해제 시 회복 | `qa/gw_integ.py` + `qa/gw_ext_client.py` | DEC-068, DEC-009 |
| TC-QA-073 | Gateway 끊김·재접속 중 시뮬레이터 연속 진행 | `qa/gw_integ.py` + `qa/gw_ext_client.py` | DEC-068, DEC-005 |
| TC-QA-074 | Gateway 버스 범위: `swarm/<gcs>/rx/**` 구독, `tx/c2/**` 발행만 | `qa/gw_integ.py` + `qa/gw_ext_client.py` | DEC-068, DEC-013 |
| TC-QA-075 | DEC-066: FOV 안 조준점 발사 LAUNCHED | `qa/fov_launch.py` | DEC-066 |
| TC-QA-076 | DEC-066: FOV 밖 조준점 REJECTED(out_of_fov), 잔량·엔티티 변화 없음 | `qa/fov_launch.py` | DEC-066 |
| TC-QA-077 | DEC-066: FOV 경계 근처(44.6°~45.4°) 판정 | `qa/fov_launch.py` | DEC-066 |
| TC-QA-078 | DEC-071·072: VI 4종과 MA_PositionReport 외부 수신, XSD 통과, 종류별 개수 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-071, DEC-072, DEC-068 |
| TC-QA-079 | DEC-072: MA_PositionReport 위치와 같은 시각 기체 상태 비교 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-072 |
| TC-QA-080 | DEC-073: 고장 주입·해제 때 SystemStatus 변화의 외부 전달 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-073, DEC-071, DEC-047 |
| TC-QA-081 | DEC-071: 외부 hold·return_to_base에 대한 MA_FlightCommandStatus 변화의 외부 전달 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-071, DEC-068 |
| TC-QA-082 | DEC-071: GCS 링크 차단 시 VI 외부 발행 감소, 해제 시 회복 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-071, DEC-009 |
| TC-QA-083 | D-27·O-13: `--no-multicast` 기동, 준비 완료 로그 뒤 명령 전달 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-068 |
| TC-QA-084 | TC-QA-069 재판정: VI·C2·P2P·MS 외부 수신 | `qa/gw_integ.py` + `qa/gw_vi.py` | DEC-068, DEC-071 |
| TC-QA-085 | D-28: flocking에서 FlightCommandStatus가 command_id별 역행·반복 없이 EXECUTING 유지 | `qa/gw_integ.py` + `qa/gw_fcs.py` | DEC-071 |
| TC-QA-086 | D-28 회귀: waypoint 외부 hold·return_to_base 때 이전 명령 취소, 새 명령 수락 | `qa/gw_integ.py` + `qa/gw_fcs.py` | DEC-071, DEC-068 |
| TC-QA-087 | TC-QA-081 재판정 | `qa/gw_integ.py` + `qa/gw_fcs.py` | DEC-071 |
| TC-QA-088 | VI 외부 수신·XSD 유지 | `qa/gw_integ.py` + `qa/gw_fcs.py` | DEC-071, DEC-072 |
| TC-QA-089 | DEC-076: 외부 MA_RoutePlan → tx/mp → DELIVERED, waypoint 기체가 항로 비행 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076, DEC-068 |
| TC-QA-090 | DEC-076: 외부 MA_MissionPlan이 move_to·route로 펴지고 waypoint·flocking이 수행 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076 |
| TC-QA-091 | DEC-076: 같은 plan_id 재전송 중복 없음, 새 plan_id는 교체 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076 |
| TC-QA-092 | DEC-076: 다른 기체 대상 계획의 영향 없음 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076, DEC-013 |
| TC-QA-093 | DEC-076: 지원 범위 밖 입력·XSD 위반 거부, Gateway 계속 동작 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076, DEC-068 |
| TC-QA-094 | DEC-075: 외부 승인 응답 → tx/c2/ApprovalResponse → DELIVERED, 외부 재발행 없음 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-075 |
| TC-QA-095 | DEC-077: publisher로 Gateway·UI 봉투 구분 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-077 |
| TC-QA-096 | DEC-076: GCS 링크 차단 시 DROPPED, 해제 후 재전송 도달 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076, DEC-009 |
| TC-QA-097 | VI·C2·P2P·MS 외부 수신과 XSD 회귀 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-071, DEC-072 |
| TC-QA-098 | D-29: RoutePlan·MissionPlan 연속 전송이 항로점 1·2개 모두 COMPLETED | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076 |
| TC-QA-099 | O-26: 단독 RoutePlan 뒤 이전 작업 CANCELLED(preempted) | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076 |
| TC-QA-100 | O-23: task-001 ACCEPTED → EXECUTING 순서, 프레임 0 지연 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-039, DEC-071 |
| TC-QA-101 | lockstep 프레임 0 처리와 같은 시드 재현 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-039, DEC-005 |
| TC-QA-102 | UI·Gateway 발행 전달 지연 유지 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-077 |
| TC-QA-103 | TC-QA-090 재판정 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076 |
| TC-QA-104 | 차단 해제 뒤 RoutePlan 재전송, Gateway를 둔 lockstep | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-076, DEC-009 |
| TC-QA-105 | 외부 수신·XSD 회귀 | `qa/gw_plan.py` + `qa/gw_ext_client.py` | DEC-071, DEC-072 |
| TC-QA-106 | 같은 시드 lockstep: 첫 SystemStatus 프레임, LinkOutcome, GCS 수신(손실 유무·고장) | `qa/gw_plan.py` | DEC-039, DEC-005 |
| TC-QA-107 | 실행 중 SystemStatus가 바뀌는 조건의 같은 시드 비교 | `qa/gw_plan.py` | DEC-039, DEC-071 |
| TC-QA-108 | 임무장비 출력·Detection 시나리오의 같은 시드 비교 | `qa/gw_plan.py` | DEC-039, DEC-051 |
| TC-QA-109 | `late_onboard` 경고 발생 여부(50기 포함) | `qa/gw_plan.py` | DEC-039 |
| TC-QA-110 | 프레임 0 처리 순서 회귀(TC-QA-100) | `qa/gw_plan.py` | DEC-039, DEC-071 |
| TC-QA-111 | Gateway 외부 수신·XSD 회귀(TC-QA-105) | `qa/gw_plan.py` | DEC-071, DEC-072 |
| TC-QA-112 | Gateway를 둔 lockstep 회귀(TC-QA-104) | `qa/gw_plan.py` | DEC-076, DEC-009 |
| TC-QA-113 | Gateway lockstep 같은 시드 재현(외부 입력 없음) | `qa/gw_plan.py` | DEC-039, DEC-068 |
| TC-QA-114 | 100대 lockstep 최대 배속: Logger 끔·켬, MA hold, 비용 사다리 | `qa/perf_p1.py` | DEC-079, OPN-067 |
| TC-QA-115 | 프레임 시간 분해(Core·Datalink·Agent·대기), Agent 프로파일 | `qa/perf_p1.py`, `qa/perf_agent.py` | DEC-079, OPN-067 |
| TC-QA-116 | 프레임당 메시지 수와 종류(버스 전체, Agent 입출력) | `qa/perf_p1.py` | DEC-079, OPN-067 |
| TC-QA-117 | CPU 코어 사용량과 GIL 포화 판단 | `qa/perf_p1.py` | DEC-079, OPN-067 |
| TC-QA-118 | 선택지별 예상 배속(Agent 분할 실측, 나머지 추정) | `qa/perf_p1.py` | DEC-079, OPN-067 |
| TC-QA-119 | 기본 정책 `GCS_LINK_CUT`: 약 5 s 뒤 선회, 복구 뒤 유지, 새 명령으로 종료 | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-120 | 기본 정책 재밍 구역 진입(GCS 재밍) | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-121 | `RESUME_ON_RECOVERY`: 복구 시 중단 작업 재개 | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-122 | `CONTINUE`: 두절·복구와 무관하게 작업 지속 | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-123 | 정책 지정 경로·우선순위, MA별 동작 | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-124 | 한 기체 두절의 다른 기체 영향 | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-125 | lockstep 같은 시드 재현성(Heartbeat·불완전 링크·두절·재밍) | `qa/p2_lostlink.py` | DEC-078 |
| TC-QA-126 | Heartbeat 유입 뒤 기존 시나리오 영향 | `qa/p2_lostlink.py` | DEC-078 |

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
| TC-QA-037 | 원인 확인 | 2026-11-06 | 0 지연 전달(rx_time = T(k-1))을 Datalink가 틱 k에 내어 Agent 소비 프레임이 벽시계에 따라 갈린다. WP4 Datalink, 계약 보완 WP0 (QA-019, D-18) |
| TC-QA-038 | 통과 | 2026-11-06 | GCS가 SensorActivity 147,976건·StrikeActivity 53건 수신. UI FOV 표시, 발사 뒤 렌더링 유지. QA-020 해소, QA-023 수정 확인 |
| TC-QA-039 | 통과 | 2026-11-06 | 고장 두절 13.3 s 동안 수신 0, 해제 뒤 0.02 s에 재수신. 거리 초과 뒤 수신 0. 재밍은 수신자 기준이라 업링크는 안 끊김(D-19) |
| TC-QA-040 | 통과 | 2026-11-06 | 6회 모두 수신 순서·프레임·본문 동일. 송신 프레임 - onboard 프레임 = 1 |
| TC-QA-041 | 통과 | 2026-11-06 | 24회 모두 궤적 한 무리, MA 입력·LinkOutcome·이벤트(seq 맞춤) 차이 0. 0 지연 전달 0, 최소 지연 20 ms. QA-019 해소 |
| TC-QA-042 | 통과 | 2026-11-06 | 늦은 구독자 지연 0.22~0.96 s, 주기 1.0 s. KILL 뒤 꺼짐 1건, 그 뒤 붙은 구독자·UI 새로 고침에는 구역 없음. QA-021 해소 |
| TC-QA-043 | 통과 | 2026-11-06 | 기체당 SensorActivity 10.0 msg/s(간격 0.1 s), 약 1.47 kB/s. 변경 전 50 msg/s, 7.36 kB/s |
| TC-QA-044 | 통과 | 2026-11-06 | 재시험(1decbcb): 설악·한라 kill 3건이 DEM 기대값과 같고 격자 밖 0 m. DEM 아래 시작 uav-004(시작 DEM 820.0 m)는 경고 후 시작 프레임 kill(DEC-060). QA-022·024 해소. 첫 실행은 부분 통과 |
| TC-QA-045 | 통과 | 2026-11-06 | 재시험(1decbcb): 함께 주면 경고 후 DEM 사용(DEC-061). 없는 파일 rc 1. QA-025 해소. 첫 실행은 불합격 |
| TC-QA-046 | 통과 | 2026-11-06 | 3회 궤적·MA 입력·LinkOutcome·이벤트(seq 맞춤, spawn 포함) 차이 0. 0 지연 전달 0. Core·Datalink RSS 증가 없음, Agent 뒤 절반 +1 MB 미만 |
| TC-QA-047 | 통과 | 2026-11-06 | 재시험(80a1cda, r12L): 발사·도달 변경 보고, 비행 중만 1 s 주기, 도달 뒤 주기 없음(수신 46→11건). SensorActivity 10 Hz 유지 |
| TC-QA-048 | 통과 | 2026-11-06 | 2 Hz 간격 0.5 s, 50 Hz·0 간격 0.02 s(매 틱), 기본 10 Hz 간격 0.1 s |
| TC-QA-049 | 통과 | 2026-11-06 | 재시작 뒤 0.80~0.88 s 안에 재두절, 그 뒤 구역 안 전달 0. 재시작 직후 전달 48·80건(O-6) |
| TC-QA-050 | 정리 | 2026-11-06 | frame 0 단발 truth 이벤트는 jam_zone뿐(재발행). 현재 영향 없음 |
| TC-QA-051 | 통과 | 2026-11-06 | 내장 GPU headless 38~86 FPS, 실패 요청 0, 콘솔 404 1건(favicon 추정). 출처 표기 2건 확인 |
| TC-QA-052 | 통과 | 2026-11-06 | 설악·한라 정상부 차폐 센서 각 2기 Detection 0(여유 −45.4·−0.29, −58.9·−0.41 m), 고도 상향·이동 센서 각 3기 300/300. 14쌍 Python 기대와 일치 |
| TC-QA-053 | 통과 | 2026-11-06 | 평지 0 m에서 14쌍 모두 300/300, 거리 Core = Python |
| TC-QA-054 | 통과 | 2026-11-06 | 50 m 표본 경계 고도 ±1 m 판정이 Python과 같다. 경계가 5 m 표본보다 1.23·2.98 m 낮다(O-8). 끝점 허용은 판정에 관여하지 않음 |
| TC-QA-055 | 통과 | 2026-11-06 | 재시험(80a1cda): 빠진 변화 0. 상한이 늦춘 것은 같은 거부 키의 REJECTED 1건(100 ms 뒤 최신 값, 지연 140 ms). 키별 마지막 상태 전달 |
| TC-QA-056 | 통과 | 2026-11-06 | 재시험(80a1cda, DEC-063): 같은 프레임 LAUNCHED w04가 0·10 Hz 모두 7.26 s 도착, LAUNCHED w02도 도착. QA-026 해소. 첫 실행은 부분 통과 |
| TC-QA-057 | 통과 | 2026-11-06 | 주기 틱 13개 모두 보낸 키 = 비행 중 무장, 종료 키 재보고 0. 같은 키 최소 간격 100 ms, 다른 무장 키는 0~40 ms. GCS 수신 102→40건 |
| TC-QA-058 | 통과 | 2026-11-07 | 프레임 249 MISSED expired, 10·0 Hz lockstep과 realtime 모두 GCS 1건(5.04 s), 6 s 틱부터 빠짐. 종료 키 재보고 0 |
| TC-QA-059 | 통과 | 2026-11-07 | 프레임 361 w02 IMPACT 살상에 w03 포함, w03 MISSED destroyed 1건(7.26 s), 이후 빠짐. 표적 소멸 뒤 w04는 마지막 위치로 IMPACT(O-11) |
| TC-QA-060 | 통과 | 2026-11-07 | 발사 판정은 DEM 가시선 사용(−0.285 m lock_failed, +0.312 m LAUNCHED). 조준점 발사·비행 중 탐색기는 가시선 미사용, 능선 지면 충돌. D-24, O-10 |
| TC-QA-061 | 통과 | 2026-11-07 | realtime 10 Hz: 변화 12건 모두 도착(25~45 ms), 같은 키 미룸 1건 121 ms, 다른 무장 키 0~40 ms, 수신 40건, overrun 0 |
| TC-QA-062 | 통과 | 2026-11-07 | 1 s 창 51변화: 10 Hz·realtime 100 ms 간격 11건, 0 Hz 20 ms 51건. 마지막 상태 전달 |
| TC-QA-063 | 통과 | 2026-11-07 | 9쌍 모두 허용 0.5 m 기대와 일치, 허용 0과 다른 4쌍(A1·A2·A3 AGL 0, B1 AGL 0.6) 보임 |
| TC-QA-064 | 통과 | 2026-11-07 | 7,909.7 m, 경계 4.8429 m(허용 0.5)·4.8737 m(허용 0). 사이 고도 4.858 m 보임, 3고도 모두 일치 |
| TC-QA-065 | 통과 | 2026-11-07 | hill: 기대 T 101–159, C 160–306, T 307–754와 재계산 상태 651프레임 일치(불일치 0). 표적까지 1.62 m 도달 |
| TC-QA-066 | 통과 | 2026-11-07 | edge: T→C→T→C→T 4회 전환 모두 같은 프레임(여유 −0.005 m 포함), 두 번째 고정점은 직전 T 프레임 표적 위치. 표적 도달 |
| TC-QA-067 | 통과 | 2026-11-07 | flat 내내 T(648프레임), coord 내내 조준점 유도(635프레임), 조준점까지 1.76 m |
| TC-QA-068 | 통과 | 2026-11-07 | hill·edge 각 2회: 궤적·이벤트·StrikeActivity 모두 일치 |
| TC-QA-069 | 통과(TC-QA-084로 재판정) | 2026-11-08 | 15차는 부분 통과(VI 0건, D-26). 16차에서 VI 수신 확인 |
| TC-QA-070 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-071 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-072 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-073 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-074 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-075 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-076 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-077 | 통과 | 2026-11-08 | msvc-debug, Zenoh 1.10.2, agra_lacal 45274ce |
| TC-QA-078 | 통과 | 2026-11-08 | r2: 12,986건 XSD 통과, 기체당 1 Hz 기대값과 일치 |
| TC-QA-079 | 통과 | 2026-11-08 | 항법 잡음 0 조건. 변환 오차 0 m |
| TC-QA-080 | 통과 | 2026-11-08 | DEGRADED·OPERATIONAL 전환, 약 70 ms |
| TC-QA-081 | 통과(TC-QA-087로 재판정) | 2026-11-09 | 16차는 조건부 통과(D-28). 17차에서 재판정 |
| TC-QA-082 | 통과 | 2026-11-08 | 초당 5.0 → 2.9 → 0 → 5.0건 |
| TC-QA-083 | 통과 | 2026-11-08 | 다른 버스와의 격리 시험은 안 함 |
| TC-QA-084 | 통과 | 2026-11-08 | 13종 중 9종 발행, 발신자 없는 4종 남음 |
| TC-QA-085 | 통과 | 2026-11-09 | 통합 실행, 역행 0, 마지막 상태 EXECUTING |
| TC-QA-086 | 통과 | 2026-11-09 | §24와 같은 흐름 |
| TC-QA-087 | 통과 | 2026-11-09 | 기대값은 `docs/21_qa_report.md` §25.5 |
| TC-QA-088 | 통과 | 2026-11-09 | §24 수준 유지 |
| TC-QA-089 | 통과 | 2026-11-09 | 항로점 3개 최소 거리 26 m 안팎 |
| TC-QA-090 | 통과(TC-QA-103으로 재판정) | 2026-11-10 | 18차는 조건부 통과(D-29). 19차에서 재판정 |
| TC-QA-091 | 통과 | 2026-11-09 | 외부 MA_TaskStatus까지 일치 |
| TC-QA-092 | 통과 | 2026-11-09 | 대조 2대 MP 수신 0 |
| TC-QA-093 | 통과 | 2026-11-09 | 범위 밖 9건 기록, XSD 위반 3건 -ERR |
| TC-QA-094 | 통과 | 2026-11-09 | 승인 요청은 QA 주입 |
| TC-QA-095 | 통과 | 2026-11-09 | rx와 MCAP. UI는 시험 클라이언트로 대체 |
| TC-QA-096 | 통과 | 2026-11-09 | FAULT_INJECTED |
| TC-QA-097 | 통과 | 2026-11-09 | 13,064건 XSD 통과 |
| TC-QA-098 | 통과 | 2026-11-10 | 각 8/8, 16쌍 중 8쌍이 MissionPlan 먼저 도착, lockstep 8/8 |
| TC-QA-099 | 통과 | 2026-11-10 | 외부 CANCELED |
| TC-QA-100 | 통과 | 2026-11-10 | waypoint 4대. flocking은 O-28 |
| TC-QA-101 | 통과(TC-QA-106으로 재판정) | 2026-11-10 | 19차는 조건부 통과(D-30). 20차에서 재판정 |
| TC-QA-102 | 통과 | 2026-11-10 | 시각 0 처리 0건. UI는 시험 클라이언트 |
| TC-QA-103 | 통과 | 2026-11-10 | flocking 2점은 설계대로 REJECTED |
| TC-QA-104 | 통과 | 2026-11-10 | 외부 입력 32건 발행 |
| TC-QA-105 | 통과 | 2026-11-10 | 13,067건 XSD 통과 |
| TC-QA-106 | 통과 | 2026-11-10 | noloss·loss·고장 각 8회 동일. D-30 해소 |
| TC-QA-107 | 통과 | 2026-11-10 | 변화 시각 8회 동일 |
| TC-QA-108 | 통과 | 2026-11-10 | 4개 시나리오 5~8회 동일 |
| TC-QA-109 | 통과 | 2026-11-10 | 경고 0건. 실제로 세어지는 경우의 통합 동작은 미확인 |
| TC-QA-110 | 통과 | 2026-11-10 | waypoint 4대 순서 유지 |
| TC-QA-111 | 통과 | 2026-11-10 | 13,070건 XSD 통과 |
| TC-QA-112 | 통과 | 2026-11-10 | 기준선 변화는 IMP-AGT-036의 의도된 결과 |
| TC-QA-113 | 통과 | 2026-11-10 | 5회 공통 구간 동일. 외부 입력이 있는 구성은 재현 대상 아님 |
| TC-QA-114 | 측정 | 2026-11-10 | 3-DoF 100대 waypoint 1.0배(P 고정 1.7배), flocking 0.27배(0.45배). 판정 아님 |
| TC-QA-115 | 측정 | 2026-11-10 | waypoint는 ControlOutput put 30%, flocking은 MA 59%. 프레임의 끝은 Agent가 98% 이상 정함 |
| TC-QA-116 | 측정 | 2026-11-10 | waypoint 314건/프레임, flocking 2,330건/프레임 |
| TC-QA-117 | 측정 | 2026-11-10 | flocking은 GIL 포화, waypoint는 프레임의 70% |
| TC-QA-118 | 측정 | 2026-11-10 | 4분할 2.76배 실측, 일괄화+FA C++ 약 11배 추정. 8분할은 D-31로 측정 불가 |
| TC-QA-119 | 통과 | 2026-11-10 | 상실은 마지막 Heartbeat 수신 후 5.06 s, 선회 반경 312 m, 130 s 새 명령으로 종료 |
| TC-QA-120 | 통과 | 2026-11-10 | 상실은 마지막 수신 후 5.06 s, 새 명령까지 선회 유지. GCS만 덮는 구역은 상실 없음 |
| TC-QA-121 | 통과 | 2026-11-10 | 지정 3경로와 항로 모두 복구 직후 재개. 작업 없는 기체는 D-32 |
| TC-QA-122 | 통과 | 2026-11-10 | 지정 3경로와 재밍 통과 모두 상실 없이 지속 |
| TC-QA-123 | 통과 | 2026-11-10 | 작업 정책이 `ma_params`를 앞섬. hold·formation·flocking 확인, 3 s 두절은 상실 아님 |
| TC-QA-124 | 통과 | 2026-11-10 | 독립 기체 궤적·링크 결과 동일. 같은 무리·편대 영향은 O-37 |
| TC-QA-125 | 통과 | 2026-11-10 | 5개 구성 각 5회 LinkOutcome·GCS 수신·상태·궤적 동일 |
| TC-QA-126 | 통과 | 2026-11-10 | 시나리오 3건 `continue` 반영 뒤 `p5_e2e`, `jam_late`, `dl_restart_jam`, TC-QA-039, TC-QA-003·018·024 재실행 통과 (§30.11) |

## 프로세스 결정

| DEC | 적용 범위 |
|---|---|
| DEC-015 | 전체 개발 프로세스: WBS 작업 패키지별 병렬 세션, WP0 계약 우선 |
| DEC-021 | 저장소 구조: 모노레포, WP별 디렉터리, worktree 병렬 작업 |
| DEC-022 | 빌드 환경: MSVC+vcpkg, MSYS2 GCC, Linux/WSL2 GCC 프리셋 병행 (IMP-API-001) |
