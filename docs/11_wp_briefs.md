# WP 세션 지시문

- 병렬 세션(DEC-015, DEC-021)을 시작할 때 쓰는 지시문이다. 각 세션은 `wp0-contracts` 브랜치에서 갈라진 자기 worktree에서 작업한다.
- 세션을 열 때 "공통 지시"와 해당 WP 절을 함께 붙여 넣는다.

## 공통 지시

```text
이 저장소는 군집/편대 알고리즘 연구용 군집 UAV 시뮬레이터 모노레포다.
먼저 CLAUDE.md, docs/00_proposal.md(아키텍처, WBS §12), docs/02_registry.md(REQ/PRP/DEC), docs/10_contracts.md(WP0 계약)를 읽는다.

- 시작 전: 현재 브랜치가 refs/heads/wp0-contracts를 포함하는지 git log로 확인한다.
- 자기 WP 디렉터리만 수정한다. proto/, api/, docs/의 계약은 바꾸지 않는다.
  계약 변경이 필요하면 구현하지 말고 최종 보고에 "계약 변경 요청"으로 적는다.
- 동역학·버스·플러그인은 api/의 인터페이스로만 연결한다. 다른 WP의 내부 구현에 의존하지 않는다.
  다른 WP가 아직 없으면 자기 디렉터리 안의 목(mock)과 InMemoryBus로 시험한다.
- C++ 빌드(MSVC): 일반 셸에 cl이 없으므로 다음 형태로 실행한다.
  cmd /c "call \"<VS설치경로>\VC\Auxiliary\Build\vcvars64.bat\" && cmake --preset msvc-debug && cmake --build --preset msvc-debug && ctest --preset msvc-debug"
  설치 경로: "%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath
- Python: uv sync, uv run python scripts/gen_proto.py, uv run pytest
- 구현 항목에 IMP-<모듈>-NNN, 시험에 TC-<모듈>-NNN을 붙이고 근거 REQ/DEC를 연결한다.
  docs/03_traceability.md는 수정하지 않고, 자기 디렉터리의 TRACE.md에 IMP/TC 표(ID, 내용, 위치, 근거, 시험 결과)를 쓴다.
- 커밋 메시지에 ID를 적는다. 예: "IMP-CORE-001: 프레임 스케줄러 (REQ-SIM-002, DEC-005)". 자기 worktree 브랜치에만 커밋하고 push하지 않는다.
- 한국어로 응답한다. 문서는 markdown, 다이어그램은 mermaid.
- 최종 보고: 브랜치 이름, 시험 결과, 계약 변경 요청(있으면).
```

## WP1 Sim Core — `core/`

```text
WP1 Sim Core를 core/에 구현한다 (로드맵 P0 우선). 모듈 코드 CORE.

1. swarm::Bus(api/cpp/include/swarm/api/bus.hpp)의 Zenoh 백엔드 ZenohBus. zenoh-cpp(zenoh-c 백엔드).
   vcpkg.json dependencies 추가와 docs/10_contracts.md §7.2의 Zenoh 설치 방법(MSVC+vcpkg, MSYS2, Linux) 추가는 허용한다.
2. 프레임 스케줄러: 50–100 Hz 고정 프레임, REALTIME / LOCKSTEP(sim/clock/done/<participant> 장벽, 시드 고정) / FREERUN.
   sim/clock/tick 발행, sim/ctrl/cmd 처리, sim/ctrl/status 발행 (DEC-005, REQ-SIM-002).
3. 엔티티 저장소(SoA)와 truth/state(TruthFrame) 발행. 동역학은 dynamics.hpp의 DynamicsModel/Integrator로만 호출하고,
   시험에는 core/ 안의 등속 2-DoF 목 모델을 쓴다 (DEC-006).
4. onboard/<id>/ControlOutput 구독 → 동역학 입력, onboard/<id>/NavigationReport 발행 (잡음 훅만 둔다).
5. 실행 파일 swarm_core. WP7 완성 전까지 최소 시나리오 파싱 또는 내장 시나리오 허용.
6. InMemoryBus 기반 단위 시험: 모드별 프레임 진행, lockstep 장벽, 일시정지·배속·스텝, truth 발행. CTest 등록.

완료 기준: msvc-debug 빌드·CTest 통과, swarm_core가 tick·truth 발행, core/TRACE.md, 커밋.
```

