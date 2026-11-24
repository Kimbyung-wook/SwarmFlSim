"""외부 `QueryDataRequest` 응답 (IMP-GW-038, DEC-112).

Gateway가 이미 내보낸 메시지의 기체별 최신 값으로 답한다. MA·런타임에는 묻지 않는다.

- 최신 값: XSD 검증을 통과해 내보낸 UCI 메시지(봉투 전 내부 메시지)를 (UCI 이름, 보고 기체, 키)마다 마지막 것 하나.
  키는 변화 보고 보관 규칙(`retain.RETAINED`, 예: TaskStatus는 작업 ID)을 쓰고, 그 밖은 기체당 하나다.
- 응답 순서: `QueryDataRequestStatus` PROCESSING(받아 처리 중)을 먼저 내고, 이어서 끝 상태를 낸다.
  - COMPLETED: `Result.Message`에 맞는 최신 값(`$type` = `<이름>MT`). 값이 아직 없으면 Result 없이 COMPLETED.
  - REJECTED: 답할 수 없는 조회. `RequestProcessingStateReason`(CannotComply)에 사유를 싣는다.
  - CANCEL 요청은 처리 중인 것이 없으므로 CANCELED 하나만 낸다.
- 답할 수 있는 조회: `QueryMessage.MessageType`이 모두 Gateway가 내보내는 메시지(비우면 내보내는 것 전부).
  `MessageData.SystemID`가 있으면 우리 시스템 UUID일 때만 값을 싣는다(다른 시스템이면 COMPLETED, 결과 없음).
  `QueryResultLimit`은 결과 수 상한으로 쓰고, 최신 값만 있으므로 `MostRecentMessagesOnly`는 그대로 만족한다.
- 거부(REJECTED, 사유 INVALID_INPUT_PARAMETER 또는 CAPABILITY_UNAVAILABLE): 내보내지 않는 메시지 종류,
  조건식(`QueryMessage.Query`), ID만 조회(`QueryIdentifiersOnly`), 원형 결과 배달(`ResultsInNative`), 페이지 나눔(`ResultsPerPage`가
  결과 수보다 작을 때).
"""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from typing import Callable

from google.protobuf.message import Message

from .envelope import message_type_name
from .retain import RETAINED

QUERY = "QueryDataRequest"
QUERY_STATUS = "QueryDataRequestStatus"


class LatestValues:
    """(UCI 이름, 보고 기체, 키) → 마지막으로 내보낸 OMS JSON. 버스 스레드와 이벤트 루프가 함께 쓴다"""

    def __init__(self, limit: int = 4096):
        self.limit = limit
        self._items: OrderedDict[tuple, dict] = OrderedDict()
        self._lock = threading.Lock()

    def note(self, full_name: str, uci: str, msg: Message, obj: dict) -> None:
        rule = RETAINED.get(full_name)
        k = (uci, msg.header.source, full_name, rule.key(msg) if rule else ())
        with self._lock:
            self._items.pop(k, None)
            self._items[k] = obj
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def latest(self, names: set[str]) -> list[dict]:
        """이름이 names에 드는 최신 값, 오래된 것부터"""
        with self._lock:
            return [o for (u, *_), o in self._items.items() if u in names]

    def __len__(self) -> int:
        return len(self._items)


def _status_data(request_id: dict, state: str, *, reason: str = "", why: str = "", results: list[dict] = ()) -> dict:
    data: dict = {"RequestID": request_id, "RequestProcessingState": state}
    if reason:
        data["RequestProcessingStateReason"] = {"Reason": reason, "Description": why[:1024]}
    if results:
        data["Result"] = {"Message": list(results)}
    return data


def answer(data: dict, *, exported: set[str], store: LatestValues, system_uuid: str, type_key: Callable[[str], str],
           limit: int = 256) -> list[tuple[str, dict]]:
    """`QueryDataRequest`의 MessageData → [(상태, `QueryDataRequestStatus` MessageData)]. 내보낼 순서대로.
    type_key: UCI 메시지 이름 → 그 전역 요소의 XSD 형식 이름(`Result.Message`의 `$type`, 예 `MA_TaskStatusMT`)"""
    rid = data["RequestID"]
    if data.get("RequestState") == "CANCEL":
        return [("CANCELED", _status_data(rid, "CANCELED"))]
    out = [("PROCESSING", _status_data(rid, "PROCESSING"))]
    qm = data.get("QueryMessage", {})
    by_type = {message_type_name(n): n for n in exported}
    asked = list(qm.get("MessageType", []))
    unknown = sorted(t for t in asked if t not in by_type)
    unsupported = [f for f, present in (("Query condition", "Query" in qm),
                                         ("QueryIdentifiersOnly", "QueryIdentifiersOnly" in data),
                                         ("ResultsInNative", bool(data.get("ResultsInNative")))) if present]
    if unknown:
        why = "not exported by this system: " + ", ".join(unknown)
        return out + [("REJECTED", _status_data(rid, "REJECTED", reason="CAPABILITY_UNAVAILABLE", why=why))]
    if unsupported:
        why = "not supported: " + ", ".join(unsupported)
        return out + [("REJECTED", _status_data(rid, "REJECTED", reason="INVALID_INPUT_PARAMETER", why=why))]
    names = {by_type[t] for t in asked} if asked else set(exported)
    sysid = data.get("SystemID", {}).get("UUID")
    found = [] if sysid and uuid.UUID(sysid) != uuid.UUID(system_uuid) else store.latest(names)
    cap = min(limit, int(data.get("QueryResultLimit", limit)))
    found = found[-cap:]
    per_page = data.get("ResultsPerPage")
    if per_page is not None and int(per_page) < len(found):
        why = f"paging not supported: {len(found)} results, ResultsPerPage {per_page}"
        return out + [("REJECTED", _status_data(rid, "REJECTED", reason="INVALID_INPUT_PARAMETER", why=why))]
    results = []
    for obj in found:
        (name, body), = obj.items()
        results.append({"$type": type_key(name), **body})
    return out + [("COMPLETED", _status_data(rid, "COMPLETED", results=results))]
