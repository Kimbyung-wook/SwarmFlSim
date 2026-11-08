# Developer manual

> Source: [docs/41_dev/README.md](../../41_dev/README.md) at commit `f0d0533`.

- Readers: algorithm plugin authors (writing MA/FA in Python) and WP contributors (changing a module directory while following the test, traceability and contract rules).
- New to the project? Read the project overview first (`../40_overview.md`, planned).
- Contracts (keys, schemas, protocol, build setup) are defined in [10_contracts.md](../../10_contracts.md) (Korean). This manual links to its sections.

## Reading order

| Reader | Order |
|---|---|
| Algorithm plugin author | 1 → 2 (Python parts) → 3 → 4 → 5 |
| WP contributor | 1 → 2 → 3 → 8 (own WP) → 9 → 10 |

## Chapters

| Ch. | File | Contents | Status |
|---|---|---|---|
| 1 | `01_setup.md` | Development environment: choosing a toolchain, installation, common failures | Planned |
| 2 | `02_build_test.md` | Build and test: C++, Python, UI, Gateway, generated code | Planned |
| 3 | `03_architecture.md` | Architecture and execution model: processes, bus key access rules, run modes, lockstep | Planned |
| 4 | `04_ma_plugin.md` | Writing an MA plugin: walkthrough, ports, parameters, batch calls, tests. Example package `examples/plugins/` (DEC-070) | Planned |
| 5 | `05_fa_plugin.md` | Writing an FA plugin: VI control modes, the default FA | Planned |
| 6 | `06_dynamics.md` | Adding a dynamics model: interfaces, factory, parameters, tests | Planned |
| 7 | `07_messages.md` | Messages and contracts: proto roles, A-GRA mapping options, adding a message | Planned |
| 8 | `08_wp/` | Per-WP contribution guide (table below) | Planned |
| 9 | `09_contributing.md` | Contribution rules: IDs, TRACE, commits, contract change requests | Planned |
| 10 | `10_qa.md` | QA harness: `qa/run_qa.py`, scenarios, determinism diagnostics | Planned |
| 11 | `11_troubleshooting.md` | Troubleshooting: symptom → cause → fix | Planned |

### Chapter 8 files (`08_wp/`)

| File | WP | Directory | Status |
|---|---|---|---|
| `core.md` | WP1 Sim Core | `core/` | Planned |
| `dynamics.md` | WP2 Dynamics | `dynamics/` | Planned |
| `datalink.md` | WP4 Datalink | `datalink/` | Planned |
| `agent.md` | WP3 Agent runtime | `agent/` | Planned |
| `algorithms.md` | WP3 Baseline algorithms | `algorithms/` | Planned |
| `bridge.md` | WP5 WebSocket bridge | `bridge/` | Planned |
| `ui.md` | WP5 GCS/UI | `ui/` | Planned |
| `monitor.md` | WP6 Traffic Monitor | `ui/monitor/` | Planned |
| `scenario.md` | WP7 Scenarios | `scenario/` | Planned |
| `logger.md` | WP7 Recording and replay | `logger/` | Planned |
| `payload.md` | WP8 Sensors, jammers and simulation events | `payload/` | Planned |
| `gateway.md` | WP9 A-GRA Gateway | `gateway/` | Planned |
| — | QA | `qa/` | Covered by chapter 10 |

## Figures

- Figures are shared with the Korean edition: [../../img/manual/dev/](../../img/manual/dev/).
