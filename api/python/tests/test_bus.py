"""TC-API-002: InMemoryBus 발행·구독"""

import pytest

from swarm_api import InMemoryBus, keys, protobuf_encoding
from swarm_api.keys import Iface


def test_put_reaches_matching_subscribers_only():
    bus = InMemoryBus()
    got_link, got_uav2 = [], []
    bus.subscribe(keys.TX_ALL, got_link.append)
    bus.subscribe(keys.rx_all("uav-002"), got_uav2.append)

    enc = protobuf_encoding("swarm.v1.LinkEnvelope")
    bus.put(keys.tx("uav-001", Iface.P2P, "PeerStatus"), b"a", enc)
    bus.put(keys.rx("uav-002", Iface.P2P, "PeerStatus"), b"b", enc)

    assert [s.payload for s in got_link] == [b"a"]
    assert [s.payload for s in got_uav2] == [b"b"]
    assert got_uav2[0].encoding == enc


def test_close_subscription():
    bus = InMemoryBus()
    got = []
    sub = bus.subscribe("truth/**", got.append)
    bus.put(keys.TRUTH_STATE, b"1", "")
    sub.close()
    bus.put(keys.TRUTH_STATE, b"2", "")
    assert [s.payload for s in got] == [b"1"]


def test_wildcard_put_rejected():
    with pytest.raises(ValueError):
        InMemoryBus().put("truth/*", b"", "")
