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
| IMP-MON-023 | 되감기는 시계 출처(sim/ctrl/status, truth/state)로만 판정. 늦게 온 outcome은 집계하고 링크 지연(sim 시각 − 최신 outcome tx 시각)을 머리줄에 표시 | `src/model/store.ts`, `src/components/Header.tsx` | REQ-UI-005, PRP-UI-002, DEC-005 | TC-MON-006, TC-MON-011 |
| IMP-MON-024 | 재생 표시를 `SimStatus.replay`로 판단. `?replay=1`은 SimStatus 수신 전 대체값, 배지 수동 전환은 `replay` 값이 바뀌면 해제. 목 생성기 `replay` 옵션 | `src/model/store.ts`, `src/components/Header.tsx`, `src/App.tsx`, `src/mock/mockTraffic.ts` | REQ-UI-005, PRP-UI-002, DEC-031 | TC-MON-012 |
| IMP-MON-025 | 손실률 분모는 수신자별 outcome임을 표 툴팁에 명시하고 `거리 밖 제외`(OUT_OF_RANGE를 분자·분모에서 뺌) 선택 추가. 목 브로드캐스트 수신 대상을 같은 편 무전기 엔티티로 한정 | `src/model/aggregator.ts`, `src/components/StatsTable.tsx`, `src/mock/mockTraffic.ts` | REQ-UI-005, PRP-LNK-002, DEC-032 | TC-MON-013 |
| IMP-MON-026 | 링크 지연을 outcome을 받은 순간의 (sim 시계 − tx 시각)으로 계산. 마지막 outcome 이후 sim 시계가 5 s 넘게 흐르면 0. 트래픽 공백(`최신 tx 시각`이 멈춘 구간)을 지연으로 보이던 결함 수정 | `src/model/store.ts`, `src/components/Header.tsx` | REQ-UI-005, PRP-UI-002, DEC-005 | TC-MON-014 |
| IMP-MON-027 | `truth/state` 프레임 번호 공백으로 누락 프레임 수를 세어 머리줄에 표시(재생 한계), `SimStatus.waiting_participants`를 머리줄에 경고 표시 | `src/model/store.ts`, `src/components/Header.tsx` | REQ-UI-005, DEC-041, DEC-042 | TC-MON-015 (Superseded by IMP-UI-059: 1 Hz 구독으로 누락을 과다 계수해 WP5 구현으로 대체) |
| IMP-MON-028 | QA-018 조사: 집계 정의는 변경 없음. 같은 outcome 열에서 독립 집계와 일치함을 시험으로 고정 | `src/model/aggregator.test.ts` | REQ-UI-005, DEC-044 | TC-MON-016 |

## 시험 (TC)

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-MON-001 | 바이너리 프레임 왕복·LE 길이·오프셋 버퍼·잘린 프레임, 인코딩 이름, welcome/error 해석 (6건) | `src/bridge/frame.test.ts` | IMP-MON-002 | 통과 |
| TC-MON-002 | observer hello, welcome 후 구독(id 고유, outcome max_hz 0), 프레임 전달·깨진 프레임 계수, 버전 불일치, error, 재접속·close (5건) | `src/bridge/source.test.ts` | IMP-MON-003 | 통과 |
| TC-MON-003 | 키별 해석, 인코딩 불일치·깨진 페이로드·형식 밖 키 무시, 빈 인코딩, swarm 키, payload echo JSON·오류 (6건) | `src/model/decode.test.ts` | IMP-MON-001, IMP-MON-004 | 통과 |
| TC-MON-004 | 송신/수신 분리, 7개 사유+기타, 지연 평균·p50·p95·최대, 5 s 창 빈도, 늦은 버킷, 타입별·엔벨로프 수·초기화 (6건) | `src/model/aggregator.test.ts` | IMP-MON-006 | 통과 |
| TC-MON-005 | outcome 필터(빈 필터, any/src/dst, 인터페이스·타입·결과, AND), 엔벨로프 필터(브로드캐스트, 유니캐스트, rx, 결과), toggle (8건) | `src/model/filter.test.ts` | IMP-MON-007 | 통과 |
| TC-MON-006 | 원형 버퍼, outcome → tx 엔벨로프 색인·축출, truth/kill 엔티티 갱신·트리, 링크 상태·SimStatus·무시 계수, 시계 되감기 초기화, 늦은 outcome·링크 지연 (6건) | `src/model/store.test.ts` | IMP-MON-008~010, IMP-MON-023 | 통과 |
| TC-MON-007 | 목 프레임 전부 계약 키로 해석, 시드 결정론, 95 s 동안 7개 사유 모두 발생·전달 수 = rx 수, rx_time, 브로드캐스트 수신자당 outcome (5건) | `src/mock/mockTraffic.test.ts` | IMP-MON-011 | 통과 |
| TC-MON-008 | 타임라인 창·필터·상한, 정지 사본, 레인 순서, 배치·클릭 판정 (4건) | `src/model/timeline.test.ts` | IMP-MON-014 | 통과 |
| TC-MON-009 | 부하 측정: 바이트 프레임 → 해석 → 집계·타임라인·echo (아래 표) | `src/load/monitor.load.ts` (`npm run bench`) | IMP-MON-006, IMP-MON-009, REQ-PRF-001 | 통과(20대 × 50 Hz 실시간 12.7배) |
| TC-MON-010 | 수동 화면 확인(목 소스, 아래 기록) | – | IMP-MON-011~022 | 확인 |
| TC-MON-011 | 실제 브리지·데이터링크 연동(아래 기록) | – | IMP-MON-003, IMP-MON-004, IMP-MON-023 | 확인 |
| TC-MON-012 | 재생 표시: SimStatus 수신 전 `?replay=1`, 수신 후 `replay` 필드, 실행 중 전환 시 머리줄 배지 변경, 수동 전환 해제, 목 `replay` 옵션 (3건) | `src/model/replay.test.ts` | IMP-MON-024 | 통과 |
| TC-MON-013 | 손실률 분모: 브로드캐스트 수신자별 outcome, 거리 밖 제외 계산, 목 브로드캐스트 수신 대상 = 같은 편 무전기 (2건) | `src/model/aggregator.test.ts`, `src/mock/mockTraffic.test.ts` | IMP-MON-025 | 통과 |
| TC-MON-014 | 트래픽 공백은 링크 지연이 아님, 늦은 outcome은 그 지연만 표시하고 5 s 후 해제 (1건) | `src/model/store.test.ts` | IMP-MON-026 | 통과 |
| TC-MON-015 | 프레임 번호 공백 누락 계수·재생 재시작·초기화, waiting_participants 보관 (2건) | `src/model/store.test.ts` | IMP-MON-027 | Superseded by IMP-UI-059 시험 |
| TC-MON-016 | 송신자별 누적 손실률·평균 지연이 독립 단순 계수와 일치, 창 이동(advance)이 누적값을 바꾸지 않음 (1건) | `src/model/aggregator.test.ts` | IMP-MON-028 | 통과 |

