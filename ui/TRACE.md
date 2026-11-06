# WP5 GCS/UI 추적표

- 1차 브랜치: `wp5-ui` (기준 `wp0-contracts` 94808ba, 계약 0.1.0)
- 2차 브랜치: `claude/wp5-bridge-cce90d` (기준 `wp0-contracts` 8972f55, 계약 0.2.0). 브리지는 `bridge/TRACE.md`(IMP-UI-020~022, TC-UI-010~016)
- `proto/`, `api/`, `docs/`는 바꾸지 않았다.

## 구현 (IMP)

| ID | 내용 | 위치 | 근거 | 시험 |
|---|---|---|---|---|
| IMP-UI-001 | proto/swarm/v1 → TS 생성(protobuf-es, buf CLI는 node_modules) | `scripts/gen-proto.mjs`, `buf.gen.yaml` | REQ-NET-001, DEC-003 | TC-UI-002, TC-UI-008 |
| IMP-UI-002 | Vite 설정: Cesium 정적 자산 복사, `/data/**` 오프라인 데이터 제공(gzip 지형) | `vite.config.ts` | DEC-003, DEC-004, DEC-016 | TC-UI-009 |
| TC-UI-017 | 프레임 바이트 배치(브리지 Python과 같은 벡터)·UTF-8·오프셋·형식 오류, 키 표현식, 제어 프레임 해석, BridgeTransport hello/welcome·구독 전송·키 분배·접속 전 put 거부, 같은 키 공유·주기 상향·해제, 재접속 후 hello·구독 재전송, 첫 접속 실패·hello 거부·프로토콜 불일치(재접속 안 함)·welcome 시간 초과, observer hello, 소스 설정 (11건) | `src/data/bridge.test.ts` | IMP-UI-023, IMP-UI-024, IMP-UI-033 | 통과 |
| TC-UI-018 | MoveTo TaskCommand 봉투(키·dst·iface·msg_type·헤더·seq·task_id·목적지), Hold·RTB·취소·빈 대상, FormationCommand·GroupAssignment(이전 구성원 포함), 그룹 저장소, TaskLog rx 연결·편대/그룹 기록 분리, 목 소스 TaskStatus 응답 (6건) | `src/model/commands.test.ts` | IMP-UI-025~029 | 통과 |
| TC-UI-019 | 수동: swarm_core(main 빌드 msvc-debug, 내장 시나리오 UAV 20 + GCS 1, `--listen tcp/127.0.0.1:17461 --no-multicast`) + `swarm-bridge --port 18765 --connect tcp/127.0.0.1:17461 --no-multicast` + `npm run dev` `?source=bus&bridge=ws://localhost:18765/bus&gcs=gcs-01`. 결과: 연결·적재 표시 → 시작으로 RUNNING, 엔티티 21 전시·이동 / 일시정지 → PAUSED, 2 s 동안 F 513 고정 / 스텝 → F 514 / 재개 → RUNNING / Ctrl+A 20대 선택 후 Hold, 우클릭 MoveTo(36.9696, 127.5056, 1020 m), Alt+1 그룹(grp-1), 쐐기 편대(grp-1, 리더 uav-001, 150 m) → 별도 Zenoh 구독자가 `swarm/gcs-01/tx/c2/{TaskCommand,GroupAssignment,FormationCommand}`를 `application/protobuf;swarm.v1.LinkEnvelope`, dst 20대, 키별 seq로 수신 / 가짜 데이터링크가 `swarm/gcs-01/rx/c2/TaskStatus` 3건 발행 → 명령 목록에 uav-001~003 수행 30/60/90% 표시 / 브리지 종료 → "연결 중", 재기동 → 자동 재접속·truth 재개 / 목 소스 전환 → 32개 | 브라우저 확인 | IMP-UI-011, IMP-UI-022, IMP-UI-024, IMP-UI-025, IMP-UI-027, IMP-UI-030~034 | 통과 |
| IMP-UI-003 | 자세·방향 변환(ZYX 오일러 ⇄ NED→FRD 쿼터니언, NED 속도 → 진행 방향·상승각) | `src/model/attitude.ts` | REQ-UI-001, REQ-UI-007 | TC-UI-001 |
| IMP-UI-004 | TruthFrame → 전시용 엔티티 뷰 | `src/model/entityView.ts` | REQ-UI-001, PRP-SIM-003 | TC-UI-002 |
| IMP-UI-005 | 궤적 꼬리(sim 시각 간격 샘플, 최대 점 수, 되감기 시 초기화) | `src/model/trails.ts` | REQ-UI-001 | TC-UI-003 |
| IMP-UI-006 | RTS 선택 로직(클릭·박스, 아군 기체 우선, replace/add/toggle) | `src/model/selection.ts` | REQ-UI-002, PRP-UI-001 | TC-UI-004 |
| IMP-UI-007 | 카메라 시점 구조(free/chase/fpv/gimbal, 쿼터니언 사용) | `src/model/camera.ts` | REQ-UI-007 | TC-UI-007 |
| IMP-UI-008 | 데이터 소스 추상화(truth/state, sim/ctrl/status 수신, sim/ctrl/cmd 송신) | `src/data/source.ts` | REQ-UI-001, DEC-002 | TC-UI-006, TC-UI-008 |
| IMP-UI-009 | 목 시나리오(UAV 4편대×6, GCS, 지상표적, 공중표적, 재밍기지 = 32개, 해석해·결정론) | `src/data/mockScenario.ts` | REQ-UI-001 | TC-UI-005 |
| IMP-UI-010 | 목 데이터 소스(실시간 진행, Start/Pause/Resume/Step/SetRate/Reset) | `src/data/mockSource.ts` | REQ-UI-001, DEC-005, DEC-014 | TC-UI-006 |
| IMP-UI-011 | 버스 데이터 소스(BusTransport 인터페이스, 키·인코딩). 2차: 구독 주기 옵션, truth/state 30 Hz 다운샘플 요청, swarm/&lt;gcs&gt;/rx/** LinkEnvelope 해석, C2 송신 키 검사. `UnimplementedTransport` 삭제 | `src/data/busSource.ts` | DEC-002, DEC-027, REQ-NET-001 | TC-UI-008 |
| IMP-UI-012 | 종류·진영별 SVG 아이콘(선택 링, 파괴 표시) | `src/model/symbology.ts` | REQ-UI-001 | TC-UI-008 |
| IMP-UI-013 | 오프라인 Viewer(로컬 TMS·Cesium 지형(layer.json) 판정, 없으면 Natural Earth II·타원체), RTS 카메라 입력 | `src/cesium/viewer.ts` | DEC-003, DEC-004, DEC-016, REQ-SIM-003 | TC-UI-009 |
| IMP-UI-014 | 엔티티 전시 레이어(Billboard 진행 방향, Polyline 궤적, Label, 화면 투영, 카메라 추종) | `src/cesium/entityLayer.ts` | REQ-UI-001, REQ-UI-007 | TC-UI-009 |
| IMP-UI-015 | 수신 상태 보관소(최신 프레임·궤적, React 재렌더 분리) | `src/model/liveState.ts` | REQ-UI-001 | TC-UI-009 |
| IMP-UI-016 | 지도 뷰(렌더 루프 갱신, 클릭·드래그 박스 입력, 2D/2.5D/3D 전환) | `src/components/MapView.tsx` | REQ-UI-001, REQ-UI-002 | TC-UI-009 |
| IMP-UI-017 | 선택 목록 패널(상태 표시, 지도 이동, 추적·1인칭 전환) | `src/components/SelectionPanel.tsx` | REQ-UI-002, REQ-UI-007 | TC-UI-009 |
| IMP-UI-018 | 도구 막대(시점 전환, 일시정지·배속 SimCommand, 상태·지도 데이터 표시) | `src/components/Toolbar.tsx` | REQ-UI-001, DEC-014 | TC-UI-009 |
| IMP-UI-019 | 화면 구성, UI 인스턴스 ID(issuer), 단축키 | `src/App.tsx` | REQ-UI-001, REQ-UI-002, DEC-020 | TC-UI-009 |
| IMP-UI-023 | 브리지 프로토콜 v1 프레임(바이너리 인코드·디코드, 제어 메시지 타입), 키 표현식 일치 | `src/data/bridgeFrame.ts` | DEC-027 | TC-UI-017 |
| IMP-UI-024 | BridgeTransport: WebSocket 접속, hello(role=control, gcs)·welcome·프로토콜 확인, 구독 재전송, 같은 키 표현식 공유와 주기 상향, 키로 콜백 분배, 끊기면 재접속, 상태·오류 통지 | `src/data/bridgeTransport.ts` | DEC-027, DEC-020 | TC-UI-017, TC-UI-019 |
| IMP-UI-025 | C2 명령 생성: TaskCommand(MoveTo·Hold·RTB·취소), FormationCommand, GroupAssignment → LinkEnvelope(iface C2, dst=대상, 키별 seq, task_id=UI ID 접두어) → `swarm/<gcs>/tx/c2/<msg>` | `src/model/commands.ts` | REQ-UI-002, REQ-UI-003, REQ-UI-004, DEC-013, DEC-014 | TC-UI-018, TC-UI-019 |
| IMP-UI-026 | 부대 그룹 저장소(지정·호출, 한 기체 한 그룹, 바뀐 그룹 목록) | `src/model/groups.ts` | REQ-UI-002, PRP-UI-001 | TC-UI-018 |
| IMP-UI-027 | 명령 기록: 보낸 명령과 rx TaskStatus(기체별 상태·진행률), 최근 rx 목록 | `src/model/taskLog.ts` | REQ-UI-003, REQ-UI-004 | TC-UI-018, TC-UI-019 |
| IMP-UI-028 | DataSource에 `gcs`, `sendC2`, rx 처리기 추가 | `src/data/source.ts` | REQ-UI-003, DEC-027 | TC-UI-008, TC-UI-018 |
| IMP-UI-029 | 목 소스 C2: TaskCommand 대상마다 TaskStatus(ACCEPTED/CANCELLED)를 rx로 응답(기동은 흉내 내지 않음) | `src/data/mockSource.ts` | REQ-UI-003 | TC-UI-018 |
| IMP-UI-030 | 도구 막대: 시작(LOADED)·일시정지/재개·스텝·리셋, 데이터 소스 선택(목/버스), 브리지 연결 상태, GCS 표시 | `src/components/Toolbar.tsx` | DEC-014, DEC-027 | TC-UI-019 |
| IMP-UI-031 | 명령 패널: Hold·RTB, 편대 모양·간격 지정, 그룹 호출·지정, 명령 상태 목록, rx 수신 목록 | `src/components/CommandPanel.tsx`, `src/styles.css` | REQ-UI-002~004 | TC-UI-019 |
| IMP-UI-032 | 지도 우클릭(끌지 않음) → 지면 위경도 → MoveTo, 목적지 표시 | `src/components/MapView.tsx` | REQ-UI-003 | TC-UI-019 |
| IMP-UI-033 | 소스 설정: `?source`, `?bridge`, `?gcs` > `VITE_BRIDGE_URL`, `VITE_GCS` > 기본값 | `src/data/sourceConfig.ts`, `src/vite-env.d.ts` | DEC-027 | TC-UI-017 |
| IMP-UI-034 | 화면 연결: BridgeTransport 소스, C2 송신·실패 표시, 명령 대상(선택 중 살아 있는 아군 비행체), 그룹 단축키(Ctrl/Alt+숫자 지정, 숫자 호출, 두 번 누르면 이동), H=Hold | `src/App.tsx` | REQ-UI-002~004, DEC-020, DEC-027 | TC-UI-019 |
| IMP-UI-035 | 지도 임무 명령 생성: `MissionSpec`(이동·선회 대기·타격·정찰·항로·귀환) → TaskCommand(HoldTask·StrikeTask·SearchAreaTask 원·RouteTask). 0 이하 값은 필드 생략, 타격은 target_id 또는 aim_point, 같은 task_id 재전송 | `src/model/commands.ts` | REQ-UI-003, REQ-UI-004, REQ-BHV-002, DEC-033 | TC-UI-020 |
| IMP-UI-036 | 항로점 편집 모델(불변): 추가(직전 고도·속력 승계), 위치 이동, 고도·속력·행위(통과/선회/정찰) 변경, 삭제, 순서 바꾸기, 보낸 항로 재편집 | `src/model/routeDraft.ts` | REQ-UI-003, DEC-033 | TC-UI-021 |
| IMP-UI-037 | 지도 입력 판정: 우클릭(임무 메뉴, 커서 아래 엔티티), Ctrl/Cmd+우클릭(항로점), 끌기 무시, 항로점 손잡이 집기. MapView 연결과 손잡이 왼쪽 끌기 | `src/model/mapInput.ts`, `src/components/MapView.tsx` | REQ-UI-003, DEC-033 | TC-UI-022, TC-UI-025 |
| IMP-UI-038 | 임무 도형(점·선·원)과 Cesium 전시: 편집 중 항로(노랑), 메뉴 미리보기(주황), 보낸 임무(청록 점선, 기체별 상태·진행률 라벨). 최근·미완료 임무 선택(`TaskLog.activeMissions`) | `src/model/missionOverlay.ts`, `src/cesium/missionLayer.ts`, `src/model/taskLog.ts` | REQ-UI-003, REQ-UI-004 | TC-UI-023, TC-UI-025 |
| IMP-UI-039 | 임무 창: 우클릭 지점 좌표·이동/선회 대기/타격 지정/정찰 선택과 입력(고도·속력·반경·시간·방향·무장), 항로 편집 목록(고도·속력·행위·위로/아래로/삭제·반복·전송/다시 전송·취소) | `src/components/MissionPanel.tsx`, `src/styles.css` | REQ-UI-003, REQ-UI-004, DEC-033 | TC-UI-025 |
| IMP-UI-040 | 화면 연결: 임무 창·항로 편집 상태, 적 엔티티 우클릭 → target_id, Esc로 임무 창 먼저 닫기, 명령 목록의 항로 "편집" | `src/App.tsx`, `src/components/CommandPanel.tsx` | REQ-UI-003, REQ-UI-004, DEC-033 | TC-UI-025 |
| IMP-UI-042 | 레이스트랙 도형 계산: 클릭점=두 원 중심의 중점, 중심=중점±(leg/2)·축(진북 시계 [0,360)), 접점 4개·폐곡선, 시계/반시계 | `src/model/racetrack.ts` | REQ-BHV-002, DEC-034 | TC-UI-026 |
| IMP-UI-043 | 명령·도형 연결: HoldTask.racetrack·LoiterAction.racetrack 생성(leg 0이면 원형), 지도 미리보기와 보낸 임무 도형을 폐곡선으로 전시 | `src/model/commands.ts`, `src/model/missionOverlay.ts` | REQ-BHV-002, DEC-034 | TC-UI-026 |
| IMP-UI-044 | 임무 창 "레이스트랙 선회" 메뉴(반경·직선 길이·축·방향·시간), 항로점 선회 행위의 원형/레이스트랙 선택, 목 소스 레이스트랙 비행. 지도 끌기로 축·길이 지정은 미구현 | `src/components/MissionPanel.tsx`, `src/data/mockGuidance.ts`, `src/styles.css` | REQ-BHV-002, DEC-034 | TC-UI-026, TC-UI-027 |
| IMP-UI-045 | 매개변수 모델: EntityParams 보관(`ParamStore`), 선택 기체 항목을 계층(기체·제어·유도·행위·결정)별로 구성(여러 기체는 소유자·이름이 같은 항목만 합침, 값이 다르면 "혼합"), ParamSpec 형식·min/max 입력 검사, `set_params` 생성(기체·소유자마다 하나, 바꿀 이름만), 기본값 되돌리기, 적용 판정(`values` 기준) | `src/model/params.ts` | REQ-CFG-003, DEC-035 | TC-UI-029, TC-UI-030 |
| IMP-UI-046 | 데이터 소스 연결: `sim/param/**` 구독(BusSource), `DataHandlers.params`, 목 소스의 동역학·FA·MA 선언·적용·거부(unknown·type·range·not_runtime)와 1초 발행. 브리지는 구독 키 제한이 없고 `set_params`가 `sim/ctrl/cmd` 발행 허용 안에 있어 코드 변경 없음(시험으로 확인) | `src/data/source.ts`, `src/data/busSource.ts`, `src/data/mockParams.ts`, `src/data/mockSource.ts`, `bridge/tests/test_bridge.py` | REQ-CFG-003, DEC-035, DEC-027 | TC-UI-028, TC-UI-030 |
| IMP-UI-047 | 매개변수 패널: 기체 선택 시 계층별 항목, 기본값·현재값 병기, 입력 검사 오류, 적용·기본값 버튼, `runtime`=false 비활성, 거부 사유 표시, 보낸 직후 "대기"·`values` 갱신 후 "적용됨" | `src/components/ParamPanel.tsx`, `src/App.tsx`, `src/styles.css` | REQ-CFG-003, DEC-035 | TC-UI-029, TC-UI-031 |
| IMP-UI-048 | 오른쪽 패널 겹침 수정(P0 점검): 임무·선택·매개변수·명령 구역이 각자 `overflow`로 자기 높이 안에 갇히고 머리글은 줄지 않는다. 임무 창은 넘치면 안에서 스크롤, 선택 목록은 최소 96 px | `src/styles.css` | REQ-UI-002, REQ-UI-003 | TC-UI-034 |
| IMP-UI-049 | `SimStatus.replay`=true이면 도구 막대에 "재생" 표시, 시작·일시정지/재개·스텝·배속 비활성(받는 Core 없음) | `src/components/Toolbar.tsx`, `src/styles.css` | DEC-031, REQ-UI-002 | TC-UI-033 |
| IMP-UI-050 | 목 소스 거부 경로: 소유자가 선언보다 엄격한 한계로 거부하는 경우(`kp_roll`>10 → range)를 흉내 내 GUI 거부 표시를 확인한다 | `src/data/mockParams.ts` | REQ-CFG-003, DEC-035 | TC-UI-032, TC-UI-034 |
| IMP-UI-051 | 계약 0.7.0 `ParamSpec.choices`: 선택지 항목은 드롭다운, 입력 검사는 허용 목록 확인, 거부 사유 `choice` 문구, 목 소스 FA `racetrack_guidance`(dubins\|vector_field)와 choice 거부 | `src/model/params.ts`, `src/components/ParamPanel.tsx`, `src/data/mockParams.ts` | REQ-CFG-003, DEC-036 | TC-UI-035, TC-UI-029 |
| IMP-UI-052 | QA-009: realtime(`SimStatus.mode`)에서는 배속 버튼 비활성과 "실시간에서는 배속 고정" 안내. 목 소스는 모드를 갖고(기본 lockstep) realtime이면 배속을 무시한다 | `src/components/Toolbar.tsx`, `src/data/mockSource.ts` | DEC-005, DEC-038, REQ-UI-002 | TC-UI-036 |
| IMP-UI-053 | 임무 응답의 거부·실패 사유를 툴팁이 아닌 본문에 표시(강조색) | `src/components/CommandPanel.tsx`, `src/styles.css` | REQ-UI-002, REQ-UI-004 | TC-UI-037 |
| IMP-UI-054 | QA-010: 브리지 CLI가 stdout·stderr를 `errors="replace"`로 다시 설정해 콘솔 인코딩(cp949 등)에서 도움말·로그로 종료하지 않는다 | `bridge/src/swarm_bridge/cli.py` | DEC-027, DEC-038 | TC-UI-038 |
| IMP-UI-055 | QA-015: truth·status를 3초 넘게 받지 못하면 도구 막대에 "시뮬레이션 응답 없음" 표시. status가 계속 오는 일시정지와 구분, 다시 받으면 해제 | `src/model/liveState.ts`, `src/components/Toolbar.tsx`, `src/App.tsx` | DEC-039 | TC-UI-039 |
| IMP-UI-056 | D-10: 선택 기체의 MA 플러그인이 flocking이면 Route 편집기에 미지원 안내(툴팁). 전송은 막지 않고 거부 사유는 명령 패널에 표시 | `src/model/params.ts`, `src/components/MissionPanel.tsx`, `src/App.tsx` | DEC-039 | TC-UI-040 |
| IMP-UI-057 | QA-017: 브리지가 버스 스레드 샘플을 클라이언트별 대기열로 묶어 이벤트 루프에 넘기고(`DRAIN_BATCH`), 송신 큐가 넘치면 경고 로그(5 s 주기)를 남긴다. 100기 flocking에서 클라이언트 전달률 22%→약 95% | `bridge/src/swarm_bridge/server.py` | DEC-027, DEC-039 | TC-UI-041 |
| TC-UI-042 | 툴바: waiting_participants 경고 표시·해제, 재생 중에만 누락 프레임 표시 (2건) | `ui/src/components/panels.test.tsx` | IMP-UI-058, IMP-UI-059 | 통과 |
| TC-UI-043 | 헤더 엿보기, 공백 계산(중복·재생 전환·되감기), BusSource가 모든 프레임 번호를 알리고 해석만 줄임 (4+1건) | `ui/src/model/frameGap.test.ts`, `ui/src/data/busSource.test.ts` | IMP-UI-059 | 통과 |
| TC-UI-044 | Monitor store: 경고 문구, 재생 중 공백 계산(해석을 줄여도 번호는 매번), 실시간은 0 (3건) | `ui/monitor/src/model/store.test.ts` | IMP-UI-058, IMP-UI-059 | 통과 |
| TC-UI-045 | Monitor 쪽 frameGap 단위 시험 (4건) | `ui/monitor/src/model/frameGap.test.ts` | IMP-UI-059 | 통과 |
| IMP-UI-058 | DEC-041: `SimStatus.waiting_participants`가 비어 있지 않으면 UI 툴바와 Monitor 헤더에 "참여자 응답 없음: <이름> — Reset 후 Start로 복구"를 보이고, 비면 지운다 | `ui/src/components/Toolbar.tsx`, `ui/src/model/liveState.ts`, `ui/monitor/src/components/Header.tsx`, `ui/monitor/src/model/store.ts` | DEC-041 | TC-UI-042, TC-UI-044 |
| IMP-UI-059 | DEC-042: 재생(`SimStatus.replay`) 중 `truth/state` 프레임 번호 공백으로 누락 프레임을 세어 UI 툴바·Monitor 헤더에 표시. 브리지 다운샘플로는 공백을 셀 수 없어 truth를 무제한 구독하고 헤더만 읽어 번호를 세며, 엔티티 해석은 UI 30 Hz·Monitor 1 Hz(벽시계)로 줄인다. 재생기는 건드리지 않는다 | `ui/src/model/frameGap.ts`, `ui/src/data/busSource.ts`, `ui/monitor/src/model/frameGap.ts`, `ui/monitor/src/bridge/source.ts` | DEC-042 | TC-UI-042~045 |
| IMP-UI-060 | truth/event/** 보관소: 재밍 구역(owner별 최신, area 원·다각형 우선·폐기 예정 zone 대체, 도형 없는 끄기는 이전 도형을 꺼짐으로, owner 진영은 truth/state), 생성 엔티티(launch·spawn·`wpn-` ID·missile/fpv) 시작·궤적(200 ms 간격, 600점)·종료(impact 위치·살상반경, kill 원인, alive=false, 프레임에서 사라짐), 추적 대상 아닌 kill 위치. 종료 후 60 s 보관, 시각 역행 시 비움 | `src/model/truthEvents.ts`, `src/model/liveState.ts` | DEC-046, DEC-003, DEC-009, DEC-012 | TC-UI-046, TC-UI-049 |
| IMP-UI-061 | 센서 시야: GCS rx `SensorActivity`(송신 기체 = envelope source)를 기체·장비별로 두고 5 s 소식 없으면 만료, active=false(고장 DEC-047 포함)는 그리지 않음. 카메라 축은 Payload와 같게(오른쪽 수평), FOV 네 모서리·경계 광선을 max_range 또는 지면(기체 아래 지형 고도의 평면)까지 그어 사각뿔·풋프린트를 만든다 | `src/model/sensorFov.ts`, `src/model/liveState.ts`, `src/App.tsx` | DEC-018, DEC-046, DEC-047 | TC-UI-047 |
| IMP-UI-062 | 데이터 소스: `truth/event/**` 구독(다운샘플 없음)·TruthEvent 해석, `DataHandlers.event` | `src/data/source.ts`, `src/data/busSource.ts` | DEC-046, DEC-027 | TC-UI-050 |
| IMP-UI-063 | 목 이벤트 각본(60 s 주기): 원형·다각형(상한 없음) 재밍 구역 켜고 끄기, 미사일 launch+spawn→impact(30 m)+kill, FPV spawn→kill(ground), 발사체를 truth/state에 싣고 종료 프레임에 alive=false 한 번, uav-001 cam0 SensorActivity 1 s 주기(τ 30–35 s 꺼짐). `MockSource({events:false})`로 끈다 | `src/data/mockEvents.ts`, `src/data/mockSource.ts` | DEC-046 | TC-UI-049 |
| IMP-UI-064 | 이벤트 전시 명세(순수 함수): 구역 진영색 반투명 기둥(꺼짐 회색·옅게, 상한 없음은 8000 m까지·라벨 표기), 궤적 꼬리(미사일 주황·FPV 자홍, 종료 후 회색), 생성 흰 점·라벨(발사 기체→표적), 종료 회색 점·원인 라벨, impact 살상반경 원(빨강), kill 마커, FOV 모서리 4선·외곽선(지면이면 굵게) | `src/model/eventOverlay.ts` | DEC-046, DEC-003 | TC-UI-048 |
| IMP-UI-065 | Cesium 이벤트 층: 구역·살상반경 원은 Entity(extruded ellipse·polygon, 도형 서명이 같으면 유지), 궤적·마커·FOV는 프리미티브 모음을 버전 변경 때 다시 채움. 2D·2.5D·3D 공통. MapView 렌더 루프에 연결 | `src/cesium/eventLayer.ts`, `src/components/MapView.tsx` | DEC-003, DEC-046 | TC-UI-051 |
| IMP-UI-066 | QA-023 수정: 이벤트 층 polyline이 색별 Material 하나를 나눠 쓰다가 `removeAll`이 그 Material을 파괴해 다음 갱신에서 "This object was destroyed"로 렌더링이 멈춤. polyline 풀을 두고 polyline마다 자기 Material을 가지며 색은 `uniforms.color`로 바꾸고 남는 것은 `show=false`로 숨긴다. 점검: `entityLayer` 궤적은 polyline마다 Material(문제 없음), `missionLayer`는 Entity API(문제 없음), effectsLayer는 없음 | `src/cesium/eventLayer.ts` | DEC-046, DEC-003 | TC-UI-052, TC-UI-053 |
| IMP-UI-067 | 지도 모드(2D·2.5D·3D) 전환 시 현재 위치 유지: 전환 직전 화면 중심(지면 교차점, 하늘을 보면 카메라 바로 아래)과 가로로 보이는 폭을 기억했다가 전환 직후 새 모드에서 같은 중심·폭으로 수직 내려다보게 놓는다(2D는 정사영 폭, 3D·2.5D는 시야각으로 높이 환산). 모핑 애니메이션은 지구 전체 뷰를 거치므로 즉시 전환(0 s) | `src/model/viewKeep.ts`, `src/cesium/cameraView.ts`, `src/components/MapView.tsx` | REQ-UI-001, DEC-003 | TC-UI-054, TC-UI-056 |
| IMP-UI-068 | 맞춤 뷰: 엔티티 전체 범위 + 변마다 15 % 여백, 엔티티 1개면 최소 5 km, 위치 (0,0)·NaN 제외. 첫 엔티티 수신 때 한 번, `SimStatus.scenario_name`이 바뀌면(새 적재) 다시 한 번 맞추고 그 밖의 갱신·리셋은 카메라를 건드리지 않는다. "전체" 버튼도 같은 함수 | `src/model/viewKeep.ts`, `src/cesium/cameraView.ts`, `src/cesium/entityLayer.ts`, `src/components/MapView.tsx` | REQ-UI-001, DEC-003 | TC-UI-055, TC-UI-056 |
| IMP-UI-069 | 영상 타일 받기 스크립트: 범위(33~43°N, 124~131°E)·줌(0~13) XYZ 타일 → 로컬 TMS(`{z}/{x}/{y}.jpg`, 남쪽 0행) + `tilemapresource.xml`(gdal2tiles `mercator` 프로파일, 위경도 BoundingBox). 요청 속도 상한(기본 2/s, 서버 신호 시 간격 증가), 재시도(지수 백오프, Retry-After), 이미지가 아닌 응답은 실패, 있는 타일 건너뛰어 이어받기, 실패 목록 `fetch_state.json`. EOX 원본은 `--eox-permission` 없으면 받지 않는다(약관상 일괄 받기 불명확, DEC-057 보고) | `../scripts/fetch_imagery.py` | REQ-SIM-003, DEC-057 | TC-UI-058 |
| IMP-UI-070 | 지형 타일 변환 스크립트: GLO-90 격자(계약 §6) → Cesium heightmap-1.0(EPSG:4326, TMS, 65×65, `(h+1000)×5`, 자식 마스크, gzip) + `layer.json`(레벨별 `available`). 레벨 0~12(77 m), DEM보다 거친 레벨은 2배 평균 피라미드에서 쌍선형 표본. 높이는 DEM 정표고 그대로(동역학 지형과 일치). numpy만 사용 | `../scripts/make_terrain_tiles.py` | REQ-SIM-003, DEC-057, DEC-053 | TC-UI-058 |
| IMP-UI-071 | 지도 자료 표기·겹침: 바탕은 늘 내장 Natural Earth II, 로컬 영상은 그 위 레이어(범위 밖이 비지 않음, 최대 줌 13). 로컬 영상이면 EOX Sentinel-2 cloudless 표기(`VITE_IMAGERY_CREDIT`로 변경), 로컬 지형이면 Copernicus DEM 표기를 화면 출처에 고정 | `src/model/mapCredits.ts`, `src/cesium/viewer.ts` | REQ-SIM-003, DEC-057 | TC-UI-057, TC-UI-058 |
| IMP-UI-041 | 목 소스 임무 비행: 선회율 제한 유도(직진·선회 구간), 이동·선회·타격·정찰·항로(반복)·귀환·취소, TaskStatus 구간 진행(EXECUTING)·완료(COMPLETED)·거부(REJECTED), 시각 되감기 시 해석 궤도 복귀 | `src/data/mockGuidance.ts`, `src/data/mockScenario.ts`, `src/data/mockSource.ts` | REQ-UI-003, REQ-UI-004 | TC-UI-024, TC-UI-025 |

## 시험 (TC)

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-UI-001 | 오일러⇄쿼터니언 왕복, NED 진행 방향·상승각, 각도 정규화 (5건) | `src/model/attitude.test.ts` | IMP-UI-003 | 통과 |
| TC-UI-002 | TruthFrame 바이너리 왕복, 뷰 변환, 기본값 (4건) | `src/model/entityView.test.ts` | IMP-UI-001, IMP-UI-004 | 통과 |
| TC-UI-003 | 궤적 샘플링·최대 점 수·소멸·되감기 (3건) | `src/model/trails.test.ts` | IMP-UI-005 | 통과 |
| TC-UI-004 | 수정키 모드, 클릭/드래그 판정, 클릭·박스 선택, 결합, 정리 (6건) | `src/model/selection.test.ts` | IMP-UI-006 | 통과 |
| TC-UI-005 | 목 시나리오 구성(UAV ≥ 20, ID 규칙), 시각, 결정론, 속도·방향 일치, 협조선회 뱅크각 (5건) | `src/data/mockScenario.test.ts` | IMP-UI-009 | 통과 |
| TC-UI-006 | 목 소스 진행, 배속, 일시정지·스텝·재개, 리셋, autoStart, 따라잡기 제한 (6건) | `src/data/mockSource.test.ts` | IMP-UI-008, IMP-UI-010 | 통과 |
| TC-UI-007 | 카메라 free/fpv/chase/gimbal 자세, 국지 오프셋 (5건) | `src/model/camera.test.ts` | IMP-UI-007 | 통과 |
| TC-UI-008 | 버스 소스 디코드·인코드·키·encoding, 구독 키·truth 주기, GCS 없을 때 C2 거부, rx 해석·해석 실패 보고, 자기 GCS tx 키만 송신, 아이콘 (5건) | `src/data/busSource.test.ts` | IMP-UI-001, IMP-UI-011, IMP-UI-012, IMP-UI-028 | 통과 |
| TC-UI-009 | 수동: `npm run dev`에서 목 소스 32개(UAV 24) 이동 전시, 궤적, 박스 선택 6대·패널, 2D 전환, 추적·1인칭 시점과 아이콘 방향, 로컬 데이터 없음 → 내장 영상·타원체 | 브라우저 확인 | IMP-UI-002, IMP-UI-013~019 | 통과 |
| TC-UI-020 | 임무 명령 생성: 선회 대기·타격(target_id/aim_point)·정찰 원·항로(속성·행위·loop·task_id 재사용) 필드 값 (4건) | `src/model/mission.test.ts` | IMP-UI-035 | 통과 |
| TC-UI-021 | 항로점 편집: 추가·이동·속성·삭제·순서 바꾸기·재편집 (4건) | `src/model/mission.test.ts` | IMP-UI-036 | 통과 |
| TC-UI-022 | 우클릭 판정: 메뉴, Ctrl/Cmd 항로점, 선택 없음, 끌기, 손잡이 집기 (5건) | `src/model/mission.test.ts` | IMP-UI-037 | 통과 |
| TC-UI-023 | 임무 도형, 최근·미완료 임무 선택 (3건) | `src/model/mission.test.ts` | IMP-UI-038 | 통과 |
| TC-UI-024 | 목 소스 임무 비행: 이동 도착·완료 보고, 비대상 기체 불변, 선회 반경, 항로 진행 보고, 정찰 원, 타격 접근, 거부·취소, 되감기 (9건) | `src/data/mockGuidance.test.ts` | IMP-UI-041 | 통과 |
| TC-UI-026 | 레이스트랙: 원 중심(중점 ± leg/2·축)·접점·폐곡선 닫힘, 시계/반시계, 축 정규화, HoldTask/LoiterAction 메시지(`racetrack` 필드, leg 0이면 생략), 지도 도형 | `src/model/racetrack.test.ts` | IMP-UI-042~044 | 통과 |
| TC-UI-027 | 목 소스 레이스트랙 비행: 시계·반시계 모두 직선 구간 따라 도형 안을 유지 | `src/model/racetrack.test.ts` | IMP-UI-044 | 통과 |
| TC-UI-028 | 브리지: `sim/param/**` 구독 전달(동역학·FA·MA 3키, 구독 밖 키 제외), control 클라이언트의 `set_params`(`sim/ctrl/cmd`)가 버스에 그대로 전달 (1건) | `bridge/tests/test_bridge.py` | IMP-UI-046, DEC-035 | 통과 |
| TC-UI-029 | 매개변수 항목 구성·검사·메시지: 계층 순서와 기본값·현재값, 다기체 합침·혼합·선언 누락, 입력 검사(숫자·범위·문자열·참/거짓), `set_params` 직렬화 왕복, 기본값 되돌리기 (5건) | `src/model/params.test.ts` | IMP-UI-045 | 통과 |
| TC-UI-030 | 적용·거부 표시와 소스 연결: 거부 4종 사유·값 불변, 적용 판정, 목 소스 `set_params` 왕복·다른 기체 불변·리셋, 버스 소스 `sim/param/**` 구독·`sim/ctrl/cmd` 발행 (4건) | `src/model/params.test.ts` | IMP-UI-045, IMP-UI-046 | 통과 |
| TC-UI-031 | 수동(브라우저, 목 소스): 24기 선택 → 공통 항목 패널, 범위 밖 입력 오류 표시, 60 적용 → "현재 60·적용됨", `runtime`=false 항목 비활성. 화면: `docs/screenshots/tc-ui-031-params.jpg` | 브라우저 확인 | IMP-UI-047 | 통과 |
| TC-UI-032 | 매개변수 패널 서버 렌더링: 형식·범위·not_runtime 거부가 항목에 사유와 함께 붙고 값은 그대로(unknown은 선언에 없는 이름이라 TC-UI-030에서 코드 확인). 목 소스 `kp_roll`>10 range 거부 (2건) | `src/components/panels.test.tsx` | IMP-UI-047, IMP-UI-050 | 통과 |
| TC-UI-033 | 도구 막대: replay=true이면 "재생" 표시와 시작·일시정지·스텝·배속 비활성, false이면 표시 없고 활성 (2건) | `src/components/panels.test.tsx` | IMP-UI-049 | 통과 |
| TC-UI-034 | 수동(브라우저, 목 소스): 24기 선택+임무 창에서 창 높이 850·700·520·400 px 모두 구역 겹침 0, `전송` 버튼 중심 클릭이 버튼에 닿음. `kp_roll`=15 적용 → "거부: 허용 범위를 벗어남", 값 2.4 유지 | 브라우저 확인 | IMP-UI-048, IMP-UI-050 | 통과 |
| TC-UI-035 | 선택지 항목: select 렌더링(선택값 표시, 입력칸과 구분), choice 거부 문구, 허용 목록 밖 입력 거절, 다기체 값이 다르면 "혼합" 선택지 (4건, `params.test.ts` 1건 포함) | `src/components/panels.test.tsx`, `src/model/params.test.ts` | IMP-UI-051 | 통과 |
| TC-UI-036 | realtime이면 ×1~×10 비활성과 안내, lockstep·freerun이면 활성·안내 없음 (2건) | `src/components/panels.test.tsx` | IMP-UI-052 | 통과 |
| TC-UI-037 | 임무 응답: REJECTED·FAILED 사유 본문 표시, 정상 응답 무표시, 전송 실패 표시 (1건). 명령 직렬화·TaskStatus 연결·목 소스 응답은 TC-UI-006~, 매개변수 명령은 TC-UI-029~030이 이미 덮는다 | `src/components/panels.test.tsx` | IMP-UI-053 | 통과 |
| TC-UI-038 | 브리지: `PYTHONIOENCODING=cp949`에서 `swarm-bridge --help`가 정상 종료(수정 전 실패 확인) (1건) | `bridge/tests/test_bridge.py` | IMP-UI-054 | 통과 |
| TC-UI-039 | isStalled 경계, 일시정지(status만 수신) 비정지, 무수신 정지·재수신 해제, truth 갱신, 배지 표시 (4건) | `src/components/panels.test.tsx` | IMP-UI-055 | 통과 |
| TC-UI-040 | `unsupported task route` 거부 사유 표시, flocking 안내 표시·전송 비차단 (2건) | `src/components/panels.test.tsx` | IMP-UI-056 | 통과 |
| TC-UI-041 | 버스 스레드에서 `3×DRAIN_BATCH+7`건을 두 키로 쏟아도 순서대로 빠짐없이 전달, 드롭 0 (1건) | `bridge/tests/test_bridge.py` | IMP-UI-057 | 통과 |
| TC-UI-025 | 수동(브라우저, 목 소스): 기체 선택 → 우클릭 임무 창 4종 전송, Ctrl+우클릭 항로 편집·끌기·전송·재전송, 지도 표시·진행 | 브라우저 확인, 화면: `docs/screenshots/tc-ui-025-*.jpg`. 정찰·선회 대기는 자동 시험(TC-UI-024)과 메뉴 미리보기로 확인 | IMP-UI-037~041 | 통과 |
| TC-UI-046 | truth 이벤트 보관소: zoneShape(원·다각형·legacy·무효), 구역 끄기·진영, launch+spawn 시작·궤적·impact 종료·살상반경, dead·gone·kill 원인 교체, kill 마커, 보관 만료·시각 역행, 궤적 간격·최대 점 (7건) | `ui/src/model/truthEvents.test.ts` | IMP-UI-060 | 통과 |
| TC-UI-047 | 센서 시야: 카메라 축 직교·수평, offsetNed, 수직 아래 풋프린트 = 높이×tan(fov/2), 지면 고도·거리 제한·수평 시야, SensorStore rx 해석·최신값·꺼짐·만료·역행 (6건) | `ui/src/model/sensorFov.test.ts` | IMP-UI-061 | 통과 |
| TC-UI-048 | 전시 명세: 구역 색·투명도·라벨·상한 없음, 궤적 색·회색 처리·생성/종료 라벨·살상반경 원, kill 마커·반경 0 무시, FOV 선 수·굵기·지면 고도 호출 (4건) | `ui/src/model/eventOverlay.test.ts` | IMP-UI-064 | 통과 |
| TC-UI-049 | 목 각본(MockSource): 60 s 이벤트 키·순서, 발사체 truth 포함·alive=false 한 번·보관소 종료 원인, SensorActivity rx/ms 1 s 주기·τ 30–35 s 꺼짐, events=false·Reset 후 재현 (4건) | `ui/src/data/mockEvents.test.ts` | IMP-UI-063, IMP-UI-060 | 통과 |
| TC-UI-050 | BusSource: `truth/event/**` 구독 키(다운샘플 없음)·TruthEvent 해석·해석 오류 보고 (1건, 구독 키 목록 시험 갱신) | `ui/src/data/busSource.test.ts` | IMP-UI-062 | 통과 |
| TC-UI-051 | 수동(브라우저, 목 소스): 2D·3D에서 재밍 구역 기둥·꺼짐, 발사체 꼬리·생성/종료 마커·살상반경 원, FOV 원뿔·풋프린트 | 브라우저 확인 | IMP-UI-065 | TC-UI-053로 실시 |
| TC-UI-052 | Cesium 객체 수명(실제 PolylineCollection·Material, 가짜 viewer): 5회 갱신 뒤 파괴된 Material 없음·polyline 유지·Material 고유, 선 수 감소 시 숨김·색 uniform 갱신, 증가 시 풀 확장, destroy 정리 (수정 전 코드에서 실패 확인) (2건) | `ui/src/cesium/eventLayer.test.ts` | IMP-UI-066 | 통과 |
| TC-UI-053 | 수동(브라우저, 목 소스): 3D와 2D에서 τ 10·15 s 발사 → 22·27 s 종료를 넘겨 각 주기 2회 이상 갱신, 두 번째 주기(τ 70 s 발사, T 81 s)까지 궤적·종료 마커(명중·지면 충돌)·살상반경 원·재밍 구역·FOV 계속 렌더링, 콘솔에 destroyed·DeveloperError 없음 | 브라우저 확인 | IMP-UI-065, IMP-UI-066 | 통과 |
| TC-UI-054 | 모드 전환 폭 유지 계산: 원근 거리→폭→높이 왕복, 2D 높이 = 폭, 상·하한·NaN (2건) | `ui/src/model/viewKeep.test.ts` | IMP-UI-067 | 통과 |
| TC-UI-055 | 맞춤 뷰: 범위·여백, 엔티티 1개 최소 5 km·(0,0)·NaN 제외·없으면 null, FitGate 첫 엔티티 1회·이름 처음 알게 됨은 교체 아님·시나리오 교체 시 엔티티 기다려 1회·rearm (5건) | `ui/src/model/viewKeep.test.ts` | IMP-UI-068 | 통과 |
| TC-UI-056 | 수동(브라우저, 목 소스, 개발 서버의 `window.__swarmViewer`로 화면 중심 읽기): 시작 시 맞춤(36.66°N 127.51°E, 높이 40 km). 3D 기울임(-40°) 중심 37.3410/127.0965 → 2D 중심 동일·폭 26.9 km(예상 2·23.3 km·tan 30°). 2D → 2.5D 중심 36.6482/127.5153 동일. 2.5D 기울임 → 3D 중심 36.8369/127.5153 동일. 3D 하늘 방향(+6°) → 2D는 카메라 아래 37.0/127.3. 2D → 3D 동일. 전환 중 지구 전체 뷰 없음. "전체" 버튼 맞춤, 카메라 옮긴 뒤 리셋은 카메라 불변. 콘솔 오류 없음 | 브라우저 확인 | IMP-UI-067, IMP-UI-068 | 통과 |
| TC-UI-057 | 출처 표기: 로컬 영상·지형일 때만 각각, 필수 문구(EOX·Copernicus Sentinel·Copernicus DEM·EU/ESA), 영상 표기 덮어쓰기·빈 문자열 (3건) | `ui/src/model/mapCredits.test.ts` | IMP-UI-071 | 통과 |
| TC-UI-058 | 수동: `fetch_dem.py`(206 MB, 4분 33초) → `make_terrain_tiles.py`(0~12레벨 49,215장, gzip 150.7 MB) 뒤 `npm run dev`에서 지형 공급자 CesiumTerrainProvider, 툴바 "지도 내장 · 지형 DEM", 타일 높이 대청봉 1688 m(DEM 1694)·한라산 1841·동해 0, 속초 앞바다 저각 시점에서 설악 능선 윤곽 보임, Copernicus DEM 출처 표기. 물 마스크 바이트 누락 시 렌더 정지 → 1바이트 추가로 해소. 영상 경로는 합성 타일(z0~9, EOX 아님)로 확인: 툴바 "지도 로컬 · 지형 DEM", 영상 층 2(NaturalEarthII 위 로컬), 범위 124~131°E·33~43°N 안만 덮음, maximumLevel 13, EOX·DEM 출처 둘 다 표기. EOX 실영상은 약관 불명확으로 받지 않음 | 브라우저 확인 | IMP-UI-069~071 | 통과(영상은 합성 타일) |


- 1차 자동 시험: `npm test` 8개 파일 38건 통과 (vitest 5.0.5). `npm run build` 통과 (tsc 7.0.2, vite 8.3.5).
- 2차 자동 시험: `npm test` 10개 파일 56건 통과. `npm run build` 통과.
- 3차 자동 시험(계약 0.4.0 지도 임무): `npm test` 12개 파일 81건 통과.
- truth 이벤트 시각화(기준 `wp0-contracts` 9979e84, 계약 0.10.0): `npm test` 20개 파일 145건 통과. `npm run build` 통과.
- QA-023 수정(기준 `wp0-contracts` 37ba3a7): `npm test` 21개 파일 146건 통과. `npm run build` 통과.
- 지도 카메라 유지·맞춤 뷰(기준 `wp0-contracts` e622ada, 계약 0.11.0): `npm test` 22개 파일 153건 통과. `npm run build` 통과. DEC-051(Agent의 `*Activity` GCS 자동 보고)은 UI가 이미 `swarm/<gcs>/rx/ms/SensorActivity`만 읽으므로 변경 없음.
- 지도 고해상도(DEC-057, 기준 `wp0-contracts` 57c69e6): `npm test` 23파일 156건 통과, `npm run build` 통과. DEM 206 MB(4분 33초), 지형 타일 49,215장 150.7 MB(40~90초). EOX 영상 일괄 받기(z0~13 62,214장)는 약관상 허용이 불명확해 받지 않음 — `fetch_imagery.py`는 `--eox-permission`(서면 허가 후) 또는 `--template` 없이는 타일 수만 계산
- 데이터링크(WP4)·Agent(WP3)와의 실제 왕복(명령 → 기체 반응 → TaskStatus)은 해당 WP 통합 뒤 확인한다.
