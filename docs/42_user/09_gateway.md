# 9. A-GRA Gateway 연동

시뮬레이터의 GCS 쪽 메시지를 외부 A-GRA 시스템과 주고받는다. Gateway는 CAL Server를 거쳐 외부 C2와 통신한다(DEC-068, DEC-069).

```mermaid
flowchart LR
    SIM["Datalink"] -- "swarm/gcs-01/rx/**" --> GW["Gateway"]
    GW -- "UCI OMS JSON" --> CAL["CAL Server"]
    CAL --> EXT["외부 C2"]
    EXT -- "MA_TaskCommand" --> CAL
    CAL --> GW
    GW -- "swarm/gcs-01/tx/c2/TaskCommand" --> SIM
```

교환 메시지 전체 표는 [gateway/README.md](../../gateway/README.md#교환-메시지)에 있다. 기체 위치(`MA_NavigationReport`, `MA_PositionReport`), 작업 상태(`MA_TaskStatus`), 비행 명령 상태(`MA_FlightCommandStatus`)를 내보내고 `MA_TaskCommand`를 받는다.

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

`--connect`의 포트는 실행기의 `--base-port`(기본 17600)를 따른다.

**4. 외부 C2를 붙인다.** 같은 CAL Server에 `external_c2` 서비스로 접속해 `swarm.c2` 토픽에 `MA_TaskCommand`를 보낸다. 시험용 클라이언트의 구현 예는 [qa/gw_ext_client.py](../../qa/gw_ext_client.py)다.

## 9.3 시작 직후

Gateway는 접속 뒤 XSD를 적재한다. 이번 확인에서 약 9초 걸렸다. 그동안 외부가 보낸 명령은 서버가 `+OK`로 답해도 받는 쪽이 없어 사라진다(O-13). 외부 C2는 `ready` 줄이 나온 뒤 명령을 보낸다.

| 로그 | 뜻 |
|---|---|
| `LA-CAL connected ... not ready yet` | 접속만 됐다 |
| `XSD loaded, mapping built` | 검증 준비 완료 |
| `LA-CAL SUB MA_TaskCommand@swarm.c2 done` | 외부 명령 구독 완료 |
| `ready at +N s` | 양방향 준비 완료 |

## 9.4 외부 C2 임시 규칙

임무 계획 연동 전까지의 임시 규칙이다(CR-GW-003, OPN-062 미결).

- `Command` 항목 하나가 수행 기체 하나다.
- `CapabilityID.DescriptiveLabel` = `<엔티티 ID>/<작업 종류>`.
- 작업 종류는 `hold`(현재 위치 선회 대기)와 `return_to_base`만 받는다.
- `TaskID.DescriptiveLabel`이 내부 작업 ID가 된다.
- `CommandState`가 `CANCEL`이면 취소다.
- 모든 항목의 `TaskID`와 `CommandState`가 같아야 한다.

이동 목적지처럼 위치 정보가 필요한 작업은 아직 받지 못한다.

`MA_TaskStatus`의 흐름은 다음과 같다. `hold`를 보내면 `EXECUTION_PENDING` → `EXECUTING`이 온다. 기체가 맡고 있던 이전 작업은 `CANCELED`가 된다.

## 9.5 카운터와 거부

`--stats-s` 주기로 `counters` 로그가 나온다.

| 항목 | 뜻 |
|---|---|
| `rx` | 버스에서 받은 메시지 |
| `exported`, `exported.<UCI 메시지>` | XSD 검증을 통과해 내보낸 수 |
| `sent` | LA-CAL로 보낸 수 |
| `ext_rx` | 외부에서 받은 명령 |
| `ext_published` | 버스로 내보낸 명령 |

- XSD 검증이나 변환에 실패한 메시지는 내보내지 않고 로그와 카운터에 남긴다. Gateway는 계속 돈다.
- 위치 대응 메시지 하나가 실패해도 다른 대응 메시지는 내보낸다.

> 알려진 제약: `config/lacal_server.yaml`의 `declared.pub`에 `MA_PositionReport`가 없다(O-20). 이번 확인에서는 메시지가 그대로 전달됐다.

다음: [10. 문제 해결](10_faq.md).
