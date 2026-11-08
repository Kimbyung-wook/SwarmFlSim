# 개발자 매뉴얼

- 독자: 알고리즘 플러그인 작성자(MA/FA를 Python으로 쓴다), WP 기여자(특정 디렉터리를 고치고 시험·추적·계약 규칙을 지킨다).
- 처음이면 프로젝트 개괄(`../40_overview.md`, 작성 예정)을 먼저 읽는다.
- 계약(키·스키마·프로토콜·빌드 설치)은 [10_contracts.md](../10_contracts.md)가 기준이다. 이 매뉴얼은 그 절로 링크한다.
- 작성 계획: [30_doc_plan.md](../30_doc_plan.md) §4. 영문판: [en/41_dev](../en/41_dev/README.md).

## 읽는 순서

| 독자 | 순서 |
|---|---|
| 알고리즘 플러그인 작성자 | 1 → 2(Python 부분) → 3 → 4 → 5 |
| WP 기여자 | 1 → 2 → 3 → 8(자기 WP) → 9 → 10 |

## 장 목록

| 장 | 파일 | 내용 | 상태 |
|---|---|---|---|
| 1 | `01_setup.md` | 개발 환경: 툴체인 선택, 설치, 흔한 실패 | 작성 예정 |
| 2 | `02_build_test.md` | 빌드와 시험: C++·Python·UI·Gateway, 코드 생성물 | 작성 예정 |
| 3 | `03_architecture.md` | 아키텍처와 실행 모델: 프로세스, 버스 키 접근 규칙, 실행 모드, lockstep | 작성 예정 |
| 4 | `04_ma_plugin.md` | MA 플러그인 작성: 따라 하기, 포트, 매개변수, 일괄 호출, 시험. 예제 패키지 `examples/plugins/`(DEC-070) | 작성 예정 |
| 5 | `05_fa_plugin.md` | FA 플러그인 작성: VI 제어 모드, 기본 FA | 작성 예정 |
| 6 | `06_dynamics.md` | 동역학 모델 추가: 인터페이스, 팩토리, 매개변수, 시험 | 작성 예정 |
| 7 | `07_messages.md` | 메시지와 계약: proto 역할, A-GRA 매핑 옵션, 메시지 추가 절차 | 작성 예정 |
| 8 | `08_wp/` | WP별 기여 안내(아래 표) | 작성 예정 |
| 9 | `09_contributing.md` | 기여 규칙: ID, TRACE, 커밋, 계약 변경 요청 | 작성 예정 |
| 10 | `10_qa.md` | QA 하니스: `qa/run_qa.py`, 시나리오, 결정성 진단 | 작성 예정 |
| 11 | `11_troubleshooting.md` | 문제 해결: 증상 → 원인 → 조치 | 작성 예정 |

### 8장 WP별 파일 (`08_wp/`)

| 파일 | WP | 디렉터리 | 상태 |
|---|---|---|---|
| `core.md` | WP1 Sim Core | `core/` | 작성 예정 |
| `dynamics.md` | WP2 동역학 | `dynamics/` | 작성 예정 |
| `datalink.md` | WP4 데이터링크 | `datalink/` | 작성 예정 |
| `agent.md` | WP3 Agent 런타임 | `agent/` | 작성 예정 |
| `algorithms.md` | WP3 기본 알고리즘 | `algorithms/` | 작성 예정 |
| `bridge.md` | WP5 WebSocket 브리지 | `bridge/` | 작성 예정 |
| `ui.md` | WP5 GCS/UI | `ui/` | 작성 예정 |
| `monitor.md` | WP6 Traffic Monitor | `ui/monitor/` | 작성 예정 |
| `scenario.md` | WP7 시나리오 | `scenario/` | 작성 예정 |
| `logger.md` | WP7 기록·재생 | `logger/` | 작성 예정 |
| `payload.md` | WP8 센서·재머·시뮬레이션 이벤트 | `payload/` | 작성 예정 |
| `gateway.md` | WP9 A-GRA Gateway | `gateway/` | 작성 예정 |
| — | QA | `qa/` | 10장으로 대체 |

## 그림

- 그림 파일은 [../img/manual/dev/](../img/manual/dev/)에 둔다.
