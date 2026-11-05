# WP0 계약

- WP 세션들은 이 문서와 `proto/`, `api/`, `bus/`만으로 서로 연결한다 (DEC-015).
- 이 계약을 바꿀 때는 WP0을 거친다. 바꾸면 `CONTRACT_VERSION`(`api/python/src/swarm_api/__init__.py`)을 올린다.
- 계약 버전: 0.12.0
  - 0.12.0: lockstep rx 불변식 `rx_time_us >= T_k`(DEC-054), 재밍 수신단 기준 명시(DEC-055), 상태 변화 보고 최대 빈도(DEC-056)
  - 0.11.0: 시나리오 엔티티 ID 25자 이하(DEC-050), 엔티티당 재머 1개(DEC-049), Agent의 `*Activity` GCS 자동 보고(DEC-051), 재밍 구역 1 s 재발행(DEC-052)
  - 0.10.0: `FrameDone.sent_count`(lockstep 송신 개수 장벽) (DEC-044)
  - 0.9.0: `SimStatus.waiting_participants`(lockstep 참여자 응답 없음 표시) (DEC-041)
  - 0.8.0: 키 `sim/ctrl/scenario`(Core가 적재한 시나리오 재발행), lockstep 준비 신호 `FrameDone{frame=0}` (DEC-037)
  - 0.7.0: `ParamSpec.choices`(문자열 허용 목록), 거부 사유 `choice` (DEC-036)
  - 0.6.0: 기체별 매개변수 `ParamSpec`·`EntityParams`·`SetParams`, `EntitySpec.dynamics_params`, 키 `sim/param/<entity>/<owner>`, 플러그인 `PARAMS`·`on_params`, `DynamicsModel::param_descs` (DEC-035)
  - 0.5.0: 레이스트랙 선회 대기 `RacetrackShape`(HoldTask·LoiterAction), VI `RacetrackCurve` (DEC-034)
  - 0.4.0: `HoldTask` 선회 매개변수, `RouteTask`·`RouteWaypoint`(항로점 행위: 선회 대기·정찰) EXT 추가 (DEC-033)
  - 0.3.0: 재밍은 수신단 기준(DEC-028), 시나리오 `link_profiles`(DEC-029), `JamZoneEvent.area`(DEC-030), `SimStatus.replay`(DEC-031), 브로드캐스트 손실 집계 기준(DEC-032)
  - 0.2.0: `to_kinematic`에 `Environment` 추가(DEC-023), `Scenario`·`RunSpec` 메시지(DEC-024, DEC-025), 공용 버스 `bus/`와 `open_bus`(DEC-026), 브라우저 연동은 WebSocket 브리지(DEC-027)

## 1. 산출물

| 구분 | 위치 | IMP |
|---|---|---|
| 저장소·빌드 구조 | `CMakeLists.txt`, `CMakePresets.json`, `vcpkg.json`, `pyproject.toml`(uv workspace) | IMP-API-001 |
| Protobuf 스키마 | `proto/swarm/v1/*.proto` | IMP-API-002 |
| Zenoh 키 체계 | `api/python/src/swarm_api/keys.py`, `api/cpp/include/swarm/api/keys.hpp` | IMP-API-003 |
| ASB 버스 계약 + 인메모리 백엔드 | `api/python/src/swarm_api/bus.py`, `api/cpp/include/swarm/api/bus.hpp` | IMP-API-004 |
| 플러그인 API (MA/FA, L1 포트) | `api/python/src/swarm_api/{ports,plugin}.py`, `api/cpp/include/swarm/api/plugin.hpp` | IMP-API-005 |
| Core ⇄ 동역학 인터페이스 | `api/cpp/include/swarm/api/dynamics.hpp` | IMP-API-006 |
| 공용 버스 라이브러리 (InMemory, Zenoh, `open_bus`) | `bus/` (C++ `swarm_bus`), `api/python/src/swarm_api/bus.py` | IMP-API-007 |

## 2. 좌표와 단위

- 위치: WGS84 위도·경도(deg), 고도는 MSL(m)
- 속도: NED(m/s)
- 자세: NED → 기체 FRD 회전 쿼터니언 (w, x, y, z)
- 각속도: 기체 FRD(rad/s)
- 시간: 시뮬레이션 시각 `sim_time_us`(uint64, µs), 프레임 번호 `frame`
- 각도 필드는 이름에 단위를 붙인다(`_deg`, `_rad`). 단위가 없는 각도 필드는 rad이다.

## 3. Zenoh 키 체계 (PRP-NET-003)

### 3.1 메시지 흐름

