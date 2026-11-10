# 8. WP5 WebSocket bridge (`bridge/`)

> Source: [docs/41_dev/08_wp/bridge.md](../../../41_dev/08_wp/bridge.md) at commit `f0729ee`.

## Responsibilities

Connects browsers to the bus (DEC-027). Handles per-client subscriptions and downsampling, and checks allowed publish keys. It is not a lockstep participant. The protocol is in [contract §3.5](../../../10_contracts.md#35-브라우저-연동-dec-027) (Korean), the structure in [bridge/README.md](../../../../bridge/README.md).

## Structure

| Path | Contents |
|---|---|
| `src/swarm_bridge/cli.py` | Entry point |
| `src/swarm_bridge/server.py` | `BridgeServer`, client and subscription handling |
| `src/swarm_bridge/frame.py` | Binary frames |

## Executable `swarm-bridge`

| Option | Meaning |
|---|---|
| `--host` | Default `127.0.0.1`. `0.0.0.0` for browsers on other PCs |
| `--port` | Default 8765. Connection address `ws://<host>:<port>/bus` |
| `--queue-limit <n>` | Per-client send queue length in frames, default 4096 |
| `-v` | Verbose logs |
| Common bus options | [3.2](../03_architecture.md#32-opening-the-bus) |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | Keys requested by clients |
| Publish | Only `sim/ctrl/cmd` and `swarm/<gcs>/tx/**` from `role=control` clients |

## Tests

```bash
uv run pytest bridge/tests
```

## Known limitations

- The default port 8765 is the same as the CAL Server default. If you run both, change one.
- When the send queue overflows, the oldest frames are dropped and the number dropped is logged when the connection closes.

Traceability: [bridge/TRACE.md](../../../../bridge/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
