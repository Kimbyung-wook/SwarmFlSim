# WP 세션 지시문 (1차: WP1, WP2, WP5, WP7)

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

## 2차 (1차 결과 통합 후)

- WP3 Agent 런타임·알고리즘, WP4 데이터링크, WP6 Traffic Monitor. 지시문은 1차 통합 후 작성한다.
