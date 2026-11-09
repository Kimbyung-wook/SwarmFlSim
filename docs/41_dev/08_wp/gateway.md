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
| `--service`, `--topic-prefix`, `--inbound-topic` | LA-CAL 서비스와 토픽 |
| `--stats-s <s>` | 카운터 로그 주기, 기본 10 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `swarm/<gcs>/rx/**`만 |
| 발행 | `swarm/<gcs>/tx/c2/<msg>`만 |

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
| CR-GW-002 | `ApprovalResponse`를 STD로 | 미결(OPN-061) |
| CR-GW-003 | 외부 `MA_TaskCommand`의 작업 내용 표현 | 미결(OPN-062). 임시 규칙 사용 |
| CR-GW-004 | 루트 워크스페이스에 편입 | 미결(등록부 항목 없음) |
| CR-GW-005 | 키 목록에 Gateway 표기 | 미결(OPN-063) |
| CR-GW-006 | 등록부 §5 갱신 | 미결(등록부 항목 없음) |

## 알려진 제약

- 외부 작업은 임시 규칙으로 `hold`, `return_to_base`, 취소만 받는다.
- `ready` 로그 전에 외부가 보낸 명령은 사라진다(O-13).
- `config/lacal_server.yaml`의 `declared.pub`에 `MA_PositionReport`가 없다(O-20).

추적: [gateway/TRACE.md](../../../gateway/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
