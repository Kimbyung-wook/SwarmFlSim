# 8. WP7 시나리오 (`scenario/`)

## 책임

JSON 시나리오의 스키마, 의미 검사, proto 변환을 맡는다. 작성법은 사용자 매뉴얼 [3장](../../42_user/03_scenario.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/swarm_scenario/cli.py` | 명령행 |
| `src/swarm_scenario/schema/scenario.schema.json` | JSON Schema |
| `src/swarm_scenario/validate.py` | 의미 검사 |
| `src/swarm_scenario/convert.py`, `enums.py` | JSON ⇄ proto |
| `examples/` | 예제 시나리오 |

## 실행 파일 `swarm-scenario`

| 명령 | 뜻 |
|---|---|
| `validate <file>` | 스키마와 의미 검사 |
| `show <file>` | 요약 출력 |
| `export <file> --out <file>` | `.pb` 또는 proto JSON으로 변환 |

## 구독·발행 키

없다. 파일 도구다. 배포는 Core가 `sim/ctrl/scenario`로 한다.

## 시험

```bash
uv run pytest scenario/tests
```

## 알려진 제약

- `validate`는 Core의 검사를 모두 포함하지 않는다. 25자 초과 ID, 재머 2개, `dof5`·`dof6`는 Core에서 거부된다.
- `run.rate`는 0보다 커야 한다. 최대 속도는 Core의 `--rate 0`으로 준다.

추적: [scenario/TRACE.md](../../../scenario/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
