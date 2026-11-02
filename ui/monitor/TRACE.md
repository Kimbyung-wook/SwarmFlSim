# WP6 Traffic Monitor 추적표

- 브랜치: `claude/wp6-monitor-d5bf8d` (기준 `wp0-contracts` 8972f55)
- 계약 버전: 0.2.0. `proto/`, `api/`, `bus/`, `docs/`, `ui/`(monitor 밖)는 바꾸지 않았다.

## 구현 (IMP)

| ID | 내용 | 위치 | 근거 | 시험 |
|---|---|---|---|---|
| IMP-MON-001 | proto/swarm/v1 → TS 생성(protobuf-es, buf CLI는 node_modules) | `scripts/gen-proto.mjs`, `buf.gen.yaml` | REQ-UI-005, DEC-003 | TC-MON-003 |
| IMP-MON-002 | 브리지 프로토콜 v1 프레임: 바이너리(키·인코딩·페이로드, LE uint16) 인코딩·해석, 텍스트(hello/welcome/sub/unsub/error) | `src/bridge/frame.ts` | DEC-027 | TC-MON-001 |
| IMP-MON-003 | FrameSource 추상화, BridgeSource(observer 접속, welcome 후 구독, 프로토콜 버전 확인, 재접속) | `src/bridge/source.ts` | DEC-027, DEC-020, REQ-UI-006 | TC-MON-002 |
| IMP-MON-004 | 키별 프레임 해석(link/outcome·state, swarm tx/rx, truth, sim/ctrl/status), 인코딩 불일치 무시, payload echo 해석(registry) | `src/model/decode.ts` | REQ-UI-005, PRP-LNK-002 | TC-MON-003 |
| IMP-MON-005 | 열거값 표시 이름, 손실 사유 순서·색, 비행체/지상체 분류 | `src/model/labels.ts` | REQ-UI-005, PRP-UI-002 | TC-MON-004, TC-MON-006 |
| IMP-MON-006 | 집계기: 엔티티별 송신/수신(outcome 수·전달·손실·바이트·사유별·지연 평균/p95/최대), sim 시각 5 s 이동 창 빈도, 쌍·메시지 타입별, 엔벨로프 수 | `src/model/aggregator.ts` | REQ-UI-005, PRP-UI-002, PRP-LNK-002 | TC-MON-004, TC-MON-009 |
| IMP-MON-007 | 필터(엔티티 any/src/dst, 인터페이스, 메시지 타입, 결과·사유), outcome·엔벨로프 판정 | `src/model/filter.ts` | REQ-UI-005, PRP-UI-002 | TC-MON-005 |
| IMP-MON-008 | 고정 용량 원형 버퍼 | `src/model/ring.ts` | REQ-UI-005, REQ-PRF-001 | TC-MON-006 |
| IMP-MON-009 | 상태 보관소: 프레임 → 집계·타임라인·echo·tx 색인, 엔티티 목록(truth·트래픽), 링크 상태, 재생 표시 상태, 되감기 감지(5 s), 처리 시간 계측 | `src/model/store.ts` | REQ-UI-005, PRP-UI-002 | TC-MON-006, TC-MON-009 |
| IMP-MON-010 | 엔티티 트리(비행체/지상체 → 진영 → 엔티티) | `src/model/tree.ts` | REQ-UI-005, PRP-UI-002 | TC-MON-006 |
| IMP-MON-011 | 목 트래픽 생성기(브리지와 같은 BusFrame, 7개 손실 사유, 시드 결정론)와 벽시계 목 소스(배속, 되감기) | `src/mock/mockTraffic.ts`, `src/mock/mockSource.ts` | REQ-UI-005, PRP-LNK-001, PRP-LNK-002 | TC-MON-007, TC-MON-010 |
| IMP-MON-012 | Vite 설정(포트 5174), 부하 측정 전용 vitest 설정 | `vite.config.ts`, `vitest.bench.config.ts` | DEC-003 | TC-MON-009 |
| IMP-MON-013 | 표시 형식(빈도·바이트·ms·%·sim 시각, bigint JSON) | `src/model/format.ts` | REQ-UI-005 | TC-MON-010 |
| IMP-MON-014 | 시퀀스 타임라인 질의(창·필터·상한), 레인 순서, 배치(전달 기울기·손실 ✕), 클릭 판정, 화면 정지 사본 | `src/model/timeline.ts` | REQ-UI-005, PRP-UI-002 | TC-MON-008 |
| IMP-MON-015 | 화면 구성, 데이터 소스 선택(URL), 250 ms 갱신, 부하 표시 계산, 재생 모드 스타일 | `src/App.tsx`, `src/styles.css` | REQ-UI-005, PRP-UI-002, DEC-027 | TC-MON-010 |
| IMP-MON-016 | 머리줄(실시간/재생 배지, 연결·계약, SimStatus, 되감기, 처리율, 정지·초기화) | `src/components/Header.tsx` | REQ-UI-005, PRP-UI-002 | TC-MON-010 |
| IMP-MON-017 | 필터 막대 | `src/components/FilterBar.tsx` | REQ-UI-005 | TC-MON-010 |
| IMP-MON-018 | 엔티티 트리 화면(체크 = 필터, 클릭 = 상세, 송신 빈도·손실률) | `src/components/EntityTree.tsx` | REQ-UI-005 | TC-MON-010 |
| IMP-MON-019 | 엔티티별 통계 표(송신/수신 기준, 정렬, 사유별, 합계) | `src/components/StatsTable.tsx` | REQ-UI-005, PRP-UI-002 | TC-MON-010 |
| IMP-MON-020 | 시퀀스 타임라인 캔버스(창 0.5–10 s, 상한 시 구간 축소, 클릭 선택) | `src/components/Timeline.tsx` | REQ-UI-005, PRP-UI-002 | TC-MON-010 |
| IMP-MON-021 | 메시지 echo(tx/rx 목록, LinkEnvelope·payload 해석, 타임라인 선택 연동) | `src/components/EchoPanel.tsx` | REQ-UI-005, PRP-UI-002 | TC-MON-010 |
| IMP-MON-022 | 엔티티 상세(메시지 타입별 송수신, 손실 상대, link/state) | `src/components/EntityDetail.tsx` | REQ-UI-005, PRP-LNK-002 | TC-MON-010 |

