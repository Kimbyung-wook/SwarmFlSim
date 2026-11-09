# 8. WP6 Traffic Monitor (`ui/monitor/`)

## 책임

데이터링크 트래픽의 집계와 시각화를 맡는 별도 앱이다. 관찰만 하고 명령을 보내지 않는다. 화면 읽는 법은 사용자 매뉴얼 [6장](../../42_user/06_monitor.md), 구조는 [ui/monitor/README.md](../../../ui/monitor/README.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/App.tsx` | 화면 구성, 250 ms 갱신 |
| `src/bridge/` | `BridgeSource`, 프레임 해석 |
| `src/model/` | `MonitorStore`, `Aggregator`, 링 버퍼 |
| `src/components/` | `Header`, `FilterBar`, `EntityTree`, `StatsTable`, `Timeline`, `EntityDetail`, `EchoPanel` |
| `src/mock/` | 목 트래픽 |

프레임은 받는 즉시 동기 처리하고, 화면은 250 ms마다 보관소를 읽는다.

## 실행

```bash
cd ui/monitor && npm run dev
```

포트는 5174다. URL 인자는 `source`(`mock` 기본, `bridge`), `url`, `replay`, 목 소스용 `uavs`, `hz`, `rate`다.

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `link/outcome/**`, `link/state/**`, `swarm/*/tx/**`, `swarm/*/rx/**`, `truth/state`, `truth/event/**`, `sim/ctrl/status` |
| 발행 | 없음(`role=observer`) |

## 시험

```bash
cd ui/monitor && npm test
```

부하 측정은 `npm run bench`다.

## 알려진 제약

- 집계는 수신자별 `LinkOutcome` 기준이다. 브로드캐스트는 닿지 않는 수신자마다 손실 1건이 된다(DEC-032).
- 필터는 타임라인과 echo에 적용되고, 통계 표에는 엔티티 필터만 적용된다.

추적: [ui/monitor/TRACE.md](../../../ui/monitor/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
