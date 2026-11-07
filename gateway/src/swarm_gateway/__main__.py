"""uv run python -m swarm_gateway --gcs gcs-01 --lacal ws://127.0.0.1:8765 (IMP-GW-012)"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from swarm_api.bus import BusConfig, open_bus

from .gateway import GatewayConfig
from .runner import DEFAULT_SERVICE, start_gateway


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m swarm_gateway",
                                 description="A-GRA Gateway: swarm/<gcs>/rx/** ⇄ LA-CAL (DEC-068)")
    ap.add_argument("--gcs", required=True, help="GCS 엔티티 ID (예: gcs-01)")
    ap.add_argument("--lacal", default="ws://127.0.0.1:8765", help="CAL Server OWP 주소")
    ap.add_argument("--service", default=DEFAULT_SERVICE, help="CAL Server 설정의 service_id")
    ap.add_argument("--topic-prefix", default="swarm", help="LA-CAL 토픽 접두어 (<prefix>.<iface>)")
    ap.add_argument("--inbound-topic", default="", help="외부 C2 수신 토픽 (기본 <prefix>.c2)")
    ap.add_argument("--bus", default="", help="zenoh | memory (기본: 설치돼 있으면 zenoh)")
    ap.add_argument("--zenoh-config", default="")
    ap.add_argument("--zenoh-mode", default="")
    ap.add_argument("--connect", action="append", default=[], help="Zenoh 접속 endpoint (반복 가능)")
    ap.add_argument("--listen", action="append", default=[])
    ap.add_argument("--stats-s", type=float, default=10.0, help="카운터 로그 주기(벽시계 s), 0이면 끔")
    ap.add_argument("--log", default="INFO")
    return ap


async def _run(args) -> None:
    bus = open_bus(BusConfig(backend=args.bus, zenoh_config_file=args.zenoh_config, zenoh_mode=args.zenoh_mode,
                             connect=args.connect, listen=args.listen))
    running = await start_gateway(bus, GatewayConfig(gcs=args.gcs, topic_prefix=args.topic_prefix), args.lacal,
                                  service_id=args.service, inbound_topic=args.inbound_topic)
    try:
        while True:
            await asyncio.sleep(args.stats_s or 3600)
            if args.stats_s:
                logging.getLogger("swarm_gateway").info("counters %s", json.dumps(dict(running.gateway.counters)))
    finally:
        await running.stop()
        bus.close()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.platform == "win32":  # agra_lacal 서버와 같은 이유로 Selector 루프를 쓴다
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
