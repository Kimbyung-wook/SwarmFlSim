# 8. WP9 A-GRA Gateway (`gateway/`)

> Source: [docs/41_dev/08_wp/gateway.md](../../../41_dev/08_wp/gateway.md) at commit `7affdae`.

## Responsibilities

As a ground participant on the GCS side, it converts between internal messages and external UCI messages (DEC-068, DEC-069). It is a standalone uv project outside the root workspace. The operating procedure is in [chapter 9](../../42_user/09_gateway.md) of the user manual, the design in [gateway/README.md](../../../../gateway/README.md).

## Structure

| Path | Contents |
|---|---|
| `src/swarm_gateway/__main__.py` | Entry point |
| `src/swarm_gateway/gateway.py` | Stage 1 and stage 2 processing, counters, rejection records |
| `src/swarm_gateway/mapping.py` | Mapping table built from proto options |
| `src/swarm_gateway/converters/` | Per-message converters |
| `src/swarm_gateway/lacal.py` | Submodule path, XSD validation, CAL Client |
| `src/swarm_gateway/runner.py` | LA-CAL connection |
| `src/swarm_gateway/ids.py` | String ID ⇄ UUID |
| `src/swarm_gateway/lacal_server.py`, `config/lacal_server.yaml` | CAL Server startup |

`third_party/agra_lacal` is a submodule and is not modified.

## Running

| Option | Meaning |
|---|---|
| `--gcs <id>` | Required. GCS entity ID |
| `--lacal <url>` | Default `ws://127.0.0.1:8765` |
| `--service`, `--topic-prefix`, `--inbound-topic` | LA-CAL service and topics |
| `--stats-s <s>` | Counter log period, default 10 |
| Common bus options | [3.2](../03_architecture.md#32-opening-the-bus) |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `swarm/<gcs>/rx/**` only |
| Publish | `swarm/<gcs>/tx/c2/<msg>` only |

`truth/**`, `onboard/**` and `link/**` are not used.

## Tests

```bash
cd gateway && uv run pytest
```

Runs with InMemoryBus and an in-process CAL Server. The first time, do the installation in [2.6](../02_build_test.md#26-gateway) first.

## Contract change request status

| ID | Contents | Status |
|---|---|---|
| CR-GW-001 | External message mapping for position | Resolved (DEC-072) |
| CR-GW-002 | `ApprovalResponse` as STD | Open (OPN-061) |
| CR-GW-003 | Representing the task content of external `MA_TaskCommand` | Open (OPN-062). Interim rules in use |
| CR-GW-004 | Join the root workspace | Open (no registry entry) |
| CR-GW-005 | Mark the Gateway in the key list | Open (OPN-063) |
| CR-GW-006 | Update registry §5 | Open (no registry entry) |

## Known limitations

- External tasks are accepted by the interim rules only for `hold`, `return_to_base` and cancel.
- Commands sent externally before the `ready` log are lost (O-13).
- `declared.pub` in `config/lacal_server.yaml` lacks `MA_PositionReport` (O-20).

Traceability: [gateway/TRACE.md](../../../../gateway/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
