"""LA-CAL 접속 실행기 (IMP-GW-011, PRP-STD-002).

Gateway를 LA-CAL 클라이언트(agra_lacal client.lacal_client.LaCalClient)에 묶는다.
- 1단계: Gateway outbox → client.publish(<prefix>.<iface>, OMS JSON)
- 2단계: client.subscribe(<외부 C2 STD 메시지>, <inbound topic>) → Gateway.handle_external

준비 전 구간(O-13): LA-CAL 접속(INIT) 뒤 XSD 적재와 SUB가 끝날 때까지는 외부 명령을 받는 구독이 없다.
그동안 외부가 PUB한 MA_TaskCommand는 서버가 +OK로 답하지만 받는 쪽이 없어 사라진다.
각 단계 완료 시점(기동 기준 경과 s)을 INFO 로그로 남기고, 마지막에 "ready" 한 줄을 남긴다.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from swarm_api.bus import Bus

from .gateway import Gateway, GatewayConfig
from .lacal import LaCalClient, OmsJsonCodec

log = logging.getLogger("swarm_gateway")

DEFAULT_SERVICE = "swarm_gateway"


@dataclass
class Running:
    gateway: Gateway
    client: LaCalClient
    sender: asyncio.Task
    ready_after_s: float = 0.0   # start_gateway 호출부터 외부 명령 구독 완료까지 (O-13)

    async def stop(self) -> None:
        self.gateway.close()
        self.sender.cancel()
        await self.client.close()


async def start_gateway(bus: Bus, config: GatewayConfig, url: str, *, service_id: str = DEFAULT_SERVICE,
                        inbound_topic: str = "", codec: OmsJsonCodec | None = None) -> Running:
    t0 = time.monotonic()
    client = LaCalClient(url, service_id)
    info = await client.connect()
    log.info("gateway: LA-CAL connected to %s as %s (server %s) at +%.2f s; not ready yet "
             "(external commands published now are not received)", url, service_id,
             info.get("server_id", "?"), time.monotonic() - t0)
    gw = Gateway(bus, config, codec=codec, sink=client.publish)
    log.info("gateway: XSD loaded, mapping built at +%.2f s", time.monotonic() - t0)
    gw.system_uuid = client.system_uuid
    topic = inbound_topic or config.topic("c2")
    for name in gw.import_names():
        await client.subscribe(name, topic, lambda n, obj: gw.handle_external(n, obj))
        log.info("gateway: LA-CAL SUB %s@%s done at +%.2f s", name, topic, time.monotonic() - t0)
    gw.start()
    sender = asyncio.create_task(gw.run_sender())
    ready = time.monotonic() - t0
    log.info("gateway: ready at +%.2f s: inbound %s on %s, bus %s", ready, gw.import_names(), topic,
             "swarm/%s/rx/**" % config.gcs)
    return Running(gw, client, sender, ready)
