"""TC-UI-010~015: 브리지 프로토콜 v1 (IMP-UI-020~022, DEC-027)"""

import asyncio
import json
from collections.abc import Awaitable, Callable

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from swarm_api import CONTRACT_VERSION, InMemoryBus, Sample
from swarm_bridge import BridgeOptions, BridgeServer, FrameError, decode_frame, encode_frame, publish_allowed
from swarm_bridge.cli import bus_config, main

ENC = "application/protobuf;swarm.v1.TruthFrame"


def run(fn: Callable[[BridgeServer, InMemoryBus], Awaitable[None]], options: BridgeOptions | None = None) -> None:
    async def go() -> None:
        bus = InMemoryBus()
        server = BridgeServer(bus, options)
        await server.start("127.0.0.1", 0)
        try:
            await asyncio.wait_for(fn(server, bus), 10)
        finally:
            await server.close()

    asyncio.run(go())


def url(server: BridgeServer, path: str = "/bus") -> str:
    return f"ws://127.0.0.1:{server.port}{path}"


async def hello(ws: ClientConnection, role: str = "control", gcs: str | None = "gcs-01", client: str = "ui-01") -> dict:
    msg = {"op": "hello", "client": client, "role": role}
    if gcs is not None:
        msg["gcs"] = gcs
    await ws.send(json.dumps(msg))
    return json.loads(await ws.recv())


async def recv_json(ws: ClientConnection) -> dict:
    m = await ws.recv()
    assert isinstance(m, str), m
    return json.loads(m)


async def settle() -> None:
    """call_soon_threadsafe로 넘긴 콜백과 송신 태스크가 돌 시간을 준다"""
    for _ in range(5):
        await asyncio.sleep(0.01)


async def drain(ws: ClientConnection, timeout: float = 0.2) -> list[str | bytes]:
    out: list[str | bytes] = []
    try:
        while True:
            out.append(await asyncio.wait_for(ws.recv(), timeout))
    except TimeoutError:
        return out


# TC-UI-010: 바이너리 프레임 ------------------------------------------------
def test_frame_roundtrip_and_layout():
    f = encode_frame("truth/state", ENC, b"\x01\x02")
    assert f[:2] == len("truth/state").to_bytes(2, "little")
    assert decode_frame(f) == ("truth/state", ENC, b"\x01\x02")
    # ui/src/data/bridge.test.ts와 같은 벡터
    assert encode_frame("a/b", "x", b"\x07") == bytes([3, 0, 97, 47, 98, 1, 0, 120, 7])
    assert decode_frame(encode_frame("sim/ctrl/cmd", "", b"")) == ("sim/ctrl/cmd", "", b"")
    # 한글 키는 UTF-8 바이트 길이
    assert decode_frame(encode_frame("a/가", "e", b"x"))[0] == "a/가"


@pytest.mark.parametrize("data", [b"", b"\x05\x00ab", b"\x02\x00ab\x09\x00x", b"\x00\x00\x00\x00", b"\x02\x00\xff\xfe\x00\x00"])
def test_frame_malformed(data):
    with pytest.raises(FrameError):
        decode_frame(data)


# TC-UI-011: 접속·hello·오류 ------------------------------------------------
def test_hello_welcome():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            w = await hello(ws)
            assert w == {"op": "welcome", "protocol": 1, "contract": CONTRACT_VERSION}
            await ws.send('{"op":"nope"}')
            assert (await recv_json(ws))["code"] == "unsupported"
            await ws.send("not json")
            assert (await recv_json(ws))["code"] == "bad_request"
            await ws.send(json.dumps({"op": "hello", "client": "ui-01", "role": "control"}))
            assert (await recv_json(ws))["code"] == "bad_request"

    run(t)


