# 8. WP1 Sim Core (`core/`)

> Source: [docs/41_dev/08_wp/core.md](../../../41_dev/08_wp/core.md) at commit `f7bcbac`.

## Responsibilities

Handles the frame scheduler (realtime, lockstep, freerun), entity state, dynamics integration, fault state, and scenario loading and distribution. Only Core produces the true state (truth), and Core manages the lockstep barrier. Payload evaluation calls the `payload/` library.

## Structure

| Path | Contents |
|---|---|
| `src/main.cpp` | Entry point, option parsing |
| `src/sim_core.cpp`, `include/swarm/core/sim_core.hpp` | Scheduler, state machine, command handling |
| `src/entity_store.cpp` | Entity store (SoA) |
| `src/wp2_dynamics.cpp` | Connection to `dynamics/`, airframe table `kAirframes` |
| `src/scripted.cpp` | Scripted path motion (`DYNAMICS_KIND_SCRIPTED`) |
| `src/scenario.cpp` | Scenario reading |
| `src/mock_dynamics.cpp` | Substitute dynamics for tests |

Start reading at the public functions of `sim_core.hpp` and the frame processing in `sim_core.cpp`.

## Executable `swarm_core`

| Option | Meaning |
|---|---|
| `--scenario <file>` | `.pb` or proto JSON. Built-in scenario if absent |
| `--uavs <n>` | Number of vehicles in the built-in scenario |
| `--autostart` | Start right after load |
| `--mode`, `--rate`, `--hz`, `--seed` | Run overrides. `--rate 0` is maximum speed |
| `--participant <id>` | Lockstep participant (repeatable) |
| `--frames <n>` | Exit after n frames |
| `--integrator rk4\|rk45` | Default rk45 |
| `--terrain-flat <m>`, `--terrain-dem <json>` | Terrain |
| Common bus options | [3.2](../03_architecture.md#32-opening-the-bus) |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `sim/ctrl/cmd`, `sim/clock/done/<p>`, `onboard/<id>/ControlOutput`, `onboard/<id>/*Command` |
| Publish | `sim/clock/tick`, `sim/ctrl/status`, `sim/ctrl/scenario`, `sim/param/<id>/dynamics`, `truth/state`, `truth/event/<kind>`, `onboard/<id>/NavigationReport`, `SystemStatus`, `Detection`, `*Activity` |

## Tests

```bash
ctest --preset msvc-debug -R "^core\.|swarm_core"
```

`swarm_core_tests` covers the scheduler, commands, reproducibility and payload integration, `swarm_core_zenoh_tests` covers real Zenoh round trips, and `core.TC-CORE-040/042` cover the DEM options.

## Known limitations

- Outside the DEM grid (outside latitude 33–43°N, longitude 124–131°E) the elevation is 0 m.
- `dof5` and `dof6` are refused at load.
- Scripted motion is ground-referenced and does not add wind.
- Lockstep participants are fixed statically by the scenario and `--participant`. New participants are not accepted after start (DEC-037).
- `SetParams` takes effect at the frame boundary when Core receives the command. Tests that need reproducibility put the values in the scenario.

Traceability: [core/TRACE.md](../../../../core/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
