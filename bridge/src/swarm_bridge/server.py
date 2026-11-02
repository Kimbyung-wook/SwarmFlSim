"""IMP-UI-021: 브리지 프로토콜 v1 서버 (DEC-027, DEC-020, DEC-006).

- 한 WebSocket 연결이 한 클라이언트다. 첫 텍스트 프레임은 hello여야 한다.
- 구독은 클라이언트별로 버스에 따로 선언하고, max_hz > 0이면 키마다 주기 안의 마지막 메시지만 보낸다.
- 발행은 role=control이고 sim/ctrl/cmd 또는 swarm/<gcs>/tx/** 일 때만 버스에 싣는다.
- 버스 콜백(Zenoh 스레드)은 call_soon_threadsafe로 이벤트 루프에 넘긴다. 송신은 클라이언트별 큐 하나로 순서를 지키고,
  큐가 넘치면 오래된 것부터 버린다(느린 브라우저가 다른 클라이언트와 버스를 막지 않게).
"""

import asyncio
import json
import logging
import threading
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from swarm_api import CONTRACT_VERSION, Bus, Sample, keys

from .frame import FrameError, decode_frame, encode_frame

log = logging.getLogger("swarm_bridge")

PROTOCOL_VERSION = 1
DEFAULT_PORT = 8765
WS_PATH = "/bus"
ROLES = ("control", "observer")
DRAIN_BATCH = 512  # 이벤트 루프를 한 번에 잡고 처리하는 샘플 수 상한
DROP_LOG_PERIOD_S = 5.0


class ProtocolError(Exception):
    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


@dataclass
class BridgeOptions:
    queue_limit: int = 4096  # 클라이언트별 송신 대기 프레임 수
    hello_timeout_s: float = 10.0


def publish_allowed(key: str, role: str, gcs: str | None) -> bool:
    """§3.5 발행 허용: control만, sim/ctrl/cmd와 swarm/<gcs>/tx/**"""
    if role != "control" or "*" in key or "$" in key:
        return False
    if key == keys.SIM_CTRL_CMD:
        return True
    return bool(gcs) and keys.keyexpr_matches(f"swarm/{gcs}/tx/**", key) and key != f"swarm/{gcs}/tx"


