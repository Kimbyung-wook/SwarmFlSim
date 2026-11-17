"""C4용 Agent 실행 래퍼. 실제 진입점 `swarm_agent.cli.main()`을 그대로 부르되 다음만 감싸 기록한다(Agent 코드는 바꾸지 않는다).

- 버스: `open_bus`가 돌려준 Bus의 subscribe(키 표현식)·put(키). MCAP에는 발행자 정보가 없어(채널 = 키) 프로세스별 키는
  여기서 얻는다. 발행 키는 MCAP 채널과 대조한다.
- L1 포트: MA 플러그인이 `ctx.ports`로 부르는 메서드가 주고받은 메시지의 전체 이름(포트·방향별 수)

CONF_AGENT_PROBE=<file> python qa/conformance/agent_probe.py --participant agent-0 ...(swarm-agent 인자)
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from confcommon import write_json  # noqa: E402

import swarm_agent.cli as cli  # noqa: E402
from swarm_agent import ports as P  # noqa: E402

OUT = Path(os.environ.get("CONF_AGENT_PROBE", "agent_probe.json"))
LOCK = threading.Lock()
D: dict = {"subscribe": [], "put": Counter(), "rx": Counter(), "port": Counter(), "started": time.time()}


def _dump() -> None:
    with LOCK:
        d = {"subscribe": list(D["subscribe"]), "put": dict(D["put"]), "rx": dict(D["rx"]),
             "port": [[*k, v] for k, v in D["port"].items()], "started": D["started"], "t": time.time()}
    write_json(OUT, d)


def _note(port: str, direction: str, msgs) -> None:  # noqa: ANN001
    if msgs is None:
        return
    seq = msgs if isinstance(msgs, (list, tuple)) else [msgs]
    with LOCK:
        for m in seq:
            desc = getattr(m, "DESCRIPTOR", None)
            D["port"][(port, direction, desc.full_name if desc is not None else type(m).__name__)] += 1


def _wrap(cls, name: str, port: str, direction: str, arg: bool = False) -> None:  # noqa: ANN001
    orig = getattr(cls, name)

    def f(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        if arg:
            _note(port, direction, a[0] if a else None)
            return orig(self, *a, **k)
        out = orig(self, *a, **k)
        _note(port, direction, out)
        return out
    setattr(cls, name, f)


for _c, _n, _p, _d, _a in [
        (P.C2PortImpl, "inbox", "C2", "MA<-", False), (P.C2PortImpl, "send", "C2", "MA->", True),
        (P.VIPortImpl, "nav", "VI", "MA<-", False), (P.VIPortImpl, "capability", "VI", "MA<-", False),
        (P.VIPortImpl, "system_status", "VI", "MA<-", False), (P.VIPortImpl, "command", "VI", "MA->", True),
        (P.VIPortImpl, "command_status", "VI", "MA<-", False),
        (P.MSPortImpl, "loadout", "MS", "MA<-", False), (P.MSPortImpl, "detections", "MS", "MA<-", False),
        (P.MSPortImpl, "command", "MS", "MA->", True), (P.MSPortImpl, "activities", "MS", "MA<-", False),
        (P.MPPortImpl, "mission_plan", "MP", "MA<-", False), (P.MPPortImpl, "route_plans", "MP", "MA<-", False),
        (P.MPPortImpl, "engagement_criteria", "MP", "MA<-", False),
        (P.P2PPortImpl, "send", "P2P", "MA->", True), (P.P2PPortImpl, "inbox", "P2P", "MA<-", False)]:
    _wrap(_c, _n, _p, _d, _a)

_orig_md = P.MDPortImpl.record


def _md(self, name, value):  # noqa: ANN001, ANN202
    with LOCK:
        D["port"][("MD", "MA->", "md.record")] += 1
    return _orig_md(self, name, value)


P.MDPortImpl.record = _md

_orig_open = cli.open_bus


def open_bus(cfg):  # noqa: ANN001, ANN201
    bus = _orig_open(cfg)
    sub0, put0 = bus.subscribe, bus.put

    def subscribe(keyexpr, cb, **kw):  # noqa: ANN001, ANN202
        with LOCK:
            D["subscribe"].append(keyexpr)

        def wrapped(s):  # noqa: ANN001, ANN202
            with LOCK:
                D["rx"][s.key] += 1
            return cb(s)
        return sub0(keyexpr, wrapped, **kw)

    def put(key, payload, encoding):  # noqa: ANN001, ANN202
        with LOCK:
            D["put"][key] += 1
        return put0(key, payload, encoding)

    bus.subscribe, bus.put = subscribe, put
    return bus


cli.open_bus = open_bus


def _loop() -> None:
    while True:
        time.sleep(1.0)
        _dump()


if __name__ == "__main__":
    threading.Thread(target=_loop, daemon=True).start()
    try:
        sys.exit(cli.main(sys.argv[1:]))
    finally:
        _dump()
