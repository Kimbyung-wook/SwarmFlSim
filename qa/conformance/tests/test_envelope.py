"""39차 봉투(DEC-111) C2 판정의 도구 시험 (TC-QA-214).

uv run python -m pytest qa/conformance/tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import judges as J  # noqa: E402

TX = "MA_TxDataPayloadCommand"


def env(**kw) -> dict:  # noqa: ANN003
    return {"name": TX, "ok": True, "mt": "MA_TASK_STATUS", "mt_ok": True, "inner_ascii": True, "hdr_same": True, **kw}


def sent(tag: str, ok: bool = True, negative: bool = False) -> dict:
    return {"tag": tag, "name": "MA_TaskCommand", "xsd_ok": True, "pub": "+OK", "negative": negative,
            "env_xsd_ok": ok, "env": {"name": "MA_RxDataPayload"}}


def test_off_mode_not_judged() -> None:
    r = J.judge_envelope([{"name": "MA_TaskStatus", "ok": True, "env": None}],
                         [{"tag": "a", "name": "MA_TaskCommand", "env": None}])
    assert r == {"fail": [], "summary": {"mode": "off"}}


def test_on_mode_pass() -> None:
    r = J.judge_envelope([{"name": "MA_TaskStatus", "ok": True, "env": env()}], [sent("a")])
    assert r["fail"] == [] and r["summary"]["rx"] == 1 and r["summary"]["tx"] == 1


def test_on_mode_failures() -> None:
    rx = [{"name": "MA_TaskStatus", "ok": True, "env": env(ok=False)},
          {"name": "MA_TaskStatus", "ok": True, "env": env(mt_ok=False)},
          {"name": "MA_Entity", "ok": True, "env": env(inner_ascii=False)},
          {"name": "MA_Entity", "ok": True, "env": None}]
    r = J.judge_envelope(rx, [sent("a", ok=False), sent("neg-x", ok=False, negative=True)])
    f = " / ".join(r["fail"])
    assert "봉투 XSD 재검증 실패 1건" in f and "MessageType이 내부 메시지와 다름 1건" in f
    assert "ASCII가 아님 1건" in f and "봉투 없이 받은 메시지 1건" in f
    assert "송신 a" in f and "neg-x" not in f          # 부정 입력의 봉투는 판정하지 않는다
    assert len(r["fail"]) == 5


def test_hdr_diff_is_info_only() -> None:
    r = J.judge_envelope([{"name": "MA_TaskStatus", "ok": True, "env": env(hdr_same=False)}], [])
    assert r["fail"] == [] and r["summary"]["hdr_diff"] == 1


def test_c2_carries_envelope_summary() -> None:
    c2 = J.judge_c2([{"client": "ext", "name": "MA_TaskStatus", "ok": True, "env": env(ok=False)}], [], [])
    assert c2["envelope"]["mode"] == "on" and any("봉투 XSD" in t for t in c2["fail"])


def test_c6_negative_flow_not_failed() -> None:
    from collections import Counter
    decl = {"swarm_gateway": {"pub": set(), "sub": set()}, "external_c2": {"pub": set(), "sub": set()}}
    flows = {"swarm_gateway": {"pub": Counter(), "sub": Counter()},
             "external_c2": {"pub": Counter({"MA_TaskCommand@swarm.c2": 1}), "sub": Counter()}}
    tap = Counter({"x@y": 1})
    r = J.judge_c6(decl, flows, tap, Counter({"x@y": 1}), {}, negative_flows={"MA_TaskCommand@swarm.c2"})
    assert r["fail"] == [] and r["declared"][0]["state"] == "선언 밖(부정 입력)"
    r = J.judge_c6(decl, flows, tap, Counter({"x@y": 1}), {})
    assert any("선언 밖 교환" in t for t in r["fail"])