```mermaid
flowchart LR
    subgraph A["기체 uav-001"]
        MA1["MA 플러그인"] --- RT1["Agent 런타임<br/>(L1 포트)"]
    end
    subgraph G["GCS gcs-01"]
        UI["GCS/UI"]
    end
    CORE["Sim Core"]
    DL["Datalink Emulator"]
    MON["Traffic Monitor<br/>Logger"]

    RT1 -- "swarm/uav-001/tx/&lt;iface&gt;/&lt;msg&gt;" --> DL
    UI -- "swarm/gcs-01/tx/c2/&lt;msg&gt;" --> DL
    DL -- "swarm/&lt;dst&gt;/rx/&lt;iface&gt;/&lt;msg&gt;" --> RT1
    DL -- "swarm/gcs-01/rx/**" --> UI
    DL -- "link/outcome/** · link/state/**" --> MON

    CORE -- "onboard/uav-001/NavigationReport · Detection" --> RT1
    RT1 -- "onboard/uav-001/ControlOutput · *Command" --> CORE
    CORE -- "sim/clock/tick" --> RT1
    CORE -- "sim/clock/tick" --> DL
    UI -- "sim/ctrl/cmd" --> CORE
    CORE -- "truth/**" --> UI
    CORE -- "truth/**" --> MON
```

### 3.2 키 목록

| 키 | 메시지 | 발행 | 구독 |
|---|---|---|---|
| `sim/clock/tick` | `ClockTick` | Core | 모든 참여자의 런타임 |
| `sim/clock/done/<participant>` | `FrameDone` | 참여자 | Core (lockstep 장벽) |
| `sim/ctrl/cmd` | `SimCommand` | UI | Core |
| `sim/ctrl/status` | `SimStatus` | Core, MCAP 재생기(`replay`=true) | UI, Monitor |
| `sim/ctrl/scenario` | `Scenario` | Core | Datalink, Agent 런타임, Logger, UI (늦게 붙는 참여자 포함) |
| `sim/param/<entity>/<owner>` | `EntityParams` (`owner`: `dynamics`, `fa`, `ma`) | Core(`dynamics`), Agent 런타임(`fa`, `ma`) | UI, Monitor, Logger |
| `swarm/<src>/tx/<iface>/<msg>` | `LinkEnvelope` | 송신 엔티티 런타임, UI(GCS) | Datalink만 |
| `swarm/<dst>/rx/<iface>/<msg>` | `LinkEnvelope` | Datalink | 수신 엔티티 런타임, UI(GCS) |
| `onboard/<id>/<msg>` | `NavigationReport`, `Detection`, `*Activity`, `ControlOutput`, `*Command` | Core ⇄ 해당 기체 런타임 | 해당 기체 런타임, Core |
| `link/outcome/<src>/<dst>` | `LinkOutcome` | Datalink | Monitor, Logger |
| `link/state/<a>/<b>` | `LinkState` (a < b 사전순) | Datalink | UI, Monitor |
| `truth/state` | `TruthFrame` | Core | UI, Monitor, Logger |
| `truth/event/<kind>` | `TruthEvent` (`launch`, `impact`, `kill`, `jam_zone`, `spawn`) | Core | UI, Monitor, Logger |

### 3.3 규칙

- `<iface>`: `c2`, `vi`, `ms`, `mp`, `md`, `p2p`. `<msg>`: proto 메시지의 짧은 이름(예: `FlightCommand`).
- 엔티티 ID: `^[a-z][a-z0-9]*(-[a-z0-9]+)+$`, 32자 이하.
  - 관례: `uav-001`, `gcs-01`, `tgt-001`, `site-01`, 발사체는 `wpn-<발사기체>-<순번>`
  - 시나리오에 정의하는 엔티티 ID는 25자 이하다. 발사체 ID가 32자 안에 들게 한다. 넘으면 시나리오 적재를 거부한다 (DEC-050).
  - 참여자(프로세스) ID도 같은 형식이다. 예: `core-0`, `datalink-0`, `agent-host-1`