## WP2 동역학 — `dynamics/`

```text
WP2 동역학을 dynamics/에 구현한다 (로드맵 P0–P1). 모듈 코드 DYN.

1. api/cpp/include/swarm/api/dynamics.hpp의 DynamicsModel 구현:
   2-DoF(KinematicCmd: speed, heading_rate, climb_rate), 3-DoF 질점 협조선회(KinematicCmd: speed, bank, climb_rate) (REQ-DYN-001, PRP-DYN-001).
   위치는 WGS84 위경도·고도, 속도는 NED (docs/10_contracts.md §2). 2/3-DoF의 자세 쿼터니언은 속도 방향과 뱅크각으로 만든다.
2. Integrator 구현: RK4 고정 스텝, RK45(Dormand-Prince) 프레임 안 가변 스텝(허용오차 설정), EventFn 영점 교차를 이분법으로 찾아 그 시점에서 멈춤 (DEC-005, REQ-DYN-003/004).
3. Terrain 구현: 평지(고정 고도)와 격자 DEM 보간(초기에는 작은 시험 격자. 한반도 저해상도 DEM 로더는 인터페이스만, DEC-016).
4. 모델·적분기 팩토리(이름 → 인스턴스)를 dynamics/ 안에 둔다. 5/6-DoF(Aerosonde)는 이번 범위가 아니며 자리만 둔다.
5. 시험: 해석해 비교(등속, 정상 선회 반경 v²/(g·tanφ)), RK4/RK45 오차 차수, 이벤트 시점 정확도(지면 교차), map_control 형식 불일치 시 false. CTest 등록.

완료 기준: msvc-debug 빌드·CTest 통과, dynamics/TRACE.md, 커밋.
```

## WP5 GCS/UI — `ui/`

```text
WP5 GCS/UI를 ui/에 구현한다 (로드맵 P0: 2D/3D 지도 전시). 모듈 코드 UI. ui/monitor/는 WP6 영역이므로 건드리지 않는다.

1. TypeScript + React + CesiumJS(Vite). Cesium ion 등 외부 서비스에 의존하지 않는다. 오프라인 이미지 타일·quantized-mesh 지형을 로컬 경로에서 읽도록 설정하고, 데이터가 없을 때는 기본 타원체로 동작한다 (DEC-003, DEC-004, DEC-016).
2. protobuf-es(@bufbuild/protobuf)로 proto/swarm/v1을 TS로 생성하는 스크립트(ui/ 안).
3. 데이터 소스 추상화: (a) 목 소스(내장 시나리오로 TruthFrame 생성), (b) 버스 소스 자리(Zenoh 브라우저 연결 방식은 zenoh-ts 또는 WebSocket 브리지 중 조사 후 제안만, 구현은 다음 단계).
4. truth/state 엔티티 전시: 종류·진영별 아이콘, 진행 방향, 궤적 꼬리, 2D/3D 전환 (REQ-UI-001).
5. RTS 선택의 기초: 클릭·드래그 박스 선택, 선택 목록 패널 (REQ-UI-002). 명령 전송은 다음 단계.
6. 카메라 시점 전환(REQ-UI-007)은 구조만 고려한다(엔티티 자세 쿼터니언 사용).
7. 시험: vitest로 데이터 변환·선택 로직 단위 시험. npm 스크립트 dev/build/test.

완료 기준: npm run build·test 통과, 목 소스로 20대 이상 이동 전시, ui/TRACE.md, 커밋.
```

## WP7 시나리오·기록 — `scenario/`, `logger/`

