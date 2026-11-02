# WP5 WebSocket 브리지 추적표 (모듈 UI)

- 브랜치: `claude/wp5-bridge-cce90d` (기준 `wp0-contracts` 8972f55)
- 계약 버전: 0.2.0. 브리지 프로토콜 v1(`docs/10_contracts.md` §3.5)을 바꾸지 않았다.
- ID는 `ui/TRACE.md`와 이어지는 번호다(IMP-UI-020~022, TC-UI-010~016).

## 구현 (IMP)

| ID | 내용 | 위치 | 근거 | 시험 |
|---|---|---|---|---|
| IMP-UI-020 | 바이너리 프레임 인코드·디코드(uint16 LE 키·인코딩 길이, 형식 오류 거부) | `src/swarm_bridge/frame.py` | DEC-027 | TC-UI-010 |
| IMP-UI-021 | 프로토콜 v1 서버: hello/welcome, sub/unsub, error(bad_request/forbidden/unsupported), 클라이언트별 버스 구독과 키별 `max_hz` 다운샘플, 발행 허용 키 검사, 다중 클라이언트, 클라이언트별 송신 큐(넘치면 오래된 것 버림), `/bus` 경로 | `src/swarm_bridge/server.py` | DEC-027, DEC-020, DEC-006, DEC-002, DEC-026 | TC-UI-011~016 |
| IMP-UI-022 | 실행 파일 `swarm-bridge`(`--host`, `--port`, `--queue-limit`, 공통 버스 옵션), `open_bus`로 버스 열기 | `src/swarm_bridge/cli.py`, `pyproject.toml` | DEC-026, DEC-027 | TC-UI-015, TC-UI-019 |

## 시험 (TC)

| ID | 내용 | 위치 | 근거 | 결과 |
|---|---|---|---|---|
| TC-UI-010 | 프레임 배치·왕복·UTF-8 키, UI와 공통 바이트 벡터, 형식 오류 5종 (6건) | `tests/test_bridge.py` | IMP-UI-020 | 통과 |
| TC-UI-011 | welcome(protocol 1, contract 0.2.0), unsupported·잘못된 JSON·중복 hello, 잘못된 첫 메시지 5종 → error 후 종료, hello 시간 초과, 다른 경로 404 (8건) | `tests/test_bridge.py` | IMP-UI-021 | 통과 |
| TC-UI-012 | 구독 키·인코딩·페이로드 전달, unsub 뒤 미수신·버스 구독 해제, sub 형식 오류 6종, 중복 id, 연결 종료 시 버스 구독 정리 (9건) | `tests/test_bridge.py` | IMP-UI-021 | 통과 |
| TC-UI-013 | `max_hz=10`에서 50 Hz 두 키 → 키별 첫 메시지·마지막 메시지 보장, 0.6 s에 5~9개, 순서 유지. `max_hz=0` 200건 전부. 송신 큐 넘침 시 오래된 것부터 버림 (3건) | `tests/test_bridge.py` | IMP-UI-021, DEC-006 | 통과 |
| TC-UI-014 | 발행 허용 규칙(sim/ctrl/cmd, swarm/&lt;gcs&gt;/tx/**만, 다른 GCS·rx·와일드카드·observer 거부), 실제 전달과 forbidden 오류 (3건) | `tests/test_bridge.py` | IMP-UI-021, DEC-027 | 통과 |
| TC-UI-015 | 다중 클라이언트(control 2 + observer 1): 구독 분리, 다른 GCS 키 발행 거부, 모니터가 tx 수신, 종료 정리. CLI 버스 옵션 파싱 (2건) | `tests/test_bridge.py` | IMP-UI-021, IMP-UI-022, DEC-020 | 통과 |
| TC-UI-016 | Zenoh 백엔드(peer 2개, 127.0.0.1 tcp, 멀티캐스트 끔): Zenoh 스레드 콜백 → WebSocket 전달, WebSocket 발행 → Zenoh 구독자 수신·encoding 유지 (1건) | `tests/test_bridge.py` | IMP-UI-021, DEC-026 | 통과 |

- 자동 시험: `uv run pytest` 전체 119건 통과(bridge 32건 포함, websockets 17.4, eclipse-zenoh 1.10).
- 수동 확인은 `ui/TRACE.md` TC-UI-019.