@pytest.mark.parametrize(
    "first",
    [
        '{"op":"sub","id":1,"key":"truth/**"}',
        '{"op":"hello","client":"UI","role":"control"}',
        '{"op":"hello","client":"ui-01","role":"admin"}',
        '{"op":"hello","client":"ui-01","role":"control","gcs":"GCS 1"}',
        b"\x01\x00a\x00\x00",
    ],
)
def test_bad_hello_closes(first):
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await ws.send(first)
            err = await recv_json(ws)
            assert err["op"] == "error" and err["code"] == "bad_request"
            with pytest.raises(ConnectionClosed):
                await ws.recv()
        assert not server.clients

    run(t)


def test_hello_timeout():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            assert (await recv_json(ws))["code"] == "bad_request"

    run(t, BridgeOptions(hello_timeout_s=0.1))


def test_wrong_path_rejected():
    async def t(server, bus):
        with pytest.raises(InvalidStatus):
            async with connect(url(server, "/other")):
                pass

    run(t)


# TC-UI-012: 구독·해제 ------------------------------------------------------
def test_subscribe_forwards_key_encoding_payload():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws, role="observer", gcs=None)
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "truth/**", "max_hz": 0}))
            await settle()
            bus.put("truth/state", b"abc", ENC)
            bus.put("truth/event/kill", b"k", "application/protobuf;swarm.v1.TruthEvent")
            bus.put("sim/ctrl/status", b"s", "x")  # 구독 밖
            got = [decode_frame(m) for m in await drain(ws)]
            assert got == [("truth/state", ENC, b"abc"), ("truth/event/kill", "application/protobuf;swarm.v1.TruthEvent", b"k")]

            await ws.send(json.dumps({"op": "unsub", "id": 1}))
            await settle()
            bus.put("truth/state", b"abc", ENC)
            assert await drain(ws) == []
            assert not bus._subs  # 버스 구독도 풀렸다

    run(t)


@pytest.mark.parametrize(
    "req",
    [
        {"op": "sub", "id": "1", "key": "a/b"},
        {"op": "sub", "id": True, "key": "a/b"},
        {"op": "sub", "id": 1, "key": ""},
        {"op": "sub", "id": 1, "key": "a/b", "max_hz": -1},
        {"op": "sub", "id": 1, "key": "a/b", "max_hz": "10"},
        {"op": "unsub", "id": 99},
    ],
)
def test_sub_bad_request(req):
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws)
            await ws.send(json.dumps(req))
            assert (await recv_json(ws))["code"] == "bad_request"

    run(t)


def test_duplicate_sub_id():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws)
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "a/**"}))
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "b/**"}))
            assert (await recv_json(ws))["code"] == "bad_request"

    run(t)


def test_disconnect_releases_bus_subscriptions():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws)
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "a/**"}))
            await ws.send(json.dumps({"op": "sub", "id": 2, "key": "b/**"}))
            await settle()
            assert len(bus._subs) == 2
        await settle()
        assert not bus._subs and not server.clients

    run(t)


# TC-UI-013: 다운샘플 -------------------------------------------------------
def test_max_hz_downsamples_and_keeps_last_per_key():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws)
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "truth/**", "max_hz": 10}))
            await settle()
            # 0.6 s 동안 약 50 Hz로 두 키를 보낸다 (Windows 시계 해상도 15.6 ms라 경과 시간으로 끊는다)
            loop = asyncio.get_running_loop()
            start = loop.time()
            n = 0
            while loop.time() - start < 0.6:
                bus.put("truth/state", str(n).encode(), ENC)
                bus.put("truth/event/spawn", str(n).encode(), ENC)
                n += 1
                await asyncio.sleep(0.02)
            frames = [decode_frame(m) for m in await drain(ws, 0.3)]
            state = [p for k, _, p in frames if k == "truth/state"]
            spawn = [p for k, _, p in frames if k == "truth/event/spawn"]
            assert n >= 20
            # 첫 메시지는 바로, 이후 0.1 s마다 하나. 주기 끝에 남은 마지막 메시지가 반드시 간다
            for seq in (state, spawn):
                assert seq[0] == b"0"
                assert seq[-1] == str(n - 1).encode()
                assert 5 <= len(seq) <= 9, seq
                assert [int(x) for x in seq] == sorted(int(x) for x in seq)

    run(t)


