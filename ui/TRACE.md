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
| IMP-UI-013 | 오프라인 Viewer(로컬 TMS·quantized-mesh 판정, 없으면 Natural Earth II·타원체), RTS 카메라 입력 | `src/cesium/viewer.ts` | DEC-003, DEC-004, DEC-016, REQ-SIM-003 | TC-UI-009 |
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

- 1차 자동 시험: `npm test` 8개 파일 38건 통과 (vitest 5.0.5). `npm run build` 통과 (tsc 7.0.2, vite 8.3.5).
- 2차 자동 시험: `npm test` 10개 파일 56건 통과. `npm run build` 통과.
- 데이터링크(WP4)·Agent(WP3)와의 실제 왕복(명령 → 기체 반응 → TaskStatus)은 해당 WP 통합 뒤 확인한다.
