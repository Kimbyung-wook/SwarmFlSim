"""uv run python -m swarm_gateway --gcs gcs-01 --lacal ws://127.0.0.1:8765 (IMP-GW-012)"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from swarm_api.bus import BusConfig, open_bus, zenoh_available

from .gateway import GatewayConfig
from .runner import DEFAULT_SERVICE, start_gateway


EXIT_NO_BACKEND = 1

NO_ZENOH_MESSAGE = (
    "오류: Zenoh 백엔드를 쓸 수 없습니다(eclipse-zenoh 미설치). 시뮬레이터 메시지를 받으려면 다음으로 설치하세요.\n"
    "  cd gateway && uv sync --extra zenoh\n"
    "시뮬레이터 없이 확인만 하려면 --bus memory를 명시하세요(시뮬레이터 메시지는 오지 않습니다)."
)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m swarm_gateway",
                                 description="A-GRA Gateway: swarm/<gcs>/rx/** <-> LA-CAL (DEC-068)")
    ap.add_argument("--gcs", required=True, help="GCS 엔티티 ID (예: gcs-01)")
    ap.add_argument("--lacal", default="ws://127.0.0.1:8765", help="CAL Server OWP 주소")
    ap.add_argument("--service", default=DEFAULT_SERVICE, help="CAL Server 설정의 service_id")
    ap.add_argument("--topic-prefix", default="swarm", help="LA-CAL 토픽 접두어 (<prefix>.<iface>)")
    ap.add_argument("--inbound-topic", default="", help="외부 C2 수신 토픽 (기본 <prefix>.c2)")
    ap.add_argument("--bus", choices=("zenoh", "memory"), default="zenoh",
                    help="버스 백엔드 (기본 zenoh). memory는 프로세스 안 버스라 시뮬레이터 메시지가 오지 않는다")
    ap.add_argument("--zenoh-config", default="")
    ap.add_argument("--zenoh-mode", default="")
    ap.add_argument("--connect", action="append", default=[], help="Zenoh 접속 endpoint (반복 가능)")
    ap.add_argument("--listen", action="append", default=[])
    ap.add_argument("--no-multicast", action="store_true",
                    help="Zenoh 멀티캐스트 스카우팅을 끈다 (같은 PC의 다른 버스와 섞이지 않게, --connect와 함께 쓴다)")
    ap.add_argument("--stats-s", type=float, default=10.0, help="카운터 로그 주기(벽시계 s), 0이면 끔")
    ap.add_argument("--log", default="INFO")
    return ap


async def _run(args) -> None:
    bus = open_bus(BusConfig(backend=args.bus, zenoh_config_file=args.zenoh_config, zenoh_mode=args.zenoh_mode,
                             connect=args.connect, listen=args.listen,
                             multicast_scouting=not args.no_multicast))
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


def _tolerate_console_encoding() -> None:
    """cp949 같은 콘솔에서 표현할 수 없는 문자가 있어도 인코딩 오류로 끝나지 않게 한다 (IMP-GW-019)"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> None:
    _tolerate_console_encoding()
    args = build_parser().parse_args(argv)
    if args.bus == "zenoh" and not zenoh_available():  # 조용히 인메모리 버스로 뜨지 않는다 (IMP-GW-018)
        print(NO_ZENOH_MESSAGE, file=sys.stderr)
        raise SystemExit(EXIT_NO_BACKEND)
    logging.basicConfig(level=args.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.bus == "memory":
        logging.getLogger("swarm_gateway").warning("in-memory bus: no simulator traffic will arrive (--bus memory)")
    if sys.platform == "win32":  # agra_lacal 서버와 같은 이유로 Selector 루프를 쓴다
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
