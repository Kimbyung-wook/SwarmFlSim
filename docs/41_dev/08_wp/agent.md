# 8. WP3 Agent 런타임 (`agent/`)

## 책임

한 프로세스가 여러 기체를 맡아 기체마다 MA와 FA를 돌린다. 포트 구현, 매개변수, GCS 상태 보고, lockstep FrameDone을 맡는다. 플러그인 작성은 [4장](../04_ma_plugin.md), [5장](../05_fa_plugin.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/swarm_agent/cli.py` | 진입점, 옵션 |
| `src/swarm_agent/runtime.py` | `AgentRuntime`, 프레임 처리 순서 |
| `src/swarm_agent/vehicle.py` | 기체 한 대의 상태 |
| `src/swarm_agent/ports.py` | 포트 6종 구현 |
| `src/swarm_agent/fa.py`, `racetrack.py` | 기본 FA |
| `src/swarm_agent/plugins.py` | entry point 로딩 |
| `src/swarm_agent/params.py` | 기체별 매개변수 |
| `src/swarm_agent/reporting.py` | GCS 상태 보고(DEC-056, DEC-071) |
| `src/swarm_agent/testing.py` | `Harness`, `FakeCore`, `FakeDatalink` |

프레임 처리 순서는 `runtime.py` 머리 주석과 `_step`을 본다.

## 실행 파일 `swarm-agent`

| 옵션 | 뜻 |
|---|---|
| `--scenario <file>` | 시작할 때 읽을 시나리오. 없으면 버스에서 받는다 |
| `--participant <id>` | 기본 `agent-0` |
| `--entities <ids>` | 맡을 기체, 쉼표 구분·반복 가능 |
| `--frames <n>` | n 틱 뒤 종료 |
| `--activity-max-hz <hz>` | 상태 변화 보고의 키별 최대 빈도, 기본 10 |
| `--vi-report-hz <hz>` | `NavigationReport` GCS 보고 빈도, 기본 1, 0 이하면 끔 |
| `--list-plugins` | 등록된 MA·FA 출력 |
| `-v` | 자세한 로그 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `sim/clock/tick`, `sim/ctrl/cmd`, `sim/ctrl/scenario`, `onboard/<id>/NavigationReport`, `Detection`, `*Activity`, `SystemStatus`, `swarm/<id>/rx/**` |
| 발행 | `swarm/<id>/tx/**`, `onboard/<id>/ControlOutput`, `onboard/<id>/*Command`, `sim/param/<id>/fa`, `sim/param/<id>/ma`, `sim/clock/done/<p>` |

`truth/**`와 `link/**`는 구독하지 않는다.

## 시험

```bash
uv run pytest agent/tests
```

성능 측정 도구는 `agent/bench/`에 있다.

## 알려진 제약

- `md.record`는 런타임 메모리에만 남는다. 버스나 MCAP으로 나가지 않는다.
- 고도 필드는 "미지정"을 표현할 수 없어 `alt_m <= 0`을 현재 고도 유지로 해석한다.
- 링크 상실 시 기체 행동은 미구현이다(로드맵 P2).
- MP 포트는 최신 계획만 들고 있다. 한 틱에 `MissionPlan` 두 개가 닿으면 마지막 것만 수행된다.
- 기체 수가 많으면 Agent를 나눈다. 시나리오의 `participants`에 모두 적는다.
- lockstep의 onboard 입력 처리 틱은 [3.6](../03_architecture.md#36-lockstep-한-프레임)을 따른다. `late_onboard` 값은 외부로 나오지 않고 첫 건의 경고만 로그에 남는다.

추적: [agent/TRACE.md](../../../agent/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
