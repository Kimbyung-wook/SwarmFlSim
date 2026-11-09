# 8. WP3 Agent runtime (`agent/`)

> Source: [docs/41_dev/08_wp/agent.md](../../../41_dev/08_wp/agent.md) at commit `bbf4d92`.

## Responsibilities

One process hosts many vehicles and runs an MA and FA for each. Handles the port implementations, parameters, GCS status reporting and lockstep FrameDone. Writing plugins is covered in [chapter 4](../04_ma_plugin.md) and [chapter 5](../05_fa_plugin.md).

## Structure

| Path | Contents |
|---|---|
| `src/swarm_agent/cli.py` | Entry point, options |
| `src/swarm_agent/runtime.py` | `AgentRuntime`, frame processing order |
| `src/swarm_agent/vehicle.py` | State of one vehicle |
| `src/swarm_agent/ports.py` | Implementation of the 6 ports |
| `src/swarm_agent/fa.py`, `racetrack.py` | Default FA |
| `src/swarm_agent/plugins.py` | Entry point loading |
| `src/swarm_agent/params.py` | Per-vehicle parameters |
| `src/swarm_agent/reporting.py` | GCS status reporting (DEC-056, DEC-071) |
| `src/swarm_agent/testing.py` | `Harness`, `FakeCore`, `FakeDatalink` |

For the frame processing order, see the header comment of `runtime.py` and `_step`.

## Executable `swarm-agent`

| Option | Meaning |
|---|---|
| `--scenario <file>` | Scenario to read at start. If absent, received from the bus |
| `--participant <id>` | Default `agent-0` |
| `--entities <ids>` | Vehicles to host, comma-separated and repeatable |
| `--frames <n>` | Exit after n ticks |
| `--activity-max-hz <hz>` | Per-key maximum rate of change reports, default 10 |
| `--vi-report-hz <hz>` | Rate of `NavigationReport` to the GCS, default 1, off at 0 or below |
| `--list-plugins` | Prints the registered MAs and FAs |
| `-v` | Verbose logs |
| Common bus options | [3.2](../03_architecture.md#32-opening-the-bus) |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `sim/clock/tick`, `sim/ctrl/cmd`, `sim/ctrl/scenario`, `onboard/<id>/NavigationReport`, `Detection`, `*Activity`, `SystemStatus`, `swarm/<id>/rx/**` |
| Publish | `swarm/<id>/tx/**`, `onboard/<id>/ControlOutput`, `onboard/<id>/*Command`, `sim/param/<id>/fa`, `sim/param/<id>/ma`, `sim/clock/done/<p>` |

`truth/**` and `link/**` are not subscribed.

## Tests

```bash
uv run pytest agent/tests
```

Performance measurement tools are in `agent/bench/`.

## Known limitations

- `md.record` stays in runtime memory. It does not go to the bus or MCAP.
- Altitude fields cannot express "unspecified", so `alt_m <= 0` is interpreted as holding the current altitude.
- Vehicle behavior on link loss is not implemented (roadmap P2).
- The MP port holds only the latest plan. If two `MissionPlan`s arrive in one tick, only the last is executed.
- With many vehicles, split them across Agents. List them all in the scenario's `participants`.

Traceability: [agent/TRACE.md](../../../../agent/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
