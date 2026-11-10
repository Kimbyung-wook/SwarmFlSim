# 8. WP5 GCS/UI (`ui/`)

> Source: [docs/41_dev/08_wp/ui.md](../../../41_dev/08_wp/ui.md) at commit `f7bcbac`.

## Responsibilities

The map display and control screen. TypeScript, React, CesiumJS. Operation is in [chapter 5](../../42_user/05_ui.md) of the user manual, the structure in [ui/README.md](../../../../ui/README.md).

## Structure

| Path | Contents |
|---|---|
| `src/App.tsx` | Top level, shortcuts |
| `src/data/` | `DataSource`: `MockSource`, `BusSource`, `BridgeTransport` |
| `src/model/` | State and commands independent of Cesium: `LiveState`, `selection`, `C2Commander`, `TaskLog`, `camera`, `shortcuts` |
| `src/cesium/` | Entity rendering |
| `src/components/` | `MapView`, `Toolbar`, `SelectionPanel`, `CommandPanel`, `MissionPanel`, `ParamPanel` |
| `src/gen/` | Proto generated code. Not committed |

React is not re-rendered every frame. The map updates in the Cesium render loop, and the panels every 250 ms.

When an input field has focus, letter and number shortcuts are ignored and only Esc is handled (`model/shortcuts.ts`, IMP-UI-074).

## Running

```bash
cd ui && npm run dev
```

The port is 5173. URL arguments are `source` (`mock` default, `bus`), `bridge`, `gcs`.

## Subscribed and published keys

| Direction | Keys |
|---|---|
| Subscribe | `truth/state` (30 Hz), `sim/ctrl/status`, `swarm/<gcs>/rx/**` |
| Publish | `sim/ctrl/cmd`, `swarm/<gcs>/tx/c2/<msg>` |

It attaches to the bus only through the bridge. `publisher` of each `LinkEnvelope` it sends holds the UI participant ID, the same as `client` in the bridge hello (DEC-077).

## Tests

```bash
cd ui && npm test
```

Most tests are unit tests of `model/` and `data/`. Map operations such as drag and right-click are not in the automatic tests and are checked in a browser.

## Known limitations

- There is no editing of scenario start values.
- Camera integration that takes gimbal angles from `SensorActivity` exists only as structure.
- The mock source only returns `TaskStatus(ACCEPTED)` and does not simulate maneuvers.

Traceability: [ui/TRACE.md](../../../../ui/TRACE.md).

Next: [9. Contribution rules](../09_contributing.md).
