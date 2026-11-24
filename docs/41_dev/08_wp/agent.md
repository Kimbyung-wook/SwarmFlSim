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
| `src/swarm_agent/fa.py` | 기본 FA. 레이스트랙 기하는 `swarm_api.racetrack`(DEC-104). `racetrack.py`, `geo.py`는 호환 별칭 |
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
| `--profile <file>` | 틱 단계별 계측 JSON 경로, 기본 꺼짐. 환경 변수 `SWARM_AGENT_PROFILE`로도 켠다([10.5](../10_qa.md#105-성능-측정)) |
| `--list-plugins` | 등록된 MA·FA 출력 |
| `-v` | 자세한 로그 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `sim/clock/tick`, `sim/ctrl/cmd`, `sim/ctrl/scenario`, `onboard_batch/NavigationBatch`, `onboard/<id>/Detection`, `*Activity`, `SystemStatus`, `StoreLoadout`, `swarm/<id>/rx/**` |
| 발행 | `swarm/<id>/tx/**`, `onboard_batch/ControlBatch/<p>`(틱당 1건, `FrameDone` 전), `onboard/<id>/*Command`, `sim/param/<id>/fa`, `sim/param/<id>/ma`, `sim/clock/done/<p>` |

`truth/**`와 `link/**`는 구독하지 않는다. 모든 구독은 `ordered=True`로 연다(DEC-083, [3.2](../03_architecture.md#32-버스-열기)).

기체 쪽 구독은 맡은 기체마다 따로 연다. 기체 하나에 `onboard/<id>/<메시지>`(수신 탑재 메시지마다)와 `swarm/<id>/rx/**`이고, 엔티티 자리 와일드카드는 쓰지 않는다(DEC-100, 계약 0.21.0, IMP-AGT-052). 기체 100대를 Agent 하나가 맡으면 구독이 700개다. 전 기체를 맡을 때 `onboard/*/<메시지>`·`swarm/*/rx/**`로 묶던 방식(IMP-AGT-043)은 없앴다. 실제 기체처럼 자기 앞 수신만 받게 하기 위해서다. Zenoh는 put마다 세션의 구독 전체와 키를 맞춰 보므로 구독 수가 put 비용에 영향을 준다. 이 변경 뒤의 성능 판정은 QA 재측정 중이다.

변화 보고에 더한 것(DEC-088, DEC-089):

- `StoreLoadout`: Payload가 보낸 `onboard/<id>/StoreLoadout`을 받은 뒤로는 그 값이 `ms.loadout()`의 기준이고, 런타임이 발사로 잔량을 따로 줄이지 않는다. 적재가 있는 기체만 시작할 때와 값이 바뀔 때 `tx/ms/StoreLoadout`으로 통제 GCS에 보낸다(IMP-AGT-048).
- 링크 복구 재보고: `GcsHeartbeat`가 MA 변수 `lost_link_timeout_s`(기본 5 s)보다 오래 끊겼다 다시 오면 다음 GCS 보고 때 그 기체의 변화 보고 키 전체와 `FlightCapability`를 한 번 다시 보낸다. 종료 상태로 지운 키는 대상이 아니다(IMP-AGT-049). 여기에 더해 기체의 마지막 `FlightCommandStatus`(이미 보내 지운 종료 상태여도)와, MA가 C2 포트로 보낸 진행 중 작업의 마지막 `TaskStatus`를 task_id 순으로 한 번 다시 보낸다(DEC-101(1), IMP-AGT-054). 종료 상태를 보낸 작업은 목록에서 지운다.

## 시험

```bash
uv run pytest agent/tests
```

성능 측정 도구는 `agent/bench/`에 있다.

## 알려진 제약

- `md.record`는 런타임 메모리에만 남는다. 버스나 MCAP으로 나가지 않는다.
- 고도 필드는 "미지정"을 표현할 수 없어 `alt_m <= 0`을 현재 고도 유지로 해석한다.
- 링크 상실 행동은 MA 공용 부품(`algorithms`)에 있고 런타임에는 없다. 사용자 MA가 그 부품을 쓰지 않으면 상실 행동도 없다([4장](../04_ma_plugin.md#48-기본-ma)).
- MP 포트는 최신 계획만 들고 있다. 한 틱에 `MissionPlan` 두 개가 닿으면 마지막 것만 실행된다.
- 기체 수가 많으면 Agent를 나눈다. 시나리오의 `participants`에 모두 적는다.
- lockstep의 onboard 입력 처리 틱은 [3.6](../03_architecture.md#36-lockstep-한-프레임)을 따른다. `late_onboard` 값은 외부로 나오지 않고 첫 건의 경고만 로그에 남는다.

추적: [agent/TRACE.md](../../../agent/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
