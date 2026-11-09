# 1. Preparation

> Source: [docs/42_user/01_install.md](../../42_user/01_install.md) at commit `7affdae`.

To use the simulator without changing code, you need the outputs below.

## 1.1 Required outputs

| Output | How to make it |
|---|---|
| `build/msvc-debug/{core/swarm_core, datalink/swarm_datalink, logger/swarm_logger}` | Developer manual [chapter 1](../41_dev/01_setup.md), [2.2](../41_dev/02_build_test.md#22-c-core-dynamics-datalink-logger-payload-bus) |
| Python packages (`swarm-agent`, `swarm-bridge`, `swarm-scenario`) | `uv sync`, then `uv run python scripts/gen_proto.py` |
| Browser screens | `npm install` in each of `ui/` and `ui/monitor/` |

- If you received an already built repository, check that the following command prints plugin names.

```bash
uv run swarm-agent --list-plugins
```

If it is working, `swarm.ma:` lists `flocking`, `flocking_basic`, `formation`, `hold`, `waypoint`, and `swarm.fa:` lists `default`. Names starting with `example_` belong to the example package and appear as well.

## 1.2 Map data (optional)

The simulator runs without it. Without it the UI uses built-in low-resolution imagery and the ellipsoid, and Core and Datalink calculate with flat terrain at 0 m.

| Data | Used by | Command | Location |
|---|---|---|---|
| DEM (Copernicus GLO-90, 33–43°N, 124–131°E) | Core's ground collision and line of sight for sensors and guided objects | `uv run scripts/fetch_dem.py` | `data/dem/` |
| Terrain tiles | UI 3D terrain | `uv run scripts/make_terrain_tiles.py` | `data/tiles/terrain/` |
| Imagery tiles (own Sentinel-2 composite) | UI map imagery | `uv run scripts/make_s2_composite_tiles.py` | `data/tiles/imagery/` |

- Run the scripts with `uv run scripts/<name>.py`, not `uv run python`. The required packages are installed from the declaration at the top of each script.
- Terrain tiles require the DEM first.
- The imagery composite downloads about 18 GB of public AWS data. It takes a long time.
- These files are not committed to the repository.
- Attribution and how to change the paths are in the terrain and tiles part of [contract §7.3](../../10_contracts.md#73-빌드와-시험) (Korean).

> Not verified: the full DEM and tile downloads were not run while writing this manual. `fetch_dem.py --help` and loading an already downloaded DEM with `swarm_core --terrain-dem` were confirmed.

Next: [2. Quick start](02_quickstart.md).
