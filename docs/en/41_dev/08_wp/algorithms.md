# 8. WP3 Baseline algorithms (`algorithms/`)

> Source: [docs/41_dev/08_wp/algorithms.md](../../../41_dev/08_wp/algorithms.md) at commit `f767bb5`.

## Responsibilities

Holds the baseline MA plugins and shared parts. The runtime is handled by [agent](agent.md). The plugins are explained in [4.8](../04_ma_plugin.md#48-baseline-mas).

## Structure

| Path | Contents |
|---|---|
| `src/swarm_algorithms/common.py` | `TaskTracker`, `TaskPilot`, `PlanWatcher`, `PayloadTasker`, `LinkMonitor`, `LostLinkGuard`, `peer_status`, `every` |
| `src/swarm_algorithms/hold.py` | `hold` |
| `src/swarm_algorithms/waypoint.py` | `waypoint` |
| `src/swarm_algorithms/formation.py` | `formation` |
| `src/swarm_algorithms/flocking.py` | `flocking`, `flocking_basic` |
| `src/swarm_algorithms/approval_demo.py` | `approval_demo` (approval-flow tests and demos only, not a baseline MA, DEC-103) |

When reading the code, start with `TaskPilot` in `common.py`, which handles task execution.

## Executable

None. `swarm-agent` loads them through the entry point `swarm.ma`.

## Subscribed and published keys

None. Plugins communicate only through ports (DEC-013).

## Tests

```bash
uv run pytest algorithms/tests
```

## Known limitations

- `flocking` rejects Route.
- The rules for `MissionPlan` and `RoutePlan` received during a run are in [4.7](../04_ma_plugin.md#47-reusable-parts). `waypoint` is the only baseline MA that flies a `RoutePlan`.
- `track`, `jam` and `strike` are carried out only by `waypoint` and the `formation` leader (DEC-106). `flocking` and `hold` reject them. The precise engagement zone (MA_WEZ) is not handled (OPN-084).
- For other vehicles' information they use only `PeerStatus` received over the datalink. Formation quality degrading along with a poor link is intended behavior.

Traceability: [algorithms/TRACE.md](../../../../algorithms/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