- 인코딩: Zenoh encoding을 `application/protobuf;<전체 메시지 이름>`으로 둔다.
- 기체 간·지상-기체 간 메시지는 반드시 `tx` → Datalink → `rx`로 흐른다. 런타임은 다른 엔티티의 `rx`에 직접 발행하지 않는다.
- `onboard/**`는 같은 기체 안의 신호다. 데이터링크를 거치지 않는다. FA→MA 간 VI도 같은 기체 안이면 런타임 내부 호출로 처리하고 버스에 싣지 않아도 된다.
- MA 플러그인은 버스에 직접 접근하지 않는다. 런타임은 `sim/ctrl/`, `truth/`, `link/` 접두어를 플러그인에 노출하지 않는다 (`MA_FORBIDDEN_PREFIXES`).
- MCAP 채널은 키와 1:1로 대응한다 (PRP-LOG-001).
- 시나리오 배포와 lockstep 시작 (DEC-037)
  - Core는 시나리오를 적재한 직후(`LoadScenario` 또는 `--scenario`)와 적재 상태와 lockstep 준비 대기 중(첫 틱 전)에 1초(벽시계)마다 `sim/ctrl/scenario`에 `Scenario` 전체를 발행한다. CLI의 실행 모드·배속 재정의(`--mode`, `--rate`)는 발행하는 `Scenario.run`에 반영한다. 그래서 준비 대기 중에 늦게 켠 참여자도 시나리오와 실행 모드를 받는다. 다른 참여자는 `LoadScenario`를 받지 못했어도 이 키에서 시나리오를 얻는다.
  - lockstep 참여자는 시나리오를 적재해 준비되면 `sim/clock/done/<participant>`에 `FrameDone{frame=0}`을 보낸다. Core는 `RunSpec.participants` 전원의 준비 신호를 받은 뒤에 첫 틱을 낸다. 이후 늦게 붙는 참여자는 시작 후에는 허용하지 않는다. 실행 중 이탈한 참여자의 재합류도 지원하지 않는다(Reset+Start로 복구, DEC-038).
  - lockstep 수신 결정성(DEC-040): Datalink는 틱 f의 rx를 모두 발행한 뒤 `FrameDone{f}`를 보낸다. Agent는 틱 f+1 처리 전에 Datalink의 `FrameDone{f}`를 받아야 하며(Datalink가 `participants`에 있을 때), 틱 f에서는 `rx_time_us <= sim_time_us(틱 f-1)`인 rx만 (rx_time_us, source, seq) 순으로 소비한다(틱 0은 소비 없음, DEC-045). 기체 간 메시지는 모델 지연에 더해 최소 1틱 늦게 소비된다. realtime과 free-run에는 적용하지 않는다.
  - rx 불변식(DEC-054): lockstep에서 Datalink가 틱 k에서 내는 rx는 `rx_time_us >= sim_time_us(틱 k)`이다. 표본 지연이 0이거나 처리량 상한으로 이월된 송신도 도착 시각을 이 값 아래로 두지 않는다. 그래서 Agent가 틱 f에서 소비하는 rx(`rx_time_us <= T(f-1)`)는 모두 Datalink 틱 f-1 이하에서 나와 `FrameDone{f-1}` 장벽 안에 든다.
  - 송신 개수 장벽(DEC-044): lockstep에서 `swarm/**`에 발행하는 참여자(Agent·Datalink)는 `FrameDone{f}`의 `sent_count[e]`에 Start(또는 Reset) 이후 그때까지 `swarm/<e>/**`에 발행한 샘플의 누적 수를 싣는다. Datalink가 모의 손실로 버린 메시지는 발행하지 않았으므로 세지 않는다.
    - 수신 측은 다른 참여자가 발행한 `swarm/<e>/**`에서 프레임 f까지의 메시지를 쓰기 전에 그 참여자의 `FrameDone{f}`를 받고, e별 누적 수신 수가 `sent_count[e]` 이상이 될 때까지 기다린다. 대상 e는 그 `FrameDone`에 실린 키 중 수신 측이 구독하는 것이다.
    - Datalink: 틱 f+1을 처리하기 전에 Agent 참여자 전원의 `FrameDone{f}`와 `swarm/<e>/tx/**` 개수를 확인한다. Agent: 틱 f+1을 처리하기 전에 Datalink의 `FrameDone{f}`와 자기 기체의 `swarm/<e>/rx/**` 개수를 확인한다.
    - 대상은 `swarm/**`뿐이다. `onboard/**`·`truth/**`·UI 표시는 대상이 아니다. realtime·free-run에서는 `sent_count`를 비워도 되고 수신 측은 무시한다. Core는 이 필드를 쓰지 않는다.
  - 참여자 응답 없음(DEC-041): lockstep에서 Core는 이탈한 참여자를 계속 기다린다. 벽시계 5 s 넘게 `FrameDone`이 없는 참여자를 `SimStatus.waiting_participants`에 싣고, 기다리는 동안에도 `sim/ctrl/status`를 계속 발행한다. UI·Monitor는 이를 경고로 표시한다. 복구는 Reset+Start다.
  - 재생 한계(DEC-042): MCAP 재생기는 속도 조절이나 배압 없이 배속대로 발행한다. 고배속에서 수신자가 놓치는 프레임은 허용하고, UI·Monitor는 `truth/state` 프레임 번호의 공백으로 누락 수를 표시한다.
  - 버스 QoS(DEC-043): `open_bus`의 Zenoh 백엔드는 모든 키를 우선순위 DATA·비express로 보내고, `sim/clock/**`와 `swarm/**`는 혼잡 제어 BLOCK, 그 밖은 DROP으로 보낸다. 참여자는 이 키들을 `open_bus`가 아닌 별도 세션이나 다른 QoS로 발행하지 않는다.
  - 입력 검증(DEC-038): 시나리오·`SimCommand`·임무·매개변수의 비유한 값과 범위 밖 값은 거부한다. 지원하지 않는 DoF 시나리오는 적재를 거부하고 Core는 종료하지 않는다. `assignees`가 비면 임무를 거부한다.
  - 참여자는 받은 시나리오의 `name`이 이전과 다르면 다시 적재하고 준비 신호를 다시 보낸다. 같으면 무시한다.