def test_max_hz_zero_is_unlimited():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws)
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "truth/state"}))
            await settle()
            for i in range(200):
                bus.put("truth/state", str(i).encode(), ENC)
            frames = await drain(ws)
            assert [decode_frame(m)[2] for m in frames] == [str(i).encode() for i in range(200)]

    run(t)


def test_queue_overflow_drops_oldest():
    async def t(server, bus):
        async with connect(url(server)) as ws:
            await hello(ws)
            await ws.send(json.dumps({"op": "sub", "id": 1, "key": "truth/state"}))
            await settle()
            (client,) = server.clients
            # 송신 태스크가 돌기 전에 한꺼번에 넣는다
            for i in range(20):
                client.send_sample(Sample("truth/state", str(i).encode(), ENC))
            frames = await drain(ws)
            assert client.dropped == 12
            assert [decode_frame(m)[2] for m in frames] == [str(i).encode() for i in range(12, 20)]

    run(t, BridgeOptions(queue_limit=8))


# TC-UI-014: 발행 허용 키 ---------------------------------------------------
def test_publish_allowed_rule():
    assert publish_allowed("sim/ctrl/cmd", "control", None)
    assert publish_allowed("swarm/gcs-01/tx/c2/TaskCommand", "control", "gcs-01")
    assert not publish_allowed("swarm/gcs-01/tx", "control", "gcs-01")
    assert not publish_allowed("swarm/gcs-02/tx/c2/TaskCommand", "control", "gcs-01")
    assert not publish_allowed("swarm/gcs-01/rx/c2/TaskStatus", "control", "gcs-01")
    assert not publish_allowed("swarm/gcs-01/tx/c2/TaskCommand", "control", None)
    assert not publish_allowed("swarm/gcs-01/tx/*/TaskCommand", "control", "gcs-01")
    assert not publish_allowed("sim/ctrl/status", "control", "gcs-01")
    assert not publish_allowed("truth/state", "control", "gcs-01")
    assert not publish_allowed("sim/ctrl/cmd", "observer", "gcs-01")


def test_publish_forwarded_and_forbidden():
    async def t(server, bus):
        seen: list[Sample] = []
        bus.subscribe("**", seen.append)
        async with connect(url(server)) as ws:
            await hello(ws, gcs="gcs-01")
            await ws.send(encode_frame("sim/ctrl/cmd", "application/protobuf;swarm.v1.SimCommand", b"p"))
            await ws.send(encode_frame("swarm/gcs-01/tx/c2/TaskCommand", "application/protobuf;swarm.v1.LinkEnvelope", b"t"))
            await ws.send(encode_frame("swarm/uav-001/rx/c2/TaskCommand", "x", b"bad"))
            err = await recv_json(ws)
            assert err["code"] == "forbidden" and "swarm/uav-001/rx" in err["msg"]
            await ws.send(b"\x09\x00")
            assert (await recv_json(ws))["code"] == "bad_request"
        assert seen == [
            Sample("sim/ctrl/cmd", b"p", "application/protobuf;swarm.v1.SimCommand"),
            Sample("swarm/gcs-01/tx/c2/TaskCommand", b"t", "application/protobuf;swarm.v1.LinkEnvelope"),
        ]
        assert server.published == 2

    run(t)


def test_observer_cannot_publish():
    async def t(server, bus):
        seen: list[Sample] = []
        bus.subscribe("**", seen.append)
        async with connect(url(server)) as ws:
            await hello(ws, role="observer", gcs="gcs-01")
            await ws.send(encode_frame("sim/ctrl/cmd", "e", b"p"))
            assert (await recv_json(ws))["code"] == "forbidden"
        assert seen == []

    run(t)


