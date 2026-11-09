# 4. MA 플러그인 작성

MA(Mission Autonomy)는 기체 하나 또는 군집의 임무 판단을 맡는 Python 클래스다. 작업을 받아 비행 명령과 장비 명령으로 바꾼다.

모든 예제는 실행되는 코드다. [examples/plugins/](../../examples/plugins/)에 있고 루트 `uv run pytest`에 포함된다.

| 예제 등록명 | 파일 | 보여 주는 것 |
|---|---|---|
| `example_turn` | [turn.py](../../examples/plugins/src/swarm_plugin_examples/turn.py) | 가장 작은 MA, 매개변수 |
| `example_patrol` | [patrol.py](../../examples/plugins/src/swarm_plugin_examples/patrol.py) | `TaskPilot` 재사용, 작업 상태 보고 |
| `example_rendezvous` | [rendezvous.py](../../examples/plugins/src/swarm_plugin_examples/rendezvous.py) | 일괄 MA, P2P 이웃 정보 |

## 4.1 따라 하기

```mermaid
flowchart LR
    A["클래스 작성<br/>MissionAutonomy 상속"] --> B["pyproject.toml<br/>entry point swarm.ma"]
    B --> C["uv sync"]
    C --> D["swarm-agent --list-plugins<br/>이름 확인"]
    D --> E["시나리오<br/>autonomy.ma_plugin"]
    E --> F["실행"]
```

**1. 클래스를 쓴다.** `on_step`만 필수다. 전체 파일은 [turn.py](../../examples/plugins/src/swarm_plugin_examples/turn.py).

```python
class TurnToHeading(MissionAutonomy):
    PARAMS = (
        ParamDef("heading_deg", 90.0, ParamLayer.BEHAVIOR, "deg", 0.0, 360.0, "목표 침로"),
    )

    def on_init(self, ctx: AgentContext) -> None:
        self.heading_deg = float(ctx.params.get("heading_deg", 90.0))
        self.sent = False

    def on_step(self, ctx: AgentContext) -> None:
        ctx.ports.c2.inbox()
        ctx.ports.vi.command_status()
        nav = ctx.ports.vi.nav()
        if self.sent or nav is None:
            return
        k = nav.kinematics
        cmd = vi_pb2.FlightCommand(command_id=f"{ctx.entity_id}-turn")
        cmd.hsa.heading_deg = self.heading_deg
        cmd.hsa.altitude_m = k.position.alt_m
        cmd.hsa.speed_mps = math.hypot(k.velocity_ned_mps.x, k.velocity_ned_mps.y)
        ctx.ports.vi.command(cmd)
        self.sent = True
```

**2. 등록한다.** 패키지의 [pyproject.toml](../../examples/plugins/pyproject.toml)에 entry point를 적는다. 왼쪽이 시나리오에 쓰는 이름이다.

```toml
[project.entry-points."swarm.ma"]
example_turn = "swarm_plugin_examples.turn:TurnToHeading"
```

새 패키지를 저장소에 둘 때는 루트 `pyproject.toml`의 네 곳에 추가한다: `tool.uv.workspace.members`, `tool.uv.sources`, `dependency-groups.dev`, `tool.pytest.ini_options.testpaths`.

**3. 설치하고 이름을 확인한다.**

```bash
uv sync
```

```bash
uv run swarm-agent --list-plugins
```

```text
swarm.ma: example_patrol, example_rendezvous, example_turn, flocking, flocking_basic, formation, hold, waypoint
swarm.fa: default, example_hsa
```

**4. 시나리오에서 고른다.** 예제 전부를 쓰는 시나리오는 [examples_all.json](../../examples/plugins/scenarios/examples_all.json)이다.

```json
"autonomy": { "ma_plugin": "example_turn", "ma_params": { "heading_deg": 120.0 } }
```

**5. 실행한다.** 시나리오를 `.pb`로 바꾼 뒤 터미널마다 하나씩 띄운다. Core의 `--rate 0`은 최대 속도, `--frames 3000`은 모의 시간 60초다.

```bash
uv run swarm-scenario export examples/plugins/scenarios/examples_all.json --out out/examples.pb
```

