# 8. WP6 Traffic Monitor (`ui/monitor/`)

> Source: [docs/41_dev/08_wp/monitor.md](../../../41_dev/08_wp/monitor.md) at commit `f7bcbac`.

## Responsibilities

A separate app that aggregates and visualizes datalink traffic. It only observes and sends no commands. How to read the screens is in [chapter 6](../../42_user/06_monitor.md) of the user manual, the structure in [ui/monitor/README.md](../../../../ui/monitor/README.md).

## Structure

| Path | Contents |
|---|---|
| `src/App.tsx` | Screen layout, 250 ms refresh |
| `src/bridge/` | `BridgeSource`, frame decoding |
| `src/model/` | `MonitorStore`, `Aggregator`, ring buffers |
| `src/components/` | `Header`, `FilterBar`, `EntityTree`, `StatsTable`, `Timeline`, `EntityDetail`, `EchoPanel` |
| `src/mock/` | Mock traffic |

Frames are processed synchronously on arrival, and the screen reads the store every 250 ms.

## Running

```bash
cd ui/monitor && npm run dev
```

The port is 5174. URL arguments are `source` (`mock` default, `bridge`), `url`, `replay`, and for the mock source `uavs`, `hz`, `rate`.

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `link/outcome/**`, `link/state/**`, `swarm/*/tx/**`, `swarm/*/rx/**`, `truth/state`, `truth/event/**`, `sim/ctrl/status` |
| Publish | None (`role=observer`) |

## Tests

```bash
cd ui/monitor && npm test
```

For load measurement use `npm run bench`.

## Known limitations

- Aggregation is based on per-receiver `LinkOutcome`. A broadcast counts as one loss for each receiver it does not reach (DEC-032).
- Filters apply to the timeline and echo. Only the entity filter applies to the statistics table.

Traceability: [ui/monitor/TRACE.md](../../../../ui/monitor/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
