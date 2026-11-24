"""uv run python -m swarm_gateway --gcs gcs-01 --lacal ws://127.0.0.1:8765 (IMP-GW-012)"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys
import uuid

from swarm_api.bus import BusConfig, open_bus, zenoh_available

from .gateway import DEFAULT_PARTICIPANT, GatewayConfig
from .runner import DEFAULT_SERVICE, start_gateway


EXIT_NO_BACKEND = 1

NO_ZENOH_MESSAGE = (
    "오류: Zenoh 백엔드를 쓸 수 없습니다(eclipse-zenoh 미설치). 시뮬레이터 메시지를 받으려면 다음으로 설치하세요.\n"
    "  cd gateway && uv sync --extra zenoh\n"
    "시뮬레이터 없이 확인만 하려면 --bus memory를 명시하세요(시뮬레이터 메시지는 오지 않습니다)."
)


def _utc(text: str) -> dt.datetime:
    try:
        t = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"ISO 8601 UTC 시각이 아니다: {text}") from exc
    if t.tzinfo is None:
        raise argparse.ArgumentTypeError(f"시간대가 없다(Z 또는 +00:00을 붙인다): {text}")
    return t.astimezone(dt.timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m swarm_gateway",
                                 description="A-GRA Gateway: swarm/<gcs>/rx/** <-> LA-CAL (DEC-068)")
    ap.add_argument("--gcs", required=True, help="GCS 엔티티 ID (예: gcs-01)")
    ap.add_argument("--lacal", default="ws://127.0.0.1:8765", help="CAL Server OWP 주소")
    ap.add_argument("--lacal-admin", default="",
                    help="CAL Server 관리 주소. 새 외부 구독에 변화 보고 마지막 값을 다시 보낸다 (DEC-089). "
                         "기본은 --lacal 호스트의 8766, none이면 끈다")
    ap.add_argument("--sim-epoch", type=_utc, default=None,
                    help="모의 시각 0의 UTC 명시 재정의 (예: 2026-01-01T00:00:00Z, 재현 시험용). UCI 시각 = 이 값 + 모의 시각. "
                         "비우면 시나리오의 run.epoch_utc_us, 시나리오 전에는 첫 메시지 기준 (DEC-098)")
    ap.add_argument("--envelope", choices=("on", "off"), default="on",
                    help="외부 교환 봉투 (DEC-111): on이면 MA_TxDataPayloadCommand로 보내고 MA_RxDataPayload를 받는다. "
                         "off는 내부 UCI 메시지를 그대로 주고받는다(9차까지의 동작, 기본 %(default)s)")
    ap.add_argument("--envelope-dest", action="append", default=[], metavar="UUID", type=lambda v: str(uuid.UUID(v)),
                    help="송신 봉투의 SpecificDestinationID (외부 시스템 UUID, 여러 번 가능). 비우면 넣지 않는다")
    ap.add_argument("--scenario-query-attempts", type=int, default=5,
                    help="시작 때 sim/ctrl/scenario 조회 횟수. 구독으로 먼저 받으면 멈춘다. 0이면 조회하지 않는다 (DEC-109)")
    ap.add_argument("--scenario-query-interval", type=float, default=0.5,
                    help="응답이 없을 때 다음 조회까지 s (기본 %(default)s)")
    ap.add_argument("--scenario-query-timeout", type=float, default=1.0,
                    help="조회 한 번의 응답 대기 s (기본 %(default)s)")
    ap.add_argument("--participant", default=DEFAULT_PARTICIPANT,
                    help="발행 참여자 ID. LinkEnvelope.publisher에 싣는다 (기본 %(default)s, DEC-077)")
    ap.add_argument("--service", default=DEFAULT_SERVICE, help="CAL Server 설정의 service_id")
    ap.add_argument("--topic-prefix", default="swarm", help="LA-CAL 토픽 접두어 (<prefix>.<iface>)")
    ap.add_argument("--inbound-topic", default="", help="외부 C2 수신 토픽 (기본 <prefix>.c2, MP는 <prefix>.mp 고정)")
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
    running = await start_gateway(bus, GatewayConfig(gcs=args.gcs, participant=args.participant, topic_prefix=args.topic_prefix,
                                                     sim_epoch=args.sim_epoch, envelope=args.envelope == "on",
                                                     envelope_destinations=tuple(args.envelope_dest),
                                                     scenario_query_attempts=args.scenario_query_attempts,
                                                     scenario_query_interval_s=args.scenario_query_interval,
                                                     scenario_query_timeout_s=args.scenario_query_timeout), args.lacal,
                                  service_id=args.service, inbound_topic=args.inbound_topic,
                                  admin_url=None if args.lacal_admin.lower() == "none" else args.lacal_admin)
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
