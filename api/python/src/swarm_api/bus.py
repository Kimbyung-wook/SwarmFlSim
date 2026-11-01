"""ASB(Abstract Service Bus) 계약 (PRP-NET-001).

Zenoh 백엔드는 WP1이 구현한다. InMemoryBus는 각 WP의 단독 시험용이다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

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
