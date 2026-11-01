"""protobuf 메시지 이름 ⇄ 클래스, 버스 인코딩 (IMP-AGT-002)."""

from google.protobuf import descriptor_pool, message_factory
from google.protobuf.message import Message

from swarm_api import protobuf_encoding

# 디스크립터 풀에 swarm.v1 메시지를 올린다. truth는 기체 쪽에서 쓰지 않으므로 올리지 않는다 (PRP-SIM-003)
from swarm.v1 import c2_pb2, common_pb2, entity_pb2, fa_pb2, link_pb2, mp_pb2, ms_pb2, p2p_pb2, sim_pb2, vi_pb2  # noqa: F401

_ALLOWED_PACKAGE = "swarm.v1."


def message_class(full_name: str) -> type[Message] | None:
    """전체 이름(swarm.v1.X)의 메시지 클래스. 모르거나 swarm.v1이 아니면 None"""
    if not full_name.startswith(_ALLOWED_PACKAGE):
        return None
    try:
        desc = descriptor_pool.Default().FindMessageTypeByName(full_name)
    except KeyError:
        return None
    return message_factory.GetMessageClass(desc)


def decode(full_name: str, payload: bytes) -> Message | None:
    cls = message_class(full_name)
    if cls is None:
        return None
    msg = cls()
    msg.ParseFromString(payload)
    return msg


def short_name(msg: Message) -> str:
    return msg.DESCRIPTOR.name


def full_name(msg: Message) -> str:
    return msg.DESCRIPTOR.full_name


def encoding(msg: Message) -> str:
    return protobuf_encoding(full_name(msg))


def fill_header(msg: Message, source: str, frame: int, sim_time_us: int, seq: int) -> None:
    """header 필드가 있으면 비어 있는 항목을 채운다"""
    if "header" not in msg.DESCRIPTOR.fields_by_name:
        return
    h = msg.header
    if not h.source:
        h.source = source
    if not h.frame:
        h.frame = frame
    if not h.sim_time_us:
        h.sim_time_us = sim_time_us
    if not h.seq:
        h.seq = seq
