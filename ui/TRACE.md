# WP5 GCS/UI 추적표

- 브랜치: `wp5-ui` (기준 `wp0-contracts` 94808ba)
- 계약 버전: 0.1.0. `proto/`, `api/`, `docs/`는 바꾸지 않았다.

## 구현 (IMP)

| ID | 내용 | 위치 | 근거 | 시험 |
|---|---|---|---|---|
| IMP-UI-001 | proto/swarm/v1 → TS 생성(protobuf-es, buf CLI는 node_modules) | `scripts/gen-proto.mjs`, `buf.gen.yaml` | REQ-NET-001, DEC-003 | TC-UI-002, TC-UI-008 |
| IMP-UI-002 | Vite 설정: Cesium 정적 자산 복사, `/data/**` 오프라인 데이터 제공(gzip 지형) | `vite.config.ts` | DEC-003, DEC-004, DEC-016 | TC-UI-009 |
| IMP-UI-003 | 자세·방향 변환(ZYX 오일러 ⇄ NED→FRD 쿼터니언, NED 속도 → 진행 방향·상승각) | `src/model/attitude.ts` | REQ-UI-001, REQ-UI-007 | TC-UI-001 |
| IMP-UI-004 | TruthFrame → 전시용 엔티티 뷰 | `src/model/entityView.ts` | REQ-UI-001, PRP-SIM-003 | TC-UI-002 |
| IMP-UI-005 | 궤적 꼬리(sim 시각 간격 샘플, 최대 점 수, 되감기 시 초기화) | `src/model/trails.ts` | REQ-UI-001 | TC-UI-003 |
| IMP-UI-006 | RTS 선택 로직(클릭·박스, 아군 기체 우선, replace/add/toggle) | `src/model/selection.ts` | REQ-UI-002, PRP-UI-001 | TC-UI-004 |
| IMP-UI-007 | 카메라 시점 구조(free/chase/fpv/gimbal, 쿼터니언 사용) | `src/model/camera.ts` | REQ-UI-007 | TC-UI-007 |
| IMP-UI-008 | 데이터 소스 추상화(truth/state, sim/ctrl/status 수신, sim/ctrl/cmd 송신) | `src/data/source.ts` | REQ-UI-001, DEC-002 | TC-UI-006, TC-UI-008 |
| IMP-UI-009 | 목 시나리오(UAV 4편대×6, GCS, 지상표적, 공중표적, 재밍기지 = 32개, 해석해·결정론) | `src/data/mockScenario.ts` | REQ-UI-001 | TC-UI-005 |
| IMP-UI-010 | 목 데이터 소스(실시간 진행, Start/Pause/Resume/Step/SetRate/Reset) | `src/data/mockSource.ts` | REQ-UI-001, DEC-005, DEC-014 | TC-UI-006 |
| IMP-UI-011 | 버스 데이터 소스 자리(BusTransport 인터페이스, 키·인코딩). 전송 계층은 README 제안 | `src/data/busSource.ts` | DEC-002, REQ-NET-001 | TC-UI-008 |
| IMP-UI-012 | 종류·진영별 SVG 아이콘(선택 링, 파괴 표시) | `src/model/symbology.ts` | REQ-UI-001 | TC-UI-008 |
| IMP-UI-013 | 오프라인 Viewer(로컬 TMS·quantized-mesh 판정, 없으면 Natural Earth II·타원체), RTS 카메라 입력 | `src/cesium/viewer.ts` | DEC-003, DEC-004, DEC-016, REQ-SIM-003 | TC-UI-009 |
| IMP-UI-014 | 엔티티 전시 레이어(Billboard 진행 방향, Polyline 궤적, Label, 화면 투영, 카메라 추종) | `src/cesium/entityLayer.ts` | REQ-UI-001, REQ-UI-007 | TC-UI-009 |
| IMP-UI-015 | 수신 상태 보관소(최신 프레임·궤적, React 재렌더 분리) | `src/model/liveState.ts` | REQ-UI-001 | TC-UI-009 |
| IMP-UI-016 | 지도 뷰(렌더 루프 갱신, 클릭·드래그 박스 입력, 2D/2.5D/3D 전환) | `src/components/MapView.tsx` | REQ-UI-001, REQ-UI-002 | TC-UI-009 |
| IMP-UI-017 | 선택 목록 패널(상태 표시, 지도 이동, 추적·1인칭 전환) | `src/components/SelectionPanel.tsx` | REQ-UI-002, REQ-UI-007 | TC-UI-009 |
| IMP-UI-018 | 도구 막대(시점 전환, 일시정지·배속 SimCommand, 상태·지도 데이터 표시) | `src/components/Toolbar.tsx` | REQ-UI-001, DEC-014 | TC-UI-009 |
| IMP-UI-019 | 화면 구성, UI 인스턴스 ID(issuer), 단축키 | `src/App.tsx` | REQ-UI-001, REQ-UI-002, DEC-020 | TC-UI-009 |

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
| TC-UI-008 | 버스 소스 디코드·인코드·키·encoding, 미구현 전송 실패, 아이콘 (4건) | `src/data/busSource.test.ts` | IMP-UI-001, IMP-UI-011, IMP-UI-012 | 통과 |
| TC-UI-009 | 수동: `npm run dev`에서 목 소스 32개(UAV 24) 이동 전시, 궤적, 박스 선택 6대·패널, 2D 전환, 추적·1인칭 시점과 아이콘 방향, 로컬 데이터 없음 → 내장 영상·타원체 | 브라우저 확인 | IMP-UI-002, IMP-UI-013~019 | 통과 |

- 자동 시험: `npm test` 8개 파일 38건 통과 (vitest 5.0.5). `npm run build` 통과 (tsc 7.0.2, vite 8.3.5).