def _check_id(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ProtocolError("bad_request", f"{field} must be a string")
    try:
        return keys.check_entity_id(value)
    except ValueError as e:
        raise ProtocolError("bad_request", f"{field}: {e}") from e


class _Subscription:
    """클라이언트 구독 하나. 키별 다운샘플 상태를 가진다 (같은 키는 주기 안에서 마지막 메시지만)"""

    def __init__(self, client: "_Client", sub_id: int, keyexpr: str, max_hz: float):
        self.client = client
        self.id = sub_id
        self.keyexpr = keyexpr
        self.period = 1.0 / max_hz if max_hz > 0 else 0.0
        self._last_sent: dict[str, float] = {}
        self._pending: dict[str, Sample] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._bus_sub: Any = None
        self.closed = False

    def open(self, bus: Bus) -> None:
        def on_bus(sample: Sample) -> None:  # 버스 스레드
            self.client.post(self, sample)

        self._bus_sub = bus.subscribe(self.keyexpr, on_bus)

    def on_sample(self, sample: Sample) -> None:
        if self.closed:
            return
        if self.period == 0.0:
            self.client.send_sample(sample)
            return
        if sample.key in self._timers:  # 이미 대기 중이면 최신값만 바꾼다(순서 유지)
            self._pending[sample.key] = sample
            return
        now = self.client.loop.time()
        last = self._last_sent.get(sample.key)
        if last is None or now - last >= self.period:
            self._last_sent[sample.key] = now
            self.client.send_sample(sample)
            return
        self._pending[sample.key] = sample
        self._timers[sample.key] = self.client.loop.call_at(last + self.period, self._flush, sample.key)

    def _flush(self, key: str) -> None:
        self._timers.pop(key, None)
        sample = self._pending.pop(key, None)
        if sample is not None and not self.closed:
            self._last_sent[key] = self.client.loop.time()
            self.client.send_sample(sample)

    def close(self) -> None:
        self.closed = True
        for t in self._timers.values():
            t.cancel()
        self._timers.clear()
        self._pending.clear()
        if self._bus_sub is not None:
            self._bus_sub.close()
            self._bus_sub = None


class _Client:
    def __init__(self, server: "BridgeServer", ws: ServerConnection):
        self.server = server
        self.ws = ws
        self.loop = asyncio.get_running_loop()
        self.name = ""
        self.role = ""
        self.gcs: str | None = None
        self.subs: dict[int, _Subscription] = {}
        self._queue: deque[str | bytes] = deque()
        self._wake = asyncio.Event()
        self.dropped = 0
        self.closed = False
        # 버스 스레드 → 이벤트 루프 인수 대기열. 샘플마다 call_soon_threadsafe를 부르지 않고 묶어서 넘긴다 (IMP-UI-057)
        self._inbox: deque[tuple[_Subscription, Sample]] = deque()
        self._inbox_lock = threading.Lock()
        self._inbox_armed = False
        self._last_drop_log = 0.0

    # 버스 스레드에서 호출 ----------------------------------------------
    def post(self, sub: "_Subscription", sample: Sample) -> None:
        self._inbox.append((sub, sample))
        with self._inbox_lock:
            if self._inbox_armed:
                return
            self._inbox_armed = True
        try:
            self.loop.call_soon_threadsafe(self._drain)
        except RuntimeError:  # 루프 종료 중
            pass

    def _drain(self) -> None:
        for _ in range(DRAIN_BATCH):
            try:
                sub, sample = self._inbox.popleft()
            except IndexError:
                break
            sub.on_sample(sample)
        with self._inbox_lock:
            more = bool(self._inbox)
            self._inbox_armed = more
        if more:  # 송신 태스크가 돌 틈을 준다
            self.loop.call_soon(self._drain)

    # 송신 ------------------------------------------------------------
    def _enqueue(self, msg: str | bytes) -> None:
        if self.closed:
            return
        if len(self._queue) >= self.server.options.queue_limit:
            self._queue.popleft()
            self.dropped += 1
            self._log_drop()
        self._queue.append(msg)
        self._wake.set()

    def _log_drop(self) -> None:
        now = self.loop.time()
        if now - self._last_drop_log >= DROP_LOG_PERIOD_S:
            self._last_drop_log = now
            log.warning("client %s: send queue full, dropped %d so far (slow consumer or overload)", self.name, self.dropped)

    def send_sample(self, sample: Sample) -> None:
        self._enqueue(encode_frame(sample.key, sample.encoding, sample.payload))

    def send_json(self, obj: dict[str, Any]) -> None:
        self._enqueue(json.dumps(obj, separators=(",", ":")))

    def send_error(self, code: str, msg: str) -> None:
        self.send_json({"op": "error", "code": code, "msg": msg})

    async def run_sender(self) -> None:
        try:
            while True:
                await self._wake.wait()
                self._wake.clear()
                while self._queue:
                    await self.ws.send(self._queue.popleft())
        except ConnectionClosed:
            pass

    # 수신 ------------------------------------------------------------
    def hello(self, msg: str | bytes) -> None:
        if not isinstance(msg, str):
            raise ProtocolError("bad_request", "first message must be a hello text frame")
        req = self._parse_json(msg)
        if req.get("op") != "hello":
            raise ProtocolError("bad_request", "first message must be hello")
        self.name = _check_id(req.get("client"), "client")
        role = req.get("role")
        if role not in ROLES:
            raise ProtocolError("bad_request", f"role must be one of {ROLES}")
        self.role = role
        gcs = req.get("gcs")
        self.gcs = None if gcs in (None, "") else _check_id(gcs, "gcs")
        self.send_json({"op": "welcome", "protocol": PROTOCOL_VERSION, "contract": CONTRACT_VERSION})

    def handle(self, msg: str | bytes) -> None:
        if isinstance(msg, bytes):
            self._publish(msg)
            return
        req = self._parse_json(msg)
        op = req.get("op")
        if op == "sub":
            self._sub(req)
        elif op == "unsub":
            self._unsub(req)
        elif op == "hello":
            raise ProtocolError("bad_request", "hello already received")
        else:
            raise ProtocolError("unsupported", f"unknown op: {op!r}")

    @staticmethod
    def _parse_json(msg: str) -> dict[str, Any]:
        try:
            req = json.loads(msg)
        except json.JSONDecodeError as e:
            raise ProtocolError("bad_request", f"invalid JSON: {e}") from e
        if not isinstance(req, dict):
            raise ProtocolError("bad_request", "control frame must be a JSON object")
        return req

    @staticmethod
    def _sub_id(req: dict[str, Any]) -> int:
        sub_id = req.get("id")
        if not isinstance(sub_id, int) or isinstance(sub_id, bool):
            raise ProtocolError("bad_request", "id must be an integer")
        return sub_id

    def _sub(self, req: dict[str, Any]) -> None:
        sub_id = self._sub_id(req)
        if sub_id in self.subs:
            raise ProtocolError("bad_request", f"subscription id {sub_id} already in use")
        key = req.get("key")
        if not isinstance(key, str) or not key:
            raise ProtocolError("bad_request", "key must be a non-empty string")
        max_hz = req.get("max_hz", 0)
        if not isinstance(max_hz, (int, float)) or isinstance(max_hz, bool) or max_hz < 0:
            raise ProtocolError("bad_request", "max_hz must be a number >= 0")
        sub = _Subscription(self, sub_id, key, float(max_hz))
        try:
            sub.open(self.server.bus)
        except Exception as e:  # Zenoh가 잘못된 키 표현식을 거부한 경우 등
            raise ProtocolError("bad_request", f"cannot subscribe {key!r}: {e}") from e
        self.subs[sub_id] = sub

    def _unsub(self, req: dict[str, Any]) -> None:
        sub_id = self._sub_id(req)
        sub = self.subs.pop(sub_id, None)
        if sub is None:
            raise ProtocolError("bad_request", f"unknown subscription id {sub_id}")
        sub.close()

    def _publish(self, data: bytes) -> None:
        try:
            key, encoding, payload = decode_frame(data)
        except FrameError as e:
            raise ProtocolError("bad_request", str(e)) from e
        if self.role != "control":
            raise ProtocolError("forbidden", f"{self.role} cannot publish")
        if not publish_allowed(key, self.role, self.gcs):
            raise ProtocolError("forbidden", f"publish not allowed: {key}")
        self.server.bus.put(key, payload, encoding)
        self.server.published += 1

    def close(self) -> None:
        self.closed = True
        for s in self.subs.values():
            s.close()
        self.subs.clear()
        self._queue.clear()
        self._inbox.clear()


class BridgeServer:
    """버스 하나를 여러 WebSocket 클라이언트에 연결한다. 버스 수명은 호출자가 관리한다"""

    def __init__(self, bus: Bus, options: BridgeOptions | None = None):
        self.bus = bus
        self.options = options or BridgeOptions()
        self.clients: set[_Client] = set()
        self.published = 0
        self._server: Server | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def start(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> int:
        self._server = await serve(
            self._handle,
            host,
            port,
            process_request=self._check_path,
            compression=None,
        )
        return self.port

    async def serve_forever(self) -> None:
        assert self._server is not None
        await self._server.serve_forever()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @staticmethod
    def _check_path(conn: ServerConnection, request: Request) -> Response | None:
        if request.path.split("?", 1)[0] != WS_PATH:
            return conn.respond(HTTPStatus.NOT_FOUND, f"bridge endpoint is {WS_PATH}\n")
        return None

    async def _handle(self, ws: ServerConnection) -> None:
        client = _Client(self, ws)
        sender = asyncio.create_task(client.run_sender())
        try:
            try:
                first = await asyncio.wait_for(ws.recv(), self.options.hello_timeout_s)
                client.hello(first)
            except (ProtocolError, TimeoutError) as e:
                code, msg = (e.code, e.msg) if isinstance(e, ProtocolError) else ("bad_request", "hello timeout")
                await ws.send(json.dumps({"op": "error", "code": code, "msg": msg}))
                await ws.close(1008, msg[:120])
                return
            self.clients.add(client)
            log.info("client %s connected (role=%s gcs=%s)", client.name, client.role, client.gcs)
            async for msg in ws:
                try:
                    client.handle(msg)
                except ProtocolError as e:
                    client.send_error(e.code, e.msg)
        except ConnectionClosed:
            pass
        finally:
            client.close()
            sender.cancel()
            if client in self.clients:
                self.clients.discard(client)
                log.info("client %s disconnected (dropped %d)", client.name, client.dropped)