```text
WP7 시나리오·기록을 scenario/(Python)와 logger/(C++)에 구현한다. 모듈 코드 SCN, LOG.

1. scenario/: 시나리오 JSON Schema(엔티티 목록 = proto EntitySpec 필드, 맵 원점·범위, 프레임 Hz, 실행 모드, 시드, 임무 계획 MissionPlan, 교전 기준 EngagementCriteria) (REQ-CFG-001/002, PRP-CFG-001).
   검증기, JSON → proto(EntitySpec 등) 변환기, 예제 시나리오(고정익 20대 + GCS 1 + 지상 표적 몇 개, 한반도 내 좌표).
   uv workspace 패키지로 만들고, 루트 pyproject.toml의 [tool.uv.workspace] members에 "scenario"를 추가하는 것만 허용한다.
2. logger/: swarm::Bus의 모든 키를 구독해 MCAP으로 기록하는 C++ 라이브러리와 실행 파일. MCAP 채널은 Zenoh 키와 1:1, 스키마는 protobuf 디스크립터 (DEC-011, PRP-LOG-001).
   재생기: MCAP을 읽어 원래 시각 간격(배속 지원)으로 버스에 다시 발행. MCAP C++ 라이브러리 의존성은 vcpkg.json dependencies 추가를 허용한다.
3. 시험: pytest(스키마 검증 성공·실패, 변환), CTest(InMemoryBus로 기록 → 재생 결과 일치).

완료 기준: pytest·CTest 통과, scenario/TRACE.md, logger/TRACE.md, 커밋.
```

# 2차 (계약 0.2.0, 로드맵 P0 데모 + P1·P2 착수)

- 공통 지시는 1차와 같다. 추가 사항:
  - 기준 브랜치는 `wp0-contracts`(계약 0.2.0)다. 버스는 반드시 `open_bus`로 연다 (DEC-026, C++ `bus/`, Python `swarm_api.open_bus`).
  - 실행 파일은 공통 버스 옵션(`--bus`, `--connect`, `--listen`, `--zenoh-mode`, `--no-multicast`)을 받는다.
  - Zenoh는 C++ `CMAKE_PREFIX_PATH=C:/dev/zenoh`(빌드 시 `-DCMAKE_PREFIX_PATH=C:/dev/zenoh`), Python은 `uv sync`로 설치된다.
  - lockstep 참여 프로세스는 `sim/clock/tick`마다 처리를 끝낸 뒤 `sim/clock/done/<participant>`에 `FrameDone`을 보낸다. 참여자 ID는 명령행 `--participant`로 받는다.
  - 이미 TRACE.md가 있는 디렉터리는 기존 ID 뒤 번호를 이어서 쓴다.

## WP1-2 Core 통합 — `core/`

```text
WP1 Core에 WP2 동역학을 붙이고 P0 데모에 필요한 Core 기능을 마무리한다. 모듈 코드 CORE (IMP-CORE-008부터).

1. swarm_core의 DynamicsProvider를 목 모델에서 dynamics/ 팩토리(swarm_dynamics)로 바꾼다.
   DynamicsKind·airframe → 모델, 적분기는 기본 rk45(명령행 --integrator rk4|rk45). 목 모델은 시험용으로 남긴다 (DEC-005).
2. 지면 충돌: make_ground_event를 적분기 EventFn으로 넘기고, 교차하면 엔티티를 죽이고 truth/event/kill(cause=ground)을 발행한다.
   지형은 우선 평지(고도 0 m), 명령행 --terrain-flat <m>. DEM 로더는 WP2 인터페이스만 있으므로 연결 자리만 둔다 (DEC-004, DEC-016).
3. DYNAMICS_KIND_SCRIPTED: EntitySpec.script_path를 일정 속도로 따라가는 스크립트 이동(적·표적 기본, DEC-017). 속도는 initial 속도 크기.
4. InjectFault: LINK_CUT·GCS_LINK_CUT은 Core가 처리하지 않는다(WP4 담당)는 것을 명시하고 무시, ENGINE(추력 0 → 속도 명령 최소), NAV(NavigationReport 중단), SENSOR(자리만)을 처리한다.
5. 시험: WP2 모델로 20대 lockstep 결정론, 지면 충돌 kill 이벤트, 스크립트 경로 추종, 고장. CTest.

완료 기준: msvc-debug 빌드·CTest 통과, swarm_core가 실제 2/3-DoF 모델로 동작, core/TRACE.md 갱신, 커밋.
```

