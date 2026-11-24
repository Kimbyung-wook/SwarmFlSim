"""외부 인터페이스(MA-C2) 봉투 (IMP-GW-036, DEC-111).

외부 C2와 주고받는 UCI 메시지는 전송 경로(LA-CAL·STOMP)와 상관없이 봉투에 싸서 오간다.

- 수신: `MA_RxDataPayload`. `EncodedPayload`(xs:hexBinary)는 내부 메시지의 UCI XML 문서 전체(XML 선언 포함)를
  문자당 1바이트로 넣은 것이다. 풀어서 XSD로 검증하고 OMS JSON으로 바꿔 기존 변환기로 넘긴다.
  `SpecificDestinationID`가 비었거나 우리 시스템 UUID를 포함할 때만 받는다. `MessageType`은 내부 메시지와 맞아야 한다.
- 송신: `MA_TxDataPayloadCommand`. 내부 메시지 머리를 복사하고 새 `CommandID`, `CommandState` NEW, `Priority`,
  `MessageType`, `DestinationRouting`, 설정한 `SpecificDestinationID`를 싣는다. 봉투도 XSD로 검증한다.
- `MessageType` 열거값은 XSD의 `MessageTypeEnum`에서 메시지 이름을 대문자 밑줄 표기로 바꿔 찾는다(목록 하드코딩 없음).
- 봉투 안 문자열은 ASCII로 제한한다(하네스가 문자→바이트를 1:1로 처리한다). 내보낼 때 ASCII가 아닌 글자는 `?`로 바꾸고
  센다. 받은 것에 ASCII가 아닌 바이트가 있으면 거부한다.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from functools import cached_property

from lxml import etree

from .lacal import InvalidMessage, OmsJsonCodec, uci_timestamp

TX = "MA_TxDataPayloadCommand"
RX = "MA_RxDataPayload"
UCI_NS = "https://www.vdl.afrl.af.mil/programs/oam"
ROUTING = "TOPIC_AND_SPECIFIC_DESTINATION"


class EnvelopeError(ValueError):
    """봉투를 풀 수 없다(형식·검증·ASCII·MessageType 불일치)"""


class NotAddressed(Exception):
    """우리에게 온 봉투가 아니다(SpecificDestinationID에 우리 UUID가 없다). 거부가 아니라 무시한다"""


def message_type_name(uci_name: str) -> str:
    """`MA_TaskCommand` → `MA_TASK_COMMAND`, `PO_Activity` → `PO_ACTIVITY`"""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", uci_name).upper()


def _same_uuid(a: str, b: str) -> bool:
    try:
        return uuid.UUID(str(a)) == uuid.UUID(str(b))
    except ValueError:
        return False


def _fold(c: str) -> str:
    """글자 하나: 분해해 ASCII가 남으면 그것(é → e), 아니면 ?"""
    kept = "".join(x for x in unicodedata.normalize("NFKD", c) if x.isascii())
    return kept or "?"


def to_ascii(obj, counter: list[int] | None = None):
    """문자열 값의 ASCII가 아닌 글자를 바꾼다(악센트는 떼고, 나머지는 `?`). counter[0]에 바꾼 값 수"""
    if isinstance(obj, dict):
        return {k: to_ascii(v, counter) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_ascii(v, counter) for v in obj]
    if isinstance(obj, str) and not obj.isascii():
        if counter is not None:
            counter[0] += 1
        return "".join(c if c.isascii() else _fold(c) for c in obj)
    return obj


@dataclass
class Envelopes:
    codec: OmsJsonCodec
    destinations: list[str] = field(default_factory=list)   # 송신 SpecificDestinationID (UUID). 비우면 넣지 않는다
    priority: tuple[int, int] = (1, 1)                      # Priority, PrecedenceWithinPriority
    routing: str = ROUTING

    @cached_property
    def message_types(self) -> frozenset[str]:
        t = self.codec.xs.maps.types[f"{{{UCI_NS}}}MessageTypeEnum"]
        return frozenset(t.enumeration or ())

    def message_type(self, uci_name: str) -> str:
        v = message_type_name(uci_name)
        if v not in self.message_types:
            raise EnvelopeError(f"{uci_name}: no MessageTypeEnum value {v}")
        return v

    # ------------------------------------------------------------------ 송신
    def inner_xml(self, inner: dict) -> bytes:
        """내부 메시지 XML 문서(XSD 검증). ASCII만"""
        data = self.codec.to_xml_bytes(inner)
        if not data.isascii():
            raise EnvelopeError("inner XML is not ASCII")
        return data

    def wrap(self, inner: dict, *, ascii_fixed: list[int] | None = None) -> dict:
        """내부 메시지(OMS JSON) → `MA_TxDataPayloadCommand`(OMS JSON, XSD 검증)"""
        inner = to_ascii(inner, ascii_fixed)
        (name, body), = inner.items()
        hdr = dict(body["MessageHeader"])
        data = {
            "CommandID": {"UUID": str(uuid.uuid4())},
            "CommandState": "NEW",
            "EncodedPayload": self.inner_xml(inner).hex().upper(),
            "MessageType": self.message_type(name),
            "Priority": {"Priority": self.priority[0], "PrecedenceWithinPriority": self.priority[1]},
            "Timestamp": hdr.get("Timestamp") or uci_timestamp(),
        }
        if self.destinations:
            data["SpecificDestinationID"] = [{"UUID": u} for u in self.destinations]
        data["DestinationRouting"] = self.routing
        env = {TX: {"SecurityInformation": body["SecurityInformation"], "MessageHeader": hdr, "MessageData": data}}
        self.codec.to_xml_bytes(env)   # 봉투도 검증한다
        return env

    # ------------------------------------------------------------------ 수신
    def unwrap(self, env: dict, system_uuid: str) -> tuple[str, dict]:
        """`MA_RxDataPayload`(OMS JSON) → (내부 메시지 이름, 내부 OMS JSON). 우리에게 온 것이 아니면 NotAddressed"""
        if set(env) != {RX}:
            raise EnvelopeError(f"not {RX}: {sorted(env)}")
        try:
            self.codec.validate_xml(self.codec.json_to_xml(env))
        except (InvalidMessage, ValueError, TypeError, KeyError) as exc:
            raise EnvelopeError(f"envelope invalid: {exc}") from exc
        data = env[RX]["MessageData"]
        dests = [d.get("UUID", "") for d in data.get("SpecificDestinationID", [])]
        if dests and not any(_same_uuid(d, system_uuid) for d in dests):
            raise NotAddressed(f"not addressed to {system_uuid}: {dests}")
        raw = bytes.fromhex(data["EncodedPayload"])
        if not raw.isascii():
            raise EnvelopeError("EncodedPayload is not ASCII")
        try:
            root = etree.fromstring(raw, parser=etree.XMLParser(resolve_entities=False, no_network=True))
            self.codec.validate_xml(root)
            inner = self.codec.xml_to_json(root)
        except (etree.XMLSyntaxError, InvalidMessage, ValueError, KeyError) as exc:
            raise EnvelopeError(f"inner message invalid: {exc}") from exc
        (name,) = inner
        if data["MessageType"] != self.message_type(name):
            raise EnvelopeError(f"MessageType {data['MessageType']} does not match inner {name}")
        return name, inner

    def rx(self, inner: dict, originator: str, receiver: str, destinations: list[str] = ()) -> dict:
        """시험·외부 흉내용: 내부 메시지를 `MA_RxDataPayload`로 싼다(외부 쪽 CAL이 하는 일)"""
        (name, body), = inner.items()
        hdr = dict(body["MessageHeader"])
        hdr["SystemID"] = {"UUID": receiver}
        data = {"RxDataPayloadID": {"UUID": str(uuid.uuid4())}, "DataPayloadOriginatorID": {"UUID": originator},
                "EncodedPayload": self.inner_xml(inner).hex().upper(), "Timestamp": hdr["Timestamp"],
                "MessageType": self.message_type(name), "DestinationRouting": self.routing}
        if destinations:
            data["SpecificDestinationID"] = [{"UUID": u} for u in destinations]
        return {RX: {"SecurityInformation": body["SecurityInformation"], "MessageHeader": hdr, "MessageData": data}}

    def open_tx(self, env: dict) -> tuple[str, dict]:
        """시험·적합성 점검용: `MA_TxDataPayloadCommand`(OMS JSON) → (내부 이름, 내부 OMS JSON). 봉투·내부 모두 검증"""
        if set(env) != {TX}:
            raise EnvelopeError(f"not {TX}: {sorted(env)}")
        self.codec.validate_xml(self.codec.json_to_xml(env))
        data = env[TX]["MessageData"]
        root = etree.fromstring(bytes.fromhex(data["EncodedPayload"]))
        self.codec.validate_xml(root)
        inner = self.codec.xml_to_json(root)
        (name,) = inner
        if data["MessageType"] != self.message_type(name):
            raise EnvelopeError(f"MessageType {data['MessageType']} does not match inner {name}")
        return name, inner
