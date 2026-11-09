# 8. WP2 Dynamics (`dynamics/`)

> Source: [docs/41_dev/08_wp/dynamics.md](../../../41_dev/08_wp/dynamics.md) at commit `24fc9be`.

## Responsibilities

Implements `DynamicsModel` and `Integrator`, terrain lookup and DEM loading. There is no executable. It is linked into Core as the library `swarm_dynamics`. The procedure for adding a model is in [chapter 6](../06_dynamics.md).

## Structure

| Path | Contents |
|---|---|
| `include/swarm/dyn/models.hpp`, `src/models.cpp` | `Dof2Model`, `Dof3Model` |
| `include/swarm/dyn/integrators.hpp`, `src/integrators.cpp` | `Rk4Integrator`, `Rk45Integrator` |
| `include/swarm/dyn/factory.hpp`, `src/factory.cpp` | Creates models and integrators by name |
| `include/swarm/dyn/terrain.hpp`, `src/terrain.cpp` | `FlatTerrain`, `GridTerrain`, `RawDemLoader` |
| `include/swarm/dyn/geo.hpp` | Geodetic conversion |
| `tests/data/` | Synthetic ridge DEM and generation script |

## Subscribed and published keys

None. Core handles the bus.

## Tests

```bash
ctest --preset msvc-debug -R "^dyn\."
```

TC-DYN-001~015 cover analytic comparison, integration order, event timing, ground crossing, factory, wind, parameters and DEM loading.

## Known limitations

- Only 2-DoF and 3-DoF are implemented. `dof5` and `dof6` are reserved names only.
- Integrator instances hold working buffers. Use a separate one per thread.
- 2-DoF and 3-DoF accept only `ControlOutput.kinematic`.

Traceability: [dynamics/TRACE.md](../../../../dynamics/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
