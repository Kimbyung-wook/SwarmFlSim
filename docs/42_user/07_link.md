# 7. 데이터링크 상황 만들기

기체 간·지상-기체 간 메시지는 모두 Datalink를 거친다. 지연·손실·대역폭·재밍을 시나리오와 고장 주입으로 조절하고, 결과는 Traffic Monitor로 본다.

## 7.1 링크 프로파일

엔티티의 `link_profile`이 프로파일 이름을 가리킨다. 내장 프로파일:

| 이름 | 쓰임 | 특징 |
|---|---|---|
| `default`, `uav_default` | 기체 | 2.4 GHz, 지연 20 ms, 지터 5 ms, 1 Mbps |
| `gcs_default` | GCS | 지연 50 ms, 지터 10 ms, 2 Mbps |
| `fpv_default` | 소형 비행체 | 5.8 GHz, 지연 10 ms, 지터 3 ms, 500 kbps |
| `ideal` | 시험용 | 거리 제한·지연·손실 없음 |

시나리오 최상위 `link_profiles`로 추가하거나 고친다. `base`를 복사한 뒤 적은 필드만 덮어쓴다. `base`를 비우면 같은 이름의 내장 프로파일을, 없으면 `default`를 쓴다.

```json
"link_profiles": [
  { "name": "uav_slow", "base": "uav_default", "latency_ms": 80.0, "jitter_ms": 20.0 }
]
```

| 필드 | 뜻 |
|---|---|
| `latency_ms`, `jitter_ms` | 고정 지연, 정규 지터 표준편차 |
| `bandwidth_bps`, `bucket_bytes`, `queue_len` | 토큰 버킷 채움 속도(0이면 무제한), 깊이, 대기 메시지 상한(0이면 무제한) |
| `freq_mhz`, `tx_power_dbm`, `antenna_gain_dbi`, `noise_floor_dbm`, `snr_min_db` | 경로손실·SNR 판정 |
| `max_range_m`, `unlimited_range` | 거리 상한(0이면 SNR로만), 거리 판정 끄기 |
| `ge` | 버스트 손실 Gilbert-Elliott: `p_gb`, `p_bg`, `loss_good`, `loss_bad`. 있으면 네 값 모두 덮어쓴다 |

## 7.2 메시지가 사라지는 이유

사유별 뜻은 Monitor의 [손실 사유 표](06_monitor.md#62-손실-사유)와 같다. `NO_LOS`에서 Datalink는 평지만 본다([4.5](04_run.md#45-지형과-적분기)). `FAULT_INJECTED`는 [7.4](#74-고장-주입)로 만든다.

## 7.3 재밍 구역

재밍 구역은 `jammer` 장비에서 생긴다. `jammer_site` 엔티티에 달면 고정 구역이 된다([3.8](03_scenario.md#38-탑재-장비-payloads)).

```mermaid
flowchart LR
    GCS["GCS"] -- "수신자가 구역 안 → JAMMED" --x U1["구역 안 기체"]
    U1 -- "수신자가 구역 밖 → 전달" --> GCS
    U2["구역 밖 기체"] -- "전달" --> GCS
```

- 수신단 기준이다. 구역 안 기체가 구역 밖으로 보낸 메시지는 전달된다(DEC-028, DEC-055).
- `link/state`는 양쪽 중 하나라도 구역 안이면 jammed로 표시한다.
- 주파수대는 모의하지 않는다.
- 구역은 UI 지도에 진영색 기둥으로 표시된다.

## 7.4 고장 주입

UI에는 고장 주입 버튼이 없다. 실행 중인 버스에 스크립트로 보낸다.

```bash
uv run python qa/inject_fault.py --connect tcp/127.0.0.1:17601 --entity uav-003 --kind LINK_CUT --duration 10
```

- `--connect`는 버스에 떠 있는 프로세스의 listen 주소다. 데모는 `17601`(Datalink)을 쓰면 된다.
- `--duration`은 초. 생략하면 해제할 때까지 유지한다. 해제는 같은 명령에 `--clear`.

| `--kind` | 효과 | 처리 프로세스 |
|---|---|---|
| `LINK_CUT` | 대상의 모든 링크 차단 | Datalink |
| `GCS_LINK_CUT` | 대상과 GCS 사이 링크만 차단 | Datalink |
| `ENGINE` | 속도 명령을 최소로 | Core |
| `NAV` | 항법 보고 중단 | Core |
| `SENSOR` | 탐지 중단, 센서 비활성 보고 | Core |
| `KILL` | 엔티티 파괴 | Core |

- 해제하거나 기간이 지나면 정상으로 돌아간다. Reset은 모든 고장을 푼다.
- 고장은 `SystemStatus`의 health·subsystems로도 GCS에 보고된다. 링크가 끊긴 동안 생긴 변화는 다음 변화가 있어야 도착한다.

> 미구현: 링크 상실 시 기체 행동(로드맵 P2). 기본 MA는 링크가 끊겨도 마지막 작업을 계속한다.

> 미구현: 피어 중계(멀티홉). 링크가 직접 닿는 수신자에게만 전달한다.

## 7.5 결과 확인

Traffic Monitor의 통계 표와 타임라인에 손실 사유가 나온다. 화면 읽는 법은 [6장](06_monitor.md). 지나간 실행은 [8장](08_record_replay.md)으로 재생해 같은 화면에서 본다.

다음: [8. 기록과 재생](08_record_replay.md).
