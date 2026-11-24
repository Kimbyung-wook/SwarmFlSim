"""LA-CAL 접속 실행기 (IMP-GW-011, PRP-STD-002).

Gateway를 LA-CAL 클라이언트(agra_lacal client.lacal_client.LaCalClient)에 묶는다.
- 1단계: Gateway outbox → client.publish(<prefix>.<iface>, OMS JSON)
- 2단계: client.subscribe(<외부 C2·MP STD 메시지>, <토픽>) → Gateway.handle_external
  C2는 <inbound topic>(기본 <prefix>.c2), MP는 <prefix>.mp

준비 전 구간(O-13, IMP-GW-034): LA-CAL에 접속(INIT)하자마자 외부 명령을 SUB한다. 구독은 XSD가 없어도
descriptor와 변환기로 정한다. XSD 적재·매핑 생성(수 초)은 그 뒤 별도 스레드에서 하고, 그동안 받은 외부 메시지는
`PreReadyInbox`에 받은 순서대로 둔다. Gateway가 준비되면 `settle_s` 동안 버스(시나리오·수신 보고)로 알려진 기체를
모은 뒤 쌓인 것을 순서대로 처리한다. 처리 전에 온 메시지도 순서를 지키려고 같은 줄 뒤에 붙인다.
남는 손실은 SUB가 걸리기 전(프로세스 기동·접속, 약 1 s)과 Gateway가 없는 동안이다. OWP에는 보관(durable) 메시지가
없어 Gateway가 받을 수 없고, 외부 C2의 재송신 책임이다(README).
각 단계 완료 시점(기동 기준 경과 s)을 INFO 로그로 남기고, 마지막에 "ready" 한 줄을 남긴다.

늦게 붙은 외부 구독자(DEC-089): CAL Server 관리 포트의 `/graph/events`를 보고 새 구독에 변화 보고 마지막 값을 다시 PUB한다.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from swarm_api.bus import Bus

from .converters import load_converters
from .envelope import RX
from .gateway import Gateway, GatewayConfig, inbound_entries
from .lacal import LaCalClient, OmsJsonCodec
from .mapping import MappingTable
from .retain import LateJoinReplayer, admin_url_for
from .stomp import StompClient

log = logging.getLogger("swarm_gateway")

DEFAULT_SERVICE = "swarm_gateway"
DEFAULT_SETTLE_S = 1.5      # 준비 뒤 쌓인 외부 메시지를 처리하기 전 알려진 기체를 모으는 시간 (D-35)
DEFAULT_INBOX_LIMIT = 256


@dataclass
class PreReadyInbox:
    """준비 전 받은 외부 메시지 (IMP-GW-034, O-13). 이벤트 루프 스레드에서만 쓴다"""
    limit: int = DEFAULT_INBOX_LIMIT
    gateway: Gateway | None = None
    queued: deque = field(default_factory=deque)
    held: int = 0            # 준비 전·처리 전에 쌓은 수
    dropped: int = 0         # 상한을 넘어 버린 오래된 것
    flushed: int = 0
    _direct: bool = False
    handle: Callable[[str, object], object] | None = None   # 비우면 gateway.handle_incoming (STOMP는 XML 본문 처리)

    def _call(self, name: str, obj):
        return (self.handle or self.gateway.handle_incoming)(name, obj)

    def on_message(self, name: str, obj) -> None:
        if self._direct and self.gateway is not None:
            self._call(name, obj)
            return
        self.held += 1
        self.queued.append((time.monotonic(), name, obj))
        while len(self.queued) > self.limit:
            self.queued.popleft()
            self.dropped += 1

    def flush(self) -> list:
        """쌓인 것을 받은 순서대로 처리하고 바로 처리로 바꾼다"""
        assert self.gateway is not None
        outs = []
        while self.queued:
            t, name, obj = self.queued.popleft()
            out = self._call(name, obj)
            outs.append(out)
            self.flushed += 1
            log.info("gateway: pre-ready %s held %.2f s -> %s%s", name, time.monotonic() - t, out.status,
                     f" ({out.reason})" if out.reason else "")
        self._direct = True
        if self.dropped:
            self.gateway.counters["pre_ready_dropped"] += self.dropped
            log.warning("gateway: %d pre-ready external messages dropped (limit %d)", self.dropped, self.limit)
        self.gateway.counters["pre_ready_flushed"] += len(outs)
        return outs


@dataclass
class Running:
    gateway: Gateway
    client: LaCalClient
    sender: asyncio.Task
    ready_after_s: float = 0.0   # start_gateway 호출부터 준비(쌓인 외부 메시지 처리 시작)까지 (O-13)
    replayer: LateJoinReplayer | None = None   # 늦게 붙은 구독자에게 마지막 값 전달 (DEC-089)
    inbox: PreReadyInbox | None = None         # 준비 전 받은 외부 메시지 (O-13)
    subscribed_after_s: float = 0.0            # 외부 명령 구독 완료까지 (이때부터 외부 PUB를 잃지 않는다)
    flusher: asyncio.Task | None = None

    async def stop(self) -> None:
        if self.flusher is not None:
            self.flusher.cancel()
        if self.replayer is not None:
            await self.replayer.stop()
        self.gateway.close()
        self.sender.cancel()
        await self.client.close()


async def start_gateway(bus: Bus, config: GatewayConfig, url: str, *, service_id: str = DEFAULT_SERVICE,
                        inbound_topic: str = "", codec: OmsJsonCodec | None = None,
                        admin_url: str | None = "", settle_s: float = DEFAULT_SETTLE_S,
                        inbox_limit: int = DEFAULT_INBOX_LIMIT) -> Running:
    """admin_url: CAL Server 관리 주소(그래프 이벤트). ""이면 OWP 주소의 호스트와 기본 관리 포트, None이면 쓰지 않는다.
    settle_s: 준비 뒤 쌓인 외부 메시지를 처리하기 전 기다리는 시간(알려진 기체 모으기). 0이면 바로 처리한다"""
    t0 = time.monotonic()
    client = LaCalClient(url, service_id)
    info = await client.connect()
    log.info("gateway: LA-CAL connected to %s as %s (server %s) at +%.2f s", url, service_id,
             info.get("server_id", "?"), time.monotonic() - t0)
    # 1) 외부 명령 구독을 먼저 건다. 받은 것은 준비될 때까지 쌓는다 (O-13)
    inbox = PreReadyInbox(limit=inbox_limit)
    subscribed = []
    wanted: dict[str, None] = {}
    for entry in inbound_entries(MappingTable.from_descriptors(), load_converters()):
        topic = (inbound_topic or config.topic("c2")) if entry.iface == "c2" else config.topic(entry.iface)
        wanted[f"{RX if config.envelope else entry.uci_name}@{topic}"] = None   # 봉투면 토픽마다 MA_RxDataPayload (DEC-111)
    for flow in wanted:
        name, topic = flow.split("@")
        await client.subscribe(name, topic, inbox.on_message)
        subscribed.append(flow)
        log.info("gateway: LA-CAL SUB %s@%s done at +%.2f s", name, topic, time.monotonic() - t0)
    sub_s = time.monotonic() - t0
    log.info("gateway: receiving external commands from +%.2f s; held until ready", sub_s)
    # 2) XSD 적재·매핑 생성. 이벤트 루프를 막지 않게 스레드에서 한다 (그동안 받은 메시지는 inbox로)
    gw = await asyncio.to_thread(Gateway, bus, config, codec=codec, sink=client.publish)
    log.info("gateway: XSD loaded, mapping built at +%.2f s", time.monotonic() - t0)
    importable = {e.uci_name for e in gw.import_entries()} | ({RX} if config.envelope else set())
    missing = [s for s in subscribed if s.split("@")[0] not in importable]
    if missing:   # XSD에 없는 수신 메시지: handle_external이 거부한다
        log.warning("gateway: subscribed but not importable (no XSD element): %s", sorted(missing))
    gw.system_uuid = client.system_uuid
    inbox.gateway = gw
    gw.start()
    sender = asyncio.create_task(gw.run_sender())
    replayer = None
    if admin_url is not None:
        replayer = LateJoinReplayer(admin_url or admin_url_for(url), gw.retained, gw.replay)
        replayer.start()
    ready = time.monotonic() - t0
    log.info("gateway: ready at +%.2f s: inbound %s, bus %s, publisher %s; %d external messages held, "
             "processed after %.1f s settle", ready, subscribed, "swarm/%s/rx/**" % config.gcs, config.participant,
             len(inbox.queued), settle_s)

    async def flush_later():
        if settle_s > 0:
            await asyncio.sleep(settle_s)   # 시나리오·수신 보고로 알려진 기체를 모은다 (D-35)
        inbox.flush()

    flusher = asyncio.create_task(flush_later())
    return Running(gw, client, sender, ready, replayer, inbox, sub_s, flusher)


# ---------------------------------------------------------------------- STOMP (DEC-110)
SIGNAL_START = "/topic/TestHarness_StartSignal"
SIGNAL_STOP = "/topic/TestHarness_StopSignal"
SIGNAL_ACK = "/topic/TestHarness_SignalAck"


def stomp_topic(uci_name: str) -> str:
    """하네스 토픽 규칙: `/topic/<UCI 메시지 이름>`"""
    return f"/topic/{uci_name}"


async def start_stomp_gateway(bus: Bus, config: GatewayConfig, host: str, port: int, *, system_uuid: str,
                              login: str = "", passcode: str = "", codec: OmsJsonCodec | None = None,
                              settle_s: float = DEFAULT_SETTLE_S, inbox_limit: int = DEFAULT_INBOX_LIMIT,
                              signals: bool = True) -> Running:
    """A-GRA 시험 하네스 버스(ActiveMQ STOMP)에 붙는다 (IMP-GW-037, DEC-110). LA-CAL 실행기와 같은 Gateway·변환기를 쓴다.

    - 받기: `/topic/MA_RxDataPayload`(봉투, DEC-111) 또는 봉투를 끄면 `/topic/<수신 UCI 이름>`. 본문은 UCI XML이다.
    - 내기: `/topic/<UCI 이름>`(봉투면 `/topic/MA_TxDataPayloadCommand`)에 XSD를 통과한 UCI XML.
    - 시작·정지 신호(`TestHarness_StartSignal`·`StopSignal`)에 `TestHarness_SignalAck`로 응답한다(`signals`).
    - 하네스 토픽은 비지속이라 하네스보다 먼저 띄워 구독해 둔다. 구독은 XSD 적재 전에 걸고, 그동안 온 것은 쌓는다(O-13과 같다).
    system_uuid: 우리 플랫폼 UUID(MessageHeader.SystemID, 봉투 목적지 대조)."""
    t0 = time.monotonic()
    client = StompClient(host, port, login=login, passcode=passcode)
    info = await client.connect()
    log.info("gateway: STOMP connected to %s:%d (server %s) at +%.2f s", host, port, info.get("server", "?"),
             time.monotonic() - t0)
    inbox = PreReadyInbox(limit=inbox_limit)
    names = [RX] if config.envelope else [e.uci_name for e in inbound_entries(MappingTable.from_descriptors(),
                                                                              load_converters())]
    dests = [stomp_topic(n) for n in dict.fromkeys(names)]
    for d in dests:
        await client.subscribe(d, lambda dest, body, hdr: inbox.on_message(dest, body))
        log.info("gateway: STOMP SUBSCRIBE %s done at +%.2f s", d, time.monotonic() - t0)
    # 신호는 쌓지 않고 Gateway가 생기는 즉시 응답한다(정착 시간을 기다리지 않는다). 그 전에 온 것만 잠깐 둔다
    early_signals: list[tuple[str, bytes]] = []
    state: dict = {}

    async def ack(dest: str, body: bytes) -> None:
        g = state["gw"]
        await client.send(SIGNAL_ACK, g.to_xml(g.signal_ack(body, dest == SIGNAL_START)))

    async def on_signal(dest: str, body: bytes, hdr: dict) -> None:
        if "gw" in state:
            await ack(dest, body)
        else:
            early_signals.append((dest, body))

    if signals:
        for d in (SIGNAL_START, SIGNAL_STOP):
            await client.subscribe(d, on_signal)
            dests.append(d)
    sub_s = time.monotonic() - t0

    async def sink(topic: str, obj: dict) -> None:
        name = next(iter(obj))
        await client.send(stomp_topic(name), gw.to_xml(obj))

    gw = await asyncio.to_thread(Gateway, bus, config, codec=codec, sink=sink)
    log.info("gateway: XSD loaded, mapping built at +%.2f s", time.monotonic() - t0)
    gw.system_uuid = system_uuid
    inbox.gateway, inbox.handle = gw, (lambda dest, body: gw.handle_xml(body))
    state["gw"] = gw
    for dest, body in early_signals:
        await ack(dest, body)
    gw.start()
    sender = asyncio.create_task(gw.run_sender())
    ready = time.monotonic() - t0
    log.info("gateway: ready at +%.2f s: STOMP %s, system %s, schema %s, envelope %s, excluded %s; %d held",
             ready, dests, system_uuid, config.schema_version, "on" if config.envelope else "off",
             list(config.exclude_messages), len(inbox.queued))

    async def flush_later():
        if settle_s > 0:
            await asyncio.sleep(settle_s)
        inbox.flush()

    flusher = asyncio.create_task(flush_later())
    return Running(gw, client, sender, ready, None, inbox, sub_s, flusher)  # type: ignore[arg-type]