## WP3 Agent 런타임·기본 알고리즘 — `agent/`, `algorithms/`

```text
WP3 Vehicle Agent를 구현한다 (로드맵 P0–P1). 모듈 코드 AGT. Python 패키지로 만들고 루트 pyproject.toml의 workspace members·dev 그룹·testpaths에 추가하는 것만 허용한다.

1. agent/: 실행 파일 swarm-agent. 한 프로세스가 여러 기체를 호스팅한다.
   - sim/ctrl/cmd의 LoadScenario.scenario를 받아, AutonomySpec이 있는 기체(또는 --entities로 지정한 기체)를 맡는다. 런타임은 sim/ctrl을 읽을 수 있지만 MA 플러그인에는 노출하지 않는다 (DEC-013, DEC-014).
   - 구독: sim/clock/tick, onboard/<id>/NavigationReport·Detection·*Activity, swarm/<id>/rx/**(LinkEnvelope를 풀어 포트 inbox로)
   - 발행: onboard/<id>/ControlOutput·*Command, swarm/<id>/tx/<iface>/<msg>(LinkEnvelope, dst는 C2 송신이면 controlling_gcs)
   - L1 포트(api/python/src/swarm_api/ports.py) 구현, AgentContext(ctx.rng 시드 고정), BatchMissionAutonomy 일괄 호출, lockstep FrameDone.
   - 플러그인 로딩: entry point swarm.ma / swarm.fa, AutonomySpec의 이름·params.
2. 기본 FA(swarm.fa "default"): FlightCommand(HSA, Waypoint, Orbit) → 2/3-DoF용 KinematicCmd. 상태 보고(FlightCommandStatus).
   FA 기본안은 우선 Python으로 만들고, C++ 이식 여부는 성능 측정 뒤 정한다(최종 보고에 측정값).
3. algorithms/: 기본 MA 플러그인
   - "hold"(현재 상태 유지), "waypoint"(MissionPlan·TaskCommand MoveTo 수행)
   - "formation": FormationCommand(LINE/COLUMN/WEDGE/ECHELON/CIRCLE/CUSTOM) leader-follower, PeerStatus를 P2P로 주고받아 리더 상대 위치 유지 (PRP-BHV-003)
   - "flocking": Reynolds(분리·정렬·응집), BatchMissionAutonomy로 구현
4. 시험: InMemoryBus에 가짜 Core(NavigationReport를 적분하는 간단한 모델)와 가짜 Datalink(tx→rx 즉시 전달)를 붙여, 편대가 수렴하는지, 기체가 truth/** 를 받지 않는지, lockstep FrameDone, 결정론을 확인한다.

완료 기준: uv run pytest 통과, swarm-agent가 Zenoh로 swarm_core와 함께 동작(수동 확인 결과 기록), agent/TRACE.md·algorithms/TRACE.md, 커밋.
```

## WP4 데이터링크 — `datalink/`

