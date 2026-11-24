"""TC-API-005: open_bus 백엔드 선택, Zenoh가 있으면 두 세션 간 송수신 (DEC-026). TC-API-008: 순서 보존 구독 (DEC-083)"""

import threading
import time

import pytest

from swarm_api import BusConfig, InMemoryBus, Sample, default_backend, keys, open_bus, protobuf_encoding, zenoh_available
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


@pytest.mark.skipif(not zenoh_available(), reason="eclipse-zenoh not installed")
def test_zenoh_declared_publishers_keep_order_and_encoding():
    """TC-API-011: 선언한 발행자로 보내도 키·페이로드·encoding이 같고, 키 사이 송신 순서가 지켜지며,
    상한을 넘는 키는 세션 put으로 보낸다. close는 발행자를 정리한다 (OPN-077(B), DEC-043, DEC-083)"""
    from swarm_api import bus as bus_mod

    a = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", listen=["tcp/127.0.0.1:17469"],
                           multicast_scouting=False))
    b = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", connect=["tcp/127.0.0.1:17469"],
                           multicast_scouting=False))
    got: list = []
    lock = threading.Lock()
    ready = threading.Event()

    def on_sample(s):
        if s.key.endswith("ping"):
            ready.set()
            return
        with lock:
            got.append(s)

    sub = b.subscribe("swarm/**", on_sample, ordered=True)
    deadline = time.monotonic() + 5
    while not ready.is_set() and time.monotonic() < deadline:
        a.put("swarm/ping", b"", "")
        ready.wait(0.05)
    assert ready.is_set()
    enc = protobuf_encoding("swarm.v1.LinkEnvelope")
    keys_ = [keys.tx(f"uav-{i:03d}", Iface.MS, "StrikeActivity") for i in range(1, 6)]
    n = 300
    old_cap = bus_mod.MAX_DECLARED_PUBLISHERS
    bus_mod.MAX_DECLARED_PUBLISHERS = 4                     # 다섯째 키는 세션 put
    try:
        for i in range(n):
            a.put(keys_[i % 5], i.to_bytes(4, "big"), enc)
    finally:
        bus_mod.MAX_DECLARED_PUBLISHERS = old_cap
    deadline = time.monotonic() + 10
    while len(got) < n and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(a._publishers) == 4
    sub.close()
    a.close()
    b.close()
    assert a._publishers == {}
    assert [int.from_bytes(s.payload, "big") for s in got] == list(range(n))
    assert all(s.key == keys_[i % 5] and s.encoding == enc for i, s in enumerate(got))


def test_memory_serve_get():
    """TC-API-012: memory 조회. 와일드카드 조회, 응답자 없음, 해제 뒤 빈 목록 (DEC-109)"""
    bus = InMemoryBus()
    enc = protobuf_encoding("swarm.v1.Scenario")
    srv = bus.serve(keys.SIM_CTRL_SCENARIO, lambda _k: [Sample(keys.SIM_CTRL_SCENARIO, b"scn", enc)])
    assert bus.get(keys.SIM_CTRL_SCENARIO) == [Sample(keys.SIM_CTRL_SCENARIO, b"scn", enc)]
    assert len(bus.get("sim/ctrl/**")) == 1
    assert bus.get("truth/state") == []
    srv.close()
    assert bus.get(keys.SIM_CTRL_SCENARIO) == []


@pytest.mark.skipif(not zenoh_available(), reason="eclipse-zenoh not installed")
def test_zenoh_serve_get():
    """TC-API-012: Zenoh 조회. 다른 세션·같은 세션 응답, 인코딩 보존, 해제 뒤 빈 목록 (DEC-109)"""
    a = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", listen=["tcp/127.0.0.1:17470"],
                           multicast_scouting=False))
    b = open_bus(BusConfig(backend="zenoh", zenoh_mode="peer", connect=["tcp/127.0.0.1:17470"],
                           multicast_scouting=False))
    try:
        enc = protobuf_encoding("swarm.v1.Scenario")
        srv = a.serve(keys.SIM_CTRL_SCENARIO, lambda _k: [Sample(keys.SIM_CTRL_SCENARIO, b"scn", enc)])
        got: list[Sample] = []
        end = time.monotonic() + 5
        while not got and time.monotonic() < end:
            got = b.get(keys.SIM_CTRL_SCENARIO, timeout_s=0.5)
        assert got == [Sample(keys.SIM_CTRL_SCENARIO, b"scn", enc)]
        assert a.get(keys.SIM_CTRL_SCENARIO, timeout_s=0.5) == [Sample(keys.SIM_CTRL_SCENARIO, b"scn", enc)]
        srv.close()
        assert b.get(keys.SIM_CTRL_SCENARIO, timeout_s=0.3) == []
    finally:
        b.close()
        a.close()
