"""ASB(Abstract Service Bus) 계약 (PRP-NET-001).

InMemoryBus는 각 WP의 단독 시험용이다. 프로세스 간 통신은 open_bus()로 Zenoh 백엔드를 연다 (DEC-026).
Zenoh 백엔드는 선택 의존성이다: uv sync --extra zenoh (eclipse-zenoh)
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .keys import keyexpr_matches


@dataclass(frozen=True)
class Sample:
    key: str
    payload: bytes
    encoding: str  # 예: "application/protobuf;swarm.v1.LinkEnvelope"


class Subscription(Protocol):
    def close(self) -> None: ...


class Bus(Protocol):
    def put(self, key: str, payload: bytes, encoding: str) -> None: ...

    def subscribe(self, keyexpr: str, callback: Callable[[Sample], None]) -> Subscription: ...

    def close(self) -> None: ...


def protobuf_encoding(full_name: str) -> str:
    return f"application/protobuf;{full_name}"


class _InMemorySubscription:
    def __init__(self, bus: "InMemoryBus", keyexpr: str, callback: Callable[[Sample], None]):
        self._bus = bus
        self.keyexpr = keyexpr
        self.callback = callback

    def close(self) -> None:
        self._bus._subs.discard(self)


class InMemoryBus:
    """동기식 단일 프로세스 버스. put 안에서 일치하는 구독 콜백을 바로 호출한다."""

    def __init__(self) -> None:
        self._subs: set[_InMemorySubscription] = set()

    def put(self, key: str, payload: bytes, encoding: str) -> None:
        if "*" in key:
            raise ValueError(f"wildcard in put key: {key!r}")
        sample = Sample(key, payload, encoding)
        for sub in list(self._subs):
            if keyexpr_matches(sub.keyexpr, key):
                sub.callback(sample)

    def subscribe(self, keyexpr: str, callback: Callable[[Sample], None]) -> Subscription:
        sub = _InMemorySubscription(self, keyexpr, callback)
        self._subs.add(sub)
        return sub

    def close(self) -> None:
        self._subs.clear()


class _ZenohSubscription:
    def __init__(self, sub: Any):
        self._sub = sub

    def close(self) -> None:
        if self._sub is not None:
            self._sub.undeclare()
            self._sub = None


class ZenohBus:
    """Zenoh 백엔드. 구독 콜백은 Zenoh 내부 스레드에서 호출된다."""

    def __init__(self, config: "BusConfig"):
        import zenoh

        conf = zenoh.Config.from_file(config.zenoh_config_file) if config.zenoh_config_file else zenoh.Config()
        if config.zenoh_mode:
            conf.insert_json5("mode", json.dumps(config.zenoh_mode))
        if config.connect:
            conf.insert_json5("connect/endpoints", json.dumps(list(config.connect)))
        if config.listen:
            conf.insert_json5("listen/endpoints", json.dumps(list(config.listen)))
        if not config.multicast_scouting:
            conf.insert_json5("scouting/multicast/enabled", "false")
        self._session = zenoh.open(conf)

    def put(self, key: str, payload: bytes, encoding: str) -> None:
        if "*" in key:
            raise ValueError(f"wildcard in put key: {key!r}")
        self._session.put(key, payload, encoding=encoding or None)

    def subscribe(self, keyexpr: str, callback: Callable[[Sample], None]) -> Subscription:
        def on_sample(z: Any) -> None:
            callback(Sample(str(z.key_expr), z.payload.to_bytes(), str(z.encoding)))

        return _ZenohSubscription(self._session.declare_subscriber(keyexpr, on_sample))

    def close(self) -> None:
        self._session.close()


@dataclass
class BusConfig:
    """C++ swarm::bus::BusConfig와 같은 항목 (DEC-026)"""

    backend: str = ""  # "zenoh" | "memory". 비우면 default_backend()
    zenoh_config_file: str = ""
    zenoh_mode: str = ""  # peer | client | router
    connect: Sequence[str] = field(default_factory=list)
    listen: Sequence[str] = field(default_factory=list)
    multicast_scouting: bool = True


def zenoh_available() -> bool:
    try:
        import zenoh  # noqa: F401
    except ImportError:
        return False
    return True


def default_backend() -> str:
    return "zenoh" if zenoh_available() else "memory"


def open_bus(config: BusConfig | None = None) -> Bus:
    """버스를 연다. 지원하지 않는 백엔드면 ValueError"""
    config = config or BusConfig()
    backend = config.backend or default_backend()
    if backend == "memory":
        return InMemoryBus()
    if backend == "zenoh" and zenoh_available():
        return ZenohBus(config)
    available = "zenoh, memory" if zenoh_available() else "memory"
    raise ValueError(f"unsupported bus backend: {backend} (available: {available})")
