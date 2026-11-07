"""agra_lacal(서브모듈) 연결부 (IMP-GW-001, DEC-069).

agra_lacal은 패키지로 설치되지 않는다(`package = false`). 서브모듈 루트를 sys.path에 넣고
`server.omsjson`(OMS JSON ⇄ XML, XSD 검증)과 `client.lacal_client`(OWP 1.0 CAL Client)를 읽기만 한다.
서브모듈 위치는 환경 변수 SWARM_AGRA_LACAL로 바꿀 수 있다.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from functools import lru_cache
from pathlib import Path

SCHEMA_VERSION = "006.0.ASK"


def lacal_root() -> Path:
    env = os.environ.get("SWARM_AGRA_LACAL")
    if env:
        root = Path(env)
    else:
        # gateway/src/swarm_gateway/lacal.py → 저장소 루트/third_party/agra_lacal
        root = Path(__file__).resolve().parents[3] / "third_party" / "agra_lacal"
    if not (root / "server" / "omsjson.py").is_file():
        raise RuntimeError(
            f"agra_lacal not found at {root}. Run: git submodule update --init third_party/agra_lacal")
    return root


def _ensure_path() -> Path:
    root = lacal_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


_ensure_path()

from client.lacal_client import CalError, LaCalClient  # noqa: E402
from server.omsjson import InvalidMessage, OmsJsonCodec  # noqa: E402

__all__ = ["CalError", "LaCalClient", "InvalidMessage", "OmsJsonCodec", "SCHEMA_VERSION",
           "lacal_root", "schema_path", "load_codec", "uci_timestamp"]


def schema_path() -> Path:
    """공개 XSD (A-GRA 6.0a, Distribution A)"""
    return lacal_root() / "schema" / "A-GRA_MessageDefinitions_v6_0_a.xsd"


@lru_cache(maxsize=1)
def load_codec() -> OmsJsonCodec:
    """XSD 적재는 수 초 걸리므로 프로세스당 한 번만 한다"""
    return OmsJsonCodec(schema_path())


def uci_timestamp(t: dt.datetime | None = None) -> str:
    t = t or dt.datetime.now(dt.timezone.utc)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
