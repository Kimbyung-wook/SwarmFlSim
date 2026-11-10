# 8. WP8 Payload (`payload/`)

> Source: [docs/41_dev/08_wp/payload.md](../../../41_dev/08_wp/payload.md) at commit `f7bcbac`.

## Responsibilities

A library that computes sensor detection, jammer zones, guided object flight and simulation event evaluation (DEC-046). It is a pure calculator with inputs and outputs only and does not use the bus. Core calls it every frame.

## Structure

| Path | Contents |
|---|---|
| `include/swarm/payload/payload.hpp`, `src/payload_system.cpp` | `PayloadSystem::step(FrameInput)` → `FrameOutput` |
| `include/swarm/payload/geometry.hpp`, `src/geometry.cpp` | FOV, range and line-of-sight geometry |
| `include/swarm/payload/weapon.hpp`, `src/weapon.cpp` | Guided object flight |
| `include/swarm/payload/profiles.hpp`, `src/profiles.cpp` | Reading profiles and overrides |
| [`profiles/`](../../../../payload/profiles/) | Equipment profile JSON |

The numbers are in the profile files. How to override them from a scenario with a profile name and `overrides` is in [3.8](../../42_user/03_scenario.md#38-onboard-payloads-payloads) of the user manual.

## Executable

None. It is linked into Core as the library `swarm_payload`.

## Subscribed and published keys

None. Core moves `FrameInput` and `FrameOutput` to and from the bus.

## Tests

```bash
ctest --preset msvc-debug -R "^pay\."
```

## Known limitations

- IMPACT in `StrikeActivity` means only the arrival of the guided object. Judge the effect from `truth/event/kill` (DEC-067).
- Only one jammer per entity is accepted.
- If it leaves the FOV in flight, guidance stops and is not reacquired.
- Baseline MAs do not issue equipment commands. Tests and MA plugins send them with `ms.command`.

Traceability: [payload/TRACE.md](../../../../payload/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
