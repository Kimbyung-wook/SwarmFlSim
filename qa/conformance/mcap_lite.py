"""MCAP 최소 읽기 (압축 없는 파일만). 루트 uv 환경에 mcap 패키지가 없어 점검 도구 안에 둔다.

Logger는 압축을 끄고 쓴다(logger/src/mcap_log.cpp, Compression::None). 채널(= Zenoh 키, PRP-LOG-001)과 채널별 메시지 수,
원하면 메시지 본문을 돌려준다. 끝이 잘린 파일(Logger가 강제 종료된 경우)도 읽은 데까지 돌려준다.
"""
from __future__ import annotations

import struct
from collections import Counter
from pathlib import Path
from typing import Callable

MAGIC = b"\x89MCAP0\r\n"
OP_CHANNEL, OP_MESSAGE, OP_CHUNK, OP_DATA_END, OP_FOOTER = 0x04, 0x05, 0x06, 0x0F, 0x02


def _str(b: bytes, o: int) -> tuple[str, int]:
    n = struct.unpack_from("<I", b, o)[0]
    return b[o + 4:o + 4 + n].decode("utf-8", "replace"), o + 4 + n


def _records(buf: bytes, start: int, end: int):
    o = start
    while o + 9 <= end:
        op = buf[o]
        n = struct.unpack_from("<Q", buf, o + 1)[0]
        body0 = o + 9
        if body0 + n > end:
            return
        yield op, body0, body0 + n
        o = body0 + n


class McapSummary:
    def __init__(self) -> None:
        self.channels: dict[int, dict] = {}
        self.counts: Counter = Counter()          # topic → 메시지 수
        self.truncated = False

    @property
    def topics(self) -> list[str]:
        return sorted({c["topic"] for c in self.channels.values()})


def read(path: Path, want: Callable[[str], bool] | None = None, on_msg=None) -> McapSummary:  # noqa: ANN001
    """want(topic)이 참인 채널의 메시지마다 on_msg(topic, log_time_ns, data)를 부른다"""
    buf = Path(path).read_bytes()
    s = McapSummary()
    if not buf.startswith(MAGIC):
        raise ValueError(f"{path}: not an MCAP file")

    def walk(b: bytes, a: int, z: int) -> bool:
        for op, b0, b1 in _records(b, a, z):
            if op == OP_CHANNEL:
                cid, _schema = struct.unpack_from("<HH", b, b0)
                topic, o = _str(b, b0 + 4)
                enc, o = _str(b, o)
                s.channels.setdefault(cid, {"id": cid, "topic": topic, "encoding": enc})
            elif op == OP_MESSAGE:
                cid, _seq, log_t, _pub_t = struct.unpack_from("<HIQQ", b, b0)
                ch = s.channels.get(cid)
                topic = ch["topic"] if ch else f"#{cid}"
                s.counts[topic] += 1
                if on_msg is not None and (want is None or want(topic)):
                    on_msg(topic, log_t, b[b0 + 22:b1])
            elif op == OP_CHUNK:
                o = b0 + 8 + 8 + 8 + 4
                comp, o = _str(b, o)
                n = struct.unpack_from("<Q", b, o)[0]
                if comp:
                    raise ValueError(f"compressed chunk ({comp}) is not supported")
                walk(b, o + 8, min(o + 8 + n, b1))
            elif op in (OP_DATA_END, OP_FOOTER):
                return True
        return False

    ended = walk(buf, len(MAGIC), len(buf))
    s.truncated = not ended
    return s
