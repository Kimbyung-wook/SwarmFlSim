"""LA-CAL 접속 실행기 (IMP-GW-011, PRP-STD-002).

Gateway를 LA-CAL 클라이언트(agra_lacal client.lacal_client.LaCalClient)에 묶는다.
- 1단계: Gateway outbox → client.publish(<prefix>.<iface>, OMS JSON)
- 2단계: client.subscribe(<외부 C2 STD 메시지>, <inbound topic>) → Gateway.handle_external
"""
from __future__ import annotations

import asyncio
import logging
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

    async def stop(self) -> None:
        self.gateway.close()
        self.sender.cancel()
        await self.client.close()


async def start_gateway(bus: Bus, config: GatewayConfig, url: str, *, service_id: str = DEFAULT_SERVICE,
                        inbound_topic: str = "", codec: OmsJsonCodec | None = None) -> Running:
    client = LaCalClient(url, service_id)
    info = await client.connect()
    gw = Gateway(bus, config, codec=codec, sink=client.publish)
    gw.system_uuid = client.system_uuid
    topic = inbound_topic or config.topic("c2")
    for name in gw.import_names():
        await client.subscribe(name, topic, lambda n, obj: gw.handle_external(n, obj))
    gw.start()
    sender = asyncio.create_task(gw.run_sender())
    log.info("gateway connected to %s as %s (server %s); inbound %s on %s", url, service_id,
             info.get("server_id", "?"), gw.import_names(), topic)
    return Running(gw, client, sender)
