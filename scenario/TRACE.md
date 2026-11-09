# WP7 시나리오 (SCN) 추적표

## 구현

| ID | 내용 | 위치 | 근거 |
|---|---|---|---|
| IMP-SCN-001 | 시나리오 JSON Schema(draft 2020-12): 맵 원점·범위, 실행(mode, frame_hz 50–100, seed, rate, duration_s), 엔티티(proto `EntitySpec` 필드), `MissionPlan`, `EngagementCriteria`. 열거값은 proto 값에서 접두어를 뺀 소문자 | `src/swarm_scenario/schema/scenario.schema.json` | REQ-CFG-001, REQ-CFG-002, PRP-CFG-001, DEC-005 |
| IMP-SCN-002 | 검증기: 스키마 검증 후 의미 검증(ID·payload·task 중복, GCS·담당·표적·편대원 참조, 맵 범위, 한반도 범위, 편대 leader·custom 오프셋). 문제를 JSON Pointer 경로로 보고 | `src/swarm_scenario/validate.py` | REQ-CFG-002, PRP-CFG-001, DEC-016 |
| IMP-SCN-003 | 변환기: JSON → `EntitySpec`·`MissionPlan`·`EngagementCriteria`·`Start`, 역변환(proto → JSON), `sim/ctrl/cmd`용 `LoadScenario`→`Start` 명령 생성. 열거값 변환은 디스크립터를 따라 일반화 | `src/swarm_scenario/convert.py`, `src/swarm_scenario/enums.py` | REQ-CFG-001, REQ-CFG-002, DEC-014 |
| IMP-SCN-004 | 명령행 도구 `swarm-scenario validate/show` | `src/swarm_scenario/cli.py` | REQ-CFG-002 |
| IMP-SCN-005 | 예제 시나리오: 고정익(2-DoF) 20대(2개 편대) + GCS 1 + 지상 표적 4(고정 3, 스크립트 1), 강원 일대, lockstep 50 Hz | `examples/korea_east_strike_20.json` | REQ-PRF-001, DEC-007, DEC-016, DEC-017 |
| IMP-SCN-006 | `swarm.v1.Scenario` 변환(`to_proto`/`from_proto`), `RunSpec.participants` 스키마·변환, `LoadScenario.scenario`로 명령 생성, `swarm-scenario export`(.pb / proto JSON) | `src/swarm_scenario/convert.py`, `cli.py`, `schema/scenario.schema.json` | DEC-024, DEC-025 |
| IMP-SCN-007 | 계약 0.3.0: 최상위 `link_profiles`(swarm.v1.LinkProfile) 스키마·변환 | `src/swarm_scenario/convert.py`, `schema/scenario.schema.json` | DEC-029 |
| IMP-SCN-008 | 계약 0.4.0: `HoldTask` 매개변수, `route`(RouteTask)·`RouteWaypoint`(loiter·recon 중 하나)·`TurnDirection` 스키마. 0.5.0: `RacetrackShape`(hold·loiter) | `schema/scenario.schema.json` | DEC-033, DEC-034 |
| IMP-SCN-009 | 계약 0.6.0: `EntitySpec.dynamics_params` 스키마 | `schema/scenario.schema.json` | DEC-035 |
| IMP-SCN-010 | P5 페이로드 예제 시나리오: 고정익 5기(카메라 eo_wide·eo_narrow·ir_generic, AGM·AAM·FPV 혼합), 이동 지상 표적 3·공중 표적 1(스크립트), 재머 기지 1(아군 경로 중간을 덮음), 카메라 `overrides` 재정의 1건. 엔티티 ID ≤25자 | `examples/p5_payload_demo_5.json` | DEC-046, DEC-017, DEC-019, REQ-PAY-001 |
| IMP-SCN-011 | 미구현 동역학 거부: 스키마·proto는 dof5·dof6를 담지만 검증기가 "미구현(로드맵 P3)"로 거부한다. 허용 목록 `IMPLEMENTED_DYNAMICS` 한 곳에서 관리하며 P3에서 5·6-DoF가 구현되면 여기에 더한다 | `src/swarm_scenario/validate.py` | REQ-CFG-002, DEC-005 |

## 시험

