# gateway — WP9 A-GRA Gateway

시뮬레이터 내부 버스와 외부 A-GRA(UCI) 시스템 사이에서 메시지를 주고받는 지상 참여자다 (DEC-068, DEC-069, PRP-STD-002).
LA-CAL(OMS Language-Agnostic CAL)에는 서브모듈 `third_party/agra_lacal`의 CAL Client로 접속한다.

```mermaid
flowchart LR
    UAV["기체 런타임"] -- "swarm/uav-*/tx/**" --> DL["Datalink"]
    DL -- "swarm/gcs-01/rx/**" --> GW["Gateway (gcs-01 쪽)"]
    DL -- "swarm/gcs-01/rx/**" --> UI["GCS/UI"]
    GW -- "1단계: UCI OMS JSON (XSD 검증 통과분만)<br/>PUB swarm.&lt;iface&gt;" --> CAL["CAL Server (agra_lacal)"]
    CAL -- "2단계: MSG MA_TaskCommand @ swarm.c2" --> GW
    GW -- "swarm/gcs-01/tx/c2/TaskCommand" --> DL
    CAL <--> EXT["외부 C2 / A-GRA 시스템"]
```

- 구독은 `swarm/<gcs>/rx/**` 하나뿐이다. 발행은 `swarm/<gcs>/tx/c2/<msg>`뿐이다. `truth/**`, `onboard/**`, `link/**`는 쓰지 않는다.
- 버스는 `open_bus(BusConfig)`로 연다 (DEC-026).
- 매핑은 proto 옵션 `(uci_name)`, `(uci_also)`, `(mapping)`, `(l1)`을 descriptor에서 읽어 만든다. STD만 외부로 내보내고 EXT·SIM은 내보내지 않는다 (DEC-014).
- 내부 메시지 하나를 받으면 `uci_name`과 `uci_also`의 UCI 메시지를 각각 따로 변환·검증·발행한다. 하나가 실패해도 나머지는 나간다 (DEC-072).
- 변환기는 내부 메시지별 플러그인이다 (`swarm_gateway/converters/`, DEC-013). `uci_also` 대상은 UCI 메시지별 `AlsoConverter`가 맡고, 어느 내부 메시지에 쓸지는 descriptor가 정한다. 엔트리 포인트 그룹 `swarm_gateway.converters`로 둘 다 추가할 수 있다.
- XSD 검증·변환에 실패한 메시지는 보내지 않고 로그와 카운터(`Gateway.counters`, `Gateway.rejections`)에 남긴다. Gateway는 계속 동작한다.

## 준비

```bash
git submodule update --init third_party/agra_lacal
```

```bash
cd gateway && uv sync --extra zenoh
```

- 루트 워크스페이스에 아직 등록되지 않아 `gateway/`에서 독립 uv 프로젝트로 실행한다(`swarm-api`는 `../api/python` 경로 의존성). proto 생성물이 없으면 저장소 루트에서 `uv run python scripts/gen_proto.py`를 먼저 실행한다.
- 시뮬레이터와 붙이려면 `--extra zenoh`가 필요하다. 빠뜨리면 Gateway는 설치 방법을 알리고 종료 코드 1로 끝난다. 나중에 `--extra zenoh` 없이 `uv sync`를 다시 하면 Zenoh가 지워진다.
- 시험만 할 때는 `uv sync`로 충분하다. Zenoh가 없어도 시험은 통과한다(실패 종료 경로의 프로세스 시험까지 돈다).

## 시험

```bash
cd gateway && uv run pytest
```

- 시험은 InMemoryBus와 프로세스 안에서 띄운 agra_lacal CAL Server(로컬 백엔드, 포트 자동 할당)를 쓴다.

## 실행

CAL Server (agra_lacal, 이 환경에서 기동. 설정은 `config/lacal_server.yaml`):

```bash
cd gateway && uv run python -m swarm_gateway.lacal_server --config config/lacal_server.yaml
```

Gateway:

```bash
cd gateway && uv run python -m swarm_gateway --gcs gcs-01 --lacal ws://127.0.0.1:8765
```

| 옵션 | 기본값 | 내용 |
|---|---|---|
| `--gcs` | (필수) | GCS 엔티티 ID |
| `--lacal` | `ws://127.0.0.1:8765` | CAL Server OWP 주소 |
| `--service` | `swarm_gateway` | CAL Server 설정의 service_id |
| `--topic-prefix` | `swarm` | LA-CAL 토픽 `<prefix>.<iface>` (vi, c2, p2p, ms) |
| `--inbound-topic` | `<prefix>.c2` | 외부 C2 수신 토픽 |
| `--bus` | `zenoh` | `zenoh` 또는 `memory`. `memory`는 프로세스 안 버스라 시뮬레이터 메시지가 오지 않는다. 명시했을 때만 쓰고 경고를 남긴다 |
| `--zenoh-config`, `--zenoh-mode`, `--connect`, `--listen` | | `BusConfig` 항목 |
| `--no-multicast` | 꺼짐(멀티캐스트 켬) | Zenoh 멀티캐스트 스카우팅을 끈다. 같은 PC의 다른 버스와 섞이지 않게 할 때 `--connect`와 함께 쓴다. 다른 참여자(Core·Datalink·Agent·브리지)와 같은 옵션이다 (D-27) |
| `--stats-s` | 10 | 카운터 로그 주기 |

외부 C2 쪽은 같은 CAL Server에 `external_c2` 서비스로 접속해 `swarm.c2` 토픽에 `MA_TaskCommand`를 PUB하면 된다.