## 시험 (TC)

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-MON-001 | 바이너리 프레임 왕복·LE 길이·오프셋 버퍼·잘린 프레임, 인코딩 이름, welcome/error 해석 (6건) | `src/bridge/frame.test.ts` | IMP-MON-002 | 통과 |
| TC-MON-002 | observer hello, welcome 후 구독(id 고유, outcome max_hz 0), 프레임 전달·깨진 프레임 계수, 버전 불일치, error, 재접속·close (5건) | `src/bridge/source.test.ts` | IMP-MON-003 | 통과 |
| TC-MON-003 | 키별 해석, 인코딩 불일치·깨진 페이로드·형식 밖 키 무시, 빈 인코딩, swarm 키, payload echo JSON·오류 (6건) | `src/model/decode.test.ts` | IMP-MON-001, IMP-MON-004 | 통과 |
| TC-MON-004 | 송신/수신 분리, 7개 사유+기타, 지연 평균·p50·p95·최대, 5 s 창 빈도, 늦은 버킷, 타입별·엔벨로프 수·초기화 (6건) | `src/model/aggregator.test.ts` | IMP-MON-006 | 통과 |
| TC-MON-005 | outcome 필터(빈 필터, any/src/dst, 인터페이스·타입·결과, AND), 엔벨로프 필터(브로드캐스트, 유니캐스트, rx, 결과), toggle (8건) | `src/model/filter.test.ts` | IMP-MON-007 | 통과 |
| TC-MON-006 | 원형 버퍼, outcome → tx 엔벨로프 색인·축출, truth/kill 엔티티 갱신·트리, 링크 상태·SimStatus·무시 계수, 되감기 초기화 (5건) | `src/model/store.test.ts` | IMP-MON-008~010 | 통과 |
| TC-MON-007 | 목 프레임 전부 계약 키로 해석, 시드 결정론, 95 s 동안 7개 사유 모두 발생·전달 수 = rx 수, rx_time, 브로드캐스트 수신자당 outcome (5건) | `src/mock/mockTraffic.test.ts` | IMP-MON-011 | 통과 |
| TC-MON-008 | 타임라인 창·필터·상한, 정지 사본, 레인 순서, 배치·클릭 판정 (4건) | `src/model/timeline.test.ts` | IMP-MON-014 | 통과 |
| TC-MON-009 | 부하 측정: 바이트 프레임 → 해석 → 집계·타임라인·echo (아래 표) | `src/load/monitor.load.ts` (`npm run bench`) | IMP-MON-006, IMP-MON-009, REQ-PRF-001 | 통과(20대 × 50 Hz 실시간 12.7배) |
| TC-MON-010 | 수동 화면 확인(목 소스, 아래 기록) | – | IMP-MON-011~022 | 확인 |

