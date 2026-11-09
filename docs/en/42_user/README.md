# User manual

> Source: [docs/42_user/README.md](../../42_user/README.md) at commit `bbf4d92`.

- Readers: researchers and operators who write scenarios, run the simulator, operate the UI and replay recordings without changing code.
- New to the project? Read the [project overview](../40_overview.md) first. For building, follow [chapters 1 and 2](../41_dev/README.md) of the developer manual.
- Writing plan: [30_doc_plan.md](../../30_doc_plan.md) (Korean) §5.

## Chapters

| Ch. | File | Contents | Status |
|---|---|---|---|
| 1 | [`01_install.md`](01_install.md) | Preparation: required build outputs, map data (DEM, terrain and imagery tiles) | Written |
| 2 | [`02_quickstart.md`](02_quickstart.md) | Quick start: launch everything with the demo runner, send a move command, shut down | Written |
| 3 | [`03_scenario.md`](03_scenario.md) | Writing scenarios: structure, entities, autonomy plugins, mission plans, payloads, validation | Written |
| 4 | [`04_run.md`](04_run.md) | Running: per-process launch, run modes and rate, terrain options, multi-PC runs | Written |
| 5 | [`05_ui.md`](05_ui.md) | Operating the GCS UI: selection, mission window, command panel, parameters, camera, event display | Written |
| 6 | [`06_monitor.md`](06_monitor.md) | Traffic Monitor: reading the screens, loss reasons, aggregation definitions | Written |
| 7 | [`07_link.md`](07_link.md) | Creating datalink conditions: link profiles, jamming zones, fault injection | Written |
| 8 | [`08_record_replay.md`](08_record_replay.md) | Recording and replay: `swarm_logger`, what is shown during replay | Written |
| 9 | [`09_gateway.md`](09_gateway.md) | A-GRA Gateway: exchanged messages, launch order, external C2 rules | Written |
| 10 | [`10_faq.md`](10_faq.md) | Troubleshooting: fixes by symptom | Written |

- To try it right now, go to [2. Quick start](02_quickstart.md).

## Figures

- Figure files are in [../../img/manual/user/](../../img/manual/user/). Screenshots use the built-in imagery.