`uv sync --all-packages` 후 `uv run pytest scenario/tests`

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-SCN-001 | 스키마가 draft 2020-12로 유효하고 예제가 검증을 통과하며 구성(UAV ≥20, GCS 1, 지상 표적)을 만족 | `tests/test_validate.py` | IMP-SCN-001, IMP-SCN-005 | Pass |
| TC-SCN-002 | 스키마 위반 16종(필수 누락, ID 형식·길이, frame_hz, 오타 필드, 열거값, 무장 수량, 스크립트 경로, task oneof, realtime 배속, 위도, 빈 엔티티, 버전, Area oneof)을 해당 경로로 보고 | `tests/test_validate.py` | IMP-SCN-001, IMP-SCN-002 | Pass |
| TC-SCN-003 | 의미 위반 15종(중복, 범위, 한반도 밖, 참조 무결성, 편대 규칙)을 해당 경로로 보고, CLI 종료 코드 | `tests/test_validate.py` | IMP-SCN-002, IMP-SCN-004 | Pass |
| TC-SCN-004 | JSON → proto 변환 값 확인(엔티티·payload Struct·스크립트 경로·Start·맵·임무·교전 기준, 선택 항목 생략) | `tests/test_convert.py` | IMP-SCN-003 | Pass |
| TC-SCN-005 | proto → JSON → proto 왕복 일치, GUI식 proto 편집 후 저장·재적재, 잘못된 proto 저장 거부 | `tests/test_convert.py` | IMP-SCN-003, REQ-CFG-002 | Pass |
| TC-SCN-006 | `LoadScenario`·`Start` SimCommand 생성과 직렬화 | `tests/test_convert.py` | IMP-SCN-003 | Pass |
| TC-SCN-007 | 스키마 `$defs`의 필드·열거값·수 타입이 proto 디스크립터와 일치(계약 이탈 감지) | `tests/test_convert.py` | IMP-SCN-001, PRP-CFG-001 | Pass |
| TC-SCN-008 | Scenario ⇄ `swarm.v1.Scenario` 왕복(participants 포함), 최상위 필드 = proto `Scenario`, `MapSpec`·`RunSpec` 필드 일치 | `tests/test_convert.py` | IMP-SCN-006 | Pass |
| TC-SCN-009 | `link_profiles` JSON ⇄ proto 왕복, 적지 않은 필드는 proto에서 미설정, `LinkProfile` 필드 = 스키마 | `tests/test_convert.py` | IMP-SCN-007 | Pass |
| TC-SCN-010 | `RouteTask`·`HoldTask` JSON ⇄ proto 왕복, 항로점 행위 종류, loiter·recon 동시 지정 거부, 레이스트랙 loiter, `RouteWaypoint`·`RacetrackShape`·`TurnDirection` = proto | `tests/test_convert.py` | IMP-SCN-008 | Pass |
| TC-SCN-011 | `dynamics_params`·`fa_params`·`ma_params` JSON ⇄ proto 왕복(수·문자열·불리언) | `tests/test_convert.py` | IMP-SCN-009 | Pass |
| TC-SCN-012 | P5 예제가 스키마·의미 검증을 통과하고 구성(고정익 4~6, 스크립트 표적, 재머), 형식 혼합, 재정의 1건, ID ≤25자, 프로파일·재정의 키가 `payload/profiles`에 있음, 재머가 경로 일부를 덮음 | `tests/test_p5_example.py` | IMP-SCN-010 | Pass |
| TC-SCN-013 | 변환한 .pb를 `swarm_core`가 적재(11 엔티티, 거부 없음)하고 1000 프레임 진행. 빌드가 없으면 건너뜀 | `tests/test_p5_example.py` | IMP-SCN-010, IMP-CORE-022 | Pass |
| TC-SCN-014 | dof5·dof6가 `/entities/N/dynamics` 경로와 "미구현(로드맵 P3)" 메시지로 거부되고(`check`도 예외), 구현된 DoF(dof2·dof3·scripted·static)는 통과, 허용 목록에 dof5·dof6 없음 | `tests/test_validate.py` | IMP-SCN-011 | Pass |

시험 결과(2026-11-05): 78 passed (TC-SCN-012~013 추가, 예제 검증 파라미터화 1건 포함)
