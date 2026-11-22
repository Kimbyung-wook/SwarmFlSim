# 8. WP7 Scenarios (`scenario/`)

> Source: [docs/41_dev/08_wp/scenario.md](../../../41_dev/08_wp/scenario.md) at commit `8ce186c`.

## Responsibilities

Handles the JSON scenario schema, semantic checks and proto conversion. How to write scenarios is in [chapter 3](../../42_user/03_scenario.md) of the user manual.

## Structure

| Path | Contents |
|---|---|
| `src/swarm_scenario/cli.py` | Command line |
| `src/swarm_scenario/schema/scenario.schema.json` | JSON Schema |
| `src/swarm_scenario/validate.py` | Semantic checks |
| `src/swarm_scenario/convert.py`, `enums.py` | JSON ⇄ proto |
| `examples/` | Example scenarios |

## Executable `swarm-scenario`

| Command | Meaning |
|---|---|
| `validate <file>` | Schema and semantic checks |
| `show <file>` | Prints a summary |
| `export <file> --out <file>` | Converts to `.pb` or proto JSON |

## Subscribed and published keys

None. It is a file tool. Core does the distribution on `sim/ctrl/scenario`.

## Tests

```bash
uv run pytest scenario/tests
```

## Known limitations

- `validate` does not include all of Core's checks. IDs over 25 characters and two jammers are refused by Core.
- `validate` refuses `dof5` and `dof6` as not implemented (roadmap P3). When they are implemented, add them to `IMPLEMENTED_DYNAMICS` in `validate.py`.
- `run.rate` must be greater than 0. Maximum speed is given with Core's `--rate 0`.
- `run.epoch_utc` (ISO 8601, time zone required) converts to `RunSpec.epoch_utc_us` (Unix epoch µs). The reverse conversion writes UTC `Z`. Empty means 0, and Core fills it in. `1970-01-01T00:00:00Z` cannot be told apart from 0 and is rejected (IMP-SCN-012, DEC-098).

Traceability: [scenario/TRACE.md](../../../../scenario/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
