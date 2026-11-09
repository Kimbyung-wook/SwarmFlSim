# Developer manual

> Source: [docs/41_dev/README.md](../../41_dev/README.md) at commit `7affdae`.

- Readers: algorithm plugin authors (writing MA/FA in Python) and WP contributors (changing a specific directory while following the test, traceability and contract rules).
- New to the project? Read the [project overview](../40_overview.md) first.
- [10_contracts.md](../../10_contracts.md) (Korean) is the authority for contracts (keys, schemas, protocols, build setup). This manual links to its sections.
- Writing plan: [30_doc_plan.md](../../30_doc_plan.md) (Korean) §4.

## Reading order

| Reader | Order |
|---|---|
| Algorithm plugin author | 1 → 2 (Python parts) → 3 → 4 → 5 |
| WP contributor | 1 → 2 → 3 → 8 (own WP) → 9 → 10 |

## Chapters

| Ch. | File | Contents | Status |
|---|---|---|---|
| 1 | [`01_setup.md`](01_setup.md) | Development environment: choosing a toolchain, installation, common failures | Written |
| 2 | [`02_build_test.md`](02_build_test.md) | Build and test: C++, Python, UI, Gateway, generated code | Written |
| 3 | [`03_architecture.md`](03_architecture.md) | Architecture and execution model: processes, bus key access rules, run modes, lockstep | Written |
| 4 | [`04_ma_plugin.md`](04_ma_plugin.md) | Writing an MA plugin: walkthrough, ports, parameters, batch calls, tests. Example package `examples/plugins/` (DEC-070) | Written |
| 5 | [`05_fa_plugin.md`](05_fa_plugin.md) | Writing an FA plugin: VI control modes, the default FA | Written |
| 6 | [`06_dynamics.md`](06_dynamics.md) | Adding a dynamics model: interfaces, factory, parameters, tests | Written |
| 7 | [`07_messages.md`](07_messages.md) | Messages and contracts: proto roles, A-GRA mapping options, adding a message | Written |
| 8 | `08_wp/` | Per-WP contribution guide (table below) | Written |
| 9 | [`09_contributing.md`](09_contributing.md) | Contribution rules: IDs, TRACE, commits, contract change requests | Written |
| 10 | [`10_qa.md`](10_qa.md) | QA harness: `qa/run_qa.py`, scenarios, determinism diagnostics | Written |
| 11 | [`11_troubleshooting.md`](11_troubleshooting.md) | Troubleshooting: symptom → cause → fix | Written |

### Chapter 8 files (`08_wp/`)

| File | WP | Directory | Status |
|---|---|---|---|
| [`core.md`](08_wp/core.md) | WP1 Sim Core | `core/` | Written |
| [`dynamics.md`](08_wp/dynamics.md) | WP2 Dynamics | `dynamics/` | Written |
| [`datalink.md`](08_wp/datalink.md) | WP4 Datalink | `datalink/` | Written |
| [`agent.md`](08_wp/agent.md) | WP3 Agent runtime | `agent/` | Written |
| [`algorithms.md`](08_wp/algorithms.md) | WP3 Baseline algorithms | `algorithms/` | Written |
| [`bridge.md`](08_wp/bridge.md) | WP5 WebSocket bridge | `bridge/` | Written |
| [`ui.md`](08_wp/ui.md) | WP5 GCS/UI | `ui/` | Written |
| [`monitor.md`](08_wp/monitor.md) | WP6 Traffic Monitor | `ui/monitor/` | Written |
| [`scenario.md`](08_wp/scenario.md) | WP7 Scenarios | `scenario/` | Written |
| [`logger.md`](08_wp/logger.md) | WP7 Recording and replay | `logger/` | Written |
| [`payload.md`](08_wp/payload.md) | WP8 Sensors, jammers and simulation events | `payload/` | Written |
| [`gateway.md`](08_wp/gateway.md) | WP9 A-GRA Gateway | `gateway/` | Written |
| — | QA | `qa/` | Replaced by [chapter 10](10_qa.md) |

## Figures

- Figure files are in [../../img/manual/dev/](../../img/manual/dev/).
