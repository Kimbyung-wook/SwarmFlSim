# 8. WP4 데이터링크 (`datalink/`)

## 책임

기체 간·지상-기체 간 메시지에 링크 모델을 적용해 전달한다. 메시지마다 전달 또는 손실 사유를 발행한다. 사용법은 사용자 매뉴얼 [7장](../../42_user/07_link.md).

## 구조

| 경로 | 내용 |
|---|---|
| `src/main.cpp` | 진입점 |
| `src/emulator.cpp`, `include/swarm/lnk/emulator.hpp` | 틱 처리, 엔티티 표, 전달 |
| `src/channel.cpp`, `include/swarm/lnk/channel.hpp` | 경로손실·SNR, 토큰 버킷, Gilbert-Elliott, 지연 |
| `src/profile.cpp`, `include/swarm/lnk/profile.hpp` | 내장 프로파일, 재정의 |

판정 순서는 생존 → 고장 → 재밍 → 거리·SNR → 가시선 → 토큰 버킷 → 버스트 손실 → 지연이다.

`sim_time_us == 0`이고 `publisher`가 있을 때만 시각 없음으로 보고 마지막 틱 시각을 쓴다. `publisher`가 없으면 0을 유효한 시각으로 유지하고, 프레임 0 송신도 `tx < T_k` 규칙으로 틱 1에서 처리한다(IMP-LNK-023, DEC-054, DEC-077).

## 실행 파일 `swarm_datalink`

| 옵션 | 뜻 |
|---|---|
| `--scenario <file>` | 없으면 `sim/ctrl/cmd`의 LoadScenario를 기다린다 |
| `--participant <id>` | 기본 `datalink-0` |
| `--no-frame-done` | FrameDone을 보내지 않는다 |
| `--seed <n>` | 난수 시드 |
| `--terrain-flat <m>`, `--no-los` | 가시선 평지 고도, 가시선 끄기 |
| `--state-period <s>` | `link/state` 주기, 기본 1, 0이면 끔 |
| `--quiet` | 로그 끔 |
| 공통 버스 옵션 | [3.2](../03_architecture.md#32-버스-열기) |

## 구독·발행 키

| 방향 | 키 |
|---|---|
| 구독 | `swarm/*/tx/**`, `sim/clock/tick`, `sim/ctrl/cmd`, `sim/ctrl/scenario`, `truth/state`, `truth/event/jam_zone`, `truth/event/kill` |
| 발행 | `swarm/<dst>/rx/**`, `link/outcome/<src>/<dst>`, `link/state/<a>/<b>`, `sim/clock/done/<p>` |

## 시험

```bash
ctest --preset msvc-debug -R "^lnk\."
```

TC-LNK 항목이 판정 단계별 동작과 같은 입력의 결정성을 본다.

## 알려진 제약

- 재밍 주파수대는 모의하지 않는다.
- 피어 중계(멀티홉)는 없다. 직접 닿는 수신자에게만 전달한다.
- 가시선은 `--terrain-flat`의 평지로만 판정한다. DEM을 쓰지 않는다.
- 다각형 구역은 위경도 평면 판정이다. 날짜변경선·극 부근은 지원하지 않는다.
- 폭주 폐기 outcome은 틱당 상한까지만 기록하고 나머지는 로그에 건수만 남긴다.

추적: [datalink/TRACE.md](../../../datalink/TRACE.md).

다음: [9. 기여 규칙](../09_contributing.md).
