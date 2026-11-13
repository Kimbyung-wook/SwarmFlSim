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

    # ordered=True: 이 버스의 ordered 구독 콜백은 모두 수신 스레드 하나에서 링크 도착 순서대로 불린다 (DEC-083).
    # 콜백이 수신을 막으므로 큐에 넣기만 하는 짧은 콜백에만 쓴다
    def subscribe(self, keyexpr: str, callback: Callable[[Sample], None], *, ordered: bool = False) -> Subscription: ...

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

    def subscribe(self, keyexpr: str, callback: Callable[[Sample], None], *, ordered: bool = False) -> Subscription:
        # put 안에서 바로 부르므로 늘 순서대로다. ordered는 받기만 한다
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


# DEC-043: lockstep 장벽과 데이터링크 경로
LOCKSTEP_PATH_PREFIXES = ("sim/clock/", "swarm/")


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
        self._zenoh = zenoh

    def put(self, key: str, payload: bytes, encoding: str) -> None:
        if "*" in key:
            raise ValueError(f"wildcard in put key: {key!r}")
        # DEC-043: lockstep 경로 키는 같은 우선순위·BLOCK으로 보내 혼잡 시 버리지 않고 링크 큐 하나의 순서를 지킨다
        congestion = (
            self._zenoh.CongestionControl.BLOCK
            if key.startswith(LOCKSTEP_PATH_PREFIXES)
            else self._zenoh.CongestionControl.DROP
        )
        self._session.put(
            key,
            payload,
            encoding=encoding or None,
            priority=self._zenoh.Priority.DATA,
            congestion_control=congestion,
            express=False,
        )

    def subscribe(self, keyexpr: str, callback: Callable[[Sample], None], *, ordered: bool = False) -> Subscription:
        def on_sample(z: Any) -> None:
            callback(Sample(str(z.key_expr), z.payload.to_bytes(), str(z.encoding)))

        # zenoh-python 기본(indirect=True)은 구독마다 다른 스레드에서 콜백을 불러 구독 간 순서가 깨진다.
        # ordered면 수신 스레드에서 바로 불러 C++ 버스와 같은 순서를 지킨다 (DEC-083, D-33).
        # indirect는 zenoh-python에서 unstable 표시다. 버전을 올릴 때 TC-API-008로 확인한다
        handler = self._zenoh.handlers.Callback(on_sample, indirect=False) if ordered else on_sample
        return _ZenohSubscription(self._session.declare_subscriber(keyexpr, handler))

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
