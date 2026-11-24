"""Agent MD 기록 덤프 실행기 (QA 37차, DEC-105 실스택 확인, TC-QA-201).

MD 포트 기록(link_state·lost_link_*)은 계약에 키가 없어 Agent 메모리에만 남는다(ports.MDPortImpl).
이 실행기는 swarm_agent.cli를 그대로 돌리면서 1 s마다 기체별 MD 기록을 QA_MD_DUMP 파일(JSON)로 쓴다.
프레임은 기록 시점 Vehicle.frame(모의 시각 = frame × 0.02 s)이다. 제품 코드는 바꾸지 않는다.

qa/p2_lostlink.py --md-dump 가 Agent 대신 띄운다.
"""
import json
import os
import sys
import threading
from pathlib import Path

from swarm_agent import cli, runtime as rtm

OUT = Path(os.environ["QA_MD_DUMP"])
KEEP = ("link_state", "lost_link")
_rt: list = []
_seen: dict[str, list] = {}


def _init(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
    _orig(self, *a, **k)
    _rt.append(self)


_orig = rtm.AgentRuntime.__init__
rtm.AgentRuntime.__init__ = _init


def _dump() -> None:
    for r in _rt:
        for vid, v in list(getattr(r, "vehicles", {}).items()):
            recs = [list(x) for x in list(v.ports.md.records) if str(x[1]).startswith(KEEP)]
            if len(recs) >= len(_seen.get(vid, [])):
                _seen[vid] = recs
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(_seen, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)


def _loop() -> None:
    ev = threading.Event()
    while not ev.wait(1.0):
        try:
            _dump()
        except Exception as e:  # noqa: BLE001  덤프 실패는 측정과 무관하게 넘긴다
            print("md dump:", e, file=sys.stderr, flush=True)


threading.Thread(target=_loop, daemon=True).start()
sys.exit(cli.main(sys.argv[1:]))
