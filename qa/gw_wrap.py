"""QA 15차 Gateway 실행 래퍼 (TC-QA-069~073). gateway/.venv의 python으로 띄운다.

실제 진입점 `swarm_gateway.__main__.main()`을 그대로 부르되, 그 모듈이 쓰는 open_bus·start_gateway만 감싸서
- Gateway가 연 구독 키 표현식과 발행 키(수),
- 구독 콜백으로 실제 들어온 표본 키의 접두어(수),
- Gateway 카운터와 거부 기록(최근 20건)
을 GW_PROBE_OUT 경로에 0.5 s마다 JSON으로 쓴다. Gateway 코드는 바꾸지 않는다.

GW_PROBE_OUT=<file> gateway/.venv/Scripts/python.exe qa/gw_wrap.py --gcs gcs-01 --lacal ws://... --connect tcp/...
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

import swarm_gateway.__main__ as M

OUT = Path(os.environ.get("GW_PROBE_OUT", "gw_probe.json"))
P: dict = {"subscribe": [], "put": Counter(), "rx_prefix": Counter(), "rx_keys": Counter(), "counters": {},
           "rejections": [], "started": time.time(), "connected": False}


def _prefix(key: str) -> str:
    parts = key.split("/")
    return "/".join(parts[:3]) if parts[0] == "swarm" else parts[0]


def _dump() -> None:
    d = {**P, "put": dict(P["put"]), "rx_prefix": dict(P["rx_prefix"]), "rx_keys": dict(P["rx_keys"]),
         "t": time.time()}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, OUT)


_orig_open = M.open_bus


def open_bus(cfg):  # noqa: ANN001, ANN201
    bus = _orig_open(cfg)
    sub0, put0 = bus.subscribe, bus.put

    def subscribe(keyexpr, cb):  # noqa: ANN001, ANN202
        P["subscribe"].append(keyexpr)

        def wrapped(s):  # noqa: ANN001, ANN202
            P["rx_prefix"][_prefix(s.key)] += 1
            P["rx_keys"]["/".join(s.key.split("/")[3:])] += 1
            return cb(s)
        return sub0(keyexpr, wrapped)

    def put(key, payload, encoding):  # noqa: ANN001, ANN202
        P["put"][key] += 1
        return put0(key, payload, encoding)

    bus.subscribe, bus.put = subscribe, put
    return bus


_orig_start = M.start_gateway


async def start_gateway(*a, **k):  # noqa: ANN002, ANN003, ANN201
    running = await _orig_start(*a, **k)
    P["connected"] = True

    async def dumper() -> None:
        while True:
            gw = running.gateway
            P["counters"] = dict(gw.counters)
            P["rejections"] = [f"{r.status}:{getattr(r, 'uci_name', '') or getattr(r, 'proto', '')}:{getattr(r, 'reason', '')}"[:240]
                               for r in list(gw.rejections)[-40:]]
            _dump()
            await asyncio.sleep(0.5)
    asyncio.create_task(dumper())
    return running


M.open_bus = open_bus
M.start_gateway = start_gateway

if __name__ == "__main__":
    _dump()
    M.main()