- 기체별 매개변수 (DEC-035)
  - 계층: 기체(airframe)·제어·유도·행위·결정 (`ParamLayer`). 소유자: 동역학(Core)·FA·MA (`ParamOwner`). 계층은 표시용이고 소유자가 적용 주체다.
  - 값 결정 순서: 소유자 기본값 → airframe 표(동역학만) → 시나리오(`EntitySpec.dynamics_params`, `AutonomySpec.fa_params`, `ma_params`) → 실행 중 `SimCommand.set_params`
  - 선언하지 않은 이름, 타입·범위·허용 목록(`choices`) 위반, 실행 중 `runtime`=false 항목은 적용하지 않고 `EntityParams.rejected`에 사유를 적는다. 조용히 무시하지 않는다.
  - 소유자는 적재 직후, 변경 직후, 그리고 적재 상태에서 1초(벽시계)마다 `sim/param/<entity>/<owner>`에 `EntityParams`를 발행한다.
  - `set_params`는 다음 프레임 시작에 적용한다. Agent 런타임은 `sim/ctrl/cmd`를 구독해 자기 기체·소유자 것만 처리한다. 플러그인에는 `on_params`로만 알리고 `sim/ctrl/`은 노출하지 않는다 (DEC-014).
- 지도 임무 명령 (DEC-033)
  - 선회 대기: `HoldTask`(center·radius_m·duration_s·direction). 지점 타격: `StrikeTask.aim_point`(엔티티를 지정하면 `target_id`). 지점 정찰: `SearchAreaTask`(원 영역).
  - 항로: `RouteTask`. 항로점마다 고도(`position.alt_m`)·속력·행위(`LoiterAction`, `ReconAction`)를 둔다. 같은 `task_id`로 다시 보내면 항로 전체를 바꾼다.
  - 레이스트랙 선회 대기: `HoldTask.racetrack` 또는 `LoiterAction.racetrack`(직선 길이·축 방향). 중심은 두 원 중심의 중점이다. MA는 VI `CurveCommand.racetrack`으로 FA에 넘긴다. 유도 방식은 FA 매개변수 `racetrack_guidance`(`dubins` 기본, `vector_field`)로 고른다 (DEC-034).
  - 지원하지 않는 작업을 받은 MA는 `TaskStatus` REJECTED로 답한다.
- 임무장비 상태 보고 (DEC-051)
  - Agent 런타임은 자기 기체의 `onboard/<id>/{SensorActivity,JammerActivity,StrikeActivity}`를 받아 값이 바뀔 때와 1 Hz(모의 시간)로 GCS에 `swarm/<id>/tx/ms/<Msg>`로 보낸다. MA 플러그인 구현과 무관하다.
  - 변화 보고는 (메시지, payload_id)별 최대 빈도를 둔다. 기본 10 Hz이고 Agent 런타임 설정(CLI `--activity-max-hz`)으로 바꾼다. 제한으로 미룬 변화는 다음 허용 시점에 최신 값으로 보낸다. 1 Hz 전체 보고는 제한과 별개다 (DEC-056).
  - Datalink를 거치므로 GCS 링크가 끊기면 지상 표시에도 반영된다. UI는 `swarm/<gcs>/rx/ms/<Msg>`만 읽고 `onboard/**`를 구독하지 않는다.
- 재밍 구역 (DEC-049, DEC-052)
  - 엔티티당 재머는 1개다. 2개 이상 탑재한 시나리오는 적재를 거부한다. `JamZoneEvent.owner`는 엔티티 ID다.
  - Core는 활성 구역을 바뀔 때와 1 s(모의 시간)마다 `truth/event/jam_zone`에 다시 발행한다. 수신 측은 owner 기준으로 멱등 처리한다(같은 owner면 덮어씀, 비활성이면 제거).
