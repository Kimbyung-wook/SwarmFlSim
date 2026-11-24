# 8. WP3 Agent runtime (`agent/`)

> Source: [docs/41_dev/08_wp/agent.md](../../../41_dev/08_wp/agent.md) at commit `0a331b0`.

## Responsibilities

One process hosts many vehicles and runs an MA and FA for each. Handles the port implementations, parameters, GCS status reporting and lockstep FrameDone. Writing plugins is covered in [chapter 4](../04_ma_plugin.md) and [chapter 5](../05_fa_plugin.md).

## Structure

| Path | Contents |
|---|---|
| `src/swarm_agent/cli.py` | Entry point, options |
| `src/swarm_agent/runtime.py` | `AgentRuntime`, frame processing order |
| `src/swarm_agent/vehicle.py` | State of one vehicle |
| `src/swarm_agent/ports.py` | Implementation of the 6 ports |
| `src/swarm_agent/fa.py` | Default FA. Racetrack geometry is `swarm_api.racetrack` (DEC-104). `racetrack.py` and `geo.py` are compatibility aliases |
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
| `--profile <file>` | Path of the per-stage tick profiling JSON, off by default. The environment variable `SWARM_AGENT_PROFILE` also turns it on ([10.5](../10_qa.md#105-performance-measurement)) |
| `--list-plugins` | Prints the registered MAs and FAs |
| `-v` | Verbose logs |
| Common bus options | [3.2](../03_architecture.md#32-opening-the-bus) |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `sim/clock/tick`, `sim/ctrl/cmd`, `sim/ctrl/scenario`, `onboard_batch/NavigationBatch`, `onboard/<id>/Detection`, `*Activity`, `SystemStatus`, `StoreLoadout`, `swarm/<id>/rx/**` |
| Publish | `swarm/<id>/tx/**`, `onboard_batch/ControlBatch/<p>` (one per tick, before `FrameDone`), `onboard/<id>/*Command`, `sim/param/<id>/fa`, `sim/param/<id>/ma`, `sim/clock/done/<p>` |

`truth/**` and `link/**` are not subscribed. All subscriptions are opened with `ordered=True` (DEC-083, [3.2](../03_architecture.md#32-opening-the-bus)).

Vehicle-side subscriptions are opened separately for each hosted vehicle: `onboard/<id>/<message>` (one per inbound onboard message) and `swarm/<id>/rx/**`. No wildcard is used in the entity position (DEC-100, contract 0.21.0, IMP-AGT-052). One Agent hosting 100 vehicles has 700 subscriptions. The earlier grouping into `onboard/*/<message>` and `swarm/*/rx/**` when hosting every vehicle (IMP-AGT-043) was removed, so that each vehicle receives only what is addressed to it, as a real vehicle does. Zenoh matches each put against every subscription in the session, so the subscription count affects the put cost. The performance judgment after this change is being remeasured by QA.

Additions to change reports (DEC-088, DEC-089):

- `StoreLoadout`: once the `onboard/<id>/StoreLoadout` sent by Payload has arrived, that value is the basis of `ms.loadout()`, and the runtime no longer lowers the count on launch by itself. Only vehicles with stores send it to the controlling GCS on `tx/ms/StoreLoadout`, at start and when the value changes (IMP-AGT-048).
- Re-report on link recovery: when `GcsHeartbeat` returns after a gap longer than the MA variable `lost_link_timeout_s` (default 5 s), the next GCS report resends every change-report key of that vehicle and `FlightCapability` once. Keys removed by an end state are not included (IMP-AGT-049). In addition, the vehicle's last `FlightCommandStatus` (even an end state already sent and removed) and the last `TaskStatus` of each in-progress task the MA sent on the C2 port are resent once in task_id order (DEC-101(1), IMP-AGT-054). Tasks whose end state was sent are removed from the list.

## Tests

```bash
uv run pytest agent/tests
```

Performance measurement tools are in `agent/bench/`.

## Known limitations

- `md.record` stays in runtime memory. It does not go to the bus or MCAP.
- Altitude fields cannot express "unspecified", so `alt_m <= 0` is interpreted as holding the current altitude.
- Link-loss behavior lives in the shared MA parts (`algorithms`), not in the runtime. A user MA that does not use those parts has no link-loss behavior ([chapter 4](../04_ma_plugin.md#48-baseline-mas)).
- The MP port holds only the latest plan. If two `MissionPlan`s arrive in one tick, only the last is executed.
- With many vehicles, split them across Agents. List them all in the scenario's `participants`.
- Processing ticks for lockstep onboard inputs follow [3.6](../03_architecture.md#36-one-lockstep-frame). The `late_onboard` value is not exposed. Only the first warning reaches the log.

Traceability: [agent/TRACE.md](../../../../agent/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