# TC-UI-015: 다중 클라이언트 ------------------------------------------------
def test_multiple_clients_independent():
    async def t(server, bus):
        async with connect(url(server)) as a, connect(url(server)) as b, connect(url(server)) as c:
            await hello(a, client="ui-a", gcs="gcs-01")
            await hello(b, client="ui-b", gcs="gcs-02")
            await hello(c, client="mon-01", role="observer", gcs=None)
            assert len(server.clients) == 3
            await a.send(json.dumps({"op": "sub", "id": 1, "key": "swarm/gcs-01/rx/**"}))
            await b.send(json.dumps({"op": "sub", "id": 1, "key": "swarm/gcs-02/rx/**"}))
            await c.send(json.dumps({"op": "sub", "id": 7, "key": "swarm/*/tx/**", "max_hz": 0}))
            await c.send(json.dumps({"op": "sub", "id": 8, "key": "truth/state", "max_hz": 5}))
            await settle()

            # a가 보낸 tx를 c(모니터)가 받는다. b의 허용 키가 아니므로 b는 a의 GCS로 보낼 수 없다
            await a.send(encode_frame("swarm/gcs-01/tx/c2/TaskCommand", "e", b"from-a"))
            await b.send(encode_frame("swarm/gcs-01/tx/c2/TaskCommand", "e", b"from-b"))
            assert (await recv_json(b))["code"] == "forbidden"
            bus.put("swarm/gcs-01/rx/c2/TaskStatus", b"st1", "e")
            bus.put("swarm/gcs-02/rx/c2/TaskStatus", b"st2", "e")
            bus.put("truth/state", b"tf", ENC)

            assert [decode_frame(m)[2] for m in await drain(a)] == [b"st1"]
            assert [decode_frame(m)[2] for m in await drain(b)] == [b"st2"]
            assert sorted(decode_frame(m)[2] for m in await drain(c)) == [b"from-a", b"tf"]
        await settle()
        assert not server.clients

    run(t)


def test_cli_bus_config():
    import argparse

    from swarm_bridge.cli import add_bus_args

    p = argparse.ArgumentParser()
    add_bus_args(p)
    a = p.parse_args(["--bus", "zenoh", "--zenoh-mode", "client", "--connect", "tcp/127.0.0.1:7447", "--connect", "tcp/h:1", "--no-multicast"])
    c = bus_config(a)
    assert (c.backend, c.zenoh_mode, list(c.connect), c.multicast_scouting) == ("zenoh", "client", ["tcp/127.0.0.1:7447", "tcp/h:1"], False)
    with pytest.raises(SystemExit):
        main(["--help"])


# TC-UI-016: Zenoh 백엔드(다른 스레드 콜백) 경유 ----------------------------
@pytest.mark.skipif(not __import__("swarm_api").zenoh_available(), reason="eclipse-zenoh 없음")
def test_zenoh_roundtrip():
    import socket

    from swarm_api import BusConfig, open_bus

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        zport = s.getsockname()[1]
    ep = f"tcp/127.0.0.1:{zport}"
    peer = open_bus(BusConfig(backend="zenoh", listen=[ep], multicast_scouting=False))
    bridge_bus = open_bus(BusConfig(backend="zenoh", connect=[ep], multicast_scouting=False))

    async def go() -> None:
        server = BridgeServer(bridge_bus)
        await server.start("127.0.0.1", 0)
        seen: list[Sample] = []
        peer.subscribe("sim/ctrl/cmd", seen.append)
        try:
            async with connect(url(server)) as ws:
                await hello(ws)
                await ws.send(json.dumps({"op": "sub", "id": 1, "key": "truth/state", "max_hz": 0}))
                await asyncio.sleep(0.5)  # 구독 선언 전파
                peer.put("truth/state", b"tf", ENC)
                assert decode_frame(await asyncio.wait_for(ws.recv(), 5)) == ("truth/state", ENC, b"tf")
                await ws.send(encode_frame("sim/ctrl/cmd", "application/protobuf;swarm.v1.SimCommand", b"p"))
                for _ in range(50):
                    if seen:
                        break
                    await asyncio.sleep(0.05)
                assert [(x.key, x.payload) for x in seen] == [("sim/ctrl/cmd", b"p")]
                assert seen[0].encoding == "application/protobuf;swarm.v1.SimCommand"
        finally:
            await server.close()

    try:
        asyncio.run(go())
    finally:
        bridge_bus.close()
        peer.close()
