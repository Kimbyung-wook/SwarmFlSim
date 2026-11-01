# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 군집 시뮬레이션 및 알고리즘 설계/개발 환경의 개발

## 작업 규칙
- 문답은 한국어로 수행
- 직접 저장소에 푸시하지 말 것.


## 문서 작성 규칙
- 문서 작성 기본은 markdown 문법으로 작성
- 다이어그램은 mermaid, svg 으로 작성

## Project
- 군집/편대 알고리즘 연구용 군집 무인항공기 시뮬레이터다.
- 모노레포이며, 작업 패키지(WP)별 디렉터리로 나눈다 (DEC-021). 디렉터리 배정은 `docs/00_proposal.md` §12를 따른다.
- 현재 WP0(계약: 스키마, 키 체계, 플러그인 API) 단계다.
- 빌드는 CMake 프리셋 `msvc-*`(vcpkg), `mingw-*`(MSYS2 UCRT64), `linux-*`를 모두 지원한다 (DEC-022). 설치·빌드·시험 명령은 `docs/10_contracts.md` §7에 있다.
- C++ 의존성은 `find_package`로만 찾는다. 툴체인 전용 설정을 CMake에 넣지 않는다.

## Documents
- `docs/00_proposal.md`: 아키텍처, 모델, WBS, 로드맵 (mermaid 다이어그램)
- `docs/01_id_convention.md`: ID 규칙 (REQ / PRP / OPN / DEC / IMP / TC)
- `docs/02_registry.md`: 요구·제안·결정사항 등록부, A-GRA 메시지 매핑 표
- `docs/03_traceability.md`: 추적 매트릭스
- `docs/10_contracts.md`: WP0 계약 (Protobuf 패키지, Zenoh 키, 플러그인 API)

## Working rules
- 모든 구현은 하나 이상의 REQ 또는 DEC에 연결한다. 구현 항목에 `IMP-<모듈>-NNN`, 시험에 `TC-<모듈>-NNN`을 부여하고 `docs/03_traceability.md`를 갱신한다.
- 커밋과 PR 설명에 관련 ID를 적는다. 예: `IMP-CORE-003: RK45 적분기 추가 (REQ-DYN-004, DEC-005)`
- ID는 재사용하지 않고 항목을 삭제하지 않는다. 상태만 바꾼다(`Superseded by …`, `Resolved by …`).
- 결정(DEC)과 충돌하는 구현을 하지 않는다. 바꿔야 하면 새 OPN을 등록하고 사용자에게 확인한다.
- 문서에는 결정과 근거만 쓴다. 부수적인 내용은 넣지 않는다.

## Architecture decisions (요약, 상세는 등록부)
- 언어: Sim Core·Datalink·Logger는 C++20, 알고리즘 플러그인과 Gateway는 Python 3.12(uv), UI는 TypeScript + CesiumJS (DEC-001, DEC-003)
- 통신: Zenoh만 사용, DDS 미사용 (DEC-002)
- 시간: 고정 프레임(50–100 Hz) + 프레임 안의 가변 스텝 RK45. 실시간, 가속 lockstep, free-run 모드 (DEC-005)
- 기체 계층은 A-GRA 경계를 따른다. MA(행동결정·군집·경로)는 L1 포트(C2/VI/MS/MP/MD/P2P)로만 통신하고, 시뮬레이터 내부 상태나 `truth/**` 채널에 직접 접근하지 않는다 (DEC-013)
- 시뮬레이션 통제는 `sim/ctrl/**` 채널로 분리한다. A-GRA로 표현할 수 없는 운용 C2는 EXT 메시지로 추가한다 (DEC-014)
- 모든 기체 간·지상-기체 간 메시지는 Datalink Emulator를 거친다.
- 지도는 한반도 전역 저해상도 (DEC-016). 적/표적은 스크립트 기본, MA 플러그인 연결 가능 (DEC-017)
- 센서 탐지는 FOV·거리·가시선만 판정하고 확률은 넣지 않는다 (DEC-018). 무장 성능은 공개 일반값 + JSON 재정의 (DEC-019)

## Multi-agent development (DEC-015, DEC-021)
- WP0(Protobuf 스키마, Zenoh 키, 플러그인 API)을 먼저 고정한다. 이후 작업 패키지별 세션이 worktree에서 병렬로 개발한다.
- 각 세션은 자기 WP 디렉터리만 수정한다. `proto/`와 `docs/10_contracts.md`의 계약 변경은 WP0을 거친다.

## Reference material
- `../open_arsenal/`: A-GRA 6.0a, AMS-GRA v14, OMS/UCI 표준 자료와 `agra_lacal`(Python OMS LA-CAL 서버/클라이언트, A-GRA 6.0a XSD 검증, uv 기반)
- A-GRA 인터페이스 볼륨 중 배포 제한(Distribution D) 표기가 있는 문서의 상세 내용은 이 저장소에 옮기지 않는다. 메시지명은 공개(Distribution A) XSD에서 가져온다.
