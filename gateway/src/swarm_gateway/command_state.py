"""외부 명령 상태의 UCI Command-2 상태 기계 (IMP-GW-032, DEC-097).

`MessageData`에 `CommandID`와 `CommandProcessingState`가 있는 UCI 메시지(`MA_FlightCommandStatus` 등
`MA_*CommandStatus`)에 적용한다. 메시지 이름을 하드코딩하지 않고 내보낼 OMS JSON 구조로 판단한다.

- 첫 보고: RECEIVED·ACCEPTED·REJECTED·CANCELED 모두 낸다(접수 전 대체의 첫 CANCELED 포함).
- RECEIVED 뒤: ACCEPTED·REJECTED·CANCELED만 낸다. RECEIVED 반복은 내지 않는다.
- 끝 상태(ACCEPTED·REJECTED·CANCELED)를 낸 뒤: 그 CommandID의 상태는 더 내지 않는다(같은 끝 상태 반복 포함).

키는 (UCI 메시지, 보고 기체(내부 `header.source`), CommandID)다. 기억은 프로세스 안에만 있어 Gateway가 재기동하면
비어 있다. 재기동 뒤 처음 보는 CommandID의 보고는 첫 보고로 보고 낸다(README "명령 상태").
"""
from __future__ import annotations

import threading
from collections import OrderedDict

TERMINAL = frozenset({"ACCEPTED", "REJECTED", "CANCELED"})
RECEIVED = "RECEIVED"


def command_key(uci: str, obj: dict, source: str = "") -> tuple[tuple, str] | None:
    """(키, 상태). 명령 상태 메시지가 아니면 None"""
    body = obj.get(uci) or {}
    data = body.get("MessageData") or {}
    state = data.get("CommandProcessingState")
    cid = data.get("CommandID")
    if state is None or not isinstance(cid, dict):
        return None
    return (uci, source, cid.get("UUID") or cid.get("DescriptiveLabel", "")), state


class CommandStateGate:
    """CommandID별 마지막으로 낸 상태. 버스 스레드에서 쓴다"""

    def __init__(self, limit: int = 65536):
        self.limit = limit
        self._last: OrderedDict[tuple, str] = OrderedDict()
        self._lock = threading.Lock()

    def admit(self, uci: str, obj: dict, source: str = "") -> tuple[bool, str]:
        """(낼지, 사유). 낸다고 답하면 그 상태를 기억한다"""
        found = command_key(uci, obj, source)
        if found is None:
            return True, ""
        key, state = found
        with self._lock:
            last = self._last.get(key)
            if last in TERMINAL:
                return False, f"after terminal {last}"
            if last == RECEIVED and state == RECEIVED:
                return False, "repeated RECEIVED"
            self._last[key] = state
            self._last.move_to_end(key)
            while len(self._last) > self.limit:
                self._last.popitem(last=False)
        return True, ""

    def last(self, uci: str, obj: dict, source: str = "") -> str | None:
        found = command_key(uci, obj, source)
        with self._lock:
            return self._last.get(found[0]) if found else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._last)
