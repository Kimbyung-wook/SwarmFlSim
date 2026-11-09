"""A-GRA Gateway 본체 (IMP-GW-009, IMP-GW-010, DEC-068).

Gateway는 지상 참여자다. GCS 엔티티의 `swarm/<gcs>/rx/**`만 구독하고, `swarm/<gcs>/tx/c2/<msg>`와 `swarm/<gcs>/tx/mp/<msg>`에만 발행한다.
`truth/**`, `onboard/**`, `link/**`는 구독하지도 발행하지도 않는다.

- 1단계(발행): rx LinkEnvelope → 매핑 표(STD만) → 변환기 → UCI OMS JSON → XML → XSD 검증 → LA-CAL PUB
- 2단계(수신): LA-CAL MSG(외부 C2·MP, STD) → XSD 검증 → 변환기 → 내부 proto → tx/c2 또는 tx/mp LinkEnvelope
검증·변환에 실패한 메시지는 보내지 않고 로그와 카운터에 남긴다. Gateway는 계속 동작한다.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from google.protobuf.message import DecodeError
from swarm.v1 import link_pb2, options_pb2
from swarm_api import keys
from swarm_api.bus import Bus, Sample, protobuf_encoding

from .converters import (AlsoConverter, ConvContext, ConversionError, Converter, load_also_converters,
                         load_converters)
from .ids import IdMap
from .lacal import SCHEMA_VERSION, InvalidMessage, OmsJsonCodec, load_codec, uci_timestamp
from .mapping import EXT, SIM, STD, MappingEntry, MappingTable

log = logging.getLogger("swarm_gateway")

# LA-CAL에 연결하기 전(시험·오프라인 검증)에 쓰는 SystemID
OFFLINE_SYSTEM_UUID = "00000000-0000-4000-8000-000000000000"

DEFAULT_PARTICIPANT = "gateway-0"

# 외부 메시지를 받아 내부로 보낼 수 있는 L1 (DEC-068, DEC-076). 발행 키의 범위이기도 하다
INBOUND_L1 = (options_pb2.L1_INTERFACE_C2, options_pb2.L1_INTERFACE_MP)

Sink = Callable[[str, dict], "Awaitable[None] | None"]


@dataclass
class GatewayConfig:
    gcs: str
    participant: str = DEFAULT_PARTICIPANT   # LinkEnvelope.publisher (DEC-077)
    topic_prefix: str = "swarm"      # LA-CAL 토픽 = <prefix>.<iface>  (예: swarm.vi)
    mode: str = "SIMULATION"         # MessageHeader.Mode
    classification: str = "U"
    owner_producer: str = "USA"      # 공개 스키마 예제 값 (SecurityInformation 필수 항목)
    rejection_log: int = 200

    def __post_init__(self) -> None:
        keys.check_entity_id(self.gcs)
        keys.check_entity_id(self.participant)

    def topic(self, iface: str) -> str:
        return f"{self.topic_prefix}.{iface}"


@dataclass
class Outcome:
    """메시지 한 건의 처리 결과 (시험·로그용)"""
    status: str                      # exported | skipped_ext | skipped_sim | unmapped | rejected | published
    proto: str = ""
    uci_name: str = ""
    reason: str = ""
    topic: str = ""
    key: str = ""
    message: dict | None = field(default=None, repr=False)
    also: list["Outcome"] = field(default_factory=list, repr=False)  # uci_also 결과 (DEC-072)


class Gateway:
    def __init__(self, bus: Bus, config: GatewayConfig, *, table: MappingTable | None = None,
                 converters: dict[str, Converter] | None = None,
                 also_converters: dict[str, AlsoConverter] | None = None, codec: OmsJsonCodec | None = None,
                 sink: Sink | None = None, ids: IdMap | None = None):
        self.bus = bus
        self.config = config
        self.table = table or MappingTable.from_descriptors()
        self.converters = converters if converters is not None else load_converters()
        self.also_converters = also_converters if also_converters is not None else load_also_converters()
        self.codec = codec or load_codec()
        self.ids = ids or IdMap()
        self.ctx = ConvContext(ids=self.ids, gcs=config.gcs)
        self.sink = sink
        self.system_uuid = OFFLINE_SYSTEM_UUID
        self.counters: Counter[str] = Counter()
        self.rejections: deque[Outcome] = deque(maxlen=config.rejection_log)
        self._subs: list = []
        self._tx_seq: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._outbox: asyncio.Queue | None = None
        self._check_converters()

    # ------------------------------------------------------------------ 매핑
    def _check_converters(self) -> None:
        """변환기는 있는데 매핑 표가 STD가 아니면 쓰지 않는다 (DEC-014)"""
        for name in list(self.converters):
            entry = self.table.by_full_name(name)
            if entry is None or not entry.exportable:
                log.warning("converter %s ignored: not an STD message in proto options", name)
                del self.converters[name]
            elif self.codec.global_element(entry.uci_name) is None:
                log.warning("converter %s ignored: %s not in XSD", name, entry.uci_name)
                del self.converters[name]
        used_also = {u for e in self.table.exportable() for u in e.uci_targets[1:]}
        for uci in list(self.also_converters):
            if uci not in used_also:
                log.info("uci_also converter %s unused: no proto lists it in (uci_also)", uci)
            if self.codec.global_element(uci) is None:
                log.warning("uci_also converter %s ignored: not in XSD", uci)
                del self.also_converters[uci]

    def export_entries(self) -> list[MappingEntry]:
        return [e for e in self.table.exportable()
                if e.full_name in self.converters and self.converters[e.full_name].supports_export()]

    def export_targets(self) -> list[tuple[MappingEntry, str]]:
        """(내부 메시지, UCI 메시지) 중 변환기가 있는 것: uci_name과 uci_also 모두 (DEC-072)"""
        return [(e, u) for e in self.table.exportable() for u in e.uci_targets if self.converter_for(e, u)]

    def import_entries(self) -> list[MappingEntry]:
        """외부 C2·MP로 받을 수 있는 STD 메시지 (2단계)"""
        return [e for e in self.table.exportable()
                if e.l1 in INBOUND_L1 and e.full_name in self.converters
                and self.converters[e.full_name].supports_import()]

    def import_names(self) -> list[str]:
        return sorted({e.uci_name for e in self.import_entries()})

    # ------------------------------------------------------------------ 수명
    def start(self) -> None:
        """버스 구독: swarm/<gcs>/rx/** 하나뿐이다"""
        try:
            self._loop = asyncio.get_running_loop()
            self._outbox = asyncio.Queue()
        except RuntimeError:
            self._loop = None
        self._subs.append(self.bus.subscribe(keys.rx_all(self.config.gcs), self._on_sample))
        log.info("gateway %s: subscribed %s; export %d UCI targets, import %s", self.config.gcs,
                 keys.rx_all(self.config.gcs), len(self.export_targets()), self.import_names())

    def close(self) -> None:
        for s in self._subs:
            s.close()
        self._subs.clear()

    # ------------------------------------------------------------------ UCI 봉투·검증
    def envelope(self, uci_name: str, data: dict) -> dict:
        return {uci_name: {
            "SecurityInformation": {"Classification": self.config.classification,
                                    "OwnerProducer": [{"GovernmentIdentifier": self.config.owner_producer}]},
            "MessageHeader": {"SystemID": {"UUID": self.system_uuid}, "Timestamp": uci_timestamp(self.ctx.now()),
                              "SchemaVersion": SCHEMA_VERSION, "Mode": self.config.mode},
            "MessageData": data,
        }}

    def to_xml(self, obj: dict) -> bytes:
        """OMS JSON → UCI XML. XSD 검증에 실패하면 InvalidMessage"""
        return self.codec.to_xml_bytes(obj)

    # ------------------------------------------------------------------ 1단계: 발행
    def _on_sample(self, sample: Sample) -> None:
        try:
            self.handle_rx(sample.key, sample.payload)
        except Exception:  # 어떤 입력에도 Gateway는 계속 동작한다
            self.counters["internal_error"] += 1
            log.exception("gateway: unexpected error on %s", sample.key)

    def handle_rx(self, key: str, payload: bytes) -> Outcome:
        self.counters["rx"] += 1
        env = link_pb2.LinkEnvelope()
        try:
            env.ParseFromString(payload)
        except DecodeError as exc:
            return self._reject(Outcome("rejected", key=key, reason=f"bad LinkEnvelope: {exc}"))
        entry = self.table.by_full_name(env.msg_type)
        if entry is None:
            return self._reject(Outcome("unmapped", proto=env.msg_type, key=key, reason="unknown msg_type"))
        if entry.mapping == EXT:
            self.counters["skipped_ext"] += 1
            return Outcome("skipped_ext", proto=entry.full_name, key=key)
        if entry.mapping != STD or not entry.uci_name:
            self.counters["skipped_sim" if entry.mapping == SIM else "unmapped"] += 1
            return Outcome("skipped_sim" if entry.mapping == SIM else "unmapped", proto=entry.full_name, key=key)
        if entry.uci_name in self.import_names():  # 외부에서 받는 명령은 되돌려 보내지 않는다
            self.counters["skipped_inbound_kind"] += 1
            return Outcome("skipped_inbound_kind", proto=entry.full_name, uci_name=entry.uci_name, key=key)
        msg = entry.new_message()
        try:
            msg.ParseFromString(env.payload)
        except DecodeError as exc:
            return self._reject(Outcome("rejected", proto=entry.full_name, uci_name=entry.uci_name, key=key,
                                        reason=f"bad payload: {exc}"))
        if not msg.header.source:
            msg.header.source = env.header.source
        # uci_name과 uci_also 각각을 따로 변환·검증·발행한다 (DEC-072). 하나가 실패해도 나머지는 나간다
        outcomes = [self._export_one(entry, uci, msg, key) for uci in entry.uci_targets]
        first = outcomes[0]
        first.also = outcomes[1:]
        return first

    def converter_for(self, entry: MappingEntry, uci: str) -> Converter | None:
        if uci == entry.uci_name:
            conv = self.converters.get(entry.full_name)
        else:
            conv = self.also_converters.get(uci)
            if conv is not None and not conv.accepts(entry.full_name):
                conv = None
        return conv if conv is not None and conv.supports_export() else None

    def _export_one(self, entry: MappingEntry, uci: str, msg, key: str) -> Outcome:
        conv = self.converter_for(entry, uci)
        if conv is None:
            return self._reject(Outcome("unmapped", proto=entry.full_name, uci_name=uci, key=key,
                                        reason="no converter"))
        try:
            obj = self.envelope(uci, conv.to_uci(msg, self.ctx))
            self.to_xml(obj)
        except (ConversionError, InvalidMessage, ValueError, TypeError, KeyError) as exc:
            self.counters["invalid"] += 1
            return self._reject(Outcome("rejected", proto=entry.full_name, uci_name=uci, key=key,
                                        reason=f"{type(exc).__name__}: {exc}"))
        topic = self.config.topic(entry.iface)
        self.counters["exported"] += 1
        self.counters[f"exported.{uci}"] += 1
        self._emit(topic, obj)
        return Outcome("exported", proto=entry.full_name, uci_name=uci, topic=topic, key=key, message=obj)

    def _emit(self, topic: str, obj: dict) -> None:
        if self._outbox is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._outbox.put_nowait, (topic, obj))
        elif self.sink is not None:
            res = self.sink(topic, obj)
            if asyncio.iscoroutine(res):
                res.close()
                raise RuntimeError("async sink needs Gateway.start() inside an event loop")

    async def run_sender(self) -> None:
        """outbox → sink(LA-CAL PUB). 전송 오류는 세고 계속한다"""
        assert self._outbox is not None, "start() inside an event loop first"
        while True:
            topic, obj = await self._outbox.get()
            try:
                res = self.sink(topic, obj) if self.sink else None
                if asyncio.iscoroutine(res):
                    await res
                self.counters["sent"] += 1
            except Exception as exc:  # CalError 포함
                self.counters["send_failed"] += 1
                self._reject(Outcome("send_failed", uci_name=next(iter(obj)), topic=topic, reason=str(exc)))

    async def drain(self) -> None:
        """시험용: outbox가 빌 때까지 기다린다"""
        if self._outbox is None:
            return
        while not self._outbox.empty():
            await asyncio.sleep(0.01)

    # ------------------------------------------------------------------ 2단계: 수신
    def handle_external(self, uci_name: str, obj: dict) -> Outcome:
        """LA-CAL에서 받은 외부 메시지. 검증 → 변환 → swarm/<gcs>/tx/<c2|mp>/<msg>"""
        self.counters["ext_rx"] += 1
        candidates = [e for e in self.import_entries() if e.uci_name == uci_name]
        if not candidates:
            return self._reject(Outcome("rejected", uci_name=uci_name, reason="no inbound mapping (STD C2/MP)"))
        try:
            if set(obj) != {uci_name}:
                raise InvalidMessage(f"message name mismatch: {sorted(obj)}")
            self.codec.validate_xml(self.codec.json_to_xml(obj))
        except (InvalidMessage, ValueError, TypeError, KeyError) as exc:
            self.counters["ext_invalid"] += 1
            return self._reject(Outcome("rejected", uci_name=uci_name, reason=f"invalid: {exc}"))
        data = obj[uci_name].get("MessageData", {})
        errors = []
        for entry in candidates:
            try:
                result = self.converters[entry.full_name].from_uci(data, self.ctx)
            except (ConversionError, ValueError, TypeError, KeyError) as exc:
                errors.append(f"{entry.short_name}: {exc}")
                continue
            if result is None:
                continue
            msg, dst = result
            key = self.publish_inbound(entry, msg, dst)
            self.counters["ext_published"] += 1
            return Outcome("published", proto=entry.full_name, uci_name=uci_name, key=key)
        self.counters["ext_rejected"] += 1
        return self._reject(Outcome("rejected", uci_name=uci_name, reason="; ".join(errors) or "not convertible"))

    def publish_inbound(self, entry: MappingEntry, msg, dst: list[str]) -> str:
        """GCS가 보내는 C2·MP처럼 tx에 싣는다. Datalink가 기체로 전달한다. seq는 발행자·키별이다 (DEC-077)"""
        if entry.l1 not in INBOUND_L1:
            raise ValueError(f"{entry.short_name}: gateway publishes only c2/mp")
        key = keys.tx(self.config.gcs, keys.Iface(entry.iface), entry.short_name)
        seq = self._tx_seq.get(key, 0)
        self._tx_seq[key] = seq + 1
        msg.header.source = self.config.gcs
        msg.header.seq = seq
        env = link_pb2.LinkEnvelope(dst=list(dst), iface=entry.l1, msg_type=entry.full_name,
                                    payload=msg.SerializeToString(), priority=0, publisher=self.config.participant)
        env.header.source = self.config.gcs
        env.header.seq = seq
        self.bus.put(key, env.SerializeToString(), protobuf_encoding(env.DESCRIPTOR.full_name))
        return key

    # ------------------------------------------------------------------
    def _reject(self, out: Outcome) -> Outcome:
        self.counters["rejected" if out.status != "unmapped" else "unmapped"] += 1
        self.rejections.append(out)
        log.warning("gateway %s: %s %s %s: %s", out.status, out.proto or "-", out.uci_name or "-",
                    out.key or out.topic, out.reason)
        return out
