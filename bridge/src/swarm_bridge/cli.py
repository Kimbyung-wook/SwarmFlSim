"""IMP-UI-022: 실행 파일 swarm-bridge.

uv run swarm-bridge [--host 127.0.0.1] [--port 8765] [버스 옵션]
버스 옵션은 C++ kBusUsage와 같은 이름이다 (DEC-026): --bus, --zenoh-config, --zenoh-mode, --connect, --listen, --no-multicast
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence

from swarm_api import BusConfig, open_bus

from .server import DEFAULT_PORT, WS_PATH, BridgeOptions, BridgeServer


def add_bus_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("버스 (DEC-026)")
    g.add_argument("--bus", default="", help="zenoh | memory (기본: Zenoh가 있으면 zenoh)")
    g.add_argument("--zenoh-config", default="", help="Zenoh json5 설정 파일")
    g.add_argument("--zenoh-mode", default="", help="peer | client | router")
    g.add_argument("--connect", action="append", default=[], help="연결할 엔드포인트 (반복 가능)")
    g.add_argument("--listen", action="append", default=[], help="대기할 엔드포인트 (반복 가능)")
    g.add_argument("--no-multicast", action="store_true", help="멀티캐스트 스카우팅을 끈다")


def bus_config(a: argparse.Namespace) -> BusConfig:
    return BusConfig(
        backend=a.bus,
        zenoh_config_file=a.zenoh_config,
        zenoh_mode=a.zenoh_mode,
        connect=a.connect,
        listen=a.listen,
        multicast_scouting=not a.no_multicast,
    )


async def _run(a: argparse.Namespace) -> None:
    bus = open_bus(bus_config(a))
    server = BridgeServer(bus, BridgeOptions(queue_limit=a.queue_limit))
    try:
        port = await server.start(a.host, a.port)
        logging.info("swarm-bridge: ws://%s:%d%s (bus=%s)", a.host, port, WS_PATH, a.bus or "default")
        await server.serve_forever()
    finally:
        await server.close()
        bus.close()


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="swarm-bridge", description="브라우저 ⇄ 버스 WebSocket 브리지 (프로토콜 v1, DEC-027)")
    p.add_argument("--host", default="127.0.0.1", help="대기 주소 (다른 PC의 UI를 받으려면 0.0.0.0)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--queue-limit", type=int, default=BridgeOptions.queue_limit, help="클라이언트별 송신 대기 프레임 수")
    p.add_argument("-v", "--verbose", action="store_true")
    add_bus_args(p)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(_run(a))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
