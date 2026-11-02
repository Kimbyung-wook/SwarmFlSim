# 식별자(ID) 규칙

요구사항, 제안사항, 결정사항, 구현 항목, 시험 항목을 한 체계로 추적하기 위한 규칙이다.

## 1. ID 형식

| 종류 | 형식 | 예시 | 작성 주체 | 등록 위치 |
|---|---|---|---|---|
| 요구사항 | `REQ-<영역>-NNN` | `REQ-DYN-001` | 사용자 요구를 정제 | [02_registry.md](02_registry.md) |
| 제안사항 | `PRP-<영역>-NNN` | `PRP-NET-002` | 설계 제안 | [02_registry.md](02_registry.md) |
| 미결정사항 | `OPN-NNN` | `OPN-016` | 확인이 필요한 질문 | [02_registry.md](02_registry.md) |
| 결정사항 | `DEC-NNN` | `DEC-005` | 사용자 확정 | [02_registry.md](02_registry.md) |
| 구현 항목 | `IMP-<모듈>-NNN` | `IMP-CORE-001` | 구현 단위 | [03_traceability.md](03_traceability.md) |
| 시험 항목 | `TC-<모듈>-NNN` | `TC-CORE-001` | 검증 단위 | [03_traceability.md](03_traceability.md) |

- `NNN`은 3자리 일련번호이며, 종류·영역마다 따로 매긴다.
- `OPN`과 `DEC`는 영역 없이 전역 번호를 쓴다.

## 2. 영역 코드 (REQ, PRP)

| 코드 | 영역 |
|---|---|
| `SIM` | 시뮬레이션 코어: 시간 관리, 엔티티, 표적/적 |
| `DYN` | 동역학 모델과 수치 적분 |
| `GNC` | 하위 유도/제어 (A-GRA FA/VI) |
| `BHV` | 상위 행동결정, 경로 계획, 군집/편대 (A-GRA MA) |
| `UI` | 지도 전시와 통제 UI (A-GRA C2) |
| `NET` | 분산 실행과 통신 인프라 |
| `LNK` | 데이터링크 모델 |
| `CFG` | 초기 상태와 시나리오 (A-GRA MP) |
| `PAY` | 임무장비, 무장, 기체 특성 (A-GRA MS) |
| `PRF` | 성능과 규모 |
| `LOG` | 기록과 재생 (A-GRA MD) |
| `STD` | 표준 정합 (A-GRA, AMS-GRA) |

## 3. 모듈 코드 (IMP, TC)

구현을 시작할 때 모듈 구조에 맞춰 확정한다. 초안은 다음과 같다.

| 코드 | 모듈 |
|---|---|
| `API` | WP0 계약: 빌드 구조, Protobuf 스키마, 키 체계, 버스, 플러그인 API |
| `CORE` | Sim Core (C++) |
| `DYN` | 동역학 라이브러리 |
| `AGT` | Vehicle Agent 런타임과 플러그인 API |
| `LNK` | Datalink Emulator |
| `UI` | GCS/UI (CesiumJS) |
| `SCN` | Scenario Manager |
| `LOG` | Logger/Replay |
| `GW` | A-GRA Gateway |
| `INT` | 통합: 여러 WP 프로세스를 실제 버스로 묶는 실행기·통합 시나리오·통합 시험 |

## 4. 상태 값

| 상태 | 의미 |
|---|---|
| `Draft` | 작성됨, 확인 전 |
| `Confirmed` | 사용자가 확인함 |
| `Rejected` | 채택하지 않음 (사유 기록) |
| `Superseded` | 다른 항목으로 대체됨 (`Superseded by <ID>`) |
| `Resolved` | OPN 전용. 결정으로 해소됨 (`Resolved by DEC-NNN`) |

## 5. 관리 규칙

1. ID는 재사용하지 않는다. 항목을 지우지 않고 상태만 바꾼다.
2. 내용을 크게 바꿀 때는 새 ID를 만들고, 기존 항목을 `Superseded`로 바꾼다.
3. 모든 DEC에는 근거(OPN, REQ, PRP)와 사용자 답변 요지를 남긴다.
4. 모든 IMP는 하나 이상의 REQ 또는 DEC에 연결한다. 모든 REQ는 최종적으로 하나 이상의 TC로 검증한다.
5. 커밋 메시지와 PR 설명에는 관련 ID를 적는다. 예: `IMP-CORE-003: RK45 적분기 추가 (REQ-DYN-004, DEC-005)`
