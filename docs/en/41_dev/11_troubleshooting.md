# 11. Troubleshooting

> Source: [docs/41_dev/11_troubleshooting.md](../../41_dev/11_troubleshooting.md) at commit `24fc9be`.

- For install and build failures, see [1.4](01_setup.md#14-common-failures) first. Symptoms from the user's point of view are in [user manual chapter 10](../42_user/10_faq.md).
- Where process logs are depends on how you ran things. The demo runner collects them in `out/p0_demo/<mode>-<time>/<process>.log`.

## 11.1 Lockstep

| Symptom | Cause | Fix |
|---|---|---|
| The first tick does not go out | A participant in `run.participants` has not sent the ready signal (`FrameDone{0}`). It did not start or its ID differs | Match the waiting-participant list in the Core log against each process's `--participant` |
| Stops during a run. UI and Monitor show waiting participants | A participant died or does not respond (DEC-041) | Rejoining is not supported. Restart the participant, then Reset+Start |
| Trajectories differ with the same seed | The plugin depends on random numbers other than `ctx.rng`, wall clocks or receive order. Or it ran in realtime or free-run | Check the rules in [3.6](03_architecture.md#36-one-lockstep-frame). Use `qa/diag_determinism.py` to find the first diverging frame |
| Rate is below target | The Python Agent is the bottleneck. `frame_overruns` increases | Split vehicles across Agents (`--entities`) or lower the rate |

## 11.2 Bus

| Symptom | Cause | Fix |
|---|---|---|
| Processes do not see each other | Endpoints do not match or multicast is blocked | Set `--listen`/`--connect` explicitly. Later processes connect to the listen address of the earlier ones |
| Messages from another run are mixed in | Joined another bus on the same PC by multicast | `--no-multicast` on all processes |
| Fails at start because a port cannot be opened | Another run is using the port | Change `--base-port`, `--bridge-port` or the listen port. The bridge and CAL Server both default to 8765, so change one when running both |
| A C++ process comes up only with the memory backend | Built without Zenoh | [1.4](01_setup.md#14-common-failures) |

## 11.3 Plugins and parameters

| Symptom | Cause | Fix |
|---|---|---|
| The plugin cannot be found | The entry point is not registered or `uv sync` was not run | Check the name with `uv run swarm-agent --list-plugins` |
| A parameter is not applied | It was rejected | See the `rejected` reason on `sim/param/<entity>/<owner>`. It is also shown in the UI parameter panel |
| `TaskStatus` states arrive out of order | Datalink latency and jitter | No effect on the outcome. Judge by `task_id` and the final state |
| Route is `REJECTED` in flocking | Not supported | Use waypoint |

## 11.4 Code generation

| Symptom | Cause | Fix |
|---|---|---|
| `swarm.v1` import fails in Python | No generated code | `uv run python scripts/gen_proto.py` |
| A field is missing after pulling proto | The generated code is old | Run the command above again. Rebuild C++ |
| The contract version shows differently | An old bridge or UI was started | Compare `contract` in the bridge `welcome` with `CONTRACT_VERSION` and pull again |

## 11.5 Diagnostic tools

```bash
uv run --with psutil python qa/run_qa.py --list
```

```bash
<build>/logger/swarm_logger info <file.mcap>
```

- `swarm_logger info` shows the message count and time range per channel. Use it to check what went out on the bus.
