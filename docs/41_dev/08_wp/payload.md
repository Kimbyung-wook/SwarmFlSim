# 8. WP8 임무장비 (`payload/`)

## 책임

센서 탐지, 재머 구역, 유도 객체의 비행과 시뮬레이션 이벤트 판정을 계산하는 라이브러리다(DEC-046). 입력과 출력만 있는 순수 계산기이고 버스를 쓰지 않는다. Core가 프레임마다 호출한다.

## 구조

| 경로 | 내용 |
|---|---|
| `include/swarm/payload/payload.hpp`, `src/payload_system.cpp` | `PayloadSystem::step(FrameInput)` → `FrameOutput` |
| `include/swarm/payload/geometry.hpp`, `src/geometry.cpp` | FOV·거리·가시선 기하 |
| `include/swarm/payload/weapon.hpp`, `src/weapon.cpp` | 유도 객체 비행 |
| `include/swarm/payload/profiles.hpp`, `src/profiles.cpp` | 프로파일 읽기와 재정의 |
| [`profiles/`](../../../payload/profiles/) | 장비 프로파일 JSON |

수치는 프로파일 파일에 있다. 시나리오에서 프로파일 이름과 `overrides`로 재정의하는 방법은 사용자 매뉴얼 [3.8](../../42_user/03_scenario.md#38-탑재-장비-payloads).

## 실행 파일

없다. 라이브러리 `swarm_payload`로 Core에 링크된다.

## 구독·발행 키

없다. `FrameInput`, `FrameOutput`을 Core가 버스로 옮긴다.

## 시험

```bash
ctest --preset msvc-debug -R "^pay\."
```

## 알려진 제약

- `StrikeActivity`의 IMPACT는 유도 객체의 도달만 뜻한다. 효과는 `truth/event/kill`로 판단한다(DEC-067).
- 엔티티당 재머 하나만 받는다.
- 비행 중 FOV를 벗어나면 유도를 멈추고 다시 획득하지 않는다.
- 기본 MA는 장비 명령을 내지 않는다. 시험과 MA 플러그인이 `ms.command`로 보낸다.

추적: [payload/TRACE.md](../../../payload/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
