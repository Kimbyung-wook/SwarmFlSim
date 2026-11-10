# 11. 문제 해결

- 설치·빌드 실패는 [1.4](01_setup.md#14-자주-나는-실패)를 먼저 본다. 사용자 관점의 증상은 [사용자 매뉴얼 10장](../42_user/10_faq.md).
- 프로세스 로그의 위치는 실행 방법마다 다르다. 데모 실행기는 `out/p0_demo/<모드>-<시각>/<프로세스>.log`에 모은다.

## 11.1 lockstep

| 증상 | 원인 | 조치 |
|---|---|---|
| 첫 틱이 나가지 않는다 | `run.participants`의 참여자가 준비 신호(`FrameDone{0}`)를 보내지 않았다. 참여자가 안 떴거나 ID가 다르다 | Core 로그의 대기 참여자 목록과 프로세스의 `--participant`를 맞춘다 |
| 진행 중 멈춘다. UI·Monitor에 참여자 대기 표시 | 참여자가 죽었거나 응답하지 않는다(DEC-041) | 재합류는 지원하지 않는다. 참여자를 다시 띄우고 Reset+Start |
| 같은 시드인데 궤적이 다르다 | 플러그인이 `ctx.rng` 외의 난수, 벽시계, 수신 순서에 의존한다. 또는 realtime·free-run으로 돌렸거나, Gateway에 외부 입력을 넣었다 | [3.6](03_architecture.md#36-lockstep-한-프레임)의 규칙을 확인한다. `qa/diag_determinism.py`로 처음 어긋나는 프레임을 찾는다 |
| 배속이 목표보다 낮다 | Python Agent가 병목이다. `frame_overruns`가 는다 | 기체를 여러 Agent로 나누거나(`--entities`) 배속을 낮춘다 |

## 11.2 버스

| 증상 | 원인 | 조치 |
|---|---|---|
| 프로세스끼리 서로 보지 못한다 | 엔드포인트가 맞지 않거나 멀티캐스트가 막혔다 | `--listen`/`--connect`를 명시한다. 먼저 뜬 프로세스의 listen 주소에 뒤 프로세스가 connect한다 |
| 다른 실행의 메시지가 섞인다 | 같은 PC의 다른 버스와 멀티캐스트로 붙었다 | 모든 프로세스에 `--no-multicast` |
| 포트를 열지 못해 시작에 실패한다 | 포트를 다른 실행이 쓰고 있다 | `--base-port`, `--bridge-port`나 listen 포트를 바꾼다. 브리지와 CAL Server의 기본 포트는 둘 다 8765이므로 함께 띄울 때 하나를 바꾼다 |
| C++ 프로세스가 memory 백엔드로만 뜬다 | Zenoh 없이 빌드됐다 | [1.4](01_setup.md#14-자주-나는-실패) |

## 11.3 플러그인과 매개변수

| 증상 | 원인 | 조치 |
|---|---|---|
| 플러그인을 찾지 못한다 | entry point가 등록되지 않았거나 `uv sync`를 안 했다 | `uv run swarm-agent --list-plugins`로 이름을 확인한다 |
| 매개변수가 적용되지 않는다 | 거부됐다 | `sim/param/<entity>/<owner>`의 `rejected` 사유를 본다. UI 매개변수 패널에도 표시된다 |
| `TaskStatus` 상태가 순서가 바뀌어 도착한다 | 데이터링크 지연·지터 때문이다 | 판정에는 영향이 없다. `task_id`와 최종 상태로 판단한다 |
| flocking에서 Route가 `REJECTED` | 지원하지 않는다 | waypoint를 쓴다 |

## 11.4 코드 생성

| 증상 | 원인 | 조치 |
|---|---|---|
| Python에서 `swarm.v1` import 실패 | 생성물이 없다 | `uv run python scripts/gen_proto.py` |
| proto를 받았는데 필드가 없다 | 생성물이 예전 것이다 | 위 명령을 다시 실행한다. C++는 다시 빌드 |
| 계약 버전이 다르게 표시된다 | 구버전 브리지나 UI를 띄웠다 | 브리지 `welcome`의 `contract`와 `CONTRACT_VERSION`을 비교하고 다시 받는다 |

## 11.5 진단 도구

```bash
uv run --with psutil python qa/run_qa.py --list
```

```bash
<build>/logger/swarm_logger info <file.mcap>
```

- `swarm_logger info`는 채널별 메시지 수와 시간 범위를 보여 준다. 버스에 나간 메시지를 확인할 때 쓴다.
