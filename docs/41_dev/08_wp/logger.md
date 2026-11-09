# 8. WP7 기록·재생 (`logger/`)

## 책임

버스의 메시지를 MCAP에 기록하고 원래 간격으로 다시 내보낸다. 사용법은 사용자 매뉴얼 [8장](../../42_user/08_record_replay.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/main.cpp` | 진입점, 하위 명령 |
| `src/mcap_log.cpp`, `include/swarm/logger/mcap_log.hpp` | `Recorder`, `replay`, `inspect` |

채널은 버스 키와 같고 스키마는 FileDescriptorSet으로 넣는다.

## 실행 파일 `swarm_logger`

| 명령 | 옵션 |
|---|---|
| `info <file>` | 요약 |
| `record --out <file>` | `--key <expr>`, `--stats <s>`, `--max-queue-messages <n>`, `--max-queue-mib <n>`, 버스 옵션 |
| `replay <file>` | `--rate <x>`, `--key <expr>`, `--dry-run`, 버스 옵션 |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | 기록 시 `--key`로 준 키. 기본은 전체 |
| 발행 | 재생 시 기록된 키 그대로. `SimStatus`는 `replay`=true로 바꾼다(DEC-031) |

## 시험

```bash
ctest --preset msvc-debug -R "swarm_logger"
```

한 실행 파일에 TC-LOG 항목이 모여 있다.

## 알려진 제약

- Logger가 정상 종료되지 않으면 파일이 닫히지 않는다.
- 재생기는 수신자 속도에 맞추지 않는다(DEC-042).
- 큐 상한을 넘으면 메시지를 버리고 건수를 남긴다.

추적: [logger/TRACE.md](../../../logger/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
