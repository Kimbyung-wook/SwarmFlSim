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

from swarm_api.bus import Bus

from .converters import load_converters
from .envelope import RX
from .gateway import Gateway, GatewayConfig, inbound_entries
from .lacal import LaCalClient, OmsJsonCodec
from .mapping import MappingTable
from .retain import LateJoinReplayer, admin_url_for

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

    def on_message(self, name: str, obj: dict) -> None:
        if self._direct and self.gateway is not None:
            self.gateway.handle_incoming(name, obj)
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
            out = self.gateway.handle_incoming(name, obj)
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
