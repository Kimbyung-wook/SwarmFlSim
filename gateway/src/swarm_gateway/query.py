"""외부 `QueryDataRequest` 응답 (IMP-GW-038·039, DEC-112).

Gateway가 이미 내보낸 메시지의 기체별 최신 값으로 답한다. MA·런타임에는 묻지 않는다.
상태 값의 뜻은 6.0a XSD 주석(`RequestProcessingStateEnum`, `QueryDataRequestMDT`·`StatusMDT`)을 따른다.

- 최신 값: XSD 검증을 통과해 내보낸 UCI 메시지(봉투 전 내부 메시지)를 (UCI 이름, 보고 기체, 키)마다 마지막 것 하나.
  키는 변화 보고 보관 규칙(`retain.RETAINED`, 예: TaskStatus는 작업 ID)을 쓰고, 그 밖은 기체당 하나다.
- NEW·UPDATE: PROCESSING("initiated and still processing")을 먼저 내고 COMPLETED를 낸다.
  - 결과는 `Result.Message`(`$type` = 그 메시지의 XSD 형식 이름). 결과가 없으면 Result를 비운다(XSD 주석).
  - `ResultsPerPage`가 결과 수보다 작으면 여러 COMPLETED 상태로 나누고 각각 `QueryPagination`(현재·전체 쪽)을 싣는다.
  - `ResultsInNative`에 든 종류는 결과를 상태에 담지 않고 그 메시지 자체로 평소 토픽에 다시 낸다("native" 배달).
    `ReceiverAddress`는 따로 주소를 정할 수단이 없어 평소 토픽으로 갈음한다.
  - `QueryResultLimit`은 상한, `MostRecentMessagesOnly`는 최신 값만 있으므로 그대로 만족한다.
  - `MessageData.SystemID`는 "요청한 시스템"이라 거르지 않는다.
- REJECTED("rejected by the recipient and will not be processed"): 처리하지 않으므로 이것 하나만 낸다.
  내보내지 않는 종류(CAPABILITY_UNAVAILABLE), 조건식 `Query`·`QueryIdentifiersOnly`(INVALID_INPUT_PARAMETER).
- CANCEL: 조회는 받자마자 끝나 처리 중인 것이 없다.
  - 받은 적이 없는 RequestID → REJECTED, 사유 UNKNOWN_ID.
  - 이미 끝난 RequestID → 그 끝 상태를 다시 알린다(끝 상태 뒤에 다른 상태를 내지 않는다).
"""
from __future__ import annotations

import math
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from google.protobuf.message import Message

from .envelope import message_type_name
from .retain import RETAINED

QUERY = "QueryDataRequest"
QUERY_STATUS = "QueryDataRequestStatus"


class LatestValues:
    """(UCI 이름, 보고 기체, 키) → (토픽, 마지막으로 내보낸 OMS JSON). 버스 스레드와 이벤트 루프가 함께 쓴다"""

    def __init__(self, limit: int = 4096):
        self.limit = limit
        self._items: OrderedDict[tuple, tuple[str, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def note(self, full_name: str, uci: str, topic: str, msg: Message, obj: dict) -> None:
        rule = RETAINED.get(full_name)
        k = (uci, topic, msg.header.source, full_name, rule.key(msg) if rule else ())
        with self._lock:
            self._items.pop(k, None)
            self._items[k] = (topic, obj)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def latest(self, names: set[str]) -> list[tuple[str, dict]]:
        """이름이 names에 드는 (토픽, 최신 값), 오래된 것부터"""
        with self._lock:
            return [v for (u, *_), v in self._items.items() if u in names]

    def __len__(self) -> int:
        return len(self._items)


class QueryLedger:
    """받은 RequestID → 끝 상태. CANCEL 응답에 쓴다"""

    def __init__(self, limit: int = 1024):
        self.limit = limit
        self._done: OrderedDict[uuid.UUID, str] = OrderedDict()
        self._lock = threading.Lock()

    def finish(self, rid: str, state: str) -> None:
        with self._lock:
            k = uuid.UUID(rid)
            self._done.pop(k, None)
            self._done[k] = state
            while len(self._done) > self.limit:
                self._done.popitem(last=False)

    def final(self, rid: str) -> str | None:
        with self._lock:
            return self._done.get(uuid.UUID(rid))


@dataclass
class Emit:
    """응답으로 낼 것 하나: 상태(state, MessageData) 또는 원형 메시지(topic, obj)"""
    state: str = ""
    data: dict | None = None
    topic: str = ""
    native: dict | None = None


def _status(request_id: dict, state: str, *, reason: str = "", why: str = "", results: list[dict] = (),
            page: tuple[int, int] | None = None) -> Emit:
    data: dict = {"RequestID": request_id, "RequestProcessingState": state}
    if reason:
        data["RequestProcessingStateReason"] = {"Reason": reason, "Description": why[:1024]}
    if results:
        data["Result"] = {"Message": list(results)}
    if page:
        data["QueryPagination"] = {"CurrentPage": page[0], "TotalPages": page[1]}
    return Emit(state, data)


def answer(data: dict, *, exported: set[str], store: LatestValues, ledger: QueryLedger,
           type_key: Callable[[str], str], limit: int = 256) -> list[Emit]:
    """`QueryDataRequest`의 MessageData → 낼 것 목록(순서대로).
    type_key: UCI 메시지 이름 → 그 전역 요소의 XSD 형식 이름(`Result.Message`의 `$type`, 예 `MA_TaskStatusMT`)"""
    rid = data["RequestID"]
    if data.get("RequestState") == "CANCEL":
        done = ledger.final(rid["UUID"])
        if done is None:
            return [_status(rid, "REJECTED", reason="UNKNOWN_ID", why="no such query request to cancel")]
        return [_status(rid, done)]                       # 이미 끝났다: 끝 상태를 다시 알린다
    qm = data.get("QueryMessage", {})
    by_type = {message_type_name(n): n for n in exported}
    asked = list(qm.get("MessageType", []))
    unknown = sorted(t for t in asked if t not in by_type)
    unsupported = [f for f, present in (("Query condition", "Query" in qm),
                                         ("QueryIdentifiersOnly", "QueryIdentifiersOnly" in data)) if present]
    native_types = [p["MessageType"] for p in data.get("ResultsInNative", [])]
    unknown += sorted(t for t in native_types if t not in by_type and t not in unknown)
    if unknown:
        out = [_status(rid, "REJECTED", reason="CAPABILITY_UNAVAILABLE",
                       why="not exported by this system: " + ", ".join(unknown))]
    elif unsupported:
        out = [_status(rid, "REJECTED", reason="INVALID_INPUT_PARAMETER", why="not supported: " + ", ".join(unsupported))]
    else:
        out = [_status(rid, "PROCESSING")]
        names = {by_type[t] for t in asked} if asked else set(exported)
        found = store.latest(names)
        cap = min(limit, int(data.get("QueryResultLimit", limit)))
        found = found[-cap:]
        native = {by_type[t] for t in native_types}
        results = []
        for topic, obj in found:
            (name, body), = obj.items()
            if name in native:
                out.append(Emit(topic=topic, native=obj))
            else:
                results.append({"$type": type_key(name), **body})
        per_page = int(data.get("ResultsPerPage", 0) or 0)
        if per_page and len(results) > per_page:
            pages = math.ceil(len(results) / per_page)
            out += [_status(rid, "COMPLETED", results=results[i * per_page:(i + 1) * per_page], page=(i + 1, pages))
                    for i in range(pages)]
        else:
            out.append(_status(rid, "COMPLETED", results=results))
    ledger.finish(rid["UUID"], out[-1].state)
    return out