```text
WP4 Datalink Emulator를 C++로 구현한다 (로드맵 P2). 모듈 코드 LNK.

1. 실행 파일 swarm_datalink: swarm/*/tx/** 를 구독해 링크 모델을 적용하고 swarm/<dst>/rx/<iface>/<msg>로 전달한다. dst가 비면 링크가 닿는 모든 엔티티(브로드캐스트).
   위치는 truth/state, 재밍 영역은 truth/event/jam_zone, 엔티티 목록·링크 프로파일은 LoadScenario.scenario에서 얻는다(데이터링크는 시뮬레이터 기반 요소라 truth를 읽을 수 있다).
2. 링크 모델 (PRP-LNK-001): 자유공간 경로손실 기반 최대 거리·SNR, DEM 가시선(dynamics/의 Terrain 인터페이스, 우선 평지), Gilbert-Elliott 버스트 손실, 지연·지터, 토큰 버킷 대역폭 큐, 재밍 영역 안 100% 손실(DEC-009).
   EntitySpec.link_profile 이름 → 프로파일(공개 일반값, 코드 내 표 + 시나리오 재정의는 다음 단계).
3. 메시지마다 link/outcome/<src>/<dst>(LinkOutcome, 손실 사유), 주기적으로 link/state/<a>/<b>(LinkState) 발행 (PRP-LNK-002, REQ-UI-005).
4. 시간: sim/clock/tick 기준으로 지연 큐를 진행한다. lockstep에서는 시드 고정 결정론, FrameDone 발행.
5. sim/ctrl/cmd의 InjectFault LINK_CUT(대상의 모든 링크), GCS_LINK_CUT(대상↔GCS)을 처리한다 (REQ-LNK-002, REQ-LNK-003).
6. 시험: InMemoryBus로 거리 밖 손실, 가시선 차단, 재밍 영역 손실, GE 버스트 통계, 지연 분포, 대역폭 초과 큐 손실, 고장 주입, 결정론. CTest.

완료 기준: msvc-debug 빌드·CTest 통과, datalink/TRACE.md, 커밋.
```

## WP5 브리지·UI 버스 연동 — `bridge/`, `ui/`

```text
WP5 2차: WebSocket 브리지와 UI 실버스 연동, 명령 전송을 구현한다. 모듈 코드 UI(브리지는 IMP-UI 번호를 이어 쓴다). ui/monitor/는 WP6 영역이므로 건드리지 않는다.

1. bridge/: Python 패키지(swarm-bridge, websockets + swarm_api.open_bus). docs/10_contracts.md §3.5 "브리지 프로토콜 v1"을 그대로 구현한다(DEC-027).
   클라이언트별 구독·max_hz 다운샘플, 발행 허용 키 검사, 여러 클라이언트 동시 접속(DEC-020). 루트 pyproject.toml workspace members·dev 그룹·testpaths 추가만 허용.
   프로토콜을 바꿔야 하면 구현하지 말고 "계약 변경 요청"으로 보고한다.
2. ui/: BusTransport를 브리지 WebSocket으로 구현하고, 목 소스와 버스 소스를 화면에서 고를 수 있게 한다.
3. 명령 전송: 툴바의 일시정지·재개·스텝·배속은 sim/ctrl/cmd. 선택한 기체에 MoveTo(지도 우클릭), Hold, RTB TaskCommand, 편대 지정 FormationCommand, 부대 그룹 지정·호출(Ctrl+숫자, GroupAssignment)을 swarm/<gcs>/tx/c2/<msg> LinkEnvelope로 보낸다 (REQ-UI-002~004).
   UI는 데이터링크를 거쳐 돌아오는 swarm/<gcs>/rx/** 의 TaskStatus 등을 표시하고, 지도 전시는 truth/state를 쓴다.
4. 시험: pytest(브리지 프로토콜, 허용 키, 다운샘플, 다중 클라이언트), vitest(프레임 인코딩, 명령 생성).

완료 기준: pytest·npm test·build 통과, UI가 브리지를 통해 swarm_core의 truth를 전시하고 일시정지 명령이 동작(수동 확인 기록), bridge/TRACE.md·ui/TRACE.md, 커밋.
```

## WP6 Traffic Monitor — `ui/monitor/`

