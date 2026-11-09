# 8. WP1 Sim Core (`core/`)

## 책임

프레임 스케줄러(realtime, lockstep, freerun), 엔티티 상태, 동역학 적분, 고장 상태, 시나리오 적재와 배포를 맡는다. 진실값의 유일한 생산자이자 lockstep 장벽의 주인이다. 임무장비 판정은 `payload/` 라이브러리를 호출한다.

## 구조

| 경로 | 내용 |
|---|---|
| `src/main.cpp` | 진입점, 옵션 해석 |
| `src/sim_core.cpp`, `include/swarm/core/sim_core.hpp` | 스케줄러, 상태 머신, 명령 처리 |
| `src/entity_store.cpp` | 엔티티 저장소(SoA) |
| `src/wp2_dynamics.cpp` | `dynamics/` 연결, airframe 표 `kAirframes` |
| `src/scripted.cpp` | 스크립트 경로 이동(`DYNAMICS_KIND_SCRIPTED`) |
| `src/scenario.cpp` | 시나리오 읽기 |
| `src/mock_dynamics.cpp` | 시험용 대체 동역학 |

처음 읽을 곳은 `sim_core.hpp`의 공개 함수와 `sim_core.cpp`의 프레임 처리다.

## 실행 파일 `swarm_core`

| 옵션 | 뜻 |
|---|---|
| `--scenario <file>` | `.pb` 또는 proto JSON. 없으면 내장 시나리오 |
| `--uavs <n>` | 내장 시나리오 기체 수 |
| `--autostart` | 적재 뒤 바로 시작 |
| `--mode`, `--rate`, `--hz`, `--seed` | 실행 재정의. `--rate 0`은 최대 속도 |
| `--participant <id>` | lockstep 참여자(반복) |
| `--frames <n>` | n 프레임 뒤 종료 |
| `--integrator rk4\|rk45` | 기본 rk45 |
| `--terrain-flat <m>`, `--terrain-dem <json>` | 지형 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `sim/ctrl/cmd`, `sim/clock/done/<p>`, `onboard/<id>/ControlOutput`, `onboard/<id>/*Command` |
| 발행 | `sim/clock/tick`, `sim/ctrl/status`, `sim/ctrl/scenario`, `sim/param/<id>/dynamics`, `truth/state`, `truth/event/<kind>`, `onboard/<id>/NavigationReport`, `SystemStatus`, `Detection`, `*Activity` |

## 시험

```bash
ctest --preset msvc-debug -R "^core\.|swarm_core"
```

`swarm_core_tests`가 스케줄러·명령·재현성·임무장비 연동을, `swarm_core_zenoh_tests`가 실제 Zenoh 왕복을, `core.TC-CORE-040/042`가 DEM 옵션을 본다.

## 알려진 제약

- DEM 격자 밖(위도 33–43°N, 경도 124–131°E 밖)은 0 m다.
- `dof5`, `dof6`는 적재에서 거부된다.
- 스크립트 이동은 대지 기준이고 바람을 더하지 않는다.
- lockstep 참여자는 시나리오와 `--participant`로 정적으로 정한다. 시작 뒤 새 참여자는 받지 않는다(DEC-037).
- `SetParams`의 적용 시각은 Core가 명령을 받은 프레임 경계다. 재현이 필요한 시험은 시나리오에 값을 넣는다.

추적: [core/TRACE.md](../../../core/TRACE.md).
