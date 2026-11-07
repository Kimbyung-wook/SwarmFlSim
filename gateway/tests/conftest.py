import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from swarm_api import InMemoryBus  # noqa: E402
from swarm_gateway.gateway import Gateway, GatewayConfig  # noqa: E402
from swarm_gateway.lacal import load_codec  # noqa: E402

from samples import GCS  # noqa: E402

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class RecordingBus(InMemoryBus):
    """구독 키 표현식과 발행 키를 기록한다 (TC-GW-009)"""

    def __init__(self) -> None:
        super().__init__()
        self.subscribed: list[str] = []
        self.published: list[str] = []

    def subscribe(self, keyexpr, callback):
        self.subscribed.append(keyexpr)
        return super().subscribe(keyexpr, callback)

    def put(self, key, payload, encoding):
        self.published.append(key)
        super().put(key, payload, encoding)


@pytest.fixture(scope="session")
def codec():
    return load_codec()


@pytest.fixture
def bus():
    return RecordingBus()


@pytest.fixture
def sent():
    return []


@pytest.fixture
def gateway(bus, codec, sent):
    gw = Gateway(bus, GatewayConfig(GCS), codec=codec, sink=lambda topic, obj: sent.append((topic, obj)))
    gw.start()
    yield gw
    gw.close()
