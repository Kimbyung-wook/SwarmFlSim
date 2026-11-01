"""IMP-UI-020: 브리지 바이너리 프레임 (DEC-027).

uint16 키 길이 | 키(UTF-8) | uint16 인코딩 길이 | 인코딩(UTF-8) | 페이로드. 정수는 little-endian, 양방향 같은 형식.
"""

import struct

_U16 = struct.Struct("<H")
_MAX_FIELD = 0xFFFF


class FrameError(ValueError):
    pass


def encode_frame(key: str, encoding: str, payload: bytes) -> bytes:
    k = key.encode("utf-8")
    e = encoding.encode("utf-8")
    if len(k) > _MAX_FIELD or len(e) > _MAX_FIELD:
        raise FrameError("key or encoding longer than 65535 bytes")
    return b"".join((_U16.pack(len(k)), k, _U16.pack(len(e)), e, payload))


def decode_frame(data: bytes) -> tuple[str, str, bytes]:
    """(키, 인코딩, 페이로드). 형식이 틀리면 FrameError"""
    view = memoryview(data)
    try:
        (klen,) = _U16.unpack_from(view, 0)
        kend = 2 + klen
        (elen,) = _U16.unpack_from(view, kend)
        eend = kend + 2 + elen
        if eend > len(view):
            raise FrameError("truncated frame")
        key = bytes(view[2:kend]).decode("utf-8")
        encoding = bytes(view[kend + 2 : eend]).decode("utf-8")
    except (struct.error, UnicodeDecodeError) as e:
        raise FrameError(f"malformed frame: {e}") from e
    if not key:
        raise FrameError("empty key")
    return key, encoding, bytes(view[eend:])
