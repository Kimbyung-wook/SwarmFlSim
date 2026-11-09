# 1. 준비

코드를 고치지 않고 시뮬레이터를 쓰려면 아래 산출물이 있으면 된다.

## 1.1 필요한 산출물

| 산출물 | 만드는 방법 |
|---|---|
| `build/msvc-debug/{core/swarm_core, datalink/swarm_datalink, logger/swarm_logger}` | 개발자 매뉴얼 [1장](../41_dev/01_setup.md), [2.2](../41_dev/02_build_test.md#22-c-core-동역학-datalink-logger-payload-버스) |
| Python 패키지 (`swarm-agent`, `swarm-bridge`, `swarm-scenario`) | `uv sync` 후 `uv run python scripts/gen_proto.py` |
| 브라우저 화면 | `ui/`, `ui/monitor/`에서 각각 `npm install` |

- 이미 빌드된 저장소를 받았다면 다음 명령이 플러그인 이름을 출력하는지 확인한다.

```bash
uv run swarm-agent --list-plugins
```

정상이면 `swarm.ma: flocking, flocking_basic, formation, hold, waypoint`와 `swarm.fa: default`가 나온다.

## 1.2 지도 자료 (선택)

없어도 실행된다. 없으면 UI는 내장 저해상도 영상과 타원체를 쓰고, Core·Datalink는 평지 0 m로 계산한다.

| 자료 | 쓰는 곳 | 받는 명령 | 위치 |
|---|---|---|---|
| DEM (Copernicus GLO-90, 33–43°N, 124–131°E) | Core의 지면 충돌과 센서·유도 객체의 가시선 | `uv run scripts/fetch_dem.py` | `data/dem/` |
| 지형 타일 | UI 3D 지형 | `uv run scripts/make_terrain_tiles.py` | `data/tiles/terrain/` |
| 영상 타일 (Sentinel-2 자체 합성) | UI 지도 영상 | `uv run scripts/make_s2_composite_tiles.py` | `data/tiles/imagery/` |

- 스크립트는 `uv run python`이 아니라 `uv run scripts/<이름>.py`로 실행한다. 필요한 패키지를 스크립트 머리의 선언으로 설치하기 때문이다.
- 지형 타일은 DEM이 먼저 있어야 한다.
- 영상 합성은 AWS 공개 자료를 약 18 GB 받는다. 오래 걸린다.
- 이 파일들은 저장소에 커밋하지 않는다.
- 출처 표기와 경로 변경 방법은 [계약 §7.3](../10_contracts.md#73-빌드와-시험)의 지형·타일 절.

> 확인 안 됨: 이 매뉴얼을 쓰면서 DEM·타일 전체 내려받기는 실행하지 않았다. `fetch_dem.py --help`와, 이미 받은 DEM을 `swarm_core --terrain-dem`으로 적재하는 것까지 확인했다.

다음: [2. 빠른 시작](02_quickstart.md).