- 데이터링크 판정
  - 재밍: 수신 엔티티가 재밍 영역(`JamZoneEvent.area`) 안이면 그 메시지는 JAMMED로 손실된다. 송신자 위치는 보지 않는다(DEC-055). `link/state`는 양쪽 중 하나라도 영역 안이면 jammed다 (DEC-028, DEC-030).
  - 브로드캐스트(`dst` 비움): 같은 편 무전기 엔티티 전원이 수신 대상이다. 닿지 않는 수신자마다 사유를 담은 `LinkOutcome`을 낸다 (DEC-032).
  - 링크 프로파일: `EntitySpec.link_profile`이 내장 프로파일 또는 시나리오 `link_profiles`의 이름을 참조한다. 시나리오 항목은 `base`(비우면 같은 이름의 내장, 없으면 `default`)를 복사한 뒤 값이 있는 필드만 덮어쓴다 (DEC-029).

### 3.4 버스 열기 (DEC-026)

- 프로세스는 버스 구현을 직접 만들지 않고 `open_bus(BusConfig)`로 연다.
  - C++: `swarm/bus/open_bus.hpp` (타깃 `swarm_bus`). Zenoh가 빌드에 없으면 memory만 된다.
  - Python: `swarm_api.open_bus(BusConfig(...))`. Zenoh는 `swarm-api[zenoh]`(eclipse-zenoh 1.10)
- `BusConfig`: `backend`(zenoh | memory, 비우면 Zenoh가 있으면 zenoh), `zenoh_config_file`, `zenoh_mode`, `connect`, `listen`, `multicast_scouting`
- 실행 파일의 명령행 옵션은 같은 이름을 쓴다: `--bus`, `--zenoh-config`, `--zenoh-mode`, `--connect`, `--listen`, `--no-multicast` (`parse_bus_arg`, `kBusUsage`)

### 3.5 브라우저 연동 (DEC-027)

```mermaid
flowchart LR
    UI["GCS/UI · Traffic Monitor<br/>(브라우저)"] <-- "WebSocket<br/>바이너리 프레임: 키 + protobuf" --> BR["WebSocket 브리지<br/>bridge/ (Python)"]
    BR <-- "open_bus (Zenoh)" --> BUS["Zenoh 버스"]
```

- 브라우저는 Zenoh에 직접 붙지 않는다. 모든 송수신은 브리지를 거친다.
- 브리지가 하는 일:
  - 구독: 클라이언트가 키 표현식과 최대 전송 주기를 지정한다. 브리지가 클라이언트별로 다운샘플한다 (DEC-006).
  - 발행: 허용한 키만 받는다. 기본 허용은 `sim/ctrl/cmd`와 그 UI가 맡은 GCS의 `swarm/<gcs>/tx/**`
  - 역할별 권한(DEC-020, P6 이후)은 브리지에 붙인다.
- 구현은 WP5가 `bridge/`에서 한다. 프로토콜은 아래와 같다 (WP5·WP6 공통).

#### 브리지 프로토콜 v1

- 접속: `ws://<host>:<port>/bus` (기본 포트 8765). 한 연결이 한 클라이언트다.
- 텍스트 프레임(JSON)은 제어, 바이너리 프레임은 버스 메시지다.

| 방향 | 텍스트 프레임 | 의미 |
|---|---|---|
| C → S | `{"op":"hello","client":"ui-01","role":"control","gcs":"gcs-01"}` | 첫 메시지. `role`: `control`(발행 가능) / `observer`(구독만). `gcs`: 이 UI가 맡은 GCS 엔티티 |
| S → C | `{"op":"welcome","protocol":1,"contract":"0.10.0"}` | 접속 승인 |
| C → S | `{"op":"sub","id":1,"key":"truth/**","max_hz":10}` | 구독. `max_hz` 0이면 제한 없음. 같은 키는 주기 안에서 마지막 메시지만 보낸다 |
| C → S | `{"op":"unsub","id":1}` | 구독 해제 |
| S → C | `{"op":"error","code":"forbidden","msg":"..."}` | 오류. `code`: `bad_request`, `forbidden`, `unsupported` |

- 바이너리 프레임 형식(양방향 같음, 정수는 little-endian):

| 필드 | 형식 |
|---|---|
| 키 길이 | uint16 |
| 키 | UTF-8 |
| 인코딩 길이 | uint16 |
| 인코딩 | UTF-8 (`application/protobuf;<전체 메시지 이름>`) |
| 페이로드 | 나머지 바이트 (protobuf) |

- 발행 허용(`role=control`): `sim/ctrl/cmd`, `swarm/<gcs>/tx/**`. 그 밖의 키는 `forbidden` 오류를 보내고 버린다. `observer`는 발행할 수 없다.
- 구독 허용: 모든 키. 역할별 제한은 DEC-020(P6 이후)에서 정한다.

## 4. Protobuf 스키마

