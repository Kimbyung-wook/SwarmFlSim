# 8. WP5 WebSocket 브리지 (`bridge/`)

## 책임

브라우저를 버스에 붙인다(DEC-027). 클라이언트별 구독과 다운샘플, 발행 키 허용 검사를 맡는다. lockstep 참여자가 아니다. 프로토콜은 [계약 §3.5](../../10_contracts.md#35-브라우저-연동-dec-027), 구조는 [bridge/README.md](../../../bridge/README.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/swarm_bridge/cli.py` | 진입점 |
| `src/swarm_bridge/server.py` | `BridgeServer`, 클라이언트·구독 처리 |
| `src/swarm_bridge/frame.py` | 바이너리 프레임 |

## 실행 파일 `swarm-bridge`

| 옵션 | 뜻 |
|---|---|
| `--host` | 기본 `127.0.0.1`. 다른 PC의 브라우저는 `0.0.0.0` |
| `--port` | 기본 8765. 접속 주소 `ws://<host>:<port>/bus` |
| `--queue-limit <n>` | 클라이언트별 송신 대기 프레임 수, 기본 4096 |
| `-v` | 자세한 로그 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | 클라이언트가 요청한 키 |
| 발행 | `role=control` 클라이언트의 `sim/ctrl/cmd`, `swarm/<gcs>/tx/**`만 |

## 시험

```bash
uv run pytest bridge/tests
```

## 알려진 제약

- 기본 포트 8765가 CAL Server의 기본 포트와 같다. 함께 띄우면 한쪽을 바꾼다.
- 송신 대기가 넘치면 오래된 프레임부터 버리고, 접속을 닫을 때 버린 수를 로그에 남긴다.

추적: [bridge/TRACE.md](../../../bridge/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
