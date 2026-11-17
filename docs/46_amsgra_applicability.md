# AMS-GRA 요구 적용성 표

- 근거: REQ-STD-001, DEC-093. 관련 결정: DEC-002, DEC-005, DEC-013, DEC-026, DEC-092.
- AMS-GRA는 개념 차용으로 둔다(DEC-093). 이 표는 준수 판정이 아니다. 요구마다 이 시뮬레이터에 해당하는지, 대응하는 요소가 어디 있는지를 보인다.
- 대상: AMS GRA 14.0 볼륨의 요구 표에 있는 요구 224건. 요구 표가 있는 볼륨 13종(Assembly, Mission System, MASI, Software Architecture, Time Distribution, MPU 볼륨 8종)에서 모았다. 요구 문구는 옮기지 않고 ID와 짧은 요지만 적는다.
- Tier와 권장 검증 방법은 원문 표의 값이다. 권장 검증 방법은 AMS-GRA 권고이며 채택 사업이 바꿀 수 있다. `—`는 원문 표에서 값을 읽지 못한 행이다.
- 점검 기준 문서 [44_standards_conformance.md](44_standards_conformance.md)의 C7이 이 표를 쓴다.

## 1. 판정 기준

| 판정 | 뜻 |
|---|---|
| 해당 | 요구의 의도가 이 시뮬레이터에 적용되고, 대응하는 요소가 있다 |
| 부분 | 요구의 의도 일부에 대응하는 요소가 있거나, 적용은 되지만 점검하지 않았다 |
| 해당없음 | 이 시뮬레이터의 범위 밖이다. 사유 코드(§2)를 적는다 |

- 해당·부분은 AMS-GRA 준수를 뜻하지 않는다. 대응 요소가 AMS-GRA가 정한 형식·인터페이스를 따르지 않는 경우가 대부분이다.

## 2. 해당없음 사유

| 코드 | 사유 | 건수 |
|---|---|---|
| R1 | 하드웨어 MPU·탑재 장비·물리 플랫폼 요구. 제안서 §1.2 범위 밖 | 29 |
| R2 | 보안·사이버·암호·CPI·다중 보안 영역 요구. 연구용 시뮬레이터라 보안 기능을 모의하지 않는다(DEC-093) | 67 |
| R3 | MPU·MASI 납품과 AMS-GRA 인증 산출물(OCI 컨테이너·오케스트레이션, `service.yml`, 문서 템플릿, MBSE 모델, DK, AMS-GRA 파이프라인). 이 저장소는 MPU로 납품하지 않는다(DEC-093) | 73 |
| R4 | 실시간 시각 동기(PTP 등)와 장비 시각. 시뮬레이터는 모의 시간을 쓴다(DEC-005) | 9 |
| R5 | AMS-GRA 고유 물리 버스·API(ABB, MEL, AMS Common Transport API). 버스는 Zenoh와 `open_bus`다(DEC-002, DEC-026) | 16 |

## 3. 요약

| 요구 군 | 정의 볼륨 | 계 | 해당 | 부분 | 해당없음 |
|---|---|---|---|---|---|
| `GRA-MS` (Mission System) | Assembly, Mission System | 59 | 0 | 6 | 53 |
| `GRA-MASI` (MASI) | Assembly, MASI, Mission System, Software Architecture | 26 | 2 | 10 | 14 |
| `GRA-MPU` (MPU 공통·볼륨별) | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU, Time Distribution | 79 | 0 | 12 | 67 |
| `GRA-DK` (Development Kit) | DPP MPU, MFA MPU | 43 | 0 | 0 | 43 |
| `GRA-CYMAN` (Cyber Manager) | Mission System | 9 | 0 | 0 | 9 |
| `GRA-CYAGE` (Cyber Agent) | Mission System | 4 | 0 | 0 | 4 |
| `GRA-CYMON` (Cyber Monitor) | Mission System | 4 | 0 | 0 | 4 |
| 계 | | 224 | 2 | 28 | 194 |

- 같은 ID가 여러 볼륨에 나오면 한 번만 센다(`GRA-MASI`는 Assembly·Mission System·MASI 볼륨에 반복된다).
- 해당·부분은 모두 소프트웨어 구조 요구다. 서비스 시작·정지, 상태·고장 감시와 기록, 서비스 간 연결, 단일 버스와 OMS CAL 연동, 시각 분배, 자동 시험과 빌드가 여기에 든다.

## 4. 상세