- 패키지: `swarm.v1`. 호환을 깨는 변경은 `swarm.v2`로 한다.
- 각 메시지에 커스텀 옵션으로 A-GRA 매핑을 단다 (`options.proto`).
  - `uci_name`: 공개 XSD의 UCI 메시지명
  - `mapping`: `STD`(외부로 내보냄) / `EXT`(확장, 외부 비공개) / `SIM`(내부 전용)
  - `l1`: L1 인터페이스
- Gateway(WP9)는 디스크립터에서 이 옵션을 읽어 매핑 표를 만든다. 등록부 §5 매핑 표와 어긋나면 proto가 기준이다.

| 파일 | 내용 | 매핑 |
|---|---|---|
| `common.proto` | Header, 좌표, 영역, CommandState | - |
| `entity.proto` | EntityKind, Side, DynamicsKind, EntityState, EntitySpec(`dynamics_params`), ParamLayer, ParamSpec | - |
| `vi.proto` | FlightCommand(HSA/Waypoint/Curve), FlightCommandStatus, FlightCapability, NavigationReport, SystemStatus | STD |
| `c2.proto` | TaskCommand, TaskStatus, ApprovalRequest (STD) / FormationCommand, GroupAssignment, ApprovalResponse, TaskCommand.route(RouteTask) (EXT) | STD/EXT |
| `p2p.proto` | PeerStatus, LeaderUpdate, TrackShare (STD) / PeerAlgorithmMessage (EXT) | STD/EXT |
| `ms.proto` | Sensor/Jammer/Strike Command·Activity, StoreLoadout (STD) / Detection (EXT) | STD/EXT |
| `mp.proto` | MissionPlan, RoutePlan, EngagementCriteria | STD |
| `fa.proto` | ControlOutput (Kinematic/Attitude/Actuator) | SIM |
| `link.proto` | LinkEnvelope, LinkOutcome, LinkState, LinkProfile | SIM |
| `sim.proto` | SimCommand(`set_params`), SimStatus(`replay`, `waiting_participants`), ClockTick, FrameDone, Scenario(MapSpec, RunSpec, link_profiles), ParamOwner, EntityParams | SIM |
| `truth.proto` | TruthFrame, TruthEvent(JamZoneEvent.area) | SIM |

- 시나리오: `LoadScenario.scenario`(`Scenario`)로 보낸다. `scenario_json`은 폐기 예정이다 (DEC-024). `Scenario`의 필드 구성은 `scenario/` JSON Schema와 같고, 변환은 `swarm_scenario.to_proto` / `from_proto`가 한다. `swarm_core --scenario`에 줄 파일은 `swarm-scenario export`로 만든다.

- 코드 생성
  - C++: CMake `protobuf_generate` (`proto/CMakeLists.txt`, 타깃 `swarm_proto`)
  - Python: `scripts/gen_proto.py` → `api/python/src/swarm/v1/`
  - TypeScript: protobuf-es(`@bufbuild/protobuf`). WP5가 `ui/`에 설정한다.

## 5. 플러그인 API

```mermaid
flowchart TB
    subgraph RT["Agent 런타임 (WP3)"]
        P["L1 포트 구현<br/>C2 · VI · MS · MP · P2P · MD"]
    end
    MA["MA 플러그인<br/>MissionAutonomy (기체별)<br/>BatchMissionAutonomy (군집 일괄)"]
    FA["FA 플러그인<br/>FlightAutonomy"]
    MA -- "ctx.ports" --> P
    P -- "FlightCommand" --> FA
    FA -- "ControlOutput" --> CORE["Sim Core / 동역학"]
```

- MA
  - 기체별: `on_init(ctx)`, `on_step(ctx)`, `on_shutdown(ctx)`
  - 군집 일괄: `on_step_batch(ctxs, nav)`. `nav`는 NumPy 배열 묶음이다. 기체마다 `ctxs[i].ports`로만 송수신한다 (DEC-008).
  - 난수는 `ctx.rng`만 쓴다 (lockstep 결정론).
- FA: `on_init` → `FlightCapability`, `on_command(FlightCommand)` → 수락/거부, `step(nav, dt)` → `ControlOutput`
- 등록
  - Python: entry point 그룹 `swarm.ma`, `swarm.fa`
  - C++: 공유 라이브러리가 `swarm_plugin_abi`, `swarm_create_ma`, `swarm_create_fa`를 내보낸다. ABI 버전은 `kPluginAbiVersion`이다.
- 시나리오는 `AutonomySpec.ma_plugin`, `fa_plugin`에 등록명을 적는다.
- 매개변수 (DEC-035)
  - Python 플러그인은 클래스 속성 `PARAMS: Sequence[ParamDef]`(이름·기본값·계층·단위·범위·설명·`runtime`)로 선언한다. 런타임은 `resolve_params`로 값을 정해 `ctx.params`(FA는 `on_init`의 `params`)로 넘기고, 실행 중 변경은 `on_params`로 알린다.
  - 동역학 모델은 `DynamicsModel::param_descs()`, `get_param`, `set_param`으로 내보낸다. 매개변수가 없는 모델은 빈 목록이다.