```bash
build/msvc-debug/datalink/swarm_datalink --no-multicast --listen tcp/127.0.0.1:17601
```

```bash
uv run swarm-agent --frames 3000 --no-multicast --listen tcp/127.0.0.1:17602 --connect tcp/127.0.0.1:17601
```

```bash
build/msvc-debug/core/swarm_core --scenario out/examples.pb --autostart --rate 0 --frames 3000 --no-multicast --listen tcp/127.0.0.1:17603 --connect tcp/127.0.0.1:17601 --connect tcp/127.0.0.1:17602
```

Agent 로그에 `hosting 4 vehicles`와 마지막의 `ticks=3000`이 나오면 정상이다. Datalink는 Ctrl+C로 끝낸다.

## 4.2 호출 순서

```mermaid
sequenceDiagram
    participant R as Agent 런타임
    participant M as MA
    participant F as FA
    R->>F: on_init(entity_id, params) (시나리오 적재 시)
    F-->>R: FlightCapability
    Note over R,M: 첫 틱
    R->>M: on_init(ctx)
    loop 틱마다
        opt 매개변수 변경이 있으면
            R->>M: on_params(ctx, changed)
        end
        R->>M: on_step(ctx)
        M->>F: ctx.ports.vi.command(cmd) → on_command
        F-->>M: 상태는 다음 command_status()로 받는다
        R->>F: step(nav, dt) (이번 틱에 항법 보고를 받은 기체만)
        F-->>R: ControlOutput
    end
    R->>M: on_shutdown(ctx)
```

- 한 프레임에서 MA는 기체 ID 순으로 호출되고, 일괄 MA는 그 뒤에 플러그인 이름 순으로 호출된다.
- `on_step`은 틱마다 불린다. 항법 보고가 아직 없으면 `nav()`가 `None`이다.
- 플러그인이 던진 예외는 로그에 남고 프로세스는 계속된다(DEC-038). 시험의 `Harness`는 `strict` 모드라 예외를 그대로 던진다.

## 4.3 AgentContext와 포트

플러그인은 `ctx.ports`로만 외부와 통신한다(DEC-013). 버스나 `truth/**`에 직접 접근하지 않는다.

| `ctx` 필드 | 뜻 |
|---|---|
| `entity_id` | 이 기체 ID |
| `frame`, `sim_time_s`, `dt_s` | 프레임 번호, 모의 시각, 프레임 간격 |
| `params` | 기본값을 채운 현재 매개변수. `on_params`가 불릴 때는 이미 새 값이다 |
| `rng` | 시드가 고정된 `numpy.random.Generator`. lockstep 결정론을 지키려면 난수는 이것만 쓴다 |
| `ports` | 아래 6종 |

| 포트 | 메서드 | 내용 |
|---|---|---|
| `c2` | `inbox()`, `send(msg)` | 통제 GCS의 작업 수신, `TaskStatus` 등 송신 |
| `vi` | `nav()`, `capability()`, `system_status()`, `command(cmd)`, `command_status()` | 항법 보고, FA 능력, 기체 상태, 비행 명령과 그 상태 |
| `ms` | `loadout()`, `detections()`, `command(msg)`, `activities()` | 탑재 장비 목록, 탐지 결과, 장비 명령(`SensorCommand`, `JammerCommand`, `StrikeCommand`), 장비 상태 |
| `mp` | `mission_plan()`, `route_plans()`, `engagement_criteria()` | 시나리오의 계획 |
| `p2p` | `send(msg, to=None)`, `inbox()` | 기체 간 통신. `to`가 없으면 방송. 데이터링크를 거쳐 손실·지연이 있다 |
| `md` | `record(name, value)` | 분석용 값 기록 |