| ID | Tier | 권장 검증 | 정의 볼륨 | 판정 | 요지 | 근거 |
|---|---|---|---|---|---|---|
| GRA-MS-001 | 1 | 검사 | Mission System | 해당없음 | — | R5 |
| GRA-MS-002 | 1 | 검사 | Mission System | 부분 | 단일 ASB, OMS 표준 준수 | 내부는 `open_bus` 단일 버스(Zenoh), 외부는 agra_lacal CAL Server로 OMS 연동(DEC-002, DEC-026, DEC-069) |
| GRA-MS-003 | 1 | 검사 | Mission System | 해당없음 | — | R1 |
| GRA-MS-004 | 1 | 검사 | Mission System | 부분 | 시각 분배 구조 문서화 | 모의 시간을 Core가 분배하고 lockstep 장벽으로 맞춘다(DEC-005, DEC-043, 계약 §3). PTP 등 실시간 시각은 없다 |
| GRA-MS-005 | 1 | 분석 | Assembly, Mission System | 해당없음 | — | R1 |
| GRA-MS-006 | 1 | 검사 | Mission System | 해당없음 | — | R1 |
| GRA-MS-007 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R1 |
| GRA-MS-008 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R1 |
| GRA-MS-009 | 1 | 검사 | Mission System | 부분 | UCI 메시지 접근용 OMS CAL | Gateway가 agra_lacal CAL Server로 UCI 메시지를 주고받는다(DEC-068, DEC-069). DPP 위 CAL은 아니다 |
| GRA-MS-010 | 1 | 검사 | Assembly, Mission System | 해당없음 | — | R3 |
| GRA-MS-013 | 3 | 분석 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-014 | 3 | 분석 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-020 | 3 | 시험 | Mission System | 해당없음 | — | R2 |
| GRA-MS-023 | 1 | 분석 | Assembly, Mission System | 해당없음 | — | R5 |
| GRA-MS-024 | 1 | 분석 | Mission System | 해당없음 | — | R5 |
| GRA-MS-025 | 1 | 분석 | Mission System | 해당없음 | — | R5 |
| GRA-MS-026 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R1 |
| GRA-MS-027 | 1 | 분석 | Assembly, Mission System | 해당없음 | — | R5 |
| GRA-MS-028 | 3 | 분석 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-029 | 3 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-030 | 3 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-031 | 3 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-032 | 3 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-033 | 1 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-034 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R3 |
| GRA-MS-035 | 3 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-036 | 3 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-037 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-041 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R1 |
| GRA-MS-045 | 1 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-046 | 1 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-049 | 1 | 분석 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-050 | 1 | 검사 | Assembly, Mission System | 해당없음 | — | R3 |
| GRA-MS-051 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-052 | 1 | 시연 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-054 | 1 | 검사 | Assembly, Mission System | 부분 | 배치·복구 전략 문서 | 빌드·실행 절차(계약 §7), 참여자 이탈 시 Reset+Start(DEC-041) |
| GRA-MS-055 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-056 | 1 | 검사 | Assembly, Mission System | 해당없음 | — | R1 |
| GRA-MS-057 | 2 | 분석 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-059 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-MS-060 | 1 | 분석 | Mission System | 해당없음 | — | R2 |
| GRA-MS-061 | 2 | 분석 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-062 | 2 | 검사 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-063 | 3 | 분석 | Mission System | 해당없음 | — | R2 |
| GRA-MS-064 | 3 | 분석 | Mission System | 해당없음 | — | R2 |
| GRA-MS-065 | 2 | 시연 | Assembly, Mission System | 부분 | 허용 통신 채널을 파일로 정의 | 외부 교환은 `gateway/config/lacal_server.yaml`의 `declared.pub·sub`, 브라우저는 브리지 발행 허용 키(DEC-027). 보안 목적 정의는 아니다 |
| GRA-MS-066 | 2 | 분석 | Mission System | 해당없음 | — | R2 |
| GRA-MS-067 | 2 | 검사 | Mission System | 해당없음 | — | R2 |
| GRA-MS-068 | 1 | 시연 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-069 | 1 | 시연 | Assembly, Mission System | 해당없음 | — | R2 |
| GRA-MS-071 | 1 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-MS-072 | 1 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-MS-073 | 1 | 시연 | Assembly, Mission System | 해당없음 | — | R5 |
| GRA-MS-074 | 2 | 검사 | Mission System | 해당없음 | — | R1 |
| GRA-MS-075 | 1 | 검사 | Mission System | 해당없음 | — | R2 |
| GRA-MS-076 | 3 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-MS-077 | 3 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-MS-078 | 3 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-MS-079 | 1 | 검사 | Mission System | 부분 | 서비스 건강·상태 메시지 발행 | 기체 `SystemStatus`를 Gateway가 외부 UCI로 내보낸다(DEC-068) |
| GRA-MASI-001 | 1 | 시연 | Assembly, MASI, Mission System | 부분 | 서비스 시작 | `scripts/run_p0_demo.py`가 Core·Datalink·Agent·Logger·Gateway 프로세스를 띄운다. 컨테이너 배치는 없다 |
| GRA-MASI-002 | 1 | 시연 | Assembly, MASI, Mission System | 부분 | 서비스 정지 | 같은 실행기가 STOP 파일을 받으면 띄운 프로세스를 PID로 정리한다 |
| GRA-MASI-003 | 1 | 분석 | Assembly, MASI, Mission System | 해당없음 | — | R1 |
| GRA-MASI-006 | 1 | 검사 | Assembly, MASI, Mission System | 부분 | 고장 정보 감시 | 기체 건강 상태 `SystemStatus`·`SubsystemStatus`(VI), 모의 고장 주입 `InjectFault`. 소프트웨어 서비스 고장 감시는 아니다 |
| GRA-MASI-008 | 1 | 분석 | Assembly, MASI, Mission System | 해당없음 | — | R1 |
| GRA-MASI-010 | 2 | 검사 | MASI, Mission System | 부분 | 고장·건강·상태 자료 모음 | Logger가 버스 전체를 MCAP으로 기록한다(WP7). Monitor가 모아 보인다(WP6) |
| GRA-MASI-011 | 2 | 검사 | MASI, Mission System | 부분 | 고장·건강·상태 자료 저장 | MCAP 기록(WP7) |
| GRA-MASI-012 | 2 | 분석 | MASI, Mission System | 부분 | 고장 정보에 대응 | lockstep 이탈 참여자를 기다리며 경고로 표시하고 Reset+Start로 복구한다(DEC-041) |
| GRA-MASI-013 | 2 | 검사 | MASI, Mission System | 부분 | 고장·건강·상태 자료 접근 수단 | MCAP 재생기, Monitor·UI 표시 |
| GRA-MASI-015 | 1 | 검사 | Assembly, MASI, Mission System | 부분 | 배치된 서비스의 건강·상태 감시 | `SimStatus.waiting_participants`로 응답 없는 참여자를 알린다(DEC-041) |
| GRA-MASI-016 | 2 | 검사 | MASI, Mission System | 해당없음 | — | R1 |
| GRA-MASI-017 | 3 | 시연 | MASI, Mission System | 해당없음 | — | R3 |
| GRA-MASI-020 | 2 | 검사 | MASI, Mission System | 해당없음 | — | R3 |
| GRA-MASI-021 | 2 | 검사 | MASI, Mission System, Software Architecture | 해당없음 | — | R3 |
| GRA-MASI-022 | 1 | 시연 | Assembly, MASI, Mission System | 해당없음 | — | R3 |
| GRA-MASI-023 | 2 | 검사 | MASI, Mission System | 해당없음 | — | R1 |
| GRA-MASI-024 | 1 | 시연 | Assembly, MASI, Mission System | 해당 | 서비스 간 연결 제공 | 모든 프로세스가 `open_bus`로 키 기반 발행·구독을 맺는다(DEC-002, DEC-026). C7 소스 점검 |
| GRA-MASI-025 | 2 | 검사 | MASI, Mission System | 해당없음 | — | R1 |
| GRA-MASI-027 | 1 | — | MASI, Mission System | 해당없음 | — | R3 |
| GRA-MASI-028 | 1 | — | MASI, Mission System | 부분 | 기반 계층 상태 보고 | Core가 `sim/ctrl/status`(`SimStatus`)로 실행 상태를 보고한다(계약 §3) |
| GRA-MASI-029 | 1 | 시험 | MASI, Mission System | 해당 | 같은 서비스 2개 이상 배치 | Agent 런타임을 여러 프로세스로 띄운다(계약 §3.2 Agent 행, DEC-086) |
| GRA-MASI-030 | 1 | 시험 | MASI, Mission System | 부분 | 소프트웨어 고장 격리 | 구성요소가 별도 프로세스이고 이탈 참여자를 표시한다(DEC-041). 격리 시험은 없다 |
| GRA-MASI-031 | 1 | 시험 | MASI, Mission System | 해당없음 | — | R3 |
| GRA-MASI-032 | 1 | — | MASI, Mission System | 해당없음 | — | R5 |
| GRA-MASI-033 | 2 | 시험 | MASI, Mission System | 해당없음 | — | R3 |
| GRA-MASI-034 | 2 | 시험 | MASI, Mission System | 해당없음 | — | R3 |
| GRA-MPU-001 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-002 | 1 | 검사 | OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-003 | 1 | 검사 | AMS GRA Service MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-004 | 1 | 검사 | OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-005 | 3 | 분석 | AMS GRA Service MPU, Data Storage MPU, MFA MPU, OMS Service MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-006 | 2 | 분석 | AMS GRA Service MPU, Data Storage MPU, MFA MPU, OMS Service MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-007 | 1 | 검사 | MFA MPU | 해당없음 | — | R4 |
| GRA-MPU-008 | 1 | 검사 | MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-009 | 1 | 검사 | MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-011 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-012 | 3 | 검사 | MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-013 | 1 | 시연 | MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-014 | 1 | 검사 | DPP MPU | 해당없음 | — | R4 |
| GRA-MPU-015 | 1 | 검사 | Switch MPU, Time Distribution | 해당없음 | — | R4 |
| GRA-MPU-019 | 1 | 검사 | AMS GRA Service MPU | 부분 | OMS 인터페이스를 OMS 요구대로 구현 | Gateway의 LA-CAL 연동(DEC-069). C6 왕복 점검 |
| GRA-MPU-020 | 1 | 시연 | AMS GRA Service MPU | 부분 | OMS 규범 서비스 상태 메시지 보고 | UCI `SystemStatus`는 보고한다. OMS 서비스 상태 메시지는 아니다 |
| GRA-MPU-021 | 1 | 시연 | AMS GRA Service MPU | 부분 | 상태를 ASB CAL에 게시 | 기체 상태가 Gateway를 거쳐 CAL로 나간다(DEC-068) |
| GRA-MPU-022 | 1 | 검사 | AMS GRA Service MPU, MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-023 | 1 | 시연 | Local Function MPU | 해당없음 | — | R1 |
| GRA-MPU-024 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, MFA MPU, OMS Service MPU | 해당없음 | — | R2 |
| GRA-MPU-025 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 부분 | 고장과 고장 상태 보고 | `SubsystemStatus.health`(NOMINAL·DEGRADED·FAILED) |
| GRA-MPU-026 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-027 | 1 | 분석 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-029 | 2 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-030 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-031 | 2 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-032 | 2 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-034 | 1 | 검사 | MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-035 | 1 | 검사 | MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-036 | 2 | 검사 | MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-037 | 1 | 검사 | Data Storage MPU | 해당없음 | — | R1 |
| GRA-MPU-038 | 1 | 검사 | DPP MPU, Data Storage MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R1 |
| GRA-MPU-039 | 2 | 검사 | AMS GRA Service MPU, Local Function MPU, MFA MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-040 | 2 | 검사 | AMS GRA Service MPU, Local Function MPU, MFA MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-041 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-042 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-043 | 1 | 검사 | MFA MPU | 해당없음 | — | R4 |
| GRA-MPU-044 | 1 | 검사 | MFA MPU | 해당없음 | — | R4 |
| GRA-MPU-045 | 1 | 검사 | MFA MPU | 해당없음 | — | R4 |
| GRA-MPU-046 | 1 | 시연 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 부분 | 자동 시험, 구조 커버리지 50% 이상 | 자동 시험(TC, `docs/03_traceability.md`)은 있다. 커버리지는 재지 않는다 |
| GRA-MPU-047 | 2 | 검사 | AMS GRA Service MPU, Data Storage MPU, OMS Service MPU | 부분 | 실행 환경에서 상대 경로만 사용 | 적용 가능하나 점검하지 않았다 |
| GRA-MPU-048 | 2 | 검사 | AMS GRA Service MPU, Data Storage MPU, OMS Service MPU | 부분 | 빌드 환경에서 상대 경로만 사용 | CMake 프리셋 기반(DEC-022). 점검하지 않았다 |
| GRA-MPU-049 | 1 | 시연 | MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-050 | 1 | 시연 | MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-051 | 1 | 검사 | AMS GRA Service MPU, Local Function MPU, OMS Service MPU | 부분 | 개방 형식 SBOM | `uv.lock`·`vcpkg.json`으로 의존성 버전을 기계 판독 형식으로 둔다. 표준 SBOM 형식은 아니다 |
| GRA-MPU-053 | 3 | 검사 | AMS GRA Service MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-057 | 1 | 시연 | AMS GRA Service MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-058 | 1 | 분석 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, MFA MPU, OMS Service MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-059 | 1 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-060 | 1 | 분석 | DPP MPU, MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-061 | 1 | 검사 | DPP MPU, Data Storage MPU, MFA MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-062 | 1 | 시연 | DPP MPU, Data Storage MPU, MFA MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-063 | 1 | 분석 | DPP MPU, Data Storage MPU, MFA MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-064 | 1 | 시연 | DPP MPU, Data Storage MPU, MFA MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-065 | 1 | 검사 | DPP MPU, Data Storage MPU, MFA MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-066 | 1 | 시연 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-067 | 1 | 시연 | DPP MPU, Data Storage MPU, MFA MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-068 | 1 | 시연 | DPP MPU, MFA MPU | 해당없음 | — | R1 |
| GRA-MPU-069 | 1 | 시연 | AMS GRA Service MPU, MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-070 | 1 | 시연 | AMS GRA Service MPU | 해당없음 | — | R5 |
| GRA-MPU-071 | 1 | 검사 | AMS GRA Service MPU, OMS Service MPU | 부분 | 자동 파이프라인으로 빌드·패키징·배포 | CMake 프리셋과 스크립트로 빌드한다(DEC-022). 자동 파이프라인(CI)은 없다 |
| GRA-MPU-074 | 3 | 분석 | AMS GRA Service MPU, Data Storage MPU, MFA MPU, OMS Service MPU, Switch MPU | 해당없음 | — | R2 |
| GRA-MPU-075 | 2 | 검사 | MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-076 | 2 | 검사 | Switch MPU | 해당없음 | — | R4 |
| GRA-MPU-077 | 3 | 시연 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 부분 | 자동 시험, 구조 커버리지 80% 이상 | 위와 같다 |
| GRA-MPU-078 | 3 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-079 | 3 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R3 |
| GRA-MPU-080 | 2 | 시연 | AMS GRA Service MPU, MFA MPU | 해당없음 | — | R5 |
| GRA-MPU-081 | 2 | 시연 | AMS GRA Service MPU | 해당없음 | — | R5 |
| GRA-MPU-082 | 2 | 검사 | AMS GRA Service MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-083 | 3 | 검사 | AMS GRA Service MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-084 | 1 | 검사 | Data Storage MPU, Processor Chassis and Backplane MPU | 해당없음 | — | R4 |
| GRA-MPU-085 | 2 | 검사 | AMS GRA Service MPU, DPP MPU, Data Storage MPU, Local Function MPU, MFA MPU, OMS Service MPU, Processor Chassis and Backplane MPU, Switch MPU | 부분 | 해당 인터페이스로 고장 보고 | `SystemStatus`(VI)로 보고한다 |
| GRA-MPU-086 | 1 | 검사 | AMS GRA Service MPU, MFA MPU, OMS Service MPU | 해당없음 | — | R1 |
| GRA-MPU-087 | 3 | 검사 | Switch MPU | 해당없음 | — | R4 |
| GRA-MPU-088 | 1 | 시연 | DPP MPU, Data Storage MPU, Switch MPU | 해당없음 | — | R1 |
| GRA-MPU-090 | 1 | 검사 | AMS GRA Service MPU, OMS Service MPU | 해당없음 | — | R3 |
| GRA-MPU-091 | 1 | 검사 | DPP MPU, Data Storage MPU, Processor Chassis and Backplane MPU, Switch MPU | 해당없음 | — | R1 |
| GRA-MPU-092 | 2 | 검사 | DPP MPU, MFA MPU | 부분 | 개방 형식 SBOM | 위와 같다 |
| GRA-DK-001 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-002 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-003 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-004 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-005 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-006 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-007 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-008 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-009 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-010 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-011 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-012 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-013 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-014 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-015 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-016 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-017 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-018 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-019 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-020 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-021 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-022 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-023 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-024 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-025 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-026 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-027 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-028 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-029 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-030 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-032 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-033 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-034 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-035 | 2 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-036 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-037 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-038 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-039 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-040 | 2 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-041 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-042 | 1 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-043 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-DK-044 | 3 | 검사 | DPP MPU, MFA MPU | 해당없음 | — | R3 |
| GRA-CYMAN-002 | 1 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-003 | 1 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-004 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-005 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-006 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-007 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-008 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-009 | 1 | 검사 | Mission System | 해당없음 | — | R2 |
| GRA-CYMAN-010 | 3 | 검사 | Mission System | 해당없음 | — | R2 |
| GRA-CYAGE-002 | 1 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYAGE-003 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYAGE-004 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYAGE-005 | 3 | 분석 | Mission System | 해당없음 | — | R2 |
| GRA-CYMON-002 | 1 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMON-003 | 2 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMON-004 | 3 | 시연 | Mission System | 해당없음 | — | R2 |
| GRA-CYMON-005 | 1 | 검사 | Mission System | 해당없음 | — | R2 |