```text
WP6 Traffic Monitor를 ui/monitor/에 별도 Vite 앱(자체 package.json)으로 구현한다 (REQ-UI-005, PRP-UI-002). 모듈 코드 MON. ui/의 다른 파일은 수정하지 않는다(코드가 필요하면 복사하지 말고 상대 경로 import로 쓰되, 공용화가 필요하면 최종 보고에 요청).

1. 데이터: 브리지 프로토콜 v1(docs/10_contracts.md §3.5)로 link/outcome/**, link/state/**, swarm/*/tx/**, swarm/*/rx/**, truth/state(엔티티 종류)를 구독한다. 브리지가 아직 없을 때를 위해 같은 형식의 목 소스(LinkOutcome 생성기)를 둔다.
2. 화면: 엔티티 트리(비행체/지상체, 진영별), 엔티티별 송수신 통계(빈도·크기·지연·손실률, 손실 사유별: 재밍·가시선·거리·버스트·큐·고장), 시퀀스 타임라인(src→dst 화살표, 손실 표시), 메시지 echo(protobuf 해석, protobuf-es), 필터(엔티티·인터페이스·메시지 타입·결과).
3. MCAP 재생 모드는 swarm_logger replay가 버스로 다시 발행하므로 같은 화면을 쓴다. 재생 중 표시만 구분한다.
4. 시험: vitest(집계기, 필터, 프레임 해석). 20대 × 50 Hz 수준 부하에서 집계가 밀리지 않는지 측정해 기록한다.

완료 기준: npm test·build 통과, 목 소스로 화면 동작, ui/monitor/TRACE.md, 커밋.
```

## WP8 Payload — `payload/`

```text
WP8 Payload를 payload/에 C++20 정적 라이브러리(swarm_payload)로 구현한다 (DEC-046, PRP-PAY-001, REQ-PAY-001~005, REQ-SIM-001). 모듈 코드 PAY. core/를 포함한 다른 WP 디렉터리는 수정하지 않는다. Core 통합은 WP1이 나중에 한다.

1. 인터페이스: Core가 프레임마다 한 번 호출하는 순수 계산기로 만든다. 입력은 프레임 번호·sim 시각·dt, 엔티티 상태(ID, 종류, 진영, 위치·속도·자세, alive, 활성 고장), 시나리오의 PayloadSpec, 이번 프레임에 받은 SensorCommand·JammerCommand·StrikeCommand, 가시선 판정 콜백(swarm/dyn/terrain.hpp 지면 모델 사용)이다. 출력은 기체별 Detection·SensorActivity·JammerActivity·StrikeActivity·StoreLoadout, 생성할 무장 엔티티(spawn), 무장 엔티티의 다음 상태, Launch·Impact·Kill·JamZone 이벤트다. 벽시계와 난수를 쓰지 않고, 같은 입력이면 같은 출력을 낸다(lockstep 결정성). 출력 순서는 엔티티 ID 순으로 고정한다.
2. 센서(PO, DEC-018): 카메라 FOV(hfov·vfov, 짐벌 지향 GimbalPointing), 최대 거리, DEM 가시선만으로 판정한다. 확률은 넣지 않는다. SENSOR 고장 중에는 Detection을 만들지 않고 active=false로 보고한다(DEC-047).
3. 재머(EA, DEC-009): 기체 탑재 재머(JammerCommand enable·radius)와 jammer_site 엔티티가 재밍 구역(Area)을 만든다. 구역이 바뀔 때만 JamZone 이벤트를 낸다(owner, active, area). Datalink가 이 이벤트로 JAMMED를 판정한다.
4. 무장(Strike·Store, DEC-012, DEC-019, PRP-DYN-003): aam_short·agm_short는 질점 + 비례항법, 탐색기 FOV·락온 거리, 추력·연소 시간. fpv는 소형 3-DoF + 종말 유도. StrikeCommand를 받으면 잔량·락온을 확인해 LAUNCHED 또는 REJECTED(reason)를 낸다. 발사체 ID는 wpn-<발사기체>-<순번>. 근접 신관 거리 안에 들거나 지면과 교차하면(교차 시점 보정, DEC-005) 탄착하고, 살상반경 안의 대상을 즉시 파괴한다(DEC-012). 연소·비행 시간이 끝나면 MISSED.
5. 프로파일(DEC-019): 공개 문헌의 일반값으로 payload/profiles/*.json에 camera·jammer·aam_short·agm_short·fpv 기본 프로파일을 둔다. 실제 체계 제원은 넣지 않는다. PayloadSpec.overrides가 프로파일 값을 덮어쓴다.
6. 표적: ground_target·air_target은 Core의 스크립트 이동(DEC-017)을 그대로 쓰고, 이 라이브러리는 탐지·피격 대상으로만 다룬다.
7. 시험: ctest에 등록한다. FOV 경계·거리·가시선 차폐, SENSOR 고장, 재밍 구역 on/off 이벤트, 잔량 0 거부, 락온 실패 거부, PN 도달·빗나감, 지면 탄착, 살상반경 다중 파괴, 같은 입력 2회 동일 출력.

완료 기준: msvc-debug 빌드·ctest 통과, payload/TRACE.md, 커밋. 최종 보고에 WP1 통합을 위한 호출 순서(입력·출력 표)와 계약 변경 요청(키·proto 필드가 부족하면)을 적는다.
```

