# 추적 매트릭스

- 각 요구사항(REQ)이 어떤 제안(PRP)과 결정(DEC)으로 이어지고, 어떤 구현(IMP)과 시험(TC)으로 검증되는지 추적한다.
- ID 규칙은 [01_id_convention.md](01_id_convention.md)를 따른다.
- 각 항목의 정의는 [02_registry.md](02_registry.md)에 있다.

## 갱신 규칙
- IMP를 추가하면 해당 REQ 행의 IMP 열에 적는다. TC도 같은 방식으로 적는다.
- `WP`는 [제안서 §12](00_proposal.md#12-작업-분할wbs과-멀티-에이전트-개발-dec-015)의 작업 패키지다.
- 검증 상태:
  - `-`: 미착수
  - `구현중`
  - `구현완료`: IMP 완료, TC 미통과
  - `검증완료`: 연결된 TC 모두 통과

## 매트릭스

| REQ | PRP | DEC | WP | IMP | TC | 검증 상태 |
|---|---|---|---|---|---|---|
| REQ-UI-001 | PRP-UI-001 | DEC-003, DEC-004 | WP5 | | | - |
| REQ-UI-002 | PRP-UI-001 | DEC-003 | WP5 | | | - |
| REQ-UI-003 | PRP-UI-001 | DEC-014 | WP5 | | | - |
| REQ-UI-004 | PRP-UI-001, PRP-BHV-001 | DEC-008 | WP5, WP3 | | | - |
| REQ-UI-005 | PRP-UI-002, PRP-LNK-002 | DEC-011 | WP6, WP4 | | | - |
| REQ-UI-006 | PRP-UI-001, PRP-NET-002 | DEC-020 | WP5 | | | - |
| REQ-UI-007 | PRP-UI-001 | DEC-003 | WP5 | | | - |
| REQ-DYN-001 | PRP-DYN-001 | DEC-007 | WP2 | | | - |
| REQ-DYN-002 | PRP-DYN-001 | DEC-007 | WP2 | | | - |
| REQ-DYN-003 | PRP-DYN-002, PRP-SIM-002 | DEC-005 | WP1, WP2 | IMP-API-006 | | 구현중 |
| REQ-DYN-004 | PRP-DYN-002 | DEC-005 | WP2 | IMP-API-006 | | 구현중 |
| REQ-DYN-005 | PRP-DYN-003 | DEC-012 | WP2, WP8 | | | - |
| REQ-GNC-001 | PRP-GNC-001, PRP-BHV-001 | DEC-013 | WP3 | | | - |
| REQ-BHV-001 | PRP-BHV-001, PRP-SIM-003 | DEC-008, DEC-013 | WP3 | | | - |
| REQ-BHV-002 | PRP-BHV-001, PRP-BHV-003 | DEC-013 | WP3 | | | - |
| REQ-BHV-003 | PRP-BHV-001, PRP-BHV-003 | DEC-008 | WP3 | | | - |
| REQ-BHV-004 | PRP-BHV-002, PRP-BHV-003 | DEC-001 | WP3 | IMP-API-005 | | 구현중 |
| REQ-NET-001 | PRP-NET-001, PRP-NET-002, PRP-NET-003, PRP-SIM-002 | DEC-002, DEC-010 | WP0, WP1 | IMP-API-001, IMP-API-003, IMP-API-004 | TC-API-001, TC-API-002, TC-API-003 | 구현중 |
| REQ-PRF-001 | PRP-BHV-002, PRP-SIM-001 | DEC-006 | WP1, WP10 | | | - |
| REQ-PRF-002 | PRP-BHV-002 | DEC-005, DEC-006 | WP10 | | | - |
| REQ-LNK-001 | PRP-LNK-001 | DEC-002 | WP4 | | | - |
| REQ-LNK-002 | PRP-LNK-001 | DEC-009 | WP4 | | | - |
| REQ-LNK-003 | PRP-LNK-001 | DEC-009 | WP4 | | | - |
| REQ-LNK-004 | PRP-LNK-001, PRP-LNK-002 | DEC-008 | WP4 | | | - |
| REQ-CFG-001 | PRP-CFG-001 | | WP5, WP7 | | | - |
| REQ-CFG-002 | PRP-CFG-001 | | WP7 | | | - |
| REQ-PAY-001 | PRP-PAY-001, PRP-CFG-001 | | WP8 | | | - |
| REQ-PAY-002 | PRP-PAY-001 | DEC-018 | WP8 | | | - |
| REQ-PAY-003 | PRP-PAY-001, PRP-LNK-001 | DEC-009 | WP8, WP4 | | | - |
| REQ-PAY-004 | PRP-PAY-001, PRP-DYN-003 | DEC-012 | WP8 | | | - |
| REQ-PAY-005 | PRP-PAY-001, PRP-DYN-003 | DEC-012, DEC-019 | WP8 | | | - |
| REQ-SIM-001 | PRP-SIM-001 | DEC-017 | WP8 | | | - |
| REQ-SIM-002 | PRP-SIM-002 | DEC-005 | WP1 | | | - |
| REQ-SIM-003 | PRP-UI-001 | DEC-004, DEC-016 | WP5, WP2 | | | - |
| REQ-LOG-001 | PRP-LOG-001 | DEC-011 | WP7 | | | - |
| REQ-STD-001 | PRP-STD-001, PRP-STD-002, PRP-GNC-001 | DEC-013, DEC-014 | WP0, WP9 | IMP-API-002, IMP-API-005 | | 구현중 |

## 구현·시험 항목

| ID | 내용 | 위치 | 근거 |
|---|---|---|---|
| IMP-API-001 | 모노레포 루트 빌드: CMake 프리셋(MSVC+vcpkg, MSYS2, Linux), uv workspace | `CMakeLists.txt`, `CMakePresets.json`, `vcpkg.json`, `pyproject.toml` | DEC-001, DEC-010, DEC-021, DEC-022 |
| IMP-API-002 | Protobuf 스키마 `swarm.v1`, A-GRA 매핑 옵션 | `proto/swarm/v1/` | PRP-STD-001, DEC-013, DEC-014 |
| IMP-API-003 | Zenoh 키 체계 (Python, C++) | `api/*/keys.*` | PRP-NET-003 |
| IMP-API-004 | ASB 버스 계약, 인메모리 백엔드 | `api/*/bus.*` | PRP-NET-001 |
| IMP-API-005 | MA/FA 플러그인 API, L1 포트 | `api/python/src/swarm_api/{ports,plugin}.py`, `api/cpp/include/swarm/api/plugin.hpp` | PRP-BHV-001, PRP-BHV-002, DEC-008, DEC-013 |
| IMP-API-006 | Core ⇄ 동역학 인터페이스 | `api/cpp/include/swarm/api/dynamics.hpp` | PRP-DYN-002, DEC-005 |
| TC-API-001 | 키 생성, 엔티티 ID 검증, 키 표현식 일치 | `api/python/tests/test_keys.py` | IMP-API-003 |
| TC-API-002 | InMemoryBus 발행·구독·해제 | `api/python/tests/test_bus.py` | IMP-API-004 |
| TC-API-003 | C++ 키·버스, 생성 코드 링크 | `api/cpp/tests/test_api.cpp` | IMP-API-002~004 |

## 시험 결과

| TC | 결과 | 일자 | 환경 |
|---|---|---|---|
| TC-API-001 | 통과 | 2026-11-01 | Windows, uv + CPython 3.12 |
| TC-API-002 | 통과 | 2026-11-01 | Windows, uv + CPython 3.12 |
| TC-API-003 | 통과 | 2026-11-01 | Windows, MSVC + vcpkg (`msvc-debug`) |

## 프로세스 결정

| DEC | 적용 범위 |
|---|---|
| DEC-015 | 전체 개발 프로세스: WBS 작업 패키지별 병렬 세션, WP0 계약 우선 |
| DEC-021 | 저장소 구조: 모노레포, WP별 디렉터리, worktree 병렬 작업 |
| DEC-022 | 빌드 환경: MSVC+vcpkg, MSYS2 GCC, Linux/WSL2 GCC 프리셋 병행 (IMP-API-001) |
