# 8. WP3 기본 알고리즘 (`algorithms/`)

## 책임

기본 MA 플러그인과 공용 부품을 둔다. 런타임은 [agent](agent.md)가 맡는다. 플러그인 해설은 [4.8](../04_ma_plugin.md#48-기본-ma).

## 구조

| 경로 | 내용 |
|---|---|
| `src/swarm_algorithms/common.py` | `TaskTracker`, `TaskPilot`, `PlanWatcher`, `peer_status`, `every` |
| `src/swarm_algorithms/hold.py` | `hold` |
| `src/swarm_algorithms/waypoint.py` | `waypoint` |
| `src/swarm_algorithms/formation.py` | `formation` |
| `src/swarm_algorithms/flocking.py` | `flocking`, `flocking_basic` |

`common.py`의 `TaskPilot`이 작업 수행의 중심이므로 여기서 읽기 시작한다.

## 실행 파일

없다. `swarm-agent`가 entry point `swarm.ma`로 불러온다.

## 구독·발행 키

없다. 플러그인은 포트로만 통신한다(DEC-013).

## 시험

```bash
uv run pytest algorithms/tests
```

## 알려진 제약

- `flocking`은 Route를 거부한다.
- 실행 중 받은 `MissionPlan`과 `RoutePlan`의 규칙은 [4.7](../04_ma_plugin.md#47-재사용-부품)에 있다. `RoutePlan`을 수행하는 내장 MA는 `waypoint`뿐이다.
- 기본 MA는 `track`, `strike`, `jam` 작업을 수행하지 않는다.
- 다른 기체 정보는 데이터링크로 받은 `PeerStatus`만 쓴다. 링크가 나쁘면 편대 품질이 함께 나빠지는 것은 의도한 동작이다.

추적: [algorithms/TRACE.md](../../../algorithms/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
