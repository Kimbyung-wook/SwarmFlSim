"""변화 보고 마지막 값 보관과 늦게 붙은 외부 시스템 전달 (IMP-GW-024, IMP-GW-025, DEC-089).

- 변화 보고(DEC-051·056·063·071)는 값이 바뀔 때만 나간다. 그 뒤에 구독한 외부 시스템은 다음 변화까지 현재 상태를 모른다(QA O-19).
- Gateway는 XSD 검증을 통과해 내보낸 변화 보고를 키별 마지막 값으로 들고 있다.
- 새 외부 구독이 생기면 그 (UCI 메시지, LA-CAL 토픽)에 해당하는 마지막 값을 한 번 다시 PUB한다.
  OWP 1.0에는 보관(retained) 메시지나 구독 알림이 없어, CAL Server 관리 포트의 그래프 이벤트(`/graph/events`)로
  구독 시점을 안다(agra_lacal `docs/graph_api.md`). 평소 보고량은 늘리지 않는다.

키는 Agent 변화 보고 키(`swarm_agent.reporting`)와 같은 규칙에 보고 기체를 더한 것이다.
종료 상태를 받은 키는 지운다. Agent도 종료 상태 키를 한 번 보낸 뒤 지운다(DEC-063).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from google.protobuf.message import Message
from swarm.v1 import common_pb2, ms_pb2

log = logging.getLogger("swarm_gateway")

STRIKE_TERMINAL = frozenset({ms_pb2.STRIKE_STATE_IMPACT, ms_pb2.STRIKE_STATE_MISSED, ms_pb2.STRIKE_STATE_REJECTED})
COMMAND_TERMINAL = frozenset({common_pb2.COMMAND_STATE_REJECTED, common_pb2.COMMAND_STATE_COMPLETED,
                              common_pb2.COMMAND_STATE_FAILED, common_pb2.COMMAND_STATE_CANCELLED})


@dataclass(frozen=True)
class RetainRule:
    key: Callable[[Message], tuple]
    terminal: Callable[[Message], bool] = lambda m: False


def _none(m: Message) -> tuple:
    return ()


# 보관하는 변화 보고 (내부 메시지 전체 이름 → 키 규칙). 주기 보고(NavigationReport, PeerStatus)와
# 사건성 메시지(ApprovalRequest, LeaderUpdate, TrackShare)는 넣지 않는다.
# FlightCommandStatus(MA_FlightCommandStatus)도 넣지 않는다: 외부 명령 상태는 끝 상태 뒤 다시 내지 않는다(DEC-097).
# 다시 PUB하면 OWP에 수신자 지정이 없어 기존 구독자에게 같은 CommandID 보고가 한 번 더 간다
RETAINED: dict[str, RetainRule] = {
    "swarm.v1.SystemStatus": RetainRule(_none),                                  # 기체당 하나 (DEC-071)
    "swarm.v1.FlightCapability": RetainRule(_none),                              # 시작 시 1회 (DEC-071)
    "swarm.v1.SensorActivity": RetainRule(lambda m: (m.payload_id,)),            # DEC-051, DEC-056
    "swarm.v1.JammerActivity": RetainRule(lambda m: (m.payload_id,)),
    "swarm.v1.StrikeActivity": RetainRule(lambda m: (m.payload_id, m.weapon_entity),   # DEC-063
                                          lambda m: m.state in STRIKE_TERMINAL),
    "swarm.v1.StoreLoadout": RetainRule(_none),                                  # 현재 잔량
    "swarm.v1.TaskStatus": RetainRule(lambda m: (m.task_id,), lambda m: m.state in COMMAND_TERMINAL),
}


class RetainedReports:
    """(UCI 메시지, 토픽, 내부 메시지, 보고 기체, 키) → 마지막 OMS JSON. 버스 스레드와 이벤트 루프가 함께 쓴다"""

    def __init__(self, limit: int = 4096, rules: dict[str, RetainRule] | None = None):
        self.limit = limit
        self.rules = RETAINED if rules is None else rules
        self._items: OrderedDict[tuple, dict] = OrderedDict()
        self._lock = threading.Lock()

    def retains(self, full_name: str) -> bool:
        return full_name in self.rules

    def note(self, full_name: str, uci: str, topic: str, msg: Message, obj: dict) -> None:
        rule = self.rules.get(full_name)
        if rule is None:
            return
        k = (uci, topic, full_name, msg.header.source, rule.key(msg))
        with self._lock:
            self._items.pop(k, None)
            if rule.terminal(msg):
                return
            self._items[k] = obj
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def latest(self, uci: str, topic: str) -> list[dict]:
        with self._lock:
            return [o for (u, t, *_), o in self._items.items() if u == uci and t == topic]

    def targets(self) -> set[tuple[str, str]]:
        with self._lock:
            return {(u, t) for (u, t, *_) in self._items}

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def admin_url_for(lacal_url: str, admin_port: int = 8766) -> str:
    """OWP 주소의 호스트에 agra_lacal 기본 관리 포트를 붙인다"""
    parts = urlsplit(lacal_url)
    scheme = "wss" if parts.scheme == "wss" else "ws"
    return urlunsplit((scheme, f"{parts.hostname}:{admin_port}", "", "", ""))


def _sub_target(edge: dict) -> tuple[str, str] | None:
    """sub 간선의 source(토픽 노드 `topic:<토픽>/<메시지>`) → (메시지, 토픽)"""
    if edge.get("kind") != "sub":
        return None
    src = str(edge.get("source", ""))
    if not src.startswith("topic:") or "/" not in src:
        return None
    topic, name = src[len("topic:"):].rsplit("/", 1)
    return name, topic


class LateJoinReplayer:
    """CAL Server 그래프 이벤트를 보고, 새 외부 구독에 보관한 마지막 값을 다시 PUB한다 (DEC-089)

    - 접속 첫 스냅샷과 재접속 스냅샷에서도 모르던 구독을 새 구독으로 본다.
    - 다른 CAL Server의 구독(DDS 병합, `remote_updated`)은 `GET /graph`로 다시 읽어 비교한다.
    - 같은 (메시지, 토픽)에 구독이 몰리면 `debounce_s` 안의 요청을 한 번으로 합친다.
    - 다시 PUB한 값은 그 토픽의 기존 구독자에게도 간다. 변화 보고는 마지막 상태라 같은 값이 한 번 더 가도 뜻이 바뀌지 않는다.
    """

    def __init__(self, admin_url: str, retained: RetainedReports, emit: Callable[[str, dict], None], *,
                 debounce_s: float = 0.2, retry_s: float = 2.0):
        self.admin_url = admin_url.rstrip("/")
        self.retained = retained
        self.emit = emit
        self.debounce_s = debounce_s
        self.retry_s = retry_s
        self.known: dict[str, tuple[str, str]] = {}
        self.connected = asyncio.Event()
        self.replayed = 0
        self._pending: dict[tuple[str, str], asyncio.TimerHandle] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        for h in self._pending.values():
            h.cancel()
        self._pending.clear()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    # ------------------------------------------------------------------ 이벤트
    def on_snapshot(self, graph: dict) -> None:
        """스냅샷(병합 그래프)과 알던 구독을 비교한다"""
        seen: dict[str, tuple[str, str]] = {}
        for e in graph.get("edges", []):
            tgt = _sub_target(e)
            if tgt is not None:
                seen[e["id"]] = tgt
        for eid, tgt in seen.items():
            if eid not in self.known:
                self._new_sub(eid, tgt)
        for eid in [eid for eid in self.known if eid not in seen]:
            del self.known[eid]

    def on_event(self, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "snapshot":
            self.on_snapshot(ev.get("graph", {}))
        elif kind == "edge_added":
            tgt = _sub_target(ev.get("edge", {}))
            if tgt is not None and ev["edge"]["id"] not in self.known:
                self._new_sub(ev["edge"]["id"], tgt)
        elif kind == "edge_removed":
            self.known.pop(ev.get("id", ""), None)
        elif kind in ("remote_updated", "remote_removed"):
            asyncio.get_running_loop().create_task(self._resync())

    def _new_sub(self, eid: str, tgt: tuple[str, str]) -> None:
        self.known[eid] = tgt
        if tgt in self._pending or tgt not in self.retained.targets():
            return
        self._pending[tgt] = asyncio.get_running_loop().call_later(self.debounce_s, self._replay, tgt)

    def _replay(self, tgt: tuple[str, str]) -> None:
        self._pending.pop(tgt, None)
        name, topic = tgt
        objs = self.retained.latest(name, topic)
        for obj in objs:
            self.emit(topic, obj)
        self.replayed += len(objs)
        log.info("gateway: replayed %d retained %s@%s to a late subscriber (DEC-089)", len(objs), name, topic)

    # ------------------------------------------------------------------ 접속
    def _http_url(self, path: str) -> str:
        parts = urlsplit(self.admin_url)
        return urlunsplit(("https" if parts.scheme == "wss" else "http", parts.netloc, path, "", ""))

    async def _resync(self) -> None:
        def get() -> dict:
            with urllib.request.urlopen(self._http_url("/graph"), timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))
        try:
            self.on_snapshot(await asyncio.to_thread(get))
        except Exception as exc:
            log.warning("gateway: GET %s/graph failed: %s", self.admin_url, exc)

    async def _run(self) -> None:
        from websockets.asyncio.client import connect

        warned = False
        while True:
            try:
                async with connect(self.admin_url + "/graph/events") as ws:
                    log.info("gateway: watching LA-CAL subscriptions at %s/graph/events (DEC-089)", self.admin_url)
                    warned = False
                    self.connected.set()
                    async for raw in ws:
                        try:
                            self.on_event(json.loads(raw))
                        except Exception:
                            log.exception("gateway: bad graph event")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not warned:
                    log.warning("gateway: LA-CAL admin %s unavailable (%s); late subscribers get no retained "
                                "reports until it is reachable. retrying every %.0f s", self.admin_url, exc,
                                self.retry_s)
                    warned = True
            self.connected.clear()
            await asyncio.sleep(self.retry_s)
