# 8. WP5 GCS/UI (`ui/`)

## 책임

지도 전시와 통제 화면이다. TypeScript, React, CesiumJS. 조작법은 사용자 매뉴얼 [5장](../../42_user/05_ui.md), 구조는 [ui/README.md](../../../ui/README.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/App.tsx` | 최상위, 단축키 |
| `src/data/` | `DataSource`: `MockSource`, `BusSource`, `BridgeTransport` |
| `src/model/` | Cesium에 의존하지 않는 상태와 명령: `LiveState`, `selection`, `C2Commander`, `TaskLog`, `camera` |
| `src/cesium/` | 엔티티 렌더링 |
| `src/components/` | `MapView`, `Toolbar`, `SelectionPanel`, `CommandPanel`, `MissionPanel`, `ParamPanel` |
| `src/gen/` | proto 생성물. 커밋하지 않는다 |

프레임마다 React를 다시 그리지 않는다. 지도는 Cesium 렌더 루프에서, 패널은 250 ms마다 갱신한다.

## 실행

```bash
cd ui && npm run dev
```

포트는 5173이다. URL 인자는 `source`(`mock` 기본, `bus`), `bridge`, `gcs`다.

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `truth/state`(30 Hz), `sim/ctrl/status`, `swarm/<gcs>/rx/**` |
| 발행 | `sim/ctrl/cmd`, `swarm/<gcs>/tx/c2/<msg>` |

브리지를 통해서만 버스에 붙는다.

## 시험

```bash
cd ui && npm test
```

`model/`과 `data/` 단위 시험이 중심이다. 드래그와 우클릭 같은 지도 조작은 자동 시험에 없고 브라우저에서 확인한다.

## 알려진 제약

- 시나리오 시작값 편집은 없다.
- 짐벌 각을 `SensorActivity`에서 받는 카메라 연동은 구조만 있다.
- 목 소스는 `TaskStatus(ACCEPTED)`만 돌려주고 기동을 흉내 내지 않는다.

추적: [ui/TRACE.md](../../../ui/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