## 6. Core ⇄ 동역학 (`dynamics.hpp`)

- `DynamicsModel`: `derivatives(t, x, u, env, dxdt)`, `map_control(ControlOutput, u)`, `to_kinematic(x, env, out)` / `from_kinematic(in, x)`
  - 상태의 속도는 대기 속도다. `to_kinematic`은 바람(`env.wind_ned_mps`)을 더한 대지 속도를 내고, 중력은 `env.gravity_mps2`를 쓴다 (DEC-023).
  - `from_kinematic`은 입력 속도를 대기 속도로 해석한다(초기 상태 설정용).
- `Integrator::step(model, t0, dt, x, u, env, event)`: 프레임 한 칸을 적분한다. RK45는 프레임 안에서 가변 스텝을 쓴다.
- `EventFn`: 영점 교차 함수(예: 고도 − DEM 고도). 적분기는 교차 시점을 이분법으로 찾아 그 시점에서 멈춘다 (DEC-005).
- `Terrain::elevation_m(lat, lon)`: DEM 조회. 구현은 WP2가 맡는다.

## 7. 빌드 환경과 시험 (DEC-022)

### 7.1 지원 툴체인

| 프리셋 | 환경 | C++ 의존성 | 셸 |
|---|---|---|---|
| `msvc-debug`, `msvc-release` | Windows, MSVC | vcpkg 매니페스트(`vcpkg.json`), `VCPKG_ROOT` 필요 | `vcvars64.bat`를 부른 cmd (x64 Native Tools) |
| `mingw-debug`, `mingw-release` | Windows, MSYS2 UCRT64 GCC | pacman 패키지 | MSYS2 UCRT64 |
| `linux-debug`, `linux-release` | Linux/WSL2, GCC | 배포판 패키지 | bash |
| `linux-vcpkg-debug` | Linux/WSL2, GCC | vcpkg | bash |

- 모든 프리셋은 Ninja 생성기를 쓴다.
- CMake는 의존성을 `find_package`로만 찾는다. 새 의존성을 추가하는 WP는 `vcpkg.json`과 아래 패키지 목록을 함께 갱신한다.
- `vcpkg.json`의 `builtin-baseline`은 vcpkg 저장소 커밋으로 라이브러리 버전을 고정한다. 모든 개발자·세션이 같은 버전을 쓰도록 WP0만 바꾼다.
- `vcvars64.bat`는 `VCPKG_ROOT`를 Visual Studio에 포함된 vcpkg로 덮어쓴다. baseline이 있으므로 어느 vcpkg를 써도 같은 버전을 받는다.
- `msvc-*` 프리셋은 오버레이 트리플렛 `triplets/x64-windows-cxx20.cmake`(`/std:c++20`)로 vcpkg 의존성을 C++20으로 빌드한다 (QA-007). protobuf의 ABI가 언어 모드에 따라 달라, 기본 트리플렛(`x64-windows`)의 DLL은 C++20 릴리스 링크에서 `GlobalEmptyString` 미해결 심볼 오류를 낸다. 기존 `build/msvc-*`가 있으면 지우고 다시 구성한다.
- vcpkg는 `build/msvc-*/vcpkg_installed` 아래에서 빌드한다. 저장소 경로가 길면 abseil 컴파일이 C1083으로 실패하므로, 그때는 구성 명령에 `-DVCPKG_INSTALL_OPTIONS=--x-buildtrees-root=C:/b/bt`를 추가해 빌드 트리를 짧은 경로에 둔다.

### 7.2 환경별 설치

MSVC + vcpkg:

```bash
winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

```bash
git clone https://github.com/microsoft/vcpkg C:\dev\vcpkg
```

```bash
C:\dev\vcpkg\bootstrap-vcpkg.bat
```

```bash
setx VCPKG_ROOT C:\dev\vcpkg
```

MSYS2 UCRT64 (MSYS2 설치 후 UCRT64 셸에서):

```bash
pacman -S --needed mingw-w64-ucrt-x86_64-toolchain mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-protobuf mingw-w64-ucrt-x86_64-eigen3
```

Ubuntu / WSL2:

```bash
sudo apt install build-essential cmake ninja-build libprotobuf-dev protobuf-compiler libeigen3-dev
```

MCAP (WP7 `logger/`):

- MSVC + vcpkg: `vcpkg.json`의 `mcap` 포트로 자동 설치된다.
- MSYS2·Ubuntu: 패키지가 없다. mcap 저장소의 C++ 헤더를 받아 `-DMCAP_INCLUDE_DIR=<mcap>/cpp/mcap/include`로 넘긴다. 지정하지 않으면 경고를 내고 `logger/`를 건너뛴다.

```bash
git clone --depth 1 https://github.com/foxglove/mcap <mcap>
```

Zenoh (zenoh-c + zenoh-cpp 1.10.2):

- vcpkg와 MSYS2·Ubuntu 배포판에 패키지가 없으므로 eclipse-zenoh 공식 릴리스의 standalone zip을 한 접두 경로에 풀고 `CMAKE_PREFIX_PATH`로 넘긴다.
- zenoh-cpp는 헤더 전용이다(`zenohcpp-1.10.2-standalone.zip`). zenoh-c는 환경별 zip을 받는다.
- Zenoh가 없으면 `bus/`는 memory 백엔드만 들어간 채로 빌드되고, Zenoh 시험은 빠진다.

| 환경 | zenoh-c zip | 접두 경로 예 |
|---|---|---|
| MSVC | `zenoh-c-1.10.2-x86_64-pc-windows-msvc-standalone.zip` | `C:\dev\zenoh` |
| MSYS2 UCRT64 | `zenoh-c-1.10.2-x86_64-pc-windows-gnu-standalone.zip` | `/ucrt64/opt/zenoh` |
| Ubuntu / WSL2 | `zenoh-c-1.10.2-x86_64-unknown-linux-gnu-standalone.zip` | `/opt/zenoh` |

MSVC (PowerShell):

```bash
curl.exe -LO https://github.com/eclipse-zenoh/zenoh-c/releases/download/1.10.2/zenoh-c-1.10.2-x86_64-pc-windows-msvc-standalone.zip
```

```bash
curl.exe -LO https://github.com/eclipse-zenoh/zenoh-cpp/releases/download/1.10.2/zenohcpp-1.10.2-standalone.zip
```

```bash
mkdir C:\dev\zenoh; tar -xf zenoh-c-1.10.2-x86_64-pc-windows-msvc-standalone.zip -C C:\dev\zenoh; tar -xf zenohcpp-1.10.2-standalone.zip -C C:\dev\zenoh
```

```bash
setx CMAKE_PREFIX_PATH C:\dev\zenoh
```

MSYS2 UCRT64 / Ubuntu (`<zip>`, `<prefix>`는 위 표):

```bash
curl -LO https://github.com/eclipse-zenoh/zenoh-c/releases/download/1.10.2/<zip>
```

```bash
curl -LO https://github.com/eclipse-zenoh/zenoh-cpp/releases/download/1.10.2/zenohcpp-1.10.2-standalone.zip
```

```bash
mkdir -p <prefix> && unzip -o <zip> -d <prefix> && unzip -o zenohcpp-1.10.2-standalone.zip -d <prefix>
```

```bash
export CMAKE_PREFIX_PATH=<prefix>
```

- Linux에서 빌드 트리 밖으로 옮긴 실행 파일은 `LD_LIBRARY_PATH=<prefix>/lib`로 실행한다. Windows는 빌드 후 `zenohc.dll`을 실행 파일 옆에 복사한다(`swarm_copy_runtime_dlls`, `bus/CMakeLists.txt`).

공통 (Python):

```bash
winget install astral-sh.uv
```

### 7.3 빌드와 시험

`<preset>` 자리에 7.1의 프리셋 이름을 넣는다.

```bash
cmake --preset <preset>
```

```bash
cmake --build --preset <preset>
```

```bash
ctest --preset <preset>
```

```bash
uv sync
```

- `uv sync`는 dev 그룹으로 워크스페이스 패키지 전체와 `eclipse-zenoh`를 설치한다. `uv run pytest`는 `api/python/tests`와 `scenario/tests`를 모두 돈다.

```bash
uv run python scripts/gen_proto.py
```

```bash
uv run pytest
```

### 7.4 툴체인별 제약

- Python 확장 모듈(WP3의 pybind11/nanobind 바인딩)은 그 모듈을 불러올 Python과 같은 툴체인으로 빌드해야 한다.
  - MSVC: python.org 또는 uv가 받은 CPython
  - MSYS2: MSYS2의 `mingw-w64-ucrt-x86_64-python`. uv가 받은 CPython과는 섞지 않는다
- 바인딩이 없는 Python 코드(MA 플러그인, Gateway, 시나리오, 시험)는 툴체인과 관계없이 uv 환경에서 실행한다.
- Zenoh는 C++(zenoh-c/zenoh-cpp)와 Python(eclipse-zenoh)이 같은 1.10 버전을 쓴다. 받는 방법은 7.2에 있다.