## WP9 A-GRA Gateway — `gateway/`

```text
WP9 A-GRA Gateway를 gateway/에 Python 3.12(uv) 패키지로 구현한다 (DEC-068, DEC-069, PRP-STD-002, DEC-013, DEC-014, REQ-STD-001). 모듈 코드 GW. gateway/ 밖은 수정하지 않는다. third_party/agra_lacal(서브모듈)은 읽기만 하고 고치지 않는다.

0. 준비: git submodule update --init third_party/agra_lacal. agra_lacal의 README·client·schema를 읽고 LA-CAL 클라이언트 접속 방법과 A-GRA 6.0a 공개 XSD 검증 방법을 확인한다. Distribution D 표기 문서의 내용은 옮기지 않는다. 메시지명은 공개 XSD에서 가져온다.
1. 위치: Gateway는 지상 참여자다. 시나리오의 GCS 엔티티(예: gcs-01) 쪽에서 swarm/<gcs>/rx/** 를 구독한다(UI와 함께 구독해도 된다). truth/**, onboard/**, link/** 는 쓰지 않는다. 버스는 open_bus로 연다(DEC-026).
2. 매핑: proto 메시지 옵션 (uci_name)을 descriptor에서 읽어 내부 메시지 ↔ UCI 메시지 표를 만든다. 하드코딩하지 않는다. 변환기는 상호작용(메시지)별 플러그인으로 둔다(DEC-013). docs/02_registry.md §5 매핑 표의 STD만 외부로 내보내고 EXT는 내보내지 않는다(DEC-014).
3. 1단계(발행): GCS가 받은 VI·C2·P2P·MS 상태(예: 항법 보고, 작업 상태, 센서·재머 활동)를 UCI XML로 바꾸고, XSD 검증을 통과한 것만 LA-CAL로 보낸다. 검증에 실패한 메시지는 보내지 않고 로그와 카운터에 남기며, Gateway는 계속 동작한다.
4. 2단계(수신): LA-CAL에서 받은 외부 C2 명령(STD)을 내부 proto로 바꿔 swarm/<gcs>/tx/c2/<msg> 로 발행한다. Datalink를 거쳐 기체에 간다. 매핑이 없거나 검증에 실패한 명령은 거부하고 기록한다.
5. 시험: uv run pytest. InMemoryBus와 agra_lacal 서버(로컬 기동 또는 목)로 왕복 시험한다. 매핑 표 생성, 상태→XML→XSD 통과, EXT 미발행, 외부 C2→tx 키 발행, 잘못된 XML 거부, truth/** 미구독 확인.
6. 실행: uv run python -m gateway --gcs gcs-01 --lacal <주소> 형태의 진입점과 gateway/README.md(실행·시험 명령).

완료 기준: P6 기준 "VI·C2·P2P 주요 상호작용을 agra_lacal과 교환"을 시험으로 보인다. pytest 통과, gateway/TRACE.md, 커밋. 최종 보고에 내보낸·받은 UCI 메시지 목록과 계약 변경 요청(키·proto·매핑 표가 부족하면)을 적는다.
```
