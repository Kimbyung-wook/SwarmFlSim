# 8. WP2 동역학 (`dynamics/`)

## 책임

`DynamicsModel`과 `Integrator`의 구현, 지형 조회와 DEM 적재를 맡는다. 실행 파일 없이 라이브러리 `swarm_dynamics`로 Core에 링크된다. 모델 추가 절차는 [6장](../06_dynamics.md).

## 구조

| 경로 | 내용 |
|---|---|
| `include/swarm/dyn/models.hpp`, `src/models.cpp` | `Dof2Model`, `Dof3Model` |
| `include/swarm/dyn/integrators.hpp`, `src/integrators.cpp` | `Rk4Integrator`, `Rk45Integrator` |
| `include/swarm/dyn/factory.hpp`, `src/factory.cpp` | 이름으로 모델·적분기 생성 |
| `include/swarm/dyn/terrain.hpp`, `src/terrain.cpp` | `FlatTerrain`, `GridTerrain`, `RawDemLoader` |
| `include/swarm/dyn/geo.hpp` | 측지 변환 |
| `tests/data/` | 합성 능선 DEM과 생성 스크립트 |

## 구독·발행 키

없다. 버스는 Core가 맡는다.

## 시험

```bash
ctest --preset msvc-debug -R "^dyn\."
```

TC-DYN-001~015는 해석해 비교, 적분 차수, 이벤트 시점, 지면 교차, 팩토리, 바람, 매개변수, DEM 적재를 본다.

## 알려진 제약

- 2·3-DoF만 구현했다. `dof5`, `dof6`는 이름만 예약돼 있다.
- 적분기 인스턴스는 작업 버퍼를 가진다. 스레드마다 따로 쓴다.
- 2·3-DoF는 `ControlOutput.kinematic`만 받는다.

추적: [dynamics/TRACE.md](../../../dynamics/TRACE.md).
