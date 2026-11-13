"""TC-API-005: open_bus 백엔드 선택, Zenoh가 있으면 두 세션 간 송수신 (DEC-026). TC-API-008: 순서 보존 구독 (DEC-083)"""

import threading
import time

import pytest

from swarm_api import BusConfig, InMemoryBus, default_backend, keys, open_bus, protobuf_encoding, zenoh_available
from swarm_api.keys import Iface


def test_memory_backend():
    assert isinstance(open_bus(BusConfig(backend="memory")), InMemoryBus)


def test_unknown_backend():
    with pytest.raises(ValueError):
        open_bus(BusConfig(backend="dds"))


def test_default_backend():
    assert default_backend() == ("zenoh" if zenoh_available() else "memory")


@pytest.mark.skipif(not zenoh_available(), reason="eclipse-zenoh not installed")
def test_zenoh_across_sessions():
    a = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", listen=["tcp/127.0.0.1:17467"],
                           multicast_scouting=False))
    b = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", connect=["tcp/127.0.0.1:17467"],
                           multicast_scouting=False))
    got = []
    done = threading.Event()

    def on_sample(s):
        got.append(s)
        done.set()

    sub = b.subscribe(keys.TX_ALL, on_sample)
    enc = protobuf_encoding("swarm.v1.LinkEnvelope")
    key = keys.tx("uav-001", Iface.P2P, "PeerStatus")
    deadline = time.monotonic() + 5
    while not done.is_set() and time.monotonic() < deadline:
        a.put(key, b"hello", enc)
        done.wait(0.05)
    sub.close()
    a.close()
    b.close()
    assert got and got[0].key == key and got[0].payload == b"hello" and got[0].encoding == enc


def test_memory_backend_accepts_ordered():
    bus = open_bus(BusConfig(backend="memory"))
    got = []
    bus.subscribe("a/*", lambda s: got.append(s.key), ordered=True)
    bus.put("a/1", b"", "")
    assert got == ["a/1"]


@pytest.mark.skipif(not zenoh_available(), reason="eclipse-zenoh not installed")
def test_zenoh_ordered_across_subscriptions():
    """TC-API-008: 다른 키의 ordered 구독 둘은 송신 순서대로 콜백을 받는다 (DEC-083, D-33)"""
    a = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", listen=["tcp/127.0.0.1:17468"],
                           multicast_scouting=False))
    b = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", connect=["tcp/127.0.0.1:17468"],
                           multicast_scouting=False))
    n = 400
    got: list[int] = []
    lock = threading.Lock()
    done = threading.Event()
    ready = threading.Event()

    def on_sample(s):
        if s.key.endswith("ping"):
            ready.set()
            return
        with lock:
            got.append(int.from_bytes(s.payload, "big"))
            if len(got) == n:
                done.set()

    subs = [b.subscribe("qa/order/x/*", on_sample, ordered=True),
            b.subscribe("qa/order/y/*", on_sample, ordered=True)]
    deadline = time.monotonic() + 5
    while not ready.is_set() and time.monotonic() < deadline:
        a.put("qa/order/x/ping", b"", "")
        ready.wait(0.05)
    assert ready.is_set()
    for i in range(n):
        a.put(f"qa/order/{'x' if i % 2 else 'y'}/m", i.to_bytes(4, "big"), "")
    done.wait(10)
    for s in subs:
        s.close()
    a.close()
    b.close()
    assert got == list(range(n))
