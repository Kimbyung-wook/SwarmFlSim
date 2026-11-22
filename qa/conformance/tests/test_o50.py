"""34차 O-50: 계약 §3.2 구독자 칸의 구독 키로 Agent 허용 구독 키를 만든다 (TC-QA-187~188).

uv run python -m pytest qa/conformance/tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import confcommon  # noqa: E402
import judges as J  # noqa: E402

ROW = ("### 3.2 키 목록\n\n| 키 | 메시지 | 발행 | 구독 |\n|---|---|---|---|\n"
       "| `swarm/<dst>/rx/<iface>/<msg>` | `LinkEnvelope` | Datalink | 수신 엔티티의 Agent 런타임"
       "(자기 기체 `swarm/<dst>/rx/**`로 구독), UI |\n"
       "| `sim/ctrl/cmd` | `SimCommand` | UI | Core, Agent 런타임 (`set_params`, §3.3) |\n"
       "| `link/<a>/state` | `LinkState` | Datalink | UI (`swarm/<dst>/rx/**` 참고) |\n\n### 3.3 x\n")


def _allowed(md):  # noqa: ANN001, ANN202
    return [a["pattern"] for a in J.agent_allowed(J.parse_contract_keys(md))["sub"]]


def test_tc_qa_187_subscriber_cell_key_read():
    """구독자 칸의 `swarm/<dst>/rx/**`는 허용 구독 키가 되고, 첫 마디가 다른 키·키가 아닌 글(`set_params`)·
    Agent가 구독자가 아닌 행의 키는 읽지 않는다"""
    pats = _allowed(ROW)
    assert "swarm/*/rx/**" in pats and "swarm/*/rx/*/*" in pats
    assert "set_params" not in pats and not any(p.startswith("link/") for p in pats)
    assert sum(p == "swarm/*/rx/**" for p in pats) == 1
    without = ROW.replace("(자기 기체 `swarm/<dst>/rx/**`로 구독)", "")
    assert not any(J.keyexpr_includes(p, "swarm/*/rx/**") for p in _allowed(without))


def test_tc_qa_188_real_contract_covers_agent_subs_without_supplement():
    """실제 계약 §3.2만으로 Agent 런타임의 구독 키 표현식이 모두 허용되고 보충 키는 없다"""
    pats = _allowed((confcommon.ROOT / "docs" / "10_contracts.md").read_text(encoding="utf-8"))
    assert J.SUPPLEMENT_SUB == []
    for k in ("swarm/*/rx/**", "sim/ctrl/cmd", "sim/clock/done/*", "sim/clock/tick", "sim/ctrl/scenario"):
        assert any(J.keyexpr_includes(p, k) for p in pats), k
