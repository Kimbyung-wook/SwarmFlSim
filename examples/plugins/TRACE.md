# 플러그인 예제 추적표 (모듈 EXP)

- 패키지 `swarm-plugin-examples`, 루트 uv 워크스페이스 멤버 (DEC-070).
- 개발자 매뉴얼 [4장](../../docs/41_dev/04_ma_plugin.md), [5장](../../docs/41_dev/05_fa_plugin.md)이 이 파일을 가리킨다.
- `algorithms/`와 `agent/`의 공개 부품만 쓴다. 두 패키지는 고치지 않았다.
- 모듈 코드 `EXP`는 이 패키지에서 처음 쓴다.

## IMP

| ID | 내용 | 위치 | 근거 | 시험 결과 |
|---|---|---|---|---|
| IMP-EXP-001 | MA `example_turn`: 정해진 침로로 돌고 속도·고도 유지. `PARAMS`·`on_params` 예제 | `src/swarm_plugin_examples/turn.py` | DEC-070, REQ-BHV-004 | TC-EXP-002, 006 통과 |
| IMP-EXP-002 | MA `example_patrol`: `TaskPilot` 재사용, 작업이 없으면 선회. `md.record` 예제 | `src/swarm_plugin_examples/patrol.py` | DEC-070, REQ-BHV-004 | TC-EXP-003, 004 통과 |
| IMP-EXP-003 | MA `example_rendezvous`: `BatchMissionAutonomy`, P2P로 받은 이웃과의 평균 위치로 이동 | `src/swarm_plugin_examples/rendezvous.py` | DEC-070, DEC-008 | TC-EXP-005 통과 |
| IMP-EXP-004 | FA `example_hsa`: HSA만 처리, 다른 모드 REJECTED | `src/swarm_plugin_examples/hsa_fa.py` | DEC-070, REQ-GNC-001 | TC-EXP-006, 007 통과 |

## TC

| ID | 내용 | 위치 | 대상 | 시험 결과 |
|---|---|---|---|---|
| TC-EXP-001 | entry point `swarm.ma` 3종, `swarm.fa` 1종 등록 | `tests/test_plugin_examples.py` | 패키지 | 통과 |
| TC-EXP-002 | `example_turn`: 60 s 뒤 침로 200°±1°, 고도 ±1 m | 같은 파일 | IMP-EXP-001 | 통과 |
| TC-EXP-003 | `example_patrol`: MoveTo가 ACCEPTED로 시작해 COMPLETED로 끝남 | 같은 파일 | IMP-EXP-002 | 통과 |
| TC-EXP-004 | `example_patrol`: 지원하지 않는 Track을 REJECTED | 같은 파일 | IMP-EXP-002 | 통과 |
| TC-EXP-005 | `example_rendezvous`: 대각 기체 간 거리가 45 s 뒤 70% 미만 | 같은 파일 | IMP-EXP-003 | 통과 |
| TC-EXP-006 | `example_hsa`로 `example_turn`의 HSA 명령 비행, 침로 120°±1° | 같은 파일 | IMP-EXP-001, 004 | 통과 |
| TC-EXP-007 | `example_hsa`: Curve 명령 REJECTED, 능력 보고에 HSA만 표시 | 같은 파일 | IMP-EXP-004 | 통과 |

## 실행 확인

| 항목 | 명령 | 결과 (msvc-debug, 2026-11-09) |
|---|---|---|
| 등록 | `uv run swarm-agent --list-plugins` | 예제 MA 3종, FA 1종 표시 |
| 시험 | `uv run pytest` (루트) | 279건 통과, 예제 7건 포함 |
| 실제 프로세스 | `scenarios/examples_all.json`을 Core·Datalink·Agent로 lockstep 3000프레임 | Core·Agent 정상 종료, `uav-patrol`의 TaskStatus 3건 기록 |
