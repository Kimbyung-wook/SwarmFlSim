# 10. Troubleshooting

> Source: [docs/42_user/10_faq.md](../../42_user/10_faq.md) at commit `f7bcbac`.

Look up by symptom. For build and code-level issues see [developer manual chapter 11](../41_dev/11_troubleshooting.md).

If you used the runner, process logs are in `out/p0_demo/<mode>-<time>/<process>.log`.

## 10.1 Map

| Symptom | Cause | Fix |
|---|---|---|
| The map is low resolution and the terrain is flat | No local tiles. The toolbar shows `지도 내장 · 지형 타원체` (Built-in map, Ellipsoid terrain) | Make tiles as in [1.2](01_install.md#12-map-data-optional). Running is not affected without them |
| Entities are not visible on screen | The camera is looking elsewhere | Press `전체` (Fit all) on the toolbar |

## 10.2 Connection

| Symptom | Cause | Fix |
|---|---|---|
| The UI shows no connection | No bridge, or the address differs | Match `bridge=` in the URL with the bridge port. Default `ws://127.0.0.1:8765/bus` |
| Shows `목 소스` (Mock source) | The URL has no `source=bus` | Open the address from chapter 2. Or choose `버스(브리지)` (Bus via bridge) on the toolbar |
| `시뮬레이션 응답 없음` (Simulation not responding) on the toolbar | Core stopped or died | Check the Core log |
| The runner does not start because of a port | Another run is using the port | Change with `--base-port`, `--bridge-port`, `--ui-port`, `--monitor-port` |

## 10.3 Commands and motion

| Symptom | Cause | Fix |
|---|---|---|
| Mission panel shows `REJECTED`, reason `unsupported task` | This MA does not support the task | See the table in [3.6](03_scenario.md#36-autonomy-plugins-autonomy). Baseline MAs do not execute `track`, `strike` or `jam` |
| Route send is `REJECTED` | flocking does not support Route | Use `waypoint` |
| `StrikeActivity` is `REJECTED`, reason `out_of_fov` | The aim point is outside the search FOV of the launching vehicle (DEC-066) | Normal evaluation. Check the aim point the plugin sent |
| `StrikeActivity` is IMPACT but the target is unchanged | IMPACT means only the arrival of the guided object (DEC-067) | Judge the effect from `truth/event/kill` |
| Status appears with executing and accepted in reversed order | Datalink latency and jitter | No effect on the outcome |
| Some vehicles do not move after a command | The link is cut or they are inside a jamming zone | Check the loss reason in the Traffic Monitor ([chapter 7](07_link.md#72-why-messages-disappear)) |
| Rate buttons are off | Realtime is fixed at rate 1. They are also off during replay | Run in lockstep |

## 10.4 Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `validate` is INVALID | Schema or semantic error | Fix the path in the output and run again |
| `validate` passes but the Core log shows `scenario rejected` | Core checks such as IDs over 25 characters, two jammers, out-of-range values | [3.9](03_scenario.md#39-check-summary) |
| A vehicle disappears right after start | It started below DEM terrain altitude | Raise the starting altitude (DEC-060) |
| A parameter does not change | The name is wrong, the value is out of range, or the item cannot be changed during a run | See the rejection reason in the UI parameter panel |

## 10.5 Gateway

| Symptom | Cause | Fix |
|---|---|---|
| Prints `Zenoh 백엔드를 쓸 수 없습니다` (Zenoh backend unavailable) right at start and exits | Installed without `--extra zenoh` | [9.1](09_gateway.md#91-preparation) |
| No response to external commands | Sent before `ready` | Send again after `ready` |
| The bridge and CAL Server do not start together | Both default to port 8765 | Change with `--bridge-port` |

## 10.6 lockstep

| Symptom | Cause | Fix |
|---|---|---|
| Started but frames do not advance | Participant IDs differ from the scenario `participants`, or a process did not start | [4.4](04_run.md#44-lockstep), check the waiting list in the Core log |
| Participant wait indicator on the toolbar | A participant died | Restart the participant, then reset and start |
| The target rate is not reached | The Python Agent cannot keep up | Split Agents or lower the rate |

## 10.7 Recording and replay

| Symptom | Cause | Fix |
|---|---|---|
| Cannot open the MCAP | The Logger did not exit normally | Stop it with Ctrl+C. A forced kill leaves the file unclosed |
| Missing frames shown during replay | Receivers cannot keep up at high rate (DEC-042) | Lower `--rate` |
| Cannot send commands during replay | Normal. The replay URL leaves `gcs=` empty | |
