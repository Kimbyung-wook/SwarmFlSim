# 8. WP9 A-GRA Gateway (`gateway/`)

## 책임

GCS 쪽 지상 참여자로서 내부 메시지와 외부 UCI 메시지를 변환한다(DEC-068, DEC-069). 루트 워크스페이스에 없는 독립 uv 프로젝트다. 운용 절차는 사용자 매뉴얼 [9장](../../42_user/09_gateway.md), 설계는 [gateway/README.md](../../../gateway/README.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/swarm_gateway/__main__.py` | 진입점 |
| `src/swarm_gateway/gateway.py` | 1단계·2단계 처리, 카운터, 거부 기록 |
| `src/swarm_gateway/mapping.py` | proto 옵션에서 만드는 매핑 표 |
| `src/swarm_gateway/converters/` | 메시지별 변환기 |
| `src/swarm_gateway/lacal.py` | 서브모듈 경로, XSD 검증, CAL Client |
| `src/swarm_gateway/runner.py` | LA-CAL 접속 |
| `src/swarm_gateway/ids.py` | 문자열 ID ⇄ UUID |
| `src/swarm_gateway/lacal_server.py`, `config/lacal_server.yaml` | CAL Server 기동 |

`third_party/agra_lacal`은 서브모듈이고 고치지 않는다.

## 실행

| 옵션 | 뜻 |
|---|---|
| `--gcs <id>` | 필수. GCS 엔티티 ID |
| `--lacal <url>` | 기본 `ws://127.0.0.1:8765` |
| `--participant <id>` | 발행 참여자 ID. `LinkEnvelope.publisher`에 싣는다. 기본 `gateway-0`, 엔티티 ID 형식(DEC-077) |
| `--service`, `--topic-prefix`, `--inbound-topic` | LA-CAL 서비스와 토픽. MP 수신 토픽은 `<prefix>.mp`로 고정 |
| `--stats-s <s>` | 카운터 로그 주기, 기본 10 |
| `--bus zenoh\|memory` | 기본 `zenoh`. Zenoh가 없으면 설치 방법을 알리고 종료 코드 1로 끝난다. `memory`는 명시했을 때만 쓰고 시뮬레이터 메시지가 오지 않는다 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `swarm/<gcs>/rx/**`만 |
| 발행 | `swarm/<gcs>/tx/c2/<msg>`, `swarm/<gcs>/tx/mp/<msg>`만 |

`truth/**`, `onboard/**`, `link/**`는 쓰지 않는다.

## 시험

```bash
cd gateway && uv run pytest
```

InMemoryBus와 프로세스 안의 CAL Server로 돈다. 처음이면 [2.6](../02_build_test.md#26-gateway)의 설치를 먼저 한다.

## 계약 변경 요청 상태

| ID | 내용 | 상태 |
|---|---|---|
| CR-GW-001 | 위치의 외부 메시지 대응 | 해소(DEC-072) |
| CR-GW-002 | `ApprovalResponse`를 STD로 | 해소(DEC-075) |
| CR-GW-003 | 외부 작업의 위치 표현 | 해소(DEC-076). 임무 계획 경로로 받는다 |
| CR-GW-004 | 루트 워크스페이스에 편입 | 미결(등록부 항목 없음) |
| CR-GW-005 | 같은 GCS 키의 발행자 구분 | 해소(DEC-077) |
| CR-GW-006 | 등록부 §5 갱신 | 미결(등록부 항목 없음) |
| CR-GW-007 | `MA_MissionPlan`의 `TaskPlanID` 내용, 경로가 아닌 위치 작업 | 미결 |
| CR-GW-008 | 실행 중 받은 `MissionPlan`을 내장 MA가 반영 | 해소(IMP-AGT-034) |
| CR-GW-009 | 계획 대상 `PackageID`·`ALL`을 엔티티로 펴는 규칙 | 미결 |

## 알려진 제약

- 외부 `MA_TaskCommand`는 `hold`, `return_to_base`, 취소만 받는다. 위치가 필요한 작업은 임무 계획 경로로 받는다(DEC-076). 지원 범위는 [gateway/README.md](../../../gateway/README.md#임무-계획-수신-dec-076).
- `ready` 로그 전에 외부가 보낸 명령은 사라진다(O-13).
- `config/lacal_server.yaml`의 `declared.pub`에 `MA_PositionReport`가 없다(O-20).

추적: [gateway/TRACE.md](../../../gateway/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