`npm test`: 8개 파일 45건 통과. `npm run build`: 통과(tsc -b, vite build).

## 부하 측정 (TC-MON-009)

- 환경: Intel i9-14900HX, Node 24.19, 2026-11-01. 목 생성 비용은 빼고, 미리 만든 바이트 프레임을 `decodeFrame` → `MonitorStore.handleFrame`에 넣은 시간을 잰다. sim 20 s(40대는 10 s), 3회 반복 중 대표값.
- 트래픽: UAV마다 PeerStatus p2p 브로드캐스트(표의 주기) + TrackShare 1 Hz 브로드캐스트 + TaskStatus 1 Hz·SensorActivity 2 Hz(→GCS), GCS 명령, truth/state·sim/ctrl/status·link/state.

| 경우 | 프레임/s | outcome/s | 처리 ms/s(sim) | µs/프레임 | 실시간 배수 |
|---|---|---|---|---|---|
| 20대 × 10 Hz (목 기본값) | 8,465 | 4,461 | 18.3 | 2.16 | 54.8 |
| 20대 × 50 Hz | 37,809 | 20,461 | 78.2–79.1 | 2.07–2.09 | 12.6–12.8 |
| 40대 × 50 Hz | 161,689 | 81,724 | 321–341 | 2.0–2.1 | 2.9–3.1 |

- 브라우저(Chromium, dev 서버, `?hz=50`, 목 생성 포함): 34–36k 프레임/s 수신, 처리 시간 비율 6–9%, sim 시각이 벽시계와 같이 진행(5 s당 5.00 s)해 밀리지 않았다.
- 메모리는 타임라인 20,000건, echo 5,000건, tx 색인 20,000건으로 고정이다.

## 수동 확인 기록 (TC-MON-010)

- 목 소스(`/`): 트리에 비행체 21(청군 20, 적군 1)·지상체 4(청군 GCS 1, 적군 3), 통계 표에 송신 기준 14 msg/s·223 outcome/s, 사유별 재밍·가시선·거리·버스트·큐 집계 확인.
- `uav-007` 체크 → 통계 1행, 필터 막대 표시. 클릭 → 상세(타입별·손실 상대·링크 상태). 30–40 s 고장 주입 구간에 타임라인이 사유 색(고장) 점선 ✕로 표시.
- 화면 정지 후 타임라인 손실 화살표 클릭 → `uav-019 → gcs-01 #90 PeerStatus 손실: 가시선`, LinkEnvelope와 PeerStatus payload JSON 해석 표시.
- `?replay=1` → 머리줄 `▶ 재생 (MCAP)` 배지와 주황 테두리. `목 되감기` → `되감기 1회`, 통계 초기화.
- `?source=bridge`(브리지 없음) → `브리지 · 끊김`(code 1006), 2 s마다 재접속 시도.
- 실제 브리지(WP5)·데이터링크(WP4)와의 연동은 해당 WP가 없어 확인하지 못했다.
