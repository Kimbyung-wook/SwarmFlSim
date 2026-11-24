"""STOMP 1.2 클라이언트 (IMP-GW-037, DEC-110).

A-GRA 시험 하네스의 버스(ActiveMQ STOMP, `/topic/<UCI 이름>`, UCI XML 본문, 비지속 토픽)에 붙는 데 필요한 만큼만 둔다:
CONNECT, SUBSCRIBE(ack auto), SEND, DISCONNECT와 MESSAGE·ERROR·RECEIPT 받기. 심장 박동은 쓰지 않는다(0,0).
asyncio 스트림 위에서 돈다(의존성 추가 없음).
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Awaitable, Callable

log = logging.getLogger("swarm_gateway")

Handler = Callable[[str, bytes, dict], "Awaitable[None] | None"]   # (destination, body, headers)

_ESC = {"\\": "\\\\", "\n": "\\n", ":": "\\c", "\r": "\\r"}
_UNESC = {"\\\\": "\\", "\\n": "\n", "\\c": ":", "\\r": "\r"}


class StompError(RuntimeError):
    pass


def _escape(v: str) -> str:
    return "".join(_ESC.get(c, c) for c in v)


def _unescape(v: str) -> str:
    out, i = [], 0
    while i < len(v):
        if v[i] == "\\" and i + 1 < len(v):
            out.append(_UNESC.get(v[i:i + 2], v[i:i + 2]))
            i += 2
        else:
            out.append(v[i])
            i += 1
    return "".join(out)


def encode_frame(command: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    if body and "content-length" not in headers:
        headers = {**headers, "content-length": str(len(body))}
    esc = command != "CONNECT"   # STOMP 1.2: CONNECT 머리는 이스케이프하지 않는다
    head = "".join(f"{_escape(k) if esc else k}:{_escape(v) if esc else v}\n" for k, v in headers.items())
    return f"{command}\n{head}\n".encode() + body + b"\x00"


async def read_frame(reader: asyncio.StreamReader) -> tuple[str, dict[str, str], bytes] | None:
    """프레임 하나. 연결이 끝나면 None. 프레임 사이 줄바꿈(심장 박동)은 건너뛴다"""
    while True:
        line = await reader.readline()
        if not line:
            return None
        cmd = line.rstrip(b"\r\n").decode()
        if cmd:
            break
    headers: dict[str, str] = {}
    while True:
        line = (await reader.readline()).rstrip(b"\r\n").decode()
        if not line:
            break
        k, _, v = line.partition(":")
        headers.setdefault(_unescape(k), _unescape(v))   # 1.2: 같은 머리가 여럿이면 처음 것
    if "content-length" in headers:
        body = await reader.readexactly(int(headers["content-length"]))
        await reader.readexactly(1)                        # NUL
    else:
        body = (await reader.readuntil(b"\x00"))[:-1]
    return cmd, headers, body


class StompClient:
    def __init__(self, host: str, port: int, *, login: str = "", passcode: str = "", vhost: str = "/"):
        self.host, self.port, self.login, self.passcode, self.vhost = host, port, login, passcode, vhost
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._subs: dict[str, tuple[str, Handler]] = {}
        self._ids = itertools.count(1)
        self._task: asyncio.Task | None = None
        self._wlock = asyncio.Lock()
        self.server: dict[str, str] = {}
        self.received = 0
        self.sent = 0

    async def connect(self, timeout: float = 10.0) -> dict[str, str]:
        self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout)
        hdr = {"accept-version": "1.2", "host": self.vhost, "heart-beat": "0,0"}
        if self.login:
            hdr |= {"login": self.login, "passcode": self.passcode}
        self._writer.write(encode_frame("CONNECT", hdr))
        await self._writer.drain()
        frame = await asyncio.wait_for(read_frame(self._reader), timeout)
        if frame is None or frame[0] != "CONNECTED":
            raise StompError(f"STOMP connect failed: {frame and frame[0]} {frame and frame[1].get('message', '')}")
        self.server = frame[1]
        self._task = asyncio.create_task(self._run())
        return self.server

    async def _send(self, command: str, headers: dict[str, str], body: bytes = b"") -> None:
        if self._writer is None:
            raise StompError("not connected")
        async with self._wlock:
            self._writer.write(encode_frame(command, headers, body))
            await self._writer.drain()

    async def subscribe(self, destination: str, handler: Handler) -> str:
        sid = str(next(self._ids))
        self._subs[sid] = (destination, handler)
        await self._send("SUBSCRIBE", {"id": sid, "destination": destination, "ack": "auto"})
        return sid

    async def send(self, destination: str, body: bytes, content_type: str = "") -> None:
        hdr = {"destination": destination}
        if content_type:
            hdr["content-type"] = content_type
        await self._send("SEND", hdr, body)
        self.sent += 1

    async def _run(self) -> None:
        assert self._reader is not None
        while True:
            try:
                frame = await read_frame(self._reader)
            except (asyncio.IncompleteReadError, ConnectionError):
                frame = None
            if frame is None:
                log.warning("gateway: STOMP connection closed")
                return
            cmd, hdr, body = frame
            if cmd == "MESSAGE":
                self.received += 1
                sub = self._subs.get(hdr.get("subscription", ""))
                if sub is None:
                    continue
                try:
                    res = sub[1](hdr.get("destination", sub[0]), body, hdr)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:  # 처리 오류에도 받기는 계속한다
                    log.exception("gateway: STOMP handler failed on %s", hdr.get("destination"))
            elif cmd == "ERROR":
                log.warning("gateway: STOMP ERROR %s %s", hdr.get("message", ""), body[:200])

    async def close(self) -> None:
        if self._writer is not None:
            try:
                await self._send("DISCONNECT", {})
            except (ConnectionError, StompError):
                pass
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except ConnectionError:
                pass
            self._writer = None
        if self._task is not None:
            self._task.cancel()
