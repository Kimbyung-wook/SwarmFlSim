# 8. WP7 Recording and replay (`logger/`)

> Source: [docs/41_dev/08_wp/logger.md](../../../41_dev/08_wp/logger.md) at commit `24fc9be`.

## Responsibilities

Records bus messages to MCAP and publishes them again at the original intervals. Usage is in [chapter 8](../../42_user/08_record_replay.md) of the user manual.

## Structure

| Path | Contents |
|---|---|
| `src/main.cpp` | Entry point, subcommands |
| `src/mcap_log.cpp`, `include/swarm/logger/mcap_log.hpp` | `Recorder`, `replay`, `inspect` |

Channels are the same as bus keys, and schemas are stored as FileDescriptorSet.

## Executable `swarm_logger`

| Command | Options |
|---|---|
| `info <file>` | Summary |
| `record --out <file>` | `--key <expr>`, `--stats <s>`, `--max-queue-messages <n>`, `--max-queue-mib <n>`, bus options |
| `replay <file>` | `--rate <x>`, `--key <expr>`, `--dry-run`, bus options |

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | Keys given with `--key` when recording. All by default |
| Publish | Recorded keys as they are during replay. `SimStatus` has `replay` changed to true (DEC-031) |

## Tests

```bash
ctest --preset msvc-debug -R "swarm_logger"
```

The TC-LOG items are gathered in one executable.

## Known limitations

- If the Logger does not exit normally, the file is not closed.
- The replayer does not adapt to receiver speed (DEC-042).
- Above the queue limit, messages are dropped and the count is left.

Traceability: [logger/TRACE.md](../../../../logger/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
