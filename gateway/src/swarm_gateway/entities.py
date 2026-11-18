"""외부 명령·계획이 가리킬 수 있는 기체 (IMP-GW-029, QA D-35).

Gateway가 받을 수 있는 정보로만 정한다. truth는 읽지 않는다.
- 시나리오: Core가 `sim/ctrl/scenario`에 다시 발행하는 `Scenario`의 `ENTITY_KIND_UAV` 엔티티 (늦게 켠 참여자도 받는다)
- 수신 보고: GCS rx(`swarm/<gcs>/rx/**`)로 보고를 보낸 엔티티(`LinkEnvelope.header.source`)

시나리오가 바뀌면(엔티티 목록이 다르면) 두 목록을 모두 새로 시작한다.
"""
from __future__ import annotations

import logging
import threading

from google.protobuf.message import DecodeError
from swarm.v1 import entity_pb2, sim_pb2

log = logging.getLogger("swarm_gateway")

COMMANDABLE_KINDS = (entity_pb2.ENTITY_KIND_UAV,)


class KnownEntities:
    def __init__(self, gcs: str):
        self.gcs = gcs
        self._scenario: frozenset[str] = frozenset()
        self._reported: set[str] = set()
        self._lock = threading.Lock()

    def on_scenario(self, payload: bytes) -> bool:
        """sim/ctrl/scenario 표본. 해석하지 못하면 False"""
        sc = sim_pb2.Scenario()
        try:
            sc.ParseFromString(payload)
        except DecodeError:
            return False
        ids = frozenset(e.id for e in sc.entities if e.kind in COMMANDABLE_KINDS and e.id)
        with self._lock:
            if ids == self._scenario:
                return True
            self._scenario = ids
            self._reported.clear()
        log.info("gateway: scenario %r: %d commandable entities %s", sc.name, len(ids), sorted(ids))
        return True

    def on_report(self, source: str) -> None:
        if source and source != self.gcs:
            with self._lock:
                self._reported.add(source)

    def known(self, entity: str) -> bool:
        with self._lock:
            return entity in self._scenario or entity in self._reported

    def unknown(self, entities) -> list[str]:
        return [e for e in entities if not self.known(e)]

    def snapshot(self) -> dict[str, list[str]]:
        with self._lock:
            return {"scenario": sorted(self._scenario), "reported": sorted(self._reported)}