`npm test`: 10개 파일 60건 통과. `npm run build`: 통과(tsc -b, vite build).

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

## 연동 확인 기록 (TC-MON-011)

- 대상: 통합 커밋 d7538ef(WP1-2·WP4·WP5·WP6 병합). `swarm_core --autostart --mode realtime --hz 50 --uavs 20`, `swarm_datalink --no-frame-done`(둘 다 msvc-debug), `swarm-bridge --port 8765`, Zenoh. Agent(WP3)가 없어 시험용 생성기가 `truth/state` 시각에 맞춰 UAV마다 PeerStatus p2p 브로드캐스트와 TaskStatus(→gcs-01, 1 Hz)를 tx로 냈다.
- 10 Hz: 연결·계약 0.2.0·SimStatus 표시, 엔티티 21(truth), 엔티티당 송신 11 msg/s·outcome 201/s(수신자 20), 전체 4,020 outcome/s, 지연 평균 20 ms·p95 33 ms, 손실은 버스트만 2.0%. 타임라인 화살표, rx echo의 LinkEnvelope(rxTimeUs)·PeerStatus 해석 확인. 처리 시간 비율 4%.
- 50 Hz: 데이터링크(debug 빌드)가 실시간을 따라가지 못해 outcome tx 시각이 sim 시각보다 수십 초 늦었고 대부분 QUEUE_OVERFLOW였다. 수정 전 모니터는 이를 되감기로 보고 통계를 계속 지웠다(되감기 2,000회 이상). IMP-MON-023 후 되감기 0회, 머리줄에 `링크 지연 29.9 s`, 누적 손실 통계 유지.

## QA-018 재현 시도 기록 (IMP-MON-028)

- 기준: wp0-contracts e60ba45(계약 0.10.0, DEC-044). msvc-debug, `qa_s6_load100_flock`, lockstep ×1(실제 ×0.14~0.22), Bridge 경유 Monitor(`?source=bridge`).
- 같은 창: Monitor `통계 초기화` 직후 `qa/link_count.py --seconds 40`을 동시에 실행. 전체 손실 1.90%·지연 20.0 ms(독립 집계, 439,049건). Monitor 엔티티별 값이 일치(uav-001 2.18%/2.1%, uav-002 2.3%/2.3%, uav-003 1.27%/1.3%, uav-037 0.75%/0.8%, uav-097 2.6%/2.7%, 지연 평균 19.8~20.2 ms). 되감기·프레임 누락 표시 없음.
- Bridge 단독: 같은 40 s에 Zenoh 직접 1.91% vs WebSocket(전체 구독) 1.91% vs WebSocket(outcome만) 1.91%. outcome 편향 없음.
- 결론: e60ba45에서 재현되지 않는다.