- 다른 기체 상태는 `p2p`로 받은 것만 쓴다. `nav()`는 잡음이 포함된 자기 항법값이다.
- 수신함은 매 프레임 비운다. 쓰지 않아도 호출해 두면 다음 프레임에 쌓이지 않는다.
- 비행 명령 모드는 [5.2](05_fa_plugin.md#52-vi-제어-모드)에 있다.

## 4.4 매개변수

클래스 속성 `PARAMS`에 `ParamDef`를 선언한다. UI 매개변수 패널은 이 선언으로 그려진다.

```python
ParamDef("idle_radius_m", 400.0, ParamLayer.BEHAVIOR, "m", 50.0, 100000.0, "작업이 없을 때 선회 반경")
```

| 인자 | 뜻 |
|---|---|
| `name`, `default`, `layer` | 이름, 기본값(형식도 여기서 정해진다), 계층 |
| `unit`, `min`, `max`, `description` | 단위, 범위, 설명 |
| `runtime` | `False`면 실행 중 변경 불가. 기본 `True` |
| `choices` | 문자열 매개변수의 허용 값 |

- 계층 `ParamLayer`: `AIRFRAME`, `CONTROL`, `GUIDANCE`, `BEHAVIOR`, `DECISION`.
- 실행 중 값이 바뀌면 프레임 시작에 `on_params(ctx, changed)`가 불린다. `changed`에는 바뀐 항목만 있다.
- 거부 사유는 `unknown`, `type`, `range`, `choice`, `not_runtime`이다. 값 결정 순서는 [3.8](03_architecture.md#38-기체별-매개변수).

## 4.5 일괄 MA

기체가 많으면 `BatchMissionAutonomy`로 한 번에 처리한다. 같은 플러그인을 쓰는 같은 호스트의 기체가 묶인다.

```python
class Rendezvous(BatchMissionAutonomy):
    def on_step_batch(self, ctxs: Sequence[AgentContext], nav: NavBatch) -> None:
        ...
```

- `NavBatch`: `ids`, `lat_lon_alt`(N×3), `velocity_ned`(N×3), `valid`(N). 행 `i`가 `ctxs[i]`다.
- 송수신은 `ctxs[i].ports`로 기체마다 따로 한다.
- `NavBatch`에서 **자기 행만** 쓴다. 다른 행을 이웃 정보로 쓰면 데이터링크 모의를 건너뛰게 된다(DEC-008). [rendezvous.py](../../examples/plugins/src/swarm_plugin_examples/rendezvous.py)가 그 형태다.
- 일괄 MA의 `on_init`, `on_shutdown`은 `ctxs`를, `on_params`는 기체 하나의 `ctx`를 받는다.

## 4.6 작업과 TaskStatus

`c2.inbox()`로 받은 `TaskCommand`에 `TaskStatus`로 답한다.

```mermaid
stateDiagram-v2
    [*] --> ACCEPTED: 지원하는 작업
    [*] --> REJECTED: 미지원·잘못된 작업
    ACCEPTED --> EXECUTING
    EXECUTING --> COMPLETED
    EXECUTING --> FAILED
    ACCEPTED --> CANCELLED: 취소·선점
    EXECUTING --> CANCELLED: 취소·선점
    REJECTED --> [*]
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

- 지원하지 않는 작업은 `REJECTED`로 답한다. 조용히 무시하면 운용자는 왜 안 움직이는지 알 수 없다.
- `assignees`가 비어 있는 작업은 거부한다. 자기가 없는 작업은 무시한다.
- 같은 `task_id`가 다시 오면 내용을 바꾼다. 이전 작업을 취소로 보고하지 않는다(DEC-033).
- `cancel`이 참이면 해당 작업을 `CANCELLED`로 끝낸다.

## 4.7 재사용 부품

위 규칙은 [algorithms/src/swarm_algorithms/common.py](../../algorithms/src/swarm_algorithms/common.py)에 구현돼 있다.

| 부품 | 맡는 일 |
|---|---|
| `TaskTracker(ctx, supported)` | `MissionPlan` 순차 수행, C2 작업 선점·취소·거부, `TaskStatus` 송신. `handle(msg)`, `update(nav)`, `status(...)`, `finish(...)` |
| `TaskPilot(ctx, acceptance_m, hold_radius_m, speed_mps, supported)` | `TaskTracker`에 비행 수행까지 더한 것. `step()` 호출 하나로 MoveTo, Hold, RTB, SearchArea, Route를 처리 |
| `every(ctx, hz)` | 기체마다 위상을 달리한 주기 판정 |
| `peer_status(nav, group_id, task_id)` | `PeerStatus` 구성 |

[patrol.py](../../examples/plugins/src/swarm_plugin_examples/patrol.py)는 `self.pilot.step()`만 부르고, 작업이 없을 때의 행동만 직접 정한다.

## 4.8 기본 MA

| 이름 | 파일 | 동작 | 매개변수 |
|---|---|---|---|
| `hold` | [hold.py](../../algorithms/src/swarm_algorithms/hold.py) | 첫 항법 상태의 침로·속도·고도 유지. 작업을 처리하지 않는다 | `orbit_radius_m`(0이면 직진) |
| `waypoint` | [waypoint.py](../../algorithms/src/swarm_algorithms/waypoint.py) | `TaskPilot`으로 작업 수행 | `acceptance_m`, `hold_radius_m`, `speed_mps` |
| `formation` | [formation.py](../../algorithms/src/swarm_algorithms/formation.py) | 리더-추종 편대. 리더는 `waypoint`처럼, 추종기는 슬롯을 HSA로 추종 | `group`, `peer_hz`, `leader_speed_mps`, `leader_timeout_s`, `corr_max_mps` 등 |
| `flocking` | [flocking.py](../../algorithms/src/swarm_algorithms/flocking.py) | Reynolds 분리·정렬·응집 일괄 MA. Route는 거부 | `cruise_mps`, `neighbor_radius_m`, `separation_m`, `w_sep`, `w_align`, `w_coh`, `peer_hz`, `stale_s`, `goal_radius_m`, `hold_radius_m`, `wander_deg`, `group` |

`flocking_basic`은 예제 시나리오용 변형이다. 전체 항목은 [algorithms/TRACE.md](../../algorithms/TRACE.md).

`formation`의 슬롯은 리더 FRD 기준 오프셋이다. `s`는 `spacing_m`, `k`는 추종기 순번(0부터)이다.

![편대 모양 6종](../img/manual/dev/formation_shapes.svg)

| 모양 | 오프셋 (전방, 우측) |
|---|---|
| `LINE` | (0, ±s·⌈(k+1)/2⌉), 짝수 k가 오른쪽 |
| `COLUMN` | (−s(k+1), 0) |
| `WEDGE` | (−s·r, ±s·r), r = ⌊k/2⌋+1 |
| `ECHELON` | (−s(k+1), s(k+1)) |
| `CIRCLE` | 리더 둘레 반경 s 등간격 |
| `CUSTOM` | `custom_offsets_m`, `members` 순서 |

## 4.9 단위 시험

`swarm_agent.testing`의 `Harness`가 가짜 Core와 Datalink로 런타임을 돌린다. 프로세스도 Zenoh도 필요 없다. 전체는 [test_plugin_examples.py](../../examples/plugins/tests/test_plugin_examples.py).

```python
from swarm_agent.testing import Harness, make_scenario, send_c2

def test_turn():
    h = Harness(make_scenario(1, "example_turn", {"heading_deg": 200.0}, course_deg=45.0))
    h.run_s(60.0)
    b = h.core.bodies["uav-001"]
    assert math.degrees(b.course) % 360.0 == pytest.approx(200.0, abs=1.0)
```

| 도구 | 쓰임 |
|---|---|
| `make_scenario(n, ma_plugin, ma_params, ...)` | 기체 `uav-001`.. n대와 `gcs-01` |
| `Harness(sc)` | 시나리오 적재까지 수행. `run_s(초)`로 진행 |
| `h.core.bodies[id]` | 현재 `lat`, `lon`, `alt`, `course`, `speed` |
| `send_c2(h.bus, "gcs-01", msg, [대상])` | GCS가 보낸 메시지 주입. 대상은 목록이다 |
| `h.task_states(task_id)`, `h.gcs_rx` | GCS가 받은 작업 상태, 전체 수신 메시지 |
| `Harness(sc, drop=...)` | `(src, dst, msg)` 판정 함수로 링크 손실 주입 |

```bash
uv run pytest examples/plugins/tests
```

> 미구현: C++ MA 플러그인. ABI 헤더만 있고 로딩 경로가 없다.

다음: [5. FA 플러그인 작성](05_fa_plugin.md).