예: 같은 PC에서 Zenoh 라우터(또는 Datalink 등)에 직접 붙고 멀티캐스트를 끈다.

```bash
cd gateway && uv run python -m swarm_gateway --gcs gcs-01 --lacal ws://127.0.0.1:8765 --no-multicast --connect tcp/127.0.0.1:7447
```

### 기동 직후 준비 전 구간 (O-13)

- Gateway는 LA-CAL에 접속(INIT)한 뒤 공개 XSD를 적재하고(수 초), 그다음에 외부 명령 구독(`SUB MA_TaskCommand swarm.c2`)을 건다.
- 접속부터 구독 완료까지는 외부 명령을 받는 쪽이 없다. 이 구간에 외부가 PUB한 `MA_TaskCommand`는 서버가 `+OK`로 답하지만 아무에게도 전달되지 않고 사라진다. 다시 보내 주지 않는다.
- 단계마다 INFO 로그를 남긴다. 외부 C2는 `ready` 줄이 나온 뒤 명령을 보내야 한다.

| 로그 | 뜻 |
|---|---|
| `gateway: LA-CAL connected ... at +N s; not ready yet` | 접속만 됐다. 아직 외부 명령을 받지 않는다 |
| `gateway: XSD loaded, mapping built at +N s` | 검증 준비 완료 |
| `gateway: LA-CAL SUB MA_TaskCommand@swarm.c2 done at +N s` | 외부 명령 구독 완료 |
| `gateway: ready at +N s: ...` | 버스 구독(`swarm/<gcs>/rx/**`)까지 끝났다. 양방향 준비 완료 |

- 외부 쪽에서는 `MA_TaskStatus`가 오지 않는 것으로만 유실을 알 수 있다. 동작 변경 제안은 TRACE.md "제안"에 적었다.

## 교환 메시지

| 방향 | 내부 메시지 (rx/tx 키) | UCI 메시지 | LA-CAL 토픽 |
|---|---|---|---|
| 발행 | `NavigationReport` | `MA_NavigationReport` | `swarm.vi` |
| 발행 | `NavigationReport` (uci_also) | `MA_PositionReport` | `swarm.vi` |
| 발행 | `SystemStatus` | `SystemStatus` | `swarm.vi` |
| 발행 | `FlightCommandStatus` | `MA_FlightCommandStatus` | `swarm.vi` |
| 발행 | `FlightCapability` | `MA_FlightCapability` | `swarm.vi` |
| 발행 | `TaskStatus` | `MA_TaskStatus` | `swarm.c2` |
| 발행 | `ApprovalRequest` | `MA_ApprovalRequest` | `swarm.c2` |
| 발행 | `PeerStatus` | `MA_PackagePartnerStatusReport` | `swarm.p2p` |
| 발행 | `PeerStatus` (uci_also) | `MA_PositionReport` | `swarm.p2p` |
| 발행 | `LeaderUpdate` | `MA_LeaderUpdateRequest` | `swarm.p2p` |
| 발행 | `TrackShare` | `MA_Entity` | `swarm.p2p` |
| 발행 | `SensorActivity` | `PO_Activity` | `swarm.ms` |
| 발행 | `JammerActivity` | `EA_Activity` | `swarm.ms` |
| 발행 | `StrikeActivity` | `StrikeActivity` | `swarm.ms` |
| 발행 | `StoreLoadout` | `StoreLoadoutConfiguration` | `swarm.ms` |
| 수신 | `TaskCommand` → `swarm/<gcs>/tx/c2/TaskCommand` | `MA_TaskCommand` | `swarm.c2` |

### ID 변환

- 내부 문자열 ID(엔티티·작업·명령)는 고정 이름공간의 UUIDv5로 바꾸고 `DescriptiveLabel`에 원래 ID를 싣는다.
- 받은 ID는 `DescriptiveLabel`을 먼저 쓰고, 없으면 Gateway가 만든 UUID의 역표를 쓴다.

### 외부 `MA_TaskCommand` 규칙 (임시, CR-GW-003)

- `Command` 항목 하나가 수행 기체 하나다. `CapabilityID.DescriptiveLabel` = `<엔티티 ID>/<작업 종류>`.
- 작업 종류는 위치 정보가 필요 없는 `hold`(현재 위치 선회 대기)와 `return_to_base`만 받는다.
- `TaskID.DescriptiveLabel` = 내부 `task_id`. `CommandState`가 `CANCEL`이면 취소 명령이다.
- 모든 항목은 같은 `TaskID`와 `CommandState`를 가져야 한다. 어긋나면 거부한다.

## 구성

| 경로 | 내용 |
|---|---|
| `src/swarm_gateway/lacal.py` | 서브모듈 경로, OMS JSON 코덱(XSD 검증), CAL Client |
| `src/swarm_gateway/mapping.py` | descriptor 기반 매핑 표 |
| `src/swarm_gateway/ids.py` | 문자열 ID ⇄ UUID |
| `src/swarm_gateway/converters/` | 메시지별 변환기 (vi, c2, p2p, ms)와 uci_also 대상 변환기 (position: `MA_PositionReport`) |
| `src/swarm_gateway/gateway.py` | 1단계·2단계 처리, 카운터, 거부 기록 |
| `src/swarm_gateway/runner.py` | LA-CAL 접속 (PUB/SUB 연결) |
| `src/swarm_gateway/__main__.py` | 진입점 |
| `src/swarm_gateway/lacal_server.py` | agra_lacal CAL Server 기동 래퍼 |
| `config/lacal_server.yaml` | 시험·연동용 CAL Server 설정 (서비스 `swarm_gateway`, `external_c2`) |
