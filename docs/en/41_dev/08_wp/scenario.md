# 8. WP7 Scenarios (`scenario/`)

> Source: [docs/41_dev/08_wp/scenario.md](../../../41_dev/08_wp/scenario.md) at commit `7affdae`.

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

- `validate` does not include all of Core's checks. IDs over 25 characters, two jammers, and `dof5`/`dof6` are refused by Core.
- `run.rate` must be greater than 0. Maximum speed is given with Core's `--rate 0`.

Traceability: [scenario/TRACE.md](../../../../scenario/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
