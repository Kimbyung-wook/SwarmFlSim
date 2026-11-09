# 8. WP4 Datalink (`datalink/`)

> Source: [docs/41_dev/08_wp/datalink.md](../../../41_dev/08_wp/datalink.md) at commit `bbf4d92`.

## Responsibilities

Applies the link model to vehicle-to-vehicle and ground-to-vehicle messages and delivers them. Publishes a delivery or loss reason for each message. Usage is in [chapter 7](../../42_user/07_link.md) of the user manual.

## Structure

| Path | Contents |
|---|---|
| `src/main.cpp` | Entry point |
| `src/emulator.cpp`, `include/swarm/lnk/emulator.hpp` | Tick processing, entity table, delivery |
| `src/channel.cpp`, `include/swarm/lnk/channel.hpp` | Path loss and SNR, token bucket, Gilbert-Elliott, latency |
| `src/profile.cpp`, `include/swarm/lnk/profile.hpp` | Built-in profiles, overrides |

The evaluation order is alive → fault → jamming → range and SNR → line of sight → token bucket → burst loss → latency.

Only when `sim_time_us == 0` and `publisher` is set is the time treated as absent and the last tick time used. If `publisher` is empty, 0 is kept as a valid time, and a frame 0 send is also processed at tick 1 by the `tx < T_k` rule (IMP-LNK-023, DEC-054, DEC-077).

## Executable `swarm_datalink`

| Option | Meaning |
|---|---|
| `--scenario <file>` | If absent, waits for LoadScenario on `sim/ctrl/cmd` |
| `--participant <id>` | Default `datalink-0` |
| `--no-frame-done` | Does not send FrameDone |
| `--seed <n>` | Random seed |
| `--terrain-flat <m>`, `--no-los` | Flat elevation for line of sight, turn off line of sight |
| `--state-period <s>` | `link/state` period, default 1, off at 0 |
| `--quiet` | Turns off logs |
| Common bus options | [3.2](../03_architecture.md#32-opening-the-bus) |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `swarm/*/tx/**`, `sim/clock/tick`, `sim/ctrl/cmd`, `sim/ctrl/scenario`, `truth/state`, `truth/event/jam_zone`, `truth/event/kill` |
| Publish | `swarm/<dst>/rx/**`, `link/outcome/<src>/<dst>`, `link/state/<a>/<b>`, `sim/clock/done/<p>` |

## Tests

```bash
ctest --preset msvc-debug -R "^lnk\."
```

TC-LNK items cover the behavior of each evaluation stage and determinism for identical inputs.

## Known limitations

- Jamming frequency bands are not modeled.
- There is no peer relay (multi-hop). Messages are delivered only to directly reachable receivers.
- Line of sight is evaluated only against the flat elevation of `--terrain-flat`. The DEM is not used.
- Polygon zones are evaluated in the latitude/longitude plane. The date line and polar regions are not supported.
- Burst discard outcomes are recorded only up to a per-tick cap, and only the count of the rest goes to the log.

Traceability: [datalink/TRACE.md](../../../../datalink/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
