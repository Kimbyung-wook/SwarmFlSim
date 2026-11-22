# 9. A-GRA Gateway 연동

시뮬레이터의 GCS 쪽 메시지를 외부 A-GRA 시스템과 주고받는다. Gateway는 CAL Server를 거쳐 외부 C2와 통신한다(DEC-068, DEC-069).

```mermaid
flowchart LR
    SIM["Datalink"] -- "swarm/gcs-01/rx/**" --> GW["Gateway"]
    GW -- "UCI OMS JSON" --> CAL["CAL Server"]
    CAL --> EXT["외부 C2"]
    EXT -- "작업 명령 · 승인 응답 · 임무 계획" --> CAL
    CAL --> GW
    GW -- "swarm/gcs-01/tx/c2/* · tx/mp/*" --> SIM
```

교환 메시지 전체 표는 [gateway/README.md](../../gateway/README.md#교환-메시지)에 있다. 기체 위치(`MA_NavigationReport`, `MA_PositionReport`), 작업 상태(`MA_TaskStatus`), 비행 명령 상태(`MA_FlightCommandStatus`), 기체가 낸 승인 요청(`MA_ApprovalRequest`)·리더 변경(`MA_LeaderUpdateRequest`)·탐지 공유(`MA_Entity`)·적재 구성(`StoreLoadoutConfiguration`, DEC-088)을 내보내고 `MA_TaskCommand`, `MA_ApprovalRequestStatus`, `MA_RoutePlan`, `MA_MissionPlan`을 받는다.

## 9.1 준비

```bash
git submodule update --init third_party/agra_lacal
```

```bash
cd gateway && uv sync --extra zenoh
```

> 주의: `--extra zenoh`를 빼면 Gateway는 설치 방법을 알리고 종료 코드 1로 끝난다. 시뮬레이터 없이 확인만 할 때는 `--bus memory`를 명시한다. 이때는 시뮬레이터 메시지가 오지 않는다.

## 9.2 실행 순서

```mermaid
sequenceDiagram
    participant C as CAL Server
    participant S as 시뮬레이터
    participant G as Gateway
    participant E as 외부 C2
    C->>C: 1. 기동 (ws://127.0.0.1:8765)
    S->>S: 2. 데모 또는 프로세스 기동
    G->>C: 3. 접속, XSD 적재
    G->>S: 구독
    G-->>G: ready 로그
    E->>C: 4. 접속 (external_c2)
    E->>C: MA_TaskCommand
    C->>G: 전달
```

**1. CAL Server를 띄운다.**

```bash
cd gateway && uv run python -m swarm_gateway.lacal_server --config config/lacal_server.yaml
```

**2. 시뮬레이터를 띄운다.** CAL Server가 8765 포트를 쓰므로 브리지 포트를 바꾼다.

```bash
uv run python scripts/run_p0_demo.py live --bridge-port 8770
```

브라우저 UI는 URL의 `bridge=`도 `ws://127.0.0.1:8770/bus`로 준다.

**3. Gateway를 띄운다.** `--no-multicast`와 `--connect`로 시뮬레이터 버스에 직접 붙는다.

```bash
cd gateway && uv run python -m swarm_gateway --gcs gcs-01 --lacal ws://127.0.0.1:8765 --no-multicast --connect tcp/127.0.0.1:17600 --connect tcp/127.0.0.1:17601
```

`--connect`의 포트는 실행기의 `--base-port`(기본 17600)를 따른다. `--participant <id>`는 Gateway의 발행자 ID다(기본 `gateway-0`).

| 옵션 | 뜻 |
|---|---|
| `--sim-epoch <UTC>` | UCI 시각의 기준 시각을 고정한다. ISO 8601, 시간대 필수(예: `2026-01-01T00:00:00Z`). 시나리오 값보다 앞선다. 재현 시험용이다. 보통은 비워 시나리오 값을 쓴다([UCI 시각](#uci-시각)) |
| `--lacal-admin <url>` | CAL Server 관리 주소. 기본은 `--lacal` 호스트의 8766. 새 외부 구독을 알아내 마지막 값을 다시 보낼 때 쓴다. `none`이면 끈다 |

**4. 외부 C2를 붙인다.** 같은 CAL Server에 `external_c2` 서비스로 접속해 `swarm.c2` 토픽에 `MA_TaskCommand`·`MA_ApprovalRequestStatus`를, `swarm.mp` 토픽에 `MA_RoutePlan`·`MA_MissionPlan`을 보낸다. 시험용 클라이언트 구현은 [qa/gw_ext_client.py](../../qa/gw_ext_client.py)에 있다.

## 9.3 시작 직후

Gateway는 접속 뒤 XSD를 적재한다. 확인 실행에서 약 9초 걸렸다. 그동안 외부가 보낸 명령은 서버가 `+OK`로 답해도 받는 쪽이 없어 사라진다(O-13). 외부 C2는 `ready` 줄이 나온 뒤 명령을 보낸다.

| 로그 | 뜻 |
|---|---|
| `LA-CAL connected ... not ready yet` | 접속만 됐다 |
| `XSD loaded, mapping built` | 검증 준비 완료 |
| `LA-CAL SUB MA_TaskCommand@swarm.c2 done` | 외부 명령 구독 완료 |
| `ready at +N s` | 양방향 준비 완료 |

## 9.4 외부 `MA_TaskCommand` 규칙

이 규칙은 위치가 필요 없는 작업과 취소에만 쓴다(DEC-076).

- `Command` 항목 하나가 수행 기체 하나다.
- `CapabilityID.DescriptiveLabel` = `<엔티티 ID>/<작업 종류>`.
- 작업 종류는 `hold`(현재 위치 선회 대기)와 `return_to_base`만 받는다.
- `TaskID.DescriptiveLabel`이 내부 작업 ID가 된다.
- `CommandState`가 `CANCEL`이면 취소다.
- 모든 항목의 `TaskID`와 `CommandState`가 같아야 한다.

이동 목적지처럼 위치 정보가 필요한 작업은 [9.6](#96-임무-계획-수신)의 임무 계획으로 받는다.

`hold`를 보내면 `MA_TaskStatus`로 `EXECUTION_PENDING` → `EXECUTING`이 온다. 기체가 맡고 있던 이전 작업은 `CANCELED`가 된다.

## 9.5 외부 승인 응답

`MA_ApprovalRequestStatus`를 `swarm.c2`로 받아 `ApprovalResponse`로 보낸다(DEC-075).

- 기체 쪽 승인 요청은 MA 변수 `approval_tasks`로 켠다([3.6](03_scenario.md#36-자율-플러그인-autonomy)). 요청은 `MA_ApprovalRequest`로 나가고 `RespondBy`는 보고 시각 + 승인 대기 시간이다.
- `RequestProcessingState`가 `COMPLETED`이고 `ApprovalRequestProcessingState`가 `APPROVED` 또는 `REJECTED`인 것만 받는다. 그 밖의 상태는 거부한다.
- Gateway가 내보낸 요청이면 요청한 기체로만 보낸다. 모르는 요청(재기동 뒤 포함)은 `dst`를 비워 보내고 받는 쪽이 `request_id`로 가른다.

## 9.6 임무 계획 수신

`MA_RoutePlan`·`MA_MissionPlan`을 `swarm.mp`로 받아 `RoutePlan`·`MissionPlan`으로 보낸다(DEC-076). 지원·거부 항목의 전체 표는 [gateway/README.md](../../gateway/README.md#임무-계획-수신-dec-076)에 있다.

- `MA_RoutePlan`을 먼저 보낸 뒤 그 경로를 참조하는 `MA_MissionPlan`을 보낸다. 받은 경로는 Gateway 메모리에만 있어(최근 1024건) 재기동 뒤에는 다시 보낸다.
- `MA_MissionPlan`은 참조한 경로마다 작업 하나가 된다. 항로점 하나면 `move_to`, 둘 이상이면 `route`이고 `task_id`는 경로 ID다.
- 대상은 `ApplicableToIDs/SystemID` 하나다. `ALL`, `NON`, `PackageID`는 거부한다(CR-GW-009).
- 영역 탐색처럼 경로로 표현되지 않는 작업은 받지 못한다(CR-GW-007).

내장 MA는 실행 중 받은 계획을 다음과 같이 반영한다.

| 받은 것 | 동작 |
|---|---|
| 이미 본 `plan_id`의 `MissionPlan` | 내용이 달라도 무시 |
| 새 `plan_id`의 `MissionPlan` | 교체. 수행 중 작업과 대기 작업은 `CANCELLED`가 되고 새 계획을 수행한다 |
| 같은 ID의 계획 작업이 있는 `RoutePlan` (`waypoint`) | 따로 비행하지 않고 그 작업이 수행한다. `RoutePlan`과 `MissionPlan`을 어느 순서로 보내도 `COMPLETED`로 끝난다 |
| 계획에 없는 단독 `RoutePlan` (`waypoint`) | 바로 비행한다. 수행 중 작업은 `CANCELLED`, 대기 작업은 항로가 끝나면 잇는다. `RoutePlan` 자체의 작업 상태는 오지 않는다 |

- `flocking`은 항로점 둘 이상의 `route` 작업을 거부한다.
- `flocking`은 `EXECUTING`을 보내지 않아 외부의 마지막 값이 `EXECUTION_PENDING`으로 남는다(O-28).

### 외부로 내는 상태와 시각

외부 시스템이 보는 규칙이다. 자세한 내용은 [gateway/README.md](../../gateway/README.md#늦게-붙은-외부-시스템-dec-089)에 있다.

#### 늦게 붙은 외부 시스템

- 변화 보고(기체 상태, 비행 능력, 장비 상태, 적재 구성, 작업 상태)는 값이 바뀔 때만 나간다. Gateway는 마지막 값을 들고 있다가 외부 시스템이 그 메시지를 새로 구독하면 한 번 다시 보낸다(DEC-089).
- 위치 같은 주기 보고, 승인 요청, 리더 변경, 탐지 공유, 비행 명령 상태는 다시 보내지 않는다.
- 다시 보낸 값은 같은 토픽의 기존 구독자에게도 한 번 더 간다. Gateway를 다시 띄우면 보관 값이 없다.
- 외부 상태 값은 공개 XSD enum 그대로다. `MA_FlightCommandStatus`에는 수행·완료 값이 없어 `ACCEPTED`로 보인다. 수행·완료는 `MA_TaskStatus`에서 읽는다(DEC-090).

#### 명령 상태

- `MA_FlightCommandStatus`는 UCI Command-2 상태 기계를 따른다. `ACCEPTED`, `REJECTED`, `CANCELED`가 끝 상태다(DEC-097).
- 한 기체의 한 `CommandID`에 끝 상태를 한 번 낸 뒤에는 그 ID의 상태를 더 내지 않는다. `RECEIVED` 반복도 내지 않는다. 막은 수는 카운터 `skipped_command_state`에 남는다.
- 첫 보고는 무엇이든 낸다. 접수 전에 다른 명령으로 바뀐 명령은 첫 보고가 `CANCELED`일 수 있다.
- Gateway를 다시 띄우면 끝난 ID를 기억하지 못해 같은 끝 상태가 ID당 최대 한 번 더 나갈 수 있다.

#### UCI 시각

UCI 머리 `Timestamp`와 위치·속도·자세 시각은 벽시계가 아니라 메시지 모의 시각의 UTC다. UTC = 기준 시각 + 모의 시각이고, 기준 시각은 다음 순서로 정한다(DEC-098).

1. `--sim-epoch`. 시나리오 값이 와도 바꾸지 않는다.
2. 시나리오의 `run.epoch_utc`. 적지 않았으면 Core가 채운 값이다([3.4](03_scenario.md#34-map-run)). 보통 이 값을 쓴다.
3. 시나리오를 받기 전에 온 첫 메시지. 그때의 벽시계 − 그 모의 시각이고, 경고 로그 `no scenario epoch yet`이 남는다.

- 3으로 정한 뒤 시나리오 값이 오면 시나리오 값으로 바꾼다. 경고 로그 `UCI time base changed`와 카운터 `epoch_changed`가 남는다. 새 시나리오의 다른 값도 같다.
- 한 기준 안에서는 일시정지·배속에서도 (Timestamp − 모의 시각)이 일정하다.

#### 모르는 기체를 가리키는 명령

- 외부 `MA_TaskCommand`, `MA_RoutePlan`, `MA_MissionPlan`이 가리키는 기체가 하나라도 알려지지 않았으면 버스에 내지 않고 거부한다(D-35). 경고 로그 `unknown entity [...]`와 카운터 `ext_rejected`가 남는다.
- 알려진 기체는 시나리오(`sim/ctrl/scenario`, Gateway는 읽기만 한다)의 UAV와 이 GCS가 보고를 받은 기체다. truth는 쓰지 않는다(DEC-096).
- `MA_TaskCommand`, `MA_MissionPlan`을 거부하면 모르는 기체별로 `MA_TaskStatus`(`DROPPED`, 사유 포함)를 보내 외부에 알린다. `MA_RoutePlan`은 알릴 상태 메시지가 없어 기록만 남는다.

## 9.7 카운터와 거부

`--stats-s` 주기로 `counters` 로그가 나온다.

| 항목 | 뜻 |
|---|---|
| `rx` | 버스에서 받은 메시지 |
| `exported`, `exported.<UCI 메시지>` | XSD 검증을 통과해 내보낸 수 |
| `sent` | LA-CAL로 보낸 수 |
| `ext_rx` | 외부에서 받은 명령 |
| `ext_published` | 버스로 내보낸 명령 |
| `ext_rejected` | 모르는 기체를 가리켜 거부한 외부 명령 |
| `skipped_command_state` | 끝 상태 뒤라서 내지 않은 명령 상태 |
| `replayed` | 늦게 붙은 외부 구독에 다시 보낸 값 |
| `epoch_changed` | UCI 기준 시각을 시나리오 값으로 바꾼 횟수 |

- XSD 검증이나 변환에 실패한 메시지는 내보내지 않고 로그와 카운터에 남긴다. Gateway는 계속 돈다.
- 위치 대응 메시지 하나가 실패해도 다른 대응 메시지는 내보낸다.

> lockstep으로 돌려도 외부 입력이 있으면 같은 시드 결과가 같지 않다. Gateway 발행 시각이 입력이 도착한 시점의 틱이라 입력을 받은 기체의 궤적이 실행마다 달라진다. 외부 입력이 없는 구성은 궤적, 링크 결과, GCS 수신이 같다.

다음: [10. 문제 해결](10_faq.md).
