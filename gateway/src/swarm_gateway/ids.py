"""내부 문자열 ID ⇄ UCI UUID (IMP-GW-003).

UCI ID 타입은 UUID와 선택 DescriptiveLabel로 이루어진다. 내부 ID(엔티티·작업·명령)는 고정 이름공간의
UUIDv5로 바꾸고 DescriptiveLabel에 원래 ID를 싣는다. 외부에서 받은 ID는 DescriptiveLabel을 먼저 보고,
없으면 이 Gateway가 만든 UUID의 역표를 본다.
"""
from __future__ import annotations

import uuid

# swarm_flight Gateway 고유 이름공간 (임의 고정값)
NAMESPACE = uuid.UUID("5d1c6b0e-8f8a-4d0b-9a7e-2f6d7c1e9a01")


class IdMap:
    def __init__(self, namespace: uuid.UUID = NAMESPACE):
        self.namespace = namespace
        self._reverse: dict[str, str] = {}

    def uuid(self, kind: str, internal_id: str) -> str:
        u = str(uuid.uuid5(self.namespace, f"{kind}:{internal_id}"))
        self._reverse[u] = internal_id
        return u

    def ref(self, kind: str, internal_id: str) -> dict:
        """UCI ID_Type 값 {UUID, DescriptiveLabel}"""
        out = {"UUID": self.uuid(kind, internal_id or "none")}
        if internal_id:
            out["DescriptiveLabel"] = internal_id[:256]
        return out

    def internal(self, ref: dict | None) -> str:
        """UCI ID_Type 값 → 내부 ID. 알 수 없으면 UUID 문자열"""
        if not ref:
            return ""
        label = ref.get("DescriptiveLabel")
        if label:
            return label
        u = ref.get("UUID", "")
        return self._reverse.get(u, u)
